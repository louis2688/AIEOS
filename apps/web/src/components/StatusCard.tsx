import type { KernelStatus } from "@/lib/types";

export function StatusCard({ status }: { status: KernelStatus | null; error?: string }) {
  if (!status) {
    return (
      <section className="panel">
        <h2 className="panel-title">Kernel status</h2>
        <p className="mt-3 text-sm text-[var(--danger)]">
          API unreachable. Start the kernel with{" "}
          <code className="font-mono text-[var(--accent)]">aeios serve</code>.
        </p>
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
