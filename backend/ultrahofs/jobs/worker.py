"""Job worker: claims queued jobs and executes them with the configured executor."""

from __future__ import annotations

import multiprocessing as mp
import signal
import time
import traceback
from datetime import UTC, datetime

from sqlalchemy import update

from ..config import get_settings
from ..db import SessionLocal, init_db
from ..models import Job
from .executors import get_executor
from .queue import claim_next


def _set(job_id: int, **values) -> None:  # noqa: ANN003
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.id == job_id).values(**values))
        db.commit()


def _cancel_requested(job_id: int) -> bool:
    with SessionLocal() as db:
        j = db.get(Job, job_id)
        return bool(j and j.cancel_requested)


def run_worker(once: bool = False) -> None:
    init_db()
    s = get_settings()
    stop = {"flag": False}

    def _handler(_sig, _frm):  # noqa: ANN001, ANN202
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
    executor = get_executor()
    print(f"[worker] started (executor={executor.name}, poll={s.worker_poll_s}s)", flush=True)
    while not stop["flag"]:
        with SessionLocal() as db:
            job = claim_next(db)
        if job is None:
            if once:
                return
            time.sleep(s.worker_poll_s)
            continue
        print(f"[worker] job {job.id} ({job.type}) started", flush=True)
        try:
            executor.run(job.id, job.type, job.params or {}, set_state=_set, cancel_requested=_cancel_requested)
        except Exception as e:  # noqa: BLE001
            _set(job.id, status="failed", error=f"{e}\n{traceback.format_exc()[-1500:]}",
                 finished_at=datetime.now(UTC))
        print(f"[worker] job {job.id} finished", flush=True)
        if once:
            return


def run_job_inline(job_id: int) -> None:
    """Execute one job in this process (used by Slurm batch scripts: ``ultrahofs run-job``)."""
    from .executors import LocalExecutor

    init_db()
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise SystemExit(f"job {job_id} not found")
        jtype, params = job.type, job.params or {}
    _set(job_id, status="running", started_at=datetime.now(UTC))
    LocalExecutor(inline=True).run(job_id, jtype, params, set_state=_set, cancel_requested=_cancel_requested)


__all__ = ["mp", "run_job_inline", "run_worker"]
