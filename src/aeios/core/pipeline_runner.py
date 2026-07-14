from __future__ import annotations

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
        run = self.store.create_run(pipeline.id, input_goal)
        run.status = "running"
        self.store.save_run(run)

        previous_output = input_goal
        for index, step in enumerate(pipeline.steps):
            goal = (
                step.goal.replace("{input}", input_goal)
                .replace("{previous}", previous_output)
            )
            if not goal.strip():
                goal = input_goal

            task = self.kernel.run_goal(goal, agent=step.agent)
            step_result = {
                "index": index,
                "agent": step.agent,
                "goal": goal,
                "task_id": task.id,
                "status": task.status.value,
                "result": task.result,
                "error": task.error,
            }
            run.step_results.append(step_result)
            self.store.save_run(run)

            if task.status.value != "completed":
                run.status = "failed"
                run.error = task.error or f"Step {index + 1} failed"
                self.store.save_run(run)
                return run

            previous_output = task.result or previous_output

        run.status = "completed"
        run.result = previous_output
        self.store.save_run(run)
        return run
