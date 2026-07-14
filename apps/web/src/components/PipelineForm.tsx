"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { createPipelineAction } from "@/app/actions";
import type { PipelineStep, Project } from "@/lib/types";

const defaultAgents = ["software_engineer", "architect", "echo"];

export function PipelineForm({
  projects,
  agents = defaultAgents,
}: {
  projects: Project[];
  agents?: string[];
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [steps, setSteps] = useState<PipelineStep[]>([
    { agent: "architect", goal: "Outline architecture for: {input}" },
    { agent: "software_engineer", goal: "Inspect workspace for: {input}" },
  ]);

  const stepsJson = useMemo(() => JSON.stringify(steps), [steps]);

  return (
    <section className="panel">
      <h2 className="panel-title">New pipeline</h2>
      <p className="mt-2 text-sm text-[var(--muted)]">
        Steps run in order. Use <code className="text-[var(--accent)]">{"{input}"}</code>{" "}
        or <code className="text-[var(--accent)]">{"{previous}"}</code> in goals.
      </p>
      <form
        className="mt-4 space-y-4"
        action={(formData) => {
          setError(null);
          startTransition(async () => {
            const result = await createPipelineAction(formData);
            if (!result.ok) {
              setError(result.error);
              return;
            }
            router.push(`/pipelines/${result.pipeline.id}`);
            router.refresh();
          });
        }}
      >
        <input type="hidden" name="steps" value={stepsJson} />
        <label className="block">
          <span className="label">Name</span>
          <input name="name" required className="field mt-1.5" placeholder="Design → Inspect" />
        </label>
        <label className="block">
          <span className="label">Description</span>
          <textarea
            name="description"
            rows={2}
            className="field mt-1.5"
            placeholder="What this workflow does"
          />
        </label>
        <label className="block">
          <span className="label">Project (optional)</span>
          <select name="project_id" defaultValue="" className="field mt-1.5">
            <option value="">None</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="label">Steps</span>
            <button
              type="button"
              className="font-mono text-[10px] tracking-wide text-[var(--accent)] uppercase"
              onClick={() =>
                setSteps((prev) => [
                  ...prev,
                  { agent: "software_engineer", goal: "{previous}" },
                ])
              }
            >
              + Add step
            </button>
          </div>
          {steps.map((step, index) => (
            <div
              key={index}
              className="space-y-2 rounded-md border border-[var(--line)] p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <p className="font-mono text-[10px] text-[var(--muted)] uppercase">
                  Step {index + 1}
                </p>
                {steps.length > 1 ? (
                  <button
                    type="button"
                    className="font-mono text-[10px] text-[var(--danger)] uppercase"
                    onClick={() =>
                      setSteps((prev) => prev.filter((_, i) => i !== index))
                    }
                  >
                    Remove
                  </button>
                ) : null}
              </div>
              <select
                className="field"
                value={step.agent}
                onChange={(e) =>
                  setSteps((prev) =>
                    prev.map((s, i) =>
                      i === index ? { ...s, agent: e.target.value } : s,
                    ),
                  )
                }
              >
                {agents.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
              <textarea
                className="field min-h-20"
                value={step.goal}
                onChange={(e) =>
                  setSteps((prev) =>
                    prev.map((s, i) =>
                      i === index ? { ...s, goal: e.target.value } : s,
                    ),
                  )
                }
              />
            </div>
          ))}
        </div>

        <button type="submit" className="btn-primary" disabled={pending}>
          {pending ? "Creating…" : "Create pipeline"}
        </button>
        {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}
      </form>
    </section>
  );
}
