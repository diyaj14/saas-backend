import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# The engine is the central connection to Supabase
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
)

# This creates a session factory
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Dependency to use in FastAPI routes
async def get_db():
    async with SessionLocal() as session:
        yield session
