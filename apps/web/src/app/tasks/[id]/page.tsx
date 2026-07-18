import Link from "next/link";
import { notFound } from "next/navigation";
import { TaskDetailLive } from "@/components/TaskDetailLive";
import { getTask, getTaskArtifacts } from "@/lib/aeios";

export default async function TaskDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let task;
  let artifacts: Awaited<ReturnType<typeof getTaskArtifacts>>["artifacts"] = [];
  try {
    task = await getTask(id);
    try {
      const art = await getTaskArtifacts(id);
      artifacts = art.artifacts;
    } catch {
      artifacts = [];
    }
  } catch {
    notFound();
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] tracking-widest text-[var(--accent)] uppercase">
            Task
          </p>
          <h2 className="font-display text-2xl text-[var(--ink)]">{task.id}</h2>
        </div>
        <Link href="/tasks" className="font-mono text-xs text-[var(--muted)] hover:text-[var(--ink)]">
          ← Back
        </Link>
      </div>

      <TaskDetailLive
        key={`${task.id}-${task.status}`}
        initialTask={task}
        artifacts={artifacts}
      />
    </div>
  );
}
