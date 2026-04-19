import os
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv

from ..database import get_db
from ..models.schema import PlatformConnection, Creator, User
from ..security import encrypt_token, decrypt_token
from ..services.youtube_service import sync_youtube_data

# Tell oauthlib to not crash if Google changes our requested scopes
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

router = APIRouter(prefix="/auth/youtube", tags=["youtube"])


# This tells Google what we want to do
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid"
]

def get_google_flow():
    # Force reload of .env using an absolute path to be 100% sure
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(base_dir, ".env")
    load_dotenv(env_path, override=True)
    
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    print("redirect uri is",redirect_uri)

    if not all([client_id, client_secret, redirect_uri]):
        missing = [k for k, v in {"GOOGLE_CLIENT_ID": client_id, "GOOGLE_CLIENT_SECRET": client_secret, "GOOGLE_REDIRECT_URI": redirect_uri}.items() if not v]
        raise HTTPException(status_code=500, detail=f"Missing Environment Variables in {env_path}: {', '.join(missing)}")

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }
        },
        scopes=SCOPES
    )
    
    # CRITICAL FIX: The Google library requires us to explicitly set this property 
    # even if it's inside the config dictionary!
    flow.redirect_uri = redirect_uri
    
    return flow

# Global dictionary to temporarily store the PKCE code_verifier.
# (In production, you'd store this in a Redis session or encrypted cookie)
auth_state = {}

@router.get("/connect")
async def youtube_connect():
    """Step 1: Send the user to Google Login"""
    flow = get_google_flow()
    
    # Now that .env is working, we don't need to pass redirect_uri twice
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent' 
    )
    
    # Save the PKCE verifier using the state string as the key
    auth_state[state] = getattr(flow, 'code_verifier', None)
    
    return RedirectResponse(authorization_url)

@router.get("/callback")
async def youtube_callback(request: Request, code: str, state: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Step 2: Catch the user, fetch their Channel ID, and save everything to the DB"""
    from sqlalchemy import select
    from googleapiclient.discovery import build
    
    flow = get_google_flow()
    
    # Restore the PKCE verifier for this specific login attempt
    if state in auth_state:
        flow.code_verifier = auth_state.pop(state)
        
    flow.fetch_token(code=code)
    credentials = flow.credentials

    # 1. Fetch the YouTube Channel ID (This is our "Platform User ID")
    youtube = build('youtube', 'v3', credentials=credentials)
    channels_response = youtube.channels().list(mine=True, part='id,snippet').execute()
    
    if not channels_response['items']:
        raise HTTPException(status_code=400, detail="No YouTube channel found for this account.")
    
    channel_id = channels_response['items'][0]['id']
    channel_title = channels_response['items'][0]['snippet']['title']

    # 2. Check if we have a "Default User" to attach this to
    # (In a real app, this would be the logged-in user's ID)
    user_result = await db.execute(select(User).limit(1))
    user = user_result.scalar_one_or_none()
    
    if not user:
        # Create a placeholder user for testing if database is empty
        user = User(email="test@crashguard.ai")
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # 3. Ensure a Creator profile exists
    creator_result = await db.execute(select(Creator).where(Creator.user_id == user.id))
    creator = creator_result.scalar_one_or_none()
    
    if not creator:
        creator = Creator(user_id=user.id, niche="General")
        db.add(creator)
        await db.commit()
        await db.refresh(creator)

    # 4. Save/Update the Connection (Encrypted)
    connection_result = await db.execute(
        select(PlatformConnection).where(
            PlatformConnection.creator_id == creator.id,
            PlatformConnection.platform == "youtube"
        )
    )
    connection = connection_result.scalar_one_or_none()

    if not connection:
        connection = PlatformConnection(
            creator_id=creator.id,
            platform="youtube"
        )
        db.add(connection)

    connection.platform_user_id = channel_id
    connection.access_token = encrypt_token(credentials.token)
    if credentials.refresh_token:
        connection.refresh_token = encrypt_token(credentials.refresh_token)
    
    await db.commit()

    # 5. Trigger the Background Sync for 90 days of history
    background_tasks.add_task(sync_youtube_data, creator.id, db)

    # Success Response
    return {
        "status": "Success",
        "message": f"Connected to YouTube Channel: {channel_title}. Initial 90-day sync started!",
        "channel_id": channel_id,
        "database_updated": True
    }
