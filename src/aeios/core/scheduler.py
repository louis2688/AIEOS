from __future__ import annotations

from collections import deque
from typing import Callable

from aeios.core.types import Task


class Scheduler:
    """Simple in-process FIFO scheduler for Phase 0."""

    def __init__(self, max_concurrent: int = 2) -> None:
        self.max_concurrent = max_concurrent
        self._queue: deque[Task] = deque()
        self._active: set[str] = set()

    def enqueue(self, task: Task) -> None:
        self._queue.append(task)

    def dequeue(self) -> Task | None:
        if not self._queue:
            return None
        if len(self._active) >= self.max_concurrent:
            return None
        task = self._queue.popleft()
        self._active.add(task.id)
        return task

    def complete(self, task_id: str) -> None:
        self._active.discard(task_id)

    def drain(self, worker: Callable[[Task], None]) -> list[Task]:
        """Process queued tasks until empty or concurrency blocks forever."""
        done: list[Task] = []
        while True:
            task = self.dequeue()
            if task is None:
                break
            try:
                worker(task)
            finally:
                self.complete(task.id)
            done.append(task)
        return done

    @property
    def pending(self) -> int:
        return len(self._queue)

    @property
    def active(self) -> int:
        return len(self._active)
