import { RunGoalForm } from "@/components/RunGoalForm";
import { StatusCard } from "@/components/StatusCard";
import { TaskTable } from "@/components/TaskTable";
import { getStatus, listTasks } from "@/lib/aeios";
import type { KernelStatus, Task } from "@/lib/types";

export default async function HomePage() {
  let status: KernelStatus | null = null;
  let tasks: Task[] = [];
  let error: string | undefined;

  try {
    [status, tasks] = await Promise.all([getStatus(), listTasks(8)]);
  } catch (err) {
    error = err instanceof Error ? err.message : "API offline";
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1.05fr_0.95fr]">
      <div className="space-y-5">
        <StatusCard status={status} error={error} />
        <TaskTable tasks={tasks} />
      </div>
      <RunGoalForm redirectTo="/tasks" />
    </div>
  );
}
