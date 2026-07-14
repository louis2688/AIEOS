import Link from "next/link";
import { notFound } from "next/navigation";
import { getTask } from "@/lib/aeios";

export default async function TaskDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let task;
  try {
    task = await getTask(id);
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
        <Meta label="Status" value={task.status} />
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
          <pre className="mt-2 overflow-x-auto rounded-md border border-[var(--line)] bg-[var(--panel-2)] p-3 font-mono text-xs whitespace-pre-wrap text-[var(--ink)]">
            {task.result || task.error || "—"}
          </pre>
        </div>
        {task.steps?.length ? (
          <div>
            <p className="label">Steps</p>
            <pre className="mt-2 overflow-x-auto rounded-md border border-[var(--line)] bg-[var(--panel-2)] p-3 font-mono text-xs whitespace-pre-wrap text-[var(--muted)]">
              {JSON.stringify(task.steps, null, 2)}
            </pre>
          </div>
        ) : null}
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
