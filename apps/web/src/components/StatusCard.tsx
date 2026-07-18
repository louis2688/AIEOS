"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import type { KernelStatus } from "@/lib/types";

function formatError(message: string) {
  const parts = message.split(/\b(aeios serve)\b/);
  return parts.map((part, i) =>
    part === "aeios serve" ? (
      <code key={i} className="font-mono text-[var(--accent)]">
        {part}
      </code>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

export function StatusCard({
  status,
  error,
}: {
  status: KernelStatus | null;
  error?: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  if (!status) {
    const message =
      error ||
      "Can't reach the AEIOS API. If the API is on Render free tier it may be cold-starting (often 30–60s) — wait and retry. Or start the kernel locally with aeios serve.";
    const isAuth = /authentication failed|401/i.test(message);

    return (
      <section className="panel">
        <div className="flex items-center justify-between gap-3">
          <h2 className="panel-title">Kernel status</h2>
          <span className="inline-flex items-center gap-2 font-mono text-[10px] tracking-widest text-[var(--danger)] uppercase">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--danger)]" />
            offline
          </span>
        </div>
        <p className="mt-3 text-sm text-[var(--danger)]">{formatError(message)}</p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={pending}
            className="btn-primary"
            onClick={() => startTransition(() => router.refresh())}
          >
            {pending ? "Retrying…" : "Retry"}
          </button>
          {isAuth ? (
            <span className="font-mono text-[10px] tracking-wide text-[var(--muted)] uppercase">
              Use Sign in in the header, then retry
            </span>
          ) : (
            <span className="font-mono text-[10px] tracking-wide text-[var(--muted)] uppercase">
              Cold start can take up to a minute
            </span>
          )}
        </div>
      </section>
    );
  }

  const rows: [string, string][] = [
    ["version", status.version],
    ["env", status.env],
    ["tasks", String(status.tasks_tracked)],
    ["llm planner", status.llm_planner ? "on" : "off"],
    ["agents", status.agents.join(", ")],
    ["tools", status.tools.join(", ")],
  ];

  return (
    <section className="panel">
      <div className="flex items-center justify-between gap-3">
        <h2 className="panel-title">Kernel status</h2>
        <span className="inline-flex items-center gap-2 font-mono text-[10px] tracking-widest text-[var(--accent)] uppercase">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] shadow-[0_0_10px_var(--accent)]" />
          online
        </span>
      </div>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2">
        {rows.map(([k, v]) => (
          <div key={k} className="border-t border-[var(--line)] pt-2">
            <dt className="font-mono text-[10px] tracking-widest text-[var(--muted)] uppercase">
              {k}
            </dt>
            <dd className="mt-1 text-sm text-[var(--ink)] break-all">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
