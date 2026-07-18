"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";
import { cancelTaskAction, getTaskAction } from "@/app/actions";
import { StatusPill } from "@/components/StatusPill";
import { TaskArtifacts } from "@/components/TaskArtifacts";
import { TaskStepList } from "@/components/TaskStepList";
import type { Task, TaskArtifact } from "@/lib/types";

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

export function TaskDetailLive({
  initialTask,
  artifacts,
}: {
  initialTask: Task;
  artifacts: TaskArtifact[];
}) {
  const router = useRouter();
  const [task, setTask] = useState(initialTask);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const watchSignal = useRef({ cancelled: false });
  const watching = !TERMINAL.has(task.status);

  useEffect(() => {
    if (TERMINAL.has(initialTask.status)) return;

    watchSignal.current = { cancelled: false };
    let active = true;

    (async () => {
      try {
        const next = await watchTask(
          initialTask.id,
          (update) => {
            if (active) setTask(update);
          },
          watchSignal.current,
        );
        if (active) {
          setTask(next);
          if (TERMINAL.has(next.status)) router.refresh();
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to watch task");
        }
      }
    })();

    return () => {
      active = false;
      watchSignal.current.cancelled = true;
    };
    // Watch once per mount for a non-terminal task (parent remounts via key on refresh).
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional mount-scoped watch
  }, [initialTask.id]);

  return (
    <section className="panel space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="label">Status</p>
          <div className="mt-1">
            <StatusPill status={task.status} />
          </div>
        </div>
        {watching ? (
          <button
            type="button"
            className="rounded-md border border-[var(--line)] px-3 py-2 font-mono text-xs text-[var(--ink)] hover:bg-[var(--panel-2)] disabled:opacity-50"
            disabled={pending}
            onClick={() => {
              watchSignal.current.cancelled = true;
              startTransition(async () => {
                const res = await cancelTaskAction(task.id);
                if (res.ok) {
                  setTask(res.task);
                  router.refresh();
                } else {
                  setError(res.error);
                }
              });
            }}
          >
            {pending ? "Cancelling…" : "Cancel"}
          </button>
        ) : null}
      </div>

      {watching ? (
        <p className="font-mono text-xs text-[var(--accent)]">
          Live · {progressText(task)}
        </p>
      ) : null}
      {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}

      <Meta label="Agent" value={task.agent || "—"} />
      <Meta label="Goal" value={task.goal} />
      {task.plan?.length ? (
        <div>
          <p className="label">Plan</p>
          <p className="mt-1 text-sm text-[var(--ink)]">{task.plan.join(" → ")}</p>
        </div>
      ) : null}
      <div>
        <p className="label">Result</p>
        {task.error ? (
          <p className="mt-2 text-sm leading-relaxed text-[var(--danger)]">{task.error}</p>
        ) : null}
        {task.result ? (
          <pre className="mt-2 overflow-x-auto rounded-md border border-[var(--line)] bg-[var(--panel-2)] p-3 font-mono text-xs whitespace-pre-wrap text-[var(--ink)]">
            {task.result}
          </pre>
        ) : !task.error ? (
          <p className="mt-2 text-sm text-[var(--muted)]">
            {watching ? "Waiting for result…" : "—"}
          </p>
        ) : null}
      </div>
      {task.steps?.length ? (
        <div>
          <p className="label">Steps</p>
          <TaskStepList steps={task.steps} />
        </div>
      ) : null}
      <div>
        <p className="label">Artifacts</p>
        <p className="mt-1 text-xs text-[var(--muted)]">
          Files written during this task. Content is also stored in the database so it
          survives ephemeral disk on Render free.
        </p>
        <TaskArtifacts artifacts={artifacts} />
      </div>
    </section>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="label">{label}</p>
      <p className="mt-1 text-sm text-[var(--ink)]">{value}</p>
    </div>
  );
}
