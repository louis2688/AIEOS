import Link from "next/link";
import type { KnowledgeHit } from "@/lib/types";

const KIND_LABEL: Record<string, string> = {
  task: "Task",
  pipeline: "Pipeline",
  pipeline_run: "Run",
  project: "Project",
  memory: "Memory",
  artifact: "Artifact",
};

export function KnowledgeSearchForm({ defaultQuery }: { defaultQuery: string }) {
  return (
    <form action="/knowledge" method="get" className="panel space-y-3">
      <h2 className="panel-title">Search knowledge</h2>
      <p className="text-sm text-[var(--muted)]">
        Search tasks, pipeline runs, projects, artifacts, and memory for past work.
      </p>
      <div className="flex flex-col gap-3 md:flex-row">
        <input
          name="q"
          defaultValue={defaultQuery}
          required
          placeholder="e.g. billing, neon, architecture"
          className="field flex-1"
        />
        <button type="submit" className="btn-primary md:w-auto">
          Search
        </button>
      </div>
    </form>
  );
}

export function KnowledgeResults({
  query,
  results,
  error,
}: {
  query: string;
  results: KnowledgeHit[];
  error?: string;
}) {
  if (error) {
    return (
      <section className="panel">
        <h2 className="panel-title">Results</h2>
        <p className="mt-3 text-sm text-[var(--danger)]">{error}</p>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Is the API running? <code className="text-[var(--accent)]">aeios serve</code>
        </p>
      </section>
    );
  }

  if (!query) {
    return (
      <section className="panel">
        <h2 className="panel-title">Results</h2>
        <p className="mt-3 text-sm text-[var(--muted)]">
          Enter a query to search across AEIOS history.
        </p>
      </section>
    );
  }

  if (results.length === 0) {
    return (
      <section className="panel">
        <h2 className="panel-title">Results</h2>
        <p className="mt-3 text-sm text-[var(--muted)]">
          No matches for <span className="text-[var(--ink)]">“{query}”</span>.
        </p>
      </section>
    );
  }

  return (
    <section className="panel space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="panel-title">Results</h2>
        <p className="font-mono text-[10px] tracking-widest text-[var(--muted)] uppercase">
          {results.length} hits
        </p>
      </div>
      <ul className="space-y-3">
        {results.map((hit) => (
          <li
            key={`${hit.kind}-${hit.id}`}
            className="rounded-md border border-[var(--line)] px-3 py-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="rounded border border-[var(--line)] px-2 py-0.5 font-mono text-[10px] tracking-wide text-[var(--accent)] uppercase">
                {KIND_LABEL[hit.kind] || hit.kind}
              </span>
              <span className="font-mono text-[10px] text-[var(--muted)]">
                score {hit.score.toFixed(2)}
              </span>
            </div>
            {hit.href ? (
              <Link
                href={hit.href}
                className="mt-2 block font-display text-lg text-[var(--ink)] hover:text-[var(--accent)]"
              >
                {hit.title}
              </Link>
            ) : (
              <p className="mt-2 font-display text-lg text-[var(--ink)]">{hit.title}</p>
            )}
            <p className="mt-1 font-mono text-[10px] text-[var(--muted)]">{hit.id}</p>
            {hit.snippet ? (
              <p className="mt-2 text-sm text-[var(--muted)]">{hit.snippet}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
