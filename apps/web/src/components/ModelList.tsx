"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import {
  deleteModelAction,
  setDefaultModelAction,
  testModelAction,
} from "@/app/actions";
import type { ModelRecord } from "@/lib/types";

export function ModelList({ models }: { models: ModelRecord[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (models.length === 0) {
    return (
      <section className="panel">
        <h2 className="panel-title">Library</h2>
        <p className="mt-3 text-sm text-[var(--muted)]">
          No models yet. Add OpenAI, Anthropic, or Ollama to enable LLM planning.
        </p>
      </section>
    );
  }

  return (
    <section className="panel space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="panel-title">Library</h2>
        <p className="font-mono text-[10px] tracking-widest text-[var(--muted)] uppercase">
          {models.length} models
        </p>
      </div>
      {message ? <p className="text-sm text-[var(--accent)]">{message}</p> : null}
      {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}
      <ul className="space-y-3">
        {models.map((m) => (
          <li
            key={m.id}
            className="rounded-md border border-[var(--line)] px-3 py-3"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-display text-lg text-[var(--ink)]">{m.name}</p>
                <p className="mt-1 font-mono text-[10px] text-[var(--muted)]">
                  {m.provider} · {m.model_id}
                  {m.is_default ? " · default" : ""}
                </p>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  {m.base_url || "default endpoint"} · key{" "}
                  {m.api_key_set ? m.api_key_masked || "set" : "none"}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {!m.is_default ? (
                  <form
                    action={(fd) => {
                      setError(null);
                      setMessage(null);
                      startTransition(async () => {
                        const result = await setDefaultModelAction(fd);
                        if (!result.ok) setError(result.error);
                        else {
                          setMessage(`Default → ${m.name}`);
                          router.refresh();
                        }
                      });
                    }}
                  >
                    <input type="hidden" name="id" value={m.id} />
                    <button
                      type="submit"
                      disabled={pending}
                      className="rounded-md border border-[var(--line)] px-2 py-1 font-mono text-[10px] uppercase text-[var(--muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
                    >
                      Make default
                    </button>
                  </form>
                ) : (
                  <span className="rounded border border-[var(--accent)]/40 px-2 py-1 font-mono text-[10px] uppercase text-[var(--accent)]">
                    Default
                  </span>
                )}
                <form
                  action={(fd) => {
                    setError(null);
                    setMessage(null);
                    startTransition(async () => {
                      const result = await testModelAction(fd);
                      if (!result.ok) setError(result.error);
                      else setMessage(`Test OK: ${result.reply.slice(0, 80)}`);
                    });
                  }}
                >
                  <input type="hidden" name="id" value={m.id} />
                  <button
                    type="submit"
                    disabled={pending}
                    className="rounded-md border border-[var(--line)] px-2 py-1 font-mono text-[10px] uppercase text-[var(--muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
                  >
                    Test
                  </button>
                </form>
                <form
                  action={(fd) => {
                    setError(null);
                    setMessage(null);
                    startTransition(async () => {
                      const result = await deleteModelAction(fd);
                      if (!result.ok) setError(result.error);
                      else router.refresh();
                    });
                  }}
                >
                  <input type="hidden" name="id" value={m.id} />
                  <button
                    type="submit"
                    disabled={pending}
                    className="rounded-md border border-[var(--line)] px-2 py-1 font-mono text-[10px] uppercase text-[var(--muted)] hover:border-[var(--danger)] hover:text-[var(--danger)]"
                  >
                    Delete
                  </button>
                </form>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
