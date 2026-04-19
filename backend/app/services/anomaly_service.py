# backend/app/services/anomaly_service.py
import uuid
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.schema import DailyMetric, MetricBaseline, Alert

CRASH_THRESHOLD = -2.0
MIN_CRASH_DAYS = 2

def compute_zscore(today_value: float, ema: float, stddev: float) -> float:
    """How many standard deviations away from 'normal' is today's value?"""
    if stddev == 0:
        return 0.0
    return round((today_value - ema) / stddev, 4)

async def detect_anomalies_for_creator(creator_id: uuid.UUID, db: AsyncSession):
    """Run anomaly detection and create Alerts if a crash is found"""

    baseline_stmt = select(MetricBaseline).where(
        MetricBaseline.creator_id == creator_id,
        MetricBaseline.platform == "youtube",
        MetricBaseline.metric_name == "views"
    )
    baseline_res = await db.execute(baseline_stmt)
    baseline = baseline_res.scalar_one_or_none()

    if not baseline or not baseline.stddev_30:
        print("No baseline found, skipping anomaly detection")
        return

    three_days_ago = datetime.now() - timedelta(days=3)
    metrics_stmt = (
        select(DailyMetric)
        .where(DailyMetric.creator_id == creator_id)
        .where(DailyMetric.date >= three_days_ago)
        .order_by(DailyMetric.date.asc())
    )
    metrics_res = await db.execute(metrics_stmt)
    recent_metrics = metrics_res.scalars().all()

    if not recent_metrics:
        return

    crash_days = []
    for m in recent_metrics:
        z = compute_zscore(float(m.views), baseline.ema_30, baseline.stddev_30)
        if z < CRASH_THRESHOLD:
            crash_days.append({"date": m.date, "views": m.views, "z_score": z})

    if len(crash_days) >= MIN_CRASH_DAYS:
        existing_stmt = select(Alert).where(
            Alert.creator_id == creator_id,
            Alert.alert_type == "YOUTUBE_VIEW_CRASH",
            Alert.status == "ACTIVE"
        )
        existing_res = await db.execute(existing_stmt)
        existing_alert = existing_res.scalar_one_or_none()

        if not existing_alert:
            alert = Alert(
                creator_id=creator_id,
                platform="youtube",
                alert_type="YOUTUBE_VIEW_CRASH",
                severity="HIGH",
                payload={
                    "crash_days": [
                        {"date": str(d["date"]), "views": d["views"], "z_score": d["z_score"]}
                        for d in crash_days
                    ],
                    "baseline_ema_30": baseline.ema_30,
                    "baseline_stddev_30": baseline.stddev_30,
                }
            )
            db.add(alert)
            await db.commit()
            print(f"ALERT CREATED: View crash detected for {creator_id}")
        else:
            print(f"Alert already active for {creator_id}, skipping.")
    else:
        print(f"No crash detected. Z-Scores: {[d['z_score'] for d in crash_days]}")

async def detect_changepoint(creator_id: uuid.UUID, db: AsyncSession):
    """Slow-bleed detector: Is the last 14 days worse than the 30 days before?"""

    forty_four_days_ago = datetime.now() - timedelta(days=44)
    stmt = (
        select(DailyMetric)
        .where(DailyMetric.creator_id == creator_id)
        .where(DailyMetric.date >= forty_four_days_ago)
        .order_by(DailyMetric.date.asc())
    )
    res = await db.execute(stmt)
    all_metrics = res.scalars().all()

    if len(all_metrics) < 30:
        return  # Not enough data yet

    views = [float(m.views) for m in all_metrics]
    previous_30 = views[:30]
    last_14 = views[-14:]

    mean_previous = sum(previous_30) / len(previous_30)
    mean_recent = sum(last_14) / len(last_14)

    if mean_previous > 0 and (mean_recent / mean_previous) < 0.70:
        existing_stmt = select(Alert).where(
            Alert.creator_id == creator_id,
            Alert.alert_type == "YOUTUBE_SLOW_DECLINE",
            Alert.status == "ACTIVE"
        )
        existing_res = await db.execute(existing_stmt)
        if not existing_res.scalar_one_or_none():
            alert = Alert(
                creator_id=creator_id,
                platform="youtube",
                alert_type="YOUTUBE_SLOW_DECLINE",
                severity="MEDIUM",
                payload={
                    "mean_previous_30_days": round(mean_previous, 2),
                    "mean_last_14_days": round(mean_recent, 2),
                    "drop_percent": round((1 - mean_recent / mean_previous) * 100, 1)
                }
            )
            db.add(alert)
            await db.commit()
            print(f"SLOW DECLINE ALERT: {round((1 - mean_recent/mean_previous)*100, 1)}% drop detected")
