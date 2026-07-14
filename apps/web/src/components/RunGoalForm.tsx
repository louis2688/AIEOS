"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { runGoalAction } from "@/app/actions";

const agents = ["software_engineer", "architect", "echo"];

export function RunGoalForm({ redirectTo }: { redirectTo?: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [lastId, setLastId] = useState<string | null>(null);

  return (
    <section className="panel">
      <h2 className="panel-title">Run goal</h2>
      <p className="mt-2 text-sm text-[var(--muted)]">
        Submit work to the kernel. Plan → act → observe, then persist.
      </p>
      <form
        className="mt-5 space-y-4"
        action={(formData) => {
          setError(null);
          startTransition(async () => {
            const result = await runGoalAction(formData);
            if (!result.ok) {
              setError(result.error);
              return;
            }
            setLastId(result.task.id);
            router.refresh();
            if (redirectTo) router.push(`${redirectTo}/${result.task.id}`);
          });
        }}
      >
        <label className="block">
          <span className="label">Goal</span>
          <textarea
            name="goal"
            required
            rows={4}
            placeholder="e.g. hello — or design the pipeline module"
            className="field mt-1.5 min-h-24 resize-y"
          />
        </label>
        <label className="block">
          <span className="label">Agent</span>
          <select name="agent" defaultValue="software_engineer" className="field mt-1.5">
            {agents.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={pending} className="btn-primary">
          {pending ? "Dispatching…" : "Dispatch to kernel"}
        </button>
        {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}
        {lastId ? (
          <p className="font-mono text-xs text-[var(--accent)]">task {lastId}</p>
        ) : null}
      </form>
    </section>
  );
}
