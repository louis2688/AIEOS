import Link from "next/link";
import { notFound } from "next/navigation";
import { StatusPill } from "@/components/StatusPill";
import { TaskArtifacts } from "@/components/TaskArtifacts";
import { TaskStepList } from "@/components/TaskStepList";
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

      <section className="panel space-y-4">
        <div>
          <p className="label">Status</p>
          <div className="mt-1">
            <StatusPill status={task.status} />
          </div>
        </div>
        <Meta label="Agent" value={task.agent || "—"} />
        <Meta label="Goal" value={task.goal} />
        {task.plan?.length ? (
          <div>
            <p className="label">Plan</p>
            <p className="mt-1 text-sm text-[var(--ink)]">{task.plan.join(" → ")}</p>
          </div>
        ) : null}
        <div>
          <p className="label">Result</p>
          {task.error ? (
            <p className="mt-2 text-sm leading-relaxed text-[var(--danger)]">{task.error}</p>
          ) : null}
          {task.result ? (
            <pre className="mt-2 overflow-x-auto rounded-md border border-[var(--line)] bg-[var(--panel-2)] p-3 font-mono text-xs whitespace-pre-wrap text-[var(--ink)]">
              {task.result}
            </pre>
          ) : !task.error ? (
            <p className="mt-2 text-sm text-[var(--muted)]">—</p>
          ) : null}
        </div>
        {task.steps?.length ? (
          <div>
            <p className="label">Steps</p>
            <TaskStepList steps={task.steps} />
          </div>
        ) : null}
        <div>
          <p className="label">Artifacts</p>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Files written during this task. On Render free, disk is ephemeral after redeploy/sleep.
          </p>
          <TaskArtifacts artifacts={artifacts} />
        </div>
      </section>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="label">{label}</p>
      <p className="mt-1 text-sm text-[var(--ink)]">{value}</p>
    </div>
  );
}
