import Link from "next/link";
import { StatusPill } from "@/components/StatusPill";
import type { Task } from "@/lib/types";

export function TaskTable({ tasks }: { tasks: Task[] }) {
  if (tasks.length === 0) {
    return (
      <section className="panel">
        <h2 className="panel-title">Recent tasks</h2>
        <p className="mt-3 text-sm text-[var(--muted)]">No tasks yet. Run a goal from Control.</p>
      </section>
    );
  }

  return (
    <section className="panel overflow-hidden">
      <h2 className="panel-title">Recent tasks</h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[36rem] text-left text-sm">
          <thead>
            <tr className="font-mono text-[10px] tracking-widest text-[var(--muted)] uppercase">
              <th className="pb-2 pr-3 font-normal">ID</th>
              <th className="pb-2 pr-3 font-normal">Status</th>
              <th className="pb-2 pr-3 font-normal">Agent</th>
              <th className="pb-2 font-normal">Goal</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => (
              <tr key={task.id} className="border-t border-[var(--line)]">
                <td className="py-3 pr-3 font-mono text-xs">
                  <Link href={`/tasks/${task.id}`} className="text-[var(--accent)] hover:underline">
                    {task.id}
                  </Link>
                </td>
                <td className="py-3 pr-3">
                  <StatusPill status={task.status} />
                </td>
                <td className="py-3 pr-3 font-mono text-xs text-[var(--muted)]">
                  {task.agent || "—"}
                </td>
                <td className="py-3 text-[var(--ink)]">{task.goal}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
