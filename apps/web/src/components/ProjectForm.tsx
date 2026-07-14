"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { createProjectAction } from "@/app/actions";

export function ProjectForm() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  return (
    <section className="panel">
      <h2 className="panel-title">New project</h2>
      <form
        className="mt-4 space-y-3"
        action={(formData) => {
          setError(null);
          startTransition(async () => {
            const result = await createProjectAction(formData);
            if (!result.ok) {
              setError(result.error);
              return;
            }
            router.refresh();
          });
        }}
      >
        <label className="block">
          <span className="label">Name</span>
          <input name="name" required className="field mt-1.5" placeholder="Launch pipeline" />
        </label>
        <label className="block">
          <span className="label">Description</span>
          <textarea
            name="description"
            rows={3}
            className="field mt-1.5"
            placeholder="What this workspace is for"
          />
        </label>
        <button type="submit" className="btn-primary" disabled={pending}>
          {pending ? "Creating…" : "Create project"}
        </button>
        {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}
      </form>
    </section>
  );
}
