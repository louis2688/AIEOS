"use client";

import { useState, useTransition } from "react";
import { getTaskAction, startGoalAction } from "@/app/actions";
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

export function AssistantClient({ agents }: { agents: string[] }) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "AEIOS assistant online. Send a goal and I’ll route it through the kernel.",
    },
  ]);
  const [pending, startTransition] = useTransition();

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

            const deadline = Date.now() + 180_000;
            while (!TERMINAL.has(task.status) && Date.now() < deadline) {
              await new Promise((r) => setTimeout(r, 1000));
              const next = await getTaskAction(task.id);
              if (!next.ok) {
                setMessages((prev) => {
                  const copy = [...prev];
                  const i = progressIdx.current;
                  if (i >= 0 && copy[i]) {
                    copy[i] = {
                      ...copy[i],
                      text: `Error while polling: ${next.error}`,
                    };
                  }
                  return copy;
                });
                return;
              }
              task = next.task;
              setMessages((prev) => {
                const copy = [...prev];
                const i = progressIdx.current;
                if (i >= 0 && copy[i]) {
                  copy[i] = {
                    role: "assistant",
                    text: TERMINAL.has(task.status)
                      ? task.result || task.error || `Task ${task.status}`
                      : `Running… ${progressText(task)}`,
                    taskId: task.id,
                    status: task.status,
                  };
                }
                return copy;
              });
            }

            if (!TERMINAL.has(task.status)) {
              setMessages((prev) => {
                const copy = [...prev];
                const i = progressIdx.current;
                if (i >= 0 && copy[i]) {
                  copy[i] = {
                    ...copy[i],
                    text: `Still ${task.status} after waiting — open task ${task.id} for details.`,
                    taskId: task.id,
                    status: task.status,
                  };
                }
                return copy;
              });
            }
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
        </div>
      </form>
    </section>
  );
}
