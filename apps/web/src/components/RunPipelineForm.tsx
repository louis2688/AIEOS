"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";
import {
  cancelPipelineRunAction,
  getPipelineRunAction,
  startPipelineRunAction,
} from "@/app/actions";
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

async function watchPipelineRun(
  runId: string,
  onUpdate: (run: PipelineRun) => void,
  signal: { cancelled: boolean },
): Promise<PipelineRun> {
  if (typeof EventSource !== "undefined") {
    try {
      return await new Promise<PipelineRun>((resolve, reject) => {
        const es = new EventSource(
          `/api/pipeline-runs/${encodeURIComponent(runId)}/events`,
        );
        let last: PipelineRun | null = null;
        const done = (run: PipelineRun) => {
          es.close();
          resolve(run);
        };
        es.onmessage = (ev) => {
          if (signal.cancelled) {
            es.close();
            return;
          }
          try {
            const run = JSON.parse(ev.data) as PipelineRun;
            last = run;
            onUpdate(run);
            if (TERMINAL.has(run.status)) done(run);
          } catch (err) {
            es.close();
            reject(err);
          }
        };
        es.onerror = () => {
          es.close();
          if (last && TERMINAL.has(last.status)) {
            resolve(last);
            return;
          }
          reject(new Error("sse-fallback"));
        };
        window.setTimeout(() => {
          es.close();
          if (last) resolve(last);
          else reject(new Error("sse-timeout"));
        }, 300_000);
      });
    } catch {
      // poll below
    }
  }

  const deadline = Date.now() + 300_000;
  const first = await getPipelineRunAction(runId);
  if (!first.ok) throw new Error(first.error);
  let run = first.run;
  onUpdate(run);
  while (!TERMINAL.has(run.status) && Date.now() < deadline && !signal.cancelled) {
    await new Promise((r) => setTimeout(r, 1000));
    const next = await getPipelineRunAction(run.id);
    if (!next.ok) throw new Error(next.error);
    run = next.run;
    onUpdate(run);
  }
  return run;
}

export function RunPipelineForm({ pipelineId }: { pipelineId: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState<PipelineRun | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const watchSignal = useRef({ cancelled: false });

  return (
    <section className="panel">
      <h2 className="panel-title">Run pipeline</h2>
      <form
        className="mt-4 space-y-3"
        action={(formData) => {
          setError(null);
          setLive(null);
          watchSignal.current = { cancelled: false };
          startTransition(async () => {
            const started = await startPipelineRunAction(formData);
            if (!started.ok) {
              setError(started.error);
              return;
            }
            let run = started.run;
            setLive(run);
            setActiveRunId(run.id);

            try {
              run = await watchPipelineRun(
                run.id,
                (next) => {
                  run = next;
                  setLive(next);
                },
                watchSignal.current,
              );
            } catch (err) {
              setError(err instanceof Error ? err.message : "Failed to watch run");
              setActiveRunId(null);
              return;
            }

            setLive(run);
            setActiveRunId(null);
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
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className="btn-primary" disabled={pending}>
            {pending ? "Running…" : "Run now"}
          </button>
          {activeRunId ? (
            <button
              type="button"
              className="rounded-md border border-[var(--line)] px-3 py-2 font-mono text-xs text-[var(--ink)] hover:bg-[var(--panel-2)] disabled:opacity-50"
              disabled={!pending}
              onClick={() => {
                const id = activeRunId;
                watchSignal.current.cancelled = true;
                startTransition(async () => {
                  const res = await cancelPipelineRunAction(id);
                  if (res.ok) {
                    setLive(res.run);
                  } else {
                    setError(res.error);
                  }
                  setActiveRunId(null);
                  router.refresh();
                });
              }}
            >
              Cancel
            </button>
          ) : null}
        </div>
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
            {live.error ? (
              <p className="mt-2 text-[var(--danger)]">{live.error}</p>
            ) : null}
            {live.result && TERMINAL.has(live.status) ? (
              <p className="mt-2 whitespace-pre-wrap text-[var(--ink)]">{live.result}</p>
            ) : null}
          </div>
        ) : null}
      </form>
    </section>
  );
}
