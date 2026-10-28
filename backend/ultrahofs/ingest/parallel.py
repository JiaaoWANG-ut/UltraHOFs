"""Run CPU-heavy functions in parallel worker processes with hard per-item timeouts."""

from __future__ import annotations

import multiprocessing as mp
import time
from collections.abc import Callable, Iterable, Iterator
from typing import Any


def _target(func: Callable, item: Any, q: mp.Queue) -> None:  # noqa: ANN401
    try:
        q.put(("ok", func(item)))
    except Exception as e:  # noqa: BLE001
        q.put(("error", f"{type(e).__name__}: {e}"))


def run_parallel(func: Callable, items: Iterable[Any], workers: int = 4,
                 timeout: float = 120.0) -> Iterator[tuple[Any, str, Any]]:
    """Yield (item, status, result) where status is ok | error | timeout.

    Each item runs in its own process so hung native code can be killed safely.
    """
    ctx = mp.get_context("fork")
    pending = list(items)
    running: list[tuple[Any, mp.Process, mp.Queue, float]] = []
    while pending or running:
        while pending and len(running) < workers:
            item = pending.pop(0)
            q = ctx.Queue(maxsize=1)
            p = ctx.Process(target=_target, args=(func, item, q), daemon=True)
            p.start()
            running.append((item, p, q, time.time()))
        still = []
        for item, p, q, t0 in running:
            if not q.empty():
                status, res = q.get()
                p.join(timeout=5)
                yield item, status, res
            elif not p.is_alive():
                if not q.empty():
                    status, res = q.get()
                    yield item, status, res
                else:
                    yield item, "error", f"worker exited with code {p.exitcode}"
            elif time.time() - t0 > timeout:
                p.kill()
                p.join(timeout=5)
                yield item, "timeout", None
            else:
                still.append((item, p, q, t0))
        running = still
        time.sleep(0.05)
