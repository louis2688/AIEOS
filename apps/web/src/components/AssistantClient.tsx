"use client";

import { useRef, useState, useTransition } from "react";
import { cancelTaskAction, getTaskAction, startGoalAction } from "@/app/actions";
import type { Task } from "@/lib/types";

type Message = {
  role: "user" | "assistant";
  text: string;
  taskId?: string;
  status?: string;
};

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

function applyTaskMessage(
  prev: Message[],
  idx: number,
  task: Task,
  text?: string,
): Message[] {
  const copy = [...prev];
  if (idx < 0 || !copy[idx]) return prev;
  copy[idx] = {
    role: "assistant",
    text:
      text ??
      (TERMINAL.has(task.status)
        ? task.result || task.error || `Task ${task.status}`
        : `Running… ${progressText(task)}`),
    taskId: task.id,
    status: task.status,
  };
  return copy;
}

async function watchTask(
  taskId: string,
  onUpdate: (task: Task) => void,
  signal: { cancelled: boolean },
): Promise<Task> {
  // Prefer SSE via Next proxy; fall back to action polling.
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
          // Fall through to polling by rejecting with a sentinel.
          reject(new Error("sse-fallback"));
        };
        // Safety timeout — same as poll
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

export function AssistantClient({ agents }: { agents: string[] }) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "AEIOS assistant online. Send a goal and I’ll route it through the kernel.",
    },
  ]);
  const [pending, startTransition] = useTransition();
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const watchSignal = useRef({ cancelled: false });

  return (
    <section className="panel flex min-h-[28rem] flex-col">
      <h2 className="panel-title">Assistant engine</h2>
      <div className="mt-4 flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.map((m, i) => (
          <div
            key={`${m.role}-${i}`}
            className={`max-w-[90%] rounded-md px-3 py-2 text-sm whitespace-pre-wrap ${
              m.role === "user"
                ? "ml-auto bg-[var(--panel-2)] text-[var(--ink)]"
                : "border border-[var(--line)] bg-[var(--panel)] text-[var(--ink)]"
            }`}
          >
            {m.text}
            {m.taskId ? (
              <p className="mt-2 font-mono text-[10px] text-[var(--accent)]">
                task {m.taskId}
                {m.status ? ` · ${m.status}` : ""}
              </p>
            ) : null}
          </div>
        ))}
      </div>
      <form
        className="mt-4 flex flex-col gap-3 border-t border-[var(--line)] pt-4"
        action={(formData) => {
          const goal = String(formData.get("goal") || "").trim();
          if (!goal) return;
          setMessages((prev) => [...prev, { role: "user", text: goal }]);
          const progressIdx = { current: -1 };
          watchSignal.current = { cancelled: false };
          startTransition(async () => {
            const started = await startGoalAction(formData);
            if (!started.ok) {
              setMessages((prev) => [
                ...prev,
                { role: "assistant", text: `Error: ${started.error}` },
              ]);
              return;
            }
            let task = started.task as Task;
            setActiveTaskId(task.id);
            setMessages((prev) => {
              progressIdx.current = prev.length;
              return [
                ...prev,
                {
                  role: "assistant",
                  text: `Running… ${progressText(task)}`,
                  taskId: task.id,
                  status: task.status,
                },
              ];
            });

            try {
              task = await watchTask(
                task.id,
                (next) => {
                  task = next;
                  setMessages((prev) =>
                    applyTaskMessage(prev, progressIdx.current, next),
                  );
                },
                watchSignal.current,
              );
            } catch (err) {
              setMessages((prev) => {
                const copy = [...prev];
                const i = progressIdx.current;
                if (i >= 0 && copy[i]) {
                  copy[i] = {
                    ...copy[i],
                    text: `Error while watching: ${
                      err instanceof Error ? err.message : "unknown"
                    }`,
                  };
                }
                return copy;
              });
              setActiveTaskId(null);
              return;
            }

            setMessages((prev) =>
              applyTaskMessage(prev, progressIdx.current, task),
            );
            if (!TERMINAL.has(task.status)) {
              setMessages((prev) =>
                applyTaskMessage(
                  prev,
                  progressIdx.current,
                  task,
                  `Still ${task.status} after waiting — open task ${task.id} for details.`,
                ),
              );
            }
            setActiveTaskId(null);
          });
        }}
      >
        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <select
            name="agent"
            defaultValue={agents[0] || "software_engineer"}
            className="field shrink-0 md:w-56"
            disabled={pending}
          >
            {agents.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
          <input
            name="goal"
            required
            placeholder="Ask the kernel…"
            className="field min-w-0 flex-1"
            disabled={pending}
            autoComplete="off"
          />
          <button type="submit" className="btn-primary shrink-0 md:w-auto" disabled={pending}>
            {pending ? "Running…" : "Send"}
          </button>
          {activeTaskId ? (
            <button
              type="button"
              className="shrink-0 rounded-md border border-[var(--line)] px-3 py-2 font-mono text-xs text-[var(--ink)] hover:bg-[var(--panel-2)] md:w-auto disabled:opacity-50"
              disabled={!pending}
              onClick={() => {
                const id = activeTaskId;
                watchSignal.current.cancelled = true;
                startTransition(async () => {
                  const res = await cancelTaskAction(id);
                  if (res.ok) {
                    setMessages((prev) => {
                      const copy = [...prev];
                      for (let i = copy.length - 1; i >= 0; i -= 1) {
                        if (copy[i]?.taskId === id) {
                          copy[i] = {
                            role: "assistant",
                            text:
                              res.task.result ||
                              res.task.error ||
                              `Task ${res.task.status}`,
                            taskId: id,
                            status: res.task.status,
                          };
                          break;
                        }
                      }
                      return copy;
                    });
                  }
                  setActiveTaskId(null);
                });
              }}
            >
              Cancel
            </button>
          ) : null}
        </div>
      </form>
    </section>
  );
}
