"use client";

import { useState, useTransition } from "react";
import { runGoalAction } from "@/app/actions";
import type { Task } from "@/lib/types";

type Message = {
  role: "user" | "assistant";
  text: string;
  taskId?: string;
};

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
              <p className="mt-2 font-mono text-[10px] text-[var(--accent)]">task {m.taskId}</p>
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
          startTransition(async () => {
            const result = await runGoalAction(formData);
            if (!result.ok) {
              setMessages((prev) => [
                ...prev,
                { role: "assistant", text: `Error: ${result.error}` },
              ]);
              return;
            }
            const task = result.task as Task;
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                text: task.result || task.error || `Task ${task.status}`,
                taskId: task.id,
              },
            ]);
          });
        }}
      >
        <div className="flex flex-col gap-3 md:flex-row">
          <select
            name="agent"
            defaultValue={agents[0] || "software_engineer"}
            className="field md:w-56"
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
            className="field flex-1"
            disabled={pending}
          />
          <button type="submit" className="btn-primary md:w-auto" disabled={pending}>
            {pending ? "Running…" : "Send"}
          </button>
        </div>
      </form>
    </section>
  );
}
