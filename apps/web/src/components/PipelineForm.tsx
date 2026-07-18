"use client";

import { memo, useCallback, useId, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { createPipelineAction } from "@/app/actions";
import type { PipelineStep, Project } from "@/lib/types";

const defaultAgents = ["software_engineer", "architect", "echo"];

type StepDraft = PipelineStep & { id: string };

function toPayload(steps: StepDraft[]): PipelineStep[] {
  return steps.map(({ agent, goal }) => ({ agent, goal }));
}

const PipelineStepRow = memo(function PipelineStepRow({
  step,
  index,
  agents,
  canRemove,
  onAgentChange,
  onGoalChange,
  onRemove,
}: {
  step: StepDraft;
  index: number;
  agents: string[];
  canRemove: boolean;
  onAgentChange: (id: string, agent: string) => void;
  onGoalChange: (id: string, goal: string) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <div className="space-y-2 rounded-md border border-[var(--line)] p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="font-mono text-[10px] text-[var(--muted)] uppercase">
          Step {index + 1}
        </p>
        {canRemove ? (
          <button
            type="button"
            className="font-mono text-[10px] text-[var(--danger)] uppercase"
            onClick={() => onRemove(step.id)}
          >
            Remove
          </button>
        ) : null}
      </div>
      <select
        className="field"
        defaultValue={step.agent}
        onChange={(e) => onAgentChange(step.id, e.target.value)}
      >
        {agents.map((a) => (
          <option key={a} value={a}>
            {a}
          </option>
        ))}
      </select>
      <textarea
        className="field min-h-20"
        defaultValue={step.goal}
        onChange={(e) => onGoalChange(step.id, e.target.value)}
      />
    </div>
  );
});

export function PipelineForm({
  projects,
  agents = defaultAgents,
}: {
  projects: Project[];
  agents?: string[];
}) {
  const router = useRouter();
  const idPrefix = useId();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const stepsRef = useRef<StepDraft[]>([]);
  const nextId = useRef(2);
  const [steps, setSteps] = useState<StepDraft[]>(() => {
    const initial: StepDraft[] = [
      {
        id: `${idPrefix}-0`,
        agent: "architect",
        goal: "Outline architecture for: {input}",
      },
      {
        id: `${idPrefix}-1`,
        agent: "software_engineer",
        goal: "Inspect workspace for: {input}",
      },
    ];
    // Ref is source of truth for field edits; state only tracks structure (add/remove).
    stepsRef.current = initial;
    return initial;
  });

  const onAgentChange = useCallback((id: string, agent: string) => {
    stepsRef.current = stepsRef.current.map((s) =>
      s.id === id ? { ...s, agent } : s,
    );
  }, []);

  const onGoalChange = useCallback((id: string, goal: string) => {
    stepsRef.current = stepsRef.current.map((s) =>
      s.id === id ? { ...s, goal } : s,
    );
  }, []);

  const onRemove = useCallback((id: string) => {
    setSteps(() => {
      const next = stepsRef.current.filter((s) => s.id !== id);
      stepsRef.current = next;
      return next;
    });
  }, []);

  const onAddStep = useCallback(() => {
    setSteps(() => {
      const next = [
        ...stepsRef.current,
        {
          id: `${idPrefix}-${nextId.current++}`,
          agent: "software_engineer",
          goal: "{previous}",
        },
      ];
      stepsRef.current = next;
      return next;
    });
  }, [idPrefix]);

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
          formData.set("steps", JSON.stringify(toPayload(stepsRef.current)));
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
              onClick={onAddStep}
            >
              + Add step
            </button>
          </div>
          {steps.map((step, index) => (
            <PipelineStepRow
              key={step.id}
              step={step}
              index={index}
              agents={agents}
              canRemove={steps.length > 1}
              onAgentChange={onAgentChange}
              onGoalChange={onGoalChange}
              onRemove={onRemove}
            />
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
