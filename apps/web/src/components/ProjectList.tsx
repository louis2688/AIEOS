"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { deleteProjectAction } from "@/app/actions";
import type { Project } from "@/lib/types";

export function ProjectList({ projects }: { projects: Project[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  if (projects.length === 0) {
    return (
      <section className="panel">
        <h2 className="panel-title">Projects</h2>
        <p className="mt-3 text-sm text-[var(--muted)]">No projects yet.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2 className="panel-title">Projects</h2>
      <ul className="mt-4 space-y-3">
        {projects.map((p) => (
          <li
            key={p.id}
            className="flex flex-col gap-2 rounded-md border border-[var(--line)] px-3 py-3 sm:flex-row sm:items-start sm:justify-between"
          >
            <div>
              <p className="font-display text-lg text-[var(--ink)]">{p.name}</p>
              <p className="mt-1 text-sm text-[var(--muted)]">
                {p.description || "No description"}
              </p>
              <p className="mt-2 font-mono text-[10px] text-[var(--muted)]">
                {p.id} · {new Date(p.created_at).toLocaleString()}
              </p>
            </div>
            <form
              action={(formData) => {
                startTransition(async () => {
                  await deleteProjectAction(formData);
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
