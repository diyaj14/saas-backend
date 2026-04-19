# backend/app/routers/alerts.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from ..database import get_db
from ..models.schema import Alert

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

@router.get("")
async def list_alerts(creator_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """List all alerts for a creator"""
    stmt = (
        select(Alert)
        .where(Alert.creator_id == creator_id)
        .order_by(Alert.detected_at.desc())
    )
    result = await db.execute(stmt)
    alerts = result.scalars().all()

    return [
        {
            "id": a.id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "status": a.status,
            "detected_at": a.detected_at,
        }
        for a in alerts
    ]

@router.get("/{alert_id}")
async def get_alert_detail(alert_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Full detail for a single alert, including raw numbers"""
    stmt = select(Alert).where(Alert.id == alert_id)
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "status": alert.status,
        "detected_at": alert.detected_at,
        "payload": alert.payload,  # Full numbers: z-scores, drop %, etc.
    }
