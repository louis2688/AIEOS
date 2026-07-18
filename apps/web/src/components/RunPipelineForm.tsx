"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { getPipelineRunAction, startPipelineRunAction } from "@/app/actions";
import type { PipelineRun } from "@/lib/types";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

function runProgress(run: PipelineRun): string {
  const n = run.step_results?.length ?? 0;
  const last = n ? run.step_results[n - 1] : null;
  const bits = [`${run.status}`];
  if (n) bits.push(`${n} step${n === 1 ? "" : "s"} done`);
  if (last?.agent) bits.push(last.agent);
  return bits.join(" · ");
}

export function RunPipelineForm({ pipelineId }: { pipelineId: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState<PipelineRun | null>(null);

  return (
    <section className="panel">
      <h2 className="panel-title">Run pipeline</h2>
      <form
        className="mt-4 space-y-3"
        action={(formData) => {
          setError(null);
          setLive(null);
          startTransition(async () => {
            const started = await startPipelineRunAction(formData);
            if (!started.ok) {
              setError(started.error);
              return;
            }
            let run = started.run;
            setLive(run);

            const deadline = Date.now() + 300_000;
            while (!TERMINAL.has(run.status) && Date.now() < deadline) {
              await new Promise((r) => setTimeout(r, 1000));
              const next = await getPipelineRunAction(run.id);
              if (!next.ok) {
                setError(next.error);
                return;
              }
              run = next.run;
              setLive(run);
            }

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
            disabled={pending}
          />
        </label>
        <button type="submit" className="btn-primary" disabled={pending}>
          {pending ? "Running…" : "Run now"}
        </button>
        {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}
        {live ? (
          <div className="rounded-md border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2 font-mono text-xs text-[var(--accent)]">
            <p>
              run {live.id} · {runProgress(live)}
            </p>
            {live.step_results?.length ? (
              <ul className="mt-2 space-y-1 text-[var(--muted)]">
                {live.step_results.map((s) => (
                  <li key={`${s.index}-${s.task_id}`}>
                    #{s.index + 1} {s.agent} — {s.status}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-[var(--muted)]">Waiting for first step…</p>
            )}
          </div>
        ) : null}
      </form>
    </section>
  );
}
