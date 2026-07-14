import { TaskTable } from "@/components/TaskTable";
import { listTasks } from "@/lib/aeios";
import type { Task } from "@/lib/types";

export default async function TasksPage() {
  let tasks: Task[] = [];
  try {
    tasks = await listTasks(50);
  } catch {
    tasks = [];
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-2xl text-[var(--ink)]">Task history</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Persisted kernel runs from SQLite.
        </p>
      </div>
      <TaskTable tasks={tasks} />
    </div>
  );
}
