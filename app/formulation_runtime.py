"""Admission control and worker-process serving for formulation."""

from __future__ import annotations

import asyncio
import atexit
import math
import multiprocessing
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

import anyio
from starlette.concurrency import run_in_threadpool

from .formulation import FormulationRequest, FormulationResult, formulate


FORMULATION_SLOTS = max(1, min(8, os.cpu_count() or 2))
FORMULATION_QUEUE_LIMIT = FORMULATION_SLOTS * 8


class FormulationBusy(RuntimeError):
    """Raised when admission control would accept unbounded waiting work."""

    def __init__(self, queued: int) -> None:
        super().__init__("The formulation engine is at capacity; retry shortly.")
        self.queued = queued


class FormulationTimeout(RuntimeError):
    """Raised when one solve exceeds the runtime safety budget."""


class FormulationRuntime:
    """Serve formulation work with bounded admission and safe process fallback."""

    def __init__(
        self,
        slots: int = FORMULATION_SLOTS,
        queue_limit: int | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        if slots < 1 or (queue_limit is not None and queue_limit < slots):
            raise ValueError("Formulation runtime limits are invalid")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Formulation timeout must be finite and positive")
        self.slots = slots
        self.queue_limit = queue_limit if queue_limit is not None else slots * 8
        self.timeout_seconds = timeout_seconds
        self._formulation_slots = anyio.Semaphore(slots)
        self._waiting = 0
        self._pool: ProcessPoolExecutor | None = None
        self._pool_lock = threading.Lock()
        self._pool_unavailable = False

    @property
    def waiting(self) -> int:
        return self._waiting

    @property
    def pool_state(self) -> str:
        if self._pool_unavailable:
            return "thread_fallback"
        if self._pool is None:
            return "not_started"
        return "process_pool"

    def snapshot(self) -> dict[str, int | float | str]:
        """Return operational state without exposing requests or recipe data."""
        return {
            "slots": self.slots,
            "queue_limit": self.queue_limit,
            "queue_depth": self._waiting,
            "timeout_seconds": self.timeout_seconds,
            "pool_state": self.pool_state,
        }

    async def solve(self, request: FormulationRequest) -> FormulationResult:
        """Admit one formulation and run it off the event loop."""
        if self._waiting >= self.queue_limit:
            raise FormulationBusy(self._waiting)
        self._waiting += 1
        try:
            async with self._formulation_slots:
                try:
                    return await asyncio.wait_for(self._run(request), self.timeout_seconds)
                except asyncio.TimeoutError as exc:
                    self.shutdown()
                    raise FormulationTimeout(
                        f"The formulation exceeded the {self.timeout_seconds:g} second time limit."
                    ) from exc
        finally:
            self._waiting -= 1

    async def _run(self, request: FormulationRequest) -> FormulationResult:
        pool = await run_in_threadpool(self._pool_or_none)
        if pool is None:
            return await run_in_threadpool(formulate, request)
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(pool, formulate, request)
        except BrokenProcessPool:
            self.shutdown()
            return await run_in_threadpool(formulate, request)

    def _pool_or_none(self) -> ProcessPoolExecutor | None:
        if self._pool is not None or self._pool_unavailable:
            return self._pool
        with self._pool_lock:
            if self._pool is None and not self._pool_unavailable:
                try:
                    self._pool = ProcessPoolExecutor(
                        max_workers=self.slots,
                        mp_context=multiprocessing.get_context("spawn"),
                    )
                except (OSError, ValueError, ImportError):
                    # Some sandboxes and container policies forbid subprocesses.
                    self._pool_unavailable = True
        return self._pool

    def shutdown(self) -> None:
        with self._pool_lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)


formulation_runtime = FormulationRuntime()
atexit.register(formulation_runtime.shutdown)
