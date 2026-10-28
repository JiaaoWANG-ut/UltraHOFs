"""Executors: run a job locally (child process, timeout, cancel) or submit it to Slurm."""

from __future__ import annotations

import multiprocessing as mp
import os
import subprocess
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ..config import REPO_ROOT, get_settings
from .tasks import TASKS, TaskContext, job_dir


def _child(job_id: int, jtype: str, params: dict, q: mp.Queue, log_path: str) -> None:
    os.environ.setdefault("OMP_NUM_THREADS", str(get_settings().torch_threads))
    from ..db import configure_engine

    configure_engine(get_settings().resolved_database_url())  # fresh connections after fork

    def progress(frac: float, msg: str) -> None:
        q.put(("progress", frac, msg))

    def should_stop() -> bool:
        from ..db import SessionLocal
        from ..models import Job

        with SessionLocal() as db:
            j = db.get(Job, job_id)
            return bool(j and j.cancel_requested)

    ctx = TaskContext(progress, should_stop, Path(log_path))
    try:
        result = TASKS[jtype](job_id, params, ctx)
        q.put(("done", result, None))
    except Exception as e:  # noqa: BLE001
        q.put(("error", f"{e}", traceback.format_exc()[-2000:]))


class LocalExecutor:
    name = "local"

    def __init__(self, inline: bool = False):
        self.inline = inline

    def run(self, job_id: int, jtype: str, params: dict, *, set_state: Callable[..., None],
            cancel_requested: Callable[[int], bool]) -> None:
        s = get_settings()
        log_path = job_dir(job_id) / "job.log"
        set_state(job_id, log_path=str(log_path), message="starting")
        if self.inline:
            ctx = TaskContext(lambda f, m: set_state(job_id, progress=f, message=m,
                                                     heartbeat_at=datetime.now(UTC)),
                              lambda: cancel_requested(job_id), log_path)
            try:
                result = TASKS[jtype](job_id, params, ctx)
                set_state(job_id, status="succeeded", result=result, progress=1.0, message="done",
                          finished_at=datetime.now(UTC))
            except Exception as e:  # noqa: BLE001
                set_state(job_id, status="failed", error=f"{e}\n{traceback.format_exc()[-1500:]}",
                          finished_at=datetime.now(UTC))
            return
        ctx_mp = mp.get_context("fork")
        q = ctx_mp.Queue()
        p = ctx_mp.Process(target=_child, args=(job_id, jtype, params, q, str(log_path)), daemon=True)
        p.start()
        t0 = time.time()
        timeout = s.relax_timeout_s if jtype == "relax" else 3 * s.relax_timeout_s
        final = None
        last_hb = 0.0
        while True:
            try:
                while not q.empty():
                    msg = q.get_nowait()
                    if msg[0] == "progress":
                        if time.time() - last_hb > 1.0:
                            set_state(job_id, progress=float(msg[1]), message=str(msg[2])[:300],
                                      heartbeat_at=datetime.now(UTC))
                            last_hb = time.time()
                    else:
                        final = msg
            except Exception:  # noqa: BLE001
                pass
            if final is not None:
                break
            if not p.is_alive():
                time.sleep(0.5)
                if q.empty():
                    final = ("error", f"worker process exited with code {p.exitcode}", "")
                    break
                continue
            if time.time() - t0 > timeout:
                p.kill()
                final = ("error", f"timeout after {timeout}s", "")
                break
            if cancel_requested(job_id) and time.time() - t0 > 2:
                time.sleep(3)
                if p.is_alive():
                    p.kill()
                    final = ("cancelled", None, None)
                    break
            time.sleep(0.5)
        p.join(timeout=5)
        kind = final[0]
        if kind == "done":
            set_state(job_id, status="succeeded", result=final[1], progress=1.0, message="done",
                      finished_at=datetime.now(UTC))
        elif kind == "cancelled" or (kind == "error" and "cancelled" in str(final[1])):
            set_state(job_id, status="cancelled", message="cancelled", finished_at=datetime.now(UTC))
        else:
            set_state(job_id, status="failed", error=f"{final[1]}\n{final[2] or ''}"[-3000:],
                      finished_at=datetime.now(UTC))


SBATCH_TEMPLATE = """#!/bin/bash
#SBATCH -A {account}
#SBATCH -C {constraint}
#SBATCH -q {qos}
#SBATCH -N 1
#SBATCH -t {walltime}
#SBATCH --gpus-per-node={gpus}
#SBATCH -J ultrahofs-{job_id}
#SBATCH -o {logdir}/slurm-%j.out
module load conda
conda activate {env}
export ULTRAHOFS_RELAX_DEVICE=cuda
cd {repo}
ultrahofs run-job {job_id}
"""


class SlurmExecutor:
    """Submits jobs to Perlmutter via sbatch; the batch job runs ``ultrahofs run-job <id>``.

    Status is written to the shared database by the batch job itself. Prepared for production use;
    the local executor is the default for login-node testing.
    """

    name = "slurm"

    def run(self, job_id: int, jtype: str, params: dict, *, set_state: Callable[..., None],
            cancel_requested: Callable[[int], bool]) -> None:
        s = get_settings()
        d = job_dir(job_id)
        script = d / "job.sbatch"
        script.write_text(SBATCH_TEMPLATE.format(
            account=s.slurm_account, constraint=s.slurm_constraint, qos=s.slurm_qos, walltime="01:00:00",
            gpus=1 if s.slurm_constraint == "gpu" else 0, job_id=job_id, logdir=d,
            env=os.environ.get("CONDA_PREFIX", ""), repo=REPO_ROOT))
        proc = subprocess.run(["sbatch", "--parsable", str(script)], capture_output=True, text=True)
        if proc.returncode != 0:
            set_state(job_id, status="failed", error=f"sbatch failed: {proc.stderr[-800:]}",
                      finished_at=datetime.now(UTC))
            return
        set_state(job_id, status="queued_slurm", external_id=proc.stdout.strip(), message="submitted to Slurm")


def get_executor():  # noqa: ANN201
    return SlurmExecutor() if get_settings().executor == "slurm" else LocalExecutor()
