import Link from "next/link";
import type { PipelineRun } from "@/lib/types";

export function PipelineRunViewer({ runs }: { runs: PipelineRun[] }) {
  if (runs.length === 0) {
    return (
      <section className="panel">
        <h2 className="panel-title">Run history</h2>
        <p className="mt-3 text-sm text-[var(--muted)]">No runs yet.</p>
      </section>
    );
  }

  return (
    <section className="panel space-y-4">
      <h2 className="panel-title">Run history</h2>
      {runs.map((run) => (
        <article
          key={run.id}
          className="rounded-md border border-[var(--line)] px-3 py-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-mono text-xs text-[var(--accent)]">{run.id}</p>
            <StatusPill status={run.status} />
          </div>
          <p className="mt-2 text-sm text-[var(--ink)]">{run.input_goal}</p>
          <ol className="mt-3 space-y-2">
            {run.step_results.map((step) => (
              <li
                key={`${run.id}-${step.index}`}
                className="rounded border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2 text-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-[10px] text-[var(--muted)] uppercase">
                    Step {step.index + 1} · {step.agent}
                  </span>
                  <StatusPill status={step.status} />
                </div>
                <p className="mt-1 text-[var(--ink)]">{step.goal}</p>
                {step.task_id ? (
                  <Link
                    href={`/tasks/${step.task_id}`}
                    className="mt-1 inline-block font-mono text-[10px] text-[var(--accent)] hover:underline"
                  >
                    task {step.task_id}
                  </Link>
                ) : null}
                {(step.result || step.error) && (
                  <pre className="mt-2 overflow-x-auto font-mono text-[11px] whitespace-pre-wrap text-[var(--muted)]">
                    {step.result || step.error}
                  </pre>
                )}
              </li>
            ))}
          </ol>
        </article>
      ))}
    </section>
  );
}

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "completed"
      ? "text-[var(--accent)] border-[var(--accent)]/40"
      : status === "failed"
        ? "text-[var(--danger)] border-[var(--danger)]/40"
        : "text-[var(--muted)] border-[var(--line)]";
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 font-mono text-[10px] uppercase ${tone}`}
    >
      {status}
    </span>
  );
}
