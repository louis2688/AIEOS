"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { deletePipelineAction } from "@/app/actions";
import type { Pipeline } from "@/lib/types";

export function PipelineList({ pipelines }: { pipelines: Pipeline[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  if (pipelines.length === 0) {
    return (
      <section className="panel">
        <h2 className="panel-title">Pipelines</h2>
        <p className="mt-3 text-sm text-[var(--muted)]">
          No pipelines yet. Create a multi-step workflow to get started.
        </p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2 className="panel-title">Pipelines</h2>
      <ul className="mt-4 space-y-3">
        {pipelines.map((p) => (
          <li
            key={p.id}
            className="flex flex-col gap-3 rounded-md border border-[var(--line)] px-3 py-3 sm:flex-row sm:items-start sm:justify-between"
          >
            <div>
              <Link
                href={`/pipelines/${p.id}`}
                className="font-display text-lg text-[var(--ink)] hover:text-[var(--accent)]"
              >
                {p.name}
              </Link>
              <p className="mt-1 text-sm text-[var(--muted)]">
                {p.description || "No description"}
              </p>
              <p className="mt-2 font-mono text-[10px] text-[var(--muted)]">
                {p.steps.length} steps · {p.id}
              </p>
            </div>
            <form
              action={(formData) => {
                startTransition(async () => {
                  await deletePipelineAction(formData);
                  router.refresh();
                });
              }}
            >
              <input type="hidden" name="id" value={p.id} />
              <button
                type="submit"
                disabled={pending}
                className="rounded-md border border-[var(--line)] px-3 py-1.5 font-mono text-[10px] tracking-wide text-[var(--muted)] uppercase hover:border-[var(--danger)] hover:text-[var(--danger)]"
              >
                Delete
              </button>
            </form>
          </li>
        ))}
      </ul>
    </section>
  );
}
