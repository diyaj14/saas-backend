# backend/app/services/youtube_service.py
import os
import uuid
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from ..models.schema import PlatformConnection, DailyMetric, Post
from ..security import decrypt_token

async def sync_youtube_videos(creator_id: uuid.UUID, conn: PlatformConnection, credentials, db: AsyncSession):
    """Fetch all videos from the channel and save to 'posts' table"""
    youtube = build('youtube', 'v3', credentials=credentials)
    
    # 1. Get the 'Uploads' playlist ID for the channel
    ch_res = youtube.channels().list(id=conn.platform_user_id, part='contentDetails').execute()
    uploads_playlist_id = ch_res['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    
    # 2. Fetch videos from that playlist
    next_page_token = None
    while True:
        playlist_res = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part='snippet,contentDetails',
            maxResults=50,
            pageToken=next_page_token
        ).execute()

        for item in playlist_res['items']:
            video_id = item['contentDetails']['videoId']
            title = item['snippet']['title']
            published_at = datetime.fromisoformat(item['snippet']['publishedAt'].replace('Z', '+00:00'))
            thumbnail = item['snippet']['thumbnails'].get('high', {}).get('url')

            # Upsert into Posts table
            stmt = select(Post).where(Post.external_id == video_id)
            res = await db.execute(stmt)
            post = res.scalar_one_or_none()

            if not post:
                post = Post(
                    creator_id=creator_id,
                    platform="youtube",
                    external_id=video_id
                )
                db.add(post)
            
            post.title = title
            post.published_at = published_at
            post.thumbnail_url = thumbnail
            post.url = f"https://www.youtube.com/watch?v={video_id}"

        next_page_token = playlist_res.get('nextPageToken')
        if not next_page_token:
            break
    
    await db.commit()

async def sync_youtube_data(creator_id: uuid.UUID, db: AsyncSession):
    """Fetch last 90 days of metrics and save to DB"""
    
    # 1. Get Connection Details from DB
    stmt = select(PlatformConnection).where(
        PlatformConnection.creator_id == creator_id,
        PlatformConnection.platform == "youtube"
    )
    result = await db.execute(stmt)
    conn = result.scalar_one_or_none()
    
    if not conn:
        print(f"No YouTube connection found for creator {creator_id}")
        return

    # 2. Rebuild Credentials
    creds = Credentials(
        token=decrypt_token(conn.access_token),
        refresh_token=decrypt_token(conn.refresh_token) if conn.refresh_token else None,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET")
    )

    # 3. First, sync all videos (Posts)
    try:
        await sync_youtube_videos(creator_id, conn, creds, db)
    except Exception as e:
        print(f"Error syncing videos: {e}")

    # 4. Build Analytics Client
    # Note: Requires "YouTube Analytics API" enabled in Google Cloud Console
    analytics = build('youtubeAnalytics', 'v2', credentials=creds)

    # 5. Define Time Range (Last 90 days)
    end_date = datetime.now().date() - timedelta(days=1)
    start_date = end_date - timedelta(days=90)

    # 6. Query Analytics (Channel Level)
    # Metrics: views, estimatedMinutesWatched, averageViewDuration, impressions, clickThroughRate
    report = analytics.reports().query(
        ids=f"channel=={conn.platform_user_id}",
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
        metrics="views,estimatedMinutesWatched,averageViewDuration",
        dimensions="day"
    ).execute()

    # 7. Parse and Save Metrics
    if "rows" in report:
        for row in report["rows"]:
            date_str, views, watch_time, avg_duration = row
            metric_date = datetime.strptime(date_str, "%Y-%m-%d")

            # Check if metric already exists for this date
            metric_stmt = select(DailyMetric).where(
                DailyMetric.creator_id == creator_id,
                DailyMetric.date == metric_date
            )
            metric_res = await db.execute(metric_stmt)
            metric = metric_res.scalar_one_or_none()

            if not metric:
                metric = DailyMetric(
                    creator_id=creator_id,
                    date=metric_date
                )
                db.add(metric)

            metric.views = int(views)
            metric.watch_time = int(watch_time * 60) # Convert minutes to seconds

        await db.commit()
        print(f"Successfully synced 90 days of data and videos for {conn.platform_user_id}")
