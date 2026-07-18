from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from aeios.persistence.pipelines import Pipeline, PipelineRun, PipelineStore

if TYPE_CHECKING:
    from aeios.core.kernel import Kernel


class PipelineRunner:
    """Execute pipeline steps sequentially through the kernel."""

    def __init__(self, kernel: Kernel, store: PipelineStore) -> None:
        self.kernel = kernel
        self.store = store

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

    def _execute(
        self, pipeline: Pipeline, run: PipelineRun, input_goal: str
    ) -> PipelineRun:
        # Reload so background thread sees the latest persisted row.
        current = self.store.get_run(run.id) or run
        previous_output = input_goal
        for index, step in enumerate(pipeline.steps):
            goal = (
                step.goal.replace("{input}", input_goal)
                .replace("{previous}", previous_output)
            )
            if not goal.strip():
                goal = input_goal

            task = self.kernel.run_goal(
                goal, agent=step.agent, owner_id=pipeline.owner_id or "local"
            )
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

            if task.status.value != "completed":
                current.status = "failed"
                current.error = task.error or f"Step {index + 1} failed"
                self.store.save_run(current)
                return current

            previous_output = task.result or previous_output

        current.status = "completed"
        current.result = previous_output
        self.store.save_run(current)
        return current
