export function StatusPill({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone =
    normalized === "completed" || normalized === "ok"
      ? "text-[var(--accent)] border-[var(--accent)]/40"
      : normalized === "failed" || normalized === "error"
        ? "text-[var(--danger)] border-[var(--danger)]/40"
        : normalized === "retry" || normalized === "started" || normalized === "running"
          ? "text-[var(--ink)] border-[var(--accent)]/25"
          : "text-[var(--muted)] border-[var(--line)]";

  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 font-mono text-[10px] uppercase ${tone}`}
    >
      {status}
    </span>
  );
}
