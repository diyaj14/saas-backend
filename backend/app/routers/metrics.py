# backend/app/routers/metrics.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
import uuid

from ..database import get_db
from ..models.schema import DailyMetric, Post

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

@router.get("/youtube/daily/{creator_id}")
async def get_daily_metrics(creator_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Fetch and compute normalized metrics for the dashboard"""
    
    # 1. Fetch the last 30 days of data
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    stmt = (
        select(DailyMetric)
        .where(DailyMetric.creator_id == creator_id)
        .where(DailyMetric.date >= thirty_days_ago)
        .order_by(DailyMetric.date.asc())
    )
    result = await db.execute(stmt)
    metrics = result.scalars().all()

    # 2. Fetch total video count to "Normalize" the data
    post_count_stmt = select(func.count(Post.id)).where(Post.creator_id == creator_id)
    post_count_res = await db.execute(post_count_stmt)
    total_videos = post_count_res.scalar() or 1 # Avoid division by zero

    # 3. Format & Compute the response
    report = []
    for m in metrics:
        report.append({
            "date": m.date.strftime("%Y-%m-%d"),
            "raw_views": m.views,
            "views_per_video": round(m.views / total_videos, 2),
            "watch_time_avg_minutes": round((m.watch_time / m.views / 60), 2) if m.views > 0 else 0,
        })

    return {
        "creator_id": creator_id,
        "total_videos_tracked": total_videos,
        "history": report
    }
