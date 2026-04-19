# backend/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import get_db, SessionLocal
from .routers import youtube, metrics, alerts
from .models.schema import Creator
from .services.baseline_service import compute_baselines_for_creator
from .services.anomaly_service import detect_anomalies_for_creator, detect_changepoint

scheduler = AsyncIOScheduler()

async def run_daily_jobs():
    """Runs every night: recompute baselines and detect crashes for all creators"""
    print("Running daily baseline + anomaly detection jobs...")
    async with SessionLocal() as db:
        result = await db.execute(select(Creator.id))
        creator_ids = result.scalars().all()

        for creator_id in creator_ids:
            await compute_baselines_for_creator(creator_id, db)
            await detect_anomalies_for_creator(creator_id, db)
            await detect_changepoint(creator_id, db)

    print("Daily jobs complete.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schedule daily job at midnight
    scheduler.add_job(run_daily_jobs, "cron", hour=0, minute=0)
    scheduler.start()
    print("Scheduler started.")
    yield
    scheduler.shutdown()
    print("Scheduler stopped.")

app = FastAPI(title="CrashGuard API", lifespan=lifespan)

# Register Routers
app.include_router(youtube.router)
app.include_router(metrics.router)
app.include_router(alerts.router)

@app.get("/")
async def root():
    return {"message": "CrashGuard Backend is Live"}

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
