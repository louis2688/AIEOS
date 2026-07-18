import { StatusPill } from "@/components/StatusPill";
import {
  stepError,
  stepName,
  stepStatus,
  stepSummary,
  stepTool,
  type StepLike,
} from "@/lib/step-format";

export function TaskStepList({ steps }: { steps: StepLike[] }) {
  if (steps.length === 0) return null;

  return (
    <ol className="mt-2 space-y-2">
      {steps.map((step, index) => {
        const name = stepName(step);
        const tool = stepTool(step);
        const status = stepStatus(step);
        const summary = stepSummary(step);
        const error = stepError(step);
        const showTool = tool && tool !== name;

        return (
          <li
            key={`${name}-${index}`}
            className="rounded-md border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="font-mono text-[10px] tracking-wide text-[var(--muted)] uppercase">
                  Step {index + 1}
                  {showTool ? ` · ${tool}` : null}
                </p>
                <p className="mt-0.5 font-mono text-xs text-[var(--accent)]">{name}</p>
              </div>
              <StatusPill status={status} />
            </div>
            {summary ? (
              <p className="mt-2 text-sm leading-relaxed text-[var(--ink)]">{summary}</p>
            ) : null}
            {error ? (
              <p className="mt-1.5 text-sm leading-relaxed text-[var(--danger)]">{error}</p>
            ) : null}
            {!summary && !error ? (
              <p className="mt-2 text-sm text-[var(--muted)]">No output</p>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
