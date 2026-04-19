# backend/app/services/baseline_service.py
import uuid
import math
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.schema import DailyMetric, MetricBaseline

def compute_ema(values: list, window: int) -> float:
    """Exponential Moving Average — recent days count more than old days"""
    if not values:
        return 0.0
    k = 2 / (window + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return round(ema, 4)

def compute_stddev(values: list) -> float:
    """Standard Deviation — measures how much values vary day to day"""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return round(math.sqrt(variance), 4)

def winsorize_outliers(values: list, cap_multiplier: float = 2.0) -> list:
    """
    Viral Trap Fix: Cap extreme outliers before computing StdDev.
    Any day with views > (cap_multiplier × median) is trimmed DOWN to
    the median level. This stops a single viral spike from inflating
    the 'normal bounce' and blinding the Z-score detector.
    """
    if not values:
        return values
    sorted_vals = sorted(values)
    mid = len(sorted_vals) // 2
    # Median: middle value (resistant to outliers unlike mean)
    median = sorted_vals[mid] if len(sorted_vals) % 2 != 0 else (
        (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    )
    cap = median * cap_multiplier
    return [min(v, cap) for v in values]

async def compute_baselines_for_creator(creator_id: uuid.UUID, db: AsyncSession):
    """Calculate and save EMA + StdDev baselines for a creator"""

    ninety_days_ago = datetime.now() - timedelta(days=90)
    stmt = (
        select(DailyMetric)
        .where(DailyMetric.creator_id == creator_id)
        .where(DailyMetric.date >= ninety_days_ago)
        .order_by(DailyMetric.date.asc())
    )
    result = await db.execute(stmt)
    metrics = result.scalars().all()

    if not metrics:
        print(f"No metrics found for creator {creator_id}")
        return

    views = [float(m.views) for m in metrics]
    last_30_views = views[-30:] if len(views) >= 30 else views

    ema_30 = compute_ema(last_30_views, 30)
    ema_90 = compute_ema(views, 90)

    # Fix the "Viral Trap": cap outliers before measuring stability
    # EMA still uses raw views (so trends are tracked accurately)
    # StdDev uses winsorized views (so viral days don't poison the alarm)
    winsorized_30 = winsorize_outliers(last_30_views)
    stddev_30 = compute_stddev(winsorized_30)

    stmt = select(MetricBaseline).where(
        MetricBaseline.creator_id == creator_id,
        MetricBaseline.platform == "youtube",
        MetricBaseline.metric_name == "views"
    )
    res = await db.execute(stmt)
    baseline = res.scalar_one_or_none()

    if not baseline:
        baseline = MetricBaseline(
            creator_id=creator_id,
            platform="youtube",
            metric_name="views"
        )
        db.add(baseline)

    baseline.ema_30 = ema_30
    baseline.ema_90 = ema_90
    baseline.stddev_30 = stddev_30

    await db.commit()
    print(f"Baselines saved → EMA30: {ema_30}, EMA90: {ema_90}, StdDev: {stddev_30}")
