"""Job queue operations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Job, User

JOB_TYPES = ("relax", "generate_batch", "analyze")


def enqueue(db: Session, user: User, job_type: str, params: dict) -> Job:
    if job_type not in JOB_TYPES:
        raise ValueError(f"unknown job type {job_type}")
    job = Job(org_id=user.org_id, owner_id=user.id, type=job_type, params=params,
              executor=get_settings().executor)
    db.add(job)
    db.flush()
    return job


def claim_next(db: Session) -> Job | None:
    """Atomically move the oldest queued job to running."""
    job = db.execute(select(Job).where(Job.status == "queued").order_by(Job.id).limit(1)).scalar_one_or_none()
    if job is None:
        return None
    res = db.execute(update(Job).where(Job.id == job.id, Job.status == "queued")
                     .values(status="running", started_at=datetime.now(UTC), heartbeat_at=datetime.now(UTC)))
    db.commit()
    if res.rowcount != 1:
        return None
    db.refresh(job)
    return job


def job_dict(j: Job) -> dict:
    return {
        "id": j.id, "type": j.type, "status": j.status, "params": j.params, "result": j.result,
        "error": j.error, "progress": j.progress, "message": j.message, "executor": j.executor,
        "external_id": j.external_id, "created_at": j.created_at, "started_at": j.started_at,
        "finished_at": j.finished_at, "owner_id": j.owner_id, "cancel_requested": j.cancel_requested,
    }
