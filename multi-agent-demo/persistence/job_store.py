"""PostgreSQL/SQLite job history CRUD operations."""

import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker

from persistence.models import Base, Job

_engine = None
_Session = None


def _get_database_url() -> str:
    """Return DATABASE_URL or fall back to local SQLite."""
    return os.getenv("DATABASE_URL", "sqlite:///jobs.db")


def init_db() -> None:
    """Create tables if they don't exist and initialize the session factory."""
    global _engine, _Session
    url = _get_database_url()
    _engine = create_engine(url, echo=False)
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(bind=_engine)
    print(f"[job_store] Database initialized ({url.split('@')[-1] if '@' in url else url})")


def _session():
    """Return a new database session, initializing if needed."""
    if _Session is None:
        init_db()
    return _Session()


def create_job(state: dict) -> Job:
    """Insert a new job record from initial state. Returns the Job."""
    job = Job(
        id=state.get("job_id", ""),
        user_id=state.get("user_id", "anonymous"),
        user_request=state.get("user_request", ""),
        status="running",
        total_tokens=0,
        cost_usd=0.0,
    )
    session = _session()
    try:
        session.add(job)
        session.commit()
        session.refresh(job)
        return job
    finally:
        session.close()


def update_job(job_id: str, state: dict) -> None:
    """Update a job record with final results."""
    session = _session()
    try:
        job = session.query(Job).filter_by(id=job_id).first()
        if not job:
            return

        has_error = bool(state.get("error"))
        job.status = "failed" if has_error else "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.total_tokens = state.get("total_tokens", 0)
        job.cost_usd = state.get("cost_usd", 0.0)
        job.cost_breakdown = state.get("cost_breakdown", {})
        job.agent_tokens = state.get("agent_tokens", {})
        job.retry_count = state.get("retry_count", 0)
        job.validation_passed = state.get("validation_passed", False)
        job.model_used = state.get("model_used", "")
        job.error = state.get("error", "") or None

        session.commit()
    finally:
        session.close()


def get_job(job_id: str) -> Job | None:
    """Fetch a single job by ID."""
    session = _session()
    try:
        return session.query(Job).filter_by(id=job_id).first()
    finally:
        session.close()


def list_jobs(user_id: str | None = None, limit: int = 20) -> list[Job]:
    """List recent jobs, optionally filtered by user_id."""
    session = _session()
    try:
        query = session.query(Job)
        if user_id:
            query = query.filter_by(user_id=user_id)
        return query.order_by(desc(Job.created_at)).limit(limit).all()
    finally:
        session.close()
