import {
  KnowledgeResults,
  KnowledgeSearchForm,
} from "@/components/KnowledgeSearch";
import { searchKnowledge } from "@/lib/aeios";
import type { KnowledgeHit } from "@/lib/types";

export default async function KnowledgePage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const params = await searchParams;
  const query = (params.q || "").trim();

  let results: KnowledgeHit[] = [];
  let error: string | undefined;

  if (query) {
    try {
      const response = await searchKnowledge(query, 40);
      results = response.results;
    } catch (err) {
      error = err instanceof Error ? err.message : "Search failed";
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-2xl text-[var(--ink)]">Knowledge base</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Find what the OS already knows from tasks, pipelines, projects, and memory.
        </p>
      </div>
      <KnowledgeSearchForm defaultQuery={query} />
      <KnowledgeResults query={query} results={results} error={error} />
    </div>
  );
}
