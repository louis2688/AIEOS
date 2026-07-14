"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { runPipelineAction } from "@/app/actions";
import type { PipelineRun } from "@/lib/types";

export function RunPipelineForm({ pipelineId }: { pipelineId: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<PipelineRun | null>(null);

  return (
    <section className="panel">
      <h2 className="panel-title">Run pipeline</h2>
      <form
        className="mt-4 space-y-3"
        action={(formData) => {
          setError(null);
          startTransition(async () => {
            const result = await runPipelineAction(formData);
            if (!result.ok) {
              setError(result.error);
              return;
            }
            setLastRun(result.run);
            router.refresh();
          });
        }}
      >
        <input type="hidden" name="id" value={pipelineId} />
        <label className="block">
          <span className="label">Input goal</span>
          <textarea
            name="input_goal"
            required
            rows={3}
            className="field mt-1.5"
            placeholder="booking module"
          />
        </label>
        <button type="submit" className="btn-primary" disabled={pending}>
          {pending ? "Running…" : "Run now"}
        </button>
        {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}
        {lastRun ? (
          <p className="font-mono text-xs text-[var(--accent)]">
            run {lastRun.id} · {lastRun.status}
          </p>
        ) : null}
      </form>
    </section>
  );
}
