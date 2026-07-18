import type { TaskArtifact } from "@/lib/types";

export function TaskArtifacts({ artifacts }: { artifacts: TaskArtifact[] }) {
  if (!artifacts.length) {
    return (
      <p className="mt-2 text-sm text-[var(--muted)]">
        No file artifacts recorded for this task.
      </p>
    );
  }

  return (
    <ul className="mt-2 space-y-3">
      {artifacts.map((a) => (
        <li
          key={a.path}
          className="rounded-md border border-[var(--line)] bg-[var(--panel-2)] p-3"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-mono text-xs text-[var(--accent)]">{a.path}</p>
            <p className="font-mono text-[10px] text-[var(--muted)]">
              {a.exists ? `${a.bytes} bytes` : "missing on disk"}
            </p>
          </div>
          {a.ephemeral_note && !a.exists ? (
            <p className="mt-1 text-xs text-[var(--muted)]">{a.ephemeral_note}</p>
          ) : null}
          {a.content ? (
            <pre className="mt-2 max-h-64 overflow-auto font-mono text-[11px] whitespace-pre-wrap text-[var(--ink)]">
              {a.content}
            </pre>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
