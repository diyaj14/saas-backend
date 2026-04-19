# backend/app/models/schema.py
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    creator = relationship("Creator", back_populates="user", cascade="all, delete-orphan", uselist=False)

class Creator(Base):
    __tablename__ = "creators"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    niche: Mapped[str] = mapped_column(String(100), nullable=True)
    time_budget_hours_per_week: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="creator")
    platform_connections = relationship("PlatformConnection", back_populates="creator", cascade="all, delete-orphan")
    daily_metrics = relationship("DailyMetric", back_populates="creator", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="creator", cascade="all, delete-orphan")
    baselines = relationship("MetricBaseline", back_populates="creator", cascade="all, delete-orphan")

class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("creators.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(50), nullable=False) # e.g. 'youtube', 'instagram'
    alert_type: Mapped[str] = mapped_column(String(100), nullable=False) # e.g. 'YOUTUBE_DISTRIBUTION_DROP'
    severity: Mapped[str] = mapped_column(String(20), nullable=False) 
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict] = mapped_column(JSONB, nullable=True) # Stores Z-Scores, anomaly metrics
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    
    # Relationships
    creator = relationship("Creator", back_populates="alerts")

class PlatformConnection(Base):
    __tablename__ = "platform_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("creators.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(50)) # 'youtube', 'instagram', 'linkedin'
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=True)
    
    # Encrypted tokens
    access_token: Mapped[str] = mapped_column(String)
    refresh_token: Mapped[str] = mapped_column(String, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("Creator", back_populates="platform_connections")

class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("creators.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(255), unique=True) # YouTube Video ID
    title: Mapped[str] = mapped_column(String(500), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    thumbnail_url: Mapped[str] = mapped_column(String, nullable=True)
    url: Mapped[str] = mapped_column(String, nullable=True)
    
    creator = relationship("Creator")

class DailyMetric(Base):
    __tablename__ = "daily_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("creators.id", ondelete="CASCADE"))
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    
    # Generic buckets for any platform
    views: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    engagement: Mapped[int] = mapped_column(Integer, default=0)
    watch_time: Mapped[int] = mapped_column(Integer, default=0) # in seconds
    
    creator = relationship("Creator", back_populates="daily_metrics")

class MetricBaseline(Base):
    __tablename__ = "metric_baselines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("creators.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(50))        # e.g. 'youtube'
    metric_name: Mapped[str] = mapped_column(String(100))    # e.g. 'views'

    ema_30: Mapped[float] = mapped_column(nullable=True)     # 30-day Exponential Moving Average
    ema_90: Mapped[float] = mapped_column(nullable=True)     # 90-day EMA
    stddev_30: Mapped[float] = mapped_column(nullable=True)  # Rolling Standard Deviation

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    creator = relationship("Creator", back_populates="baselines")
