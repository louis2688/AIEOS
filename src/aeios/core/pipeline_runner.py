from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from aeios.persistence.pipelines import Pipeline, PipelineRun, PipelineStore

if TYPE_CHECKING:
    from aeios.core.kernel import Kernel

_RUN_TERMINAL = frozenset({"completed", "failed", "cancelled"})
_TASK_TERMINAL = frozenset({"completed", "failed", "cancelled"})


class PipelineRunner:
    """Execute pipeline steps sequentially through the kernel."""

    def __init__(self, kernel: Kernel, store: PipelineStore) -> None:
        self.kernel = kernel
        self.store = store
        self._cancel_requested: set[str] = set()
        self._active_child: dict[str, str] = {}
        self._lock = threading.Lock()

    def request_cancel(self, run_id: str) -> PipelineRun | None:
        """Request cancellation of an in-flight pipeline run."""
        run = self.store.get_run(run_id)
        if not run:
            return None
        if run.status in _RUN_TERMINAL:
            return run
        with self._lock:
            self._cancel_requested.add(run_id)
            child_id = self._active_child.get(run_id)
        if child_id:
            self.kernel.request_cancel(child_id)
        run.status = "cancelled"
        run.error = run.error or "Cancelled by user"
        self.store.save_run(run)
        return self.store.get_run(run_id) or run

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._cancel_requested

    def run(self, pipeline: Pipeline, input_goal: str) -> PipelineRun:
        """Run all steps synchronously; return when finished."""
        run = self._begin(pipeline, input_goal)
        return self._execute(pipeline, run, input_goal)

    def start(self, pipeline: Pipeline, input_goal: str) -> PipelineRun:
        """Start a run on a daemon thread; return the in-progress run immediately."""
        run = self._begin(pipeline, input_goal)

        def _bg() -> None:
            self._execute(pipeline, run, input_goal)

        threading.Thread(
            target=_bg, name=f"aeios-pipeline-{run.id[:8]}", daemon=True
        ).start()
        return run

    def _begin(self, pipeline: Pipeline, input_goal: str) -> PipelineRun:
        run = self.store.create_run(pipeline.id, input_goal)
        run.status = "running"
        self.store.save_run(run)
        return run

    def _mark_cancelled(self, current: PipelineRun) -> PipelineRun:
        current.status = "cancelled"
        current.error = current.error or "Cancelled by user"
        self.store.save_run(current)
        with self._lock:
            self._cancel_requested.discard(current.id)
        return current

    def _wait_for_task(self, task_id: str, run_id: str):
        """Poll until the child task is terminal; cancel child if run cancelled."""
        deadline = time.time() + 600
        while time.time() < deadline:
            if self.is_cancel_requested(run_id):
                self.kernel.request_cancel(task_id)
            task = self.kernel.get_task(task_id)
            if task is None:
                return None
            if task.status.value in _TASK_TERMINAL:
                return task
            time.sleep(0.05)
        return self.kernel.get_task(task_id)

    def _execute(
        self, pipeline: Pipeline, run: PipelineRun, input_goal: str
    ) -> PipelineRun:
        # Reload so background thread sees the latest persisted row.
        current = self.store.get_run(run.id) or run
        previous_output = input_goal
        owner_id = pipeline.owner_id or "local"
        for index, step in enumerate(pipeline.steps):
            current = self.store.get_run(run.id) or current
            if self.is_cancel_requested(run.id) or current.status == "cancelled":
                return self._mark_cancelled(current)

            goal = (
                step.goal.replace("{input}", input_goal)
                .replace("{previous}", previous_output)
            )
            if not goal.strip():
                goal = input_goal

            task = self.kernel.run_goal_async(
                goal, agent=step.agent, owner_id=owner_id
            )
            with self._lock:
                self._active_child[run.id] = task.id
            try:
                task = self._wait_for_task(task.id, run.id) or task
            finally:
                with self._lock:
                    self._active_child.pop(run.id, None)

            current = self.store.get_run(run.id) or current
            step_result = {
                "index": index,
                "agent": step.agent,
                "goal": goal,
                "task_id": task.id,
                "status": task.status.value,
                "result": task.result,
                "error": task.error,
            }
            current.step_results.append(step_result)
            self.store.save_run(current)

            if self.is_cancel_requested(run.id) or current.status == "cancelled":
                return self._mark_cancelled(current)

            if task.status.value == "cancelled":
                return self._mark_cancelled(current)

            if task.status.value != "completed":
                current.status = "failed"
                current.error = task.error or f"Step {index + 1} failed"
                self.store.save_run(current)
                with self._lock:
                    self._cancel_requested.discard(run.id)
                return current

            previous_output = task.result or previous_output

        current = self.store.get_run(run.id) or current
        if self.is_cancel_requested(run.id) or current.status == "cancelled":
            return self._mark_cancelled(current)

        current.status = "completed"
        current.result = previous_output
        self.store.save_run(current)
        with self._lock:
            self._cancel_requested.discard(run.id)
        return current
