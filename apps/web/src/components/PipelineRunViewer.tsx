import Link from "next/link";
import { StatusPill } from "@/components/StatusPill";
import { textPreview } from "@/lib/step-format";
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
            {run.step_results.map((step) => {
              const resultPreview = textPreview(step.result);
              const errorPreview = textPreview(step.error, 400);
              return (
                <li
                  key={`${run.id}-${step.index}`}
                  className="rounded border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2 text-sm"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-mono text-[10px] text-[var(--muted)] uppercase">
                        Step {step.index + 1} · {step.agent}
                      </p>
                      <p className="mt-0.5 text-[var(--ink)]">{step.goal}</p>
                    </div>
                    <StatusPill status={step.status} />
                  </div>
                  {step.task_id ? (
                    <Link
                      href={`/tasks/${step.task_id}`}
                      className="mt-1.5 inline-block font-mono text-[10px] text-[var(--accent)] hover:underline"
                    >
                      task {step.task_id}
                    </Link>
                  ) : null}
                  {resultPreview ? (
                    <div className="mt-2">
                      <p className="label">Result</p>
                      <p className="mt-1 text-sm leading-relaxed text-[var(--ink)]">
                        {resultPreview}
                      </p>
                    </div>
                  ) : null}
                  {errorPreview ? (
                    <div className="mt-2">
                      <p className="label">Error</p>
                      <p className="mt-1 text-sm leading-relaxed text-[var(--danger)]">
                        {errorPreview}
                      </p>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ol>
          {run.result || run.error ? (
            <div className="mt-3 border-t border-[var(--line)] pt-3">
              {run.result ? (
                <div>
                  <p className="label">Run result</p>
                  <p className="mt-1 text-sm leading-relaxed text-[var(--ink)]">
                    {textPreview(run.result, 480)}
                  </p>
                </div>
              ) : null}
              {run.error ? (
                <div className={run.result ? "mt-2" : undefined}>
                  <p className="label">Run error</p>
                  <p className="mt-1 text-sm leading-relaxed text-[var(--danger)]">
                    {textPreview(run.error, 480)}
                  </p>
                </div>
              ) : null}
            </div>
          ) : null}
        </article>
      ))}
    </section>
  );
}
