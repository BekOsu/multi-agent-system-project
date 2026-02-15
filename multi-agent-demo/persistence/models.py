"""SQLAlchemy models for persistent job history."""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Boolean,
    Text,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(128), nullable=False, index=True)
    user_request = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending | running | completed | failed
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    cost_breakdown = Column(JSON, nullable=True)
    agent_tokens = Column(JSON, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    validation_passed = Column(Boolean, nullable=False, default=False)
    model_used = Column(String(64), nullable=True)
    error = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Job {self.id} status={self.status} cost=${self.cost_usd:.6f}>"
