"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";
import {
  cancelTaskAction,
  getTaskAction,
  startGoalAction,
} from "@/app/actions";
import type { Task } from "@/lib/types";

const agents = ["software_engineer", "architect", "echo"];
const TERMINAL = new Set(["completed", "failed", "cancelled"]);

function progressText(task: Task): string {
  const stepCount = task.steps?.length ?? 0;
  const last = stepCount ? task.steps[stepCount - 1] : null;
  const lastHint =
    last && typeof last === "object"
      ? String(last.step || last.tool || last.status || "")
      : "";
  const bits = [`status: ${task.status}`];
  if (stepCount) bits.push(`${stepCount} step${stepCount === 1 ? "" : "s"}`);
  if (lastHint) bits.push(lastHint);
  if (task.plan?.length && task.status === "planning") {
    bits.push(task.plan.slice(0, 2).join(" → "));
  }
  return bits.join(" · ");
}

async function watchTask(
  taskId: string,
  onUpdate: (task: Task) => void,
  signal: { cancelled: boolean },
): Promise<Task> {
  if (typeof EventSource !== "undefined") {
    try {
      return await new Promise<Task>((resolve, reject) => {
        const es = new EventSource(`/api/tasks/${encodeURIComponent(taskId)}/events`);
        let last: Task | null = null;
        const done = (task: Task) => {
          es.close();
          resolve(task);
        };
        es.onmessage = (ev) => {
          if (signal.cancelled) {
            es.close();
            return;
          }
          try {
            const task = JSON.parse(ev.data) as Task;
            last = task;
            onUpdate(task);
            if (TERMINAL.has(task.status)) done(task);
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
        }, 180_000);
      });
    } catch {
      // poll below
    }
  }

  const deadline = Date.now() + 180_000;
  const first = await getTaskAction(taskId);
  if (!first.ok) throw new Error(first.error);
  let task = first.task;
  onUpdate(task);
  while (!TERMINAL.has(task.status) && Date.now() < deadline && !signal.cancelled) {
    await new Promise((r) => setTimeout(r, 1000));
    const next = await getTaskAction(taskId);
    if (!next.ok) throw new Error(next.error);
    task = next.task;
    onUpdate(task);
  }
  return task;
}

export function RunGoalForm({ redirectTo }: { redirectTo?: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState<Task | null>(null);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const watchSignal = useRef({ cancelled: false });

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
          setLive(null);
          watchSignal.current = { cancelled: false };
          startTransition(async () => {
            const started = await startGoalAction(formData);
            if (!started.ok) {
              setError(started.error);
              return;
            }
            let task = started.task;
            setLive(task);
            setActiveTaskId(task.id);

            try {
              task = await watchTask(
                task.id,
                (next) => {
                  task = next;
                  setLive(next);
                },
                watchSignal.current,
              );
            } catch (err) {
              setError(err instanceof Error ? err.message : "Failed to watch task");
              setActiveTaskId(null);
              return;
            }

            setLive(task);
            setActiveTaskId(null);
            router.refresh();
            if (redirectTo && TERMINAL.has(task.status)) {
              router.push(`${redirectTo}/${task.id}`);
            }
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
            disabled={pending}
          />
        </label>
        <label className="block">
          <span className="label">Agent</span>
          <select
            name="agent"
            defaultValue="software_engineer"
            className="field mt-1.5"
            disabled={pending}
          >
            {agents.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={pending} className="btn-primary">
            {pending ? "Running…" : "Dispatch to kernel"}
          </button>
          {activeTaskId ? (
            <button
              type="button"
              className="rounded-md border border-[var(--line)] px-3 py-2 font-mono text-xs text-[var(--ink)] hover:bg-[var(--panel-2)] disabled:opacity-50"
              disabled={!pending}
              onClick={() => {
                const id = activeTaskId;
                watchSignal.current.cancelled = true;
                startTransition(async () => {
                  const res = await cancelTaskAction(id);
                  if (res.ok) {
                    setLive(res.task);
                  } else {
                    setError(res.error);
                  }
                  setActiveTaskId(null);
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
              task {live.id} · {progressText(live)}
            </p>
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
