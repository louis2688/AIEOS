"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { createModelAction } from "@/app/actions";

const providers = [
  { id: "openai", label: "OpenAI", hint: "api.openai.com" },
  { id: "anthropic", label: "Anthropic", hint: "api.anthropic.com" },
  { id: "ollama", label: "Ollama", hint: "127.0.0.1:11434" },
];

export function ModelForm() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [provider, setProvider] = useState("openai");

  return (
    <section className="panel">
      <h2 className="panel-title">Add model</h2>
      <p className="mt-2 text-sm text-[var(--muted)]">
        Register a provider for planning. Keys stay on the kernel host (masked in the UI).
      </p>
      <form
        className="mt-4 space-y-3"
        action={(formData) => {
          setError(null);
          startTransition(async () => {
            const result = await createModelAction(formData);
            if (!result.ok) {
              setError(result.error);
              return;
            }
            router.refresh();
          });
        }}
      >
        <label className="block">
          <span className="label">Display name</span>
          <input name="name" required className="field mt-1.5" placeholder="GPT-4o mini" />
        </label>
        <label className="block">
          <span className="label">Provider</span>
          <select
            name="provider"
            className="field mt-1.5"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="label">Model id</span>
          <input
            name="model_id"
            required
            className="field mt-1.5"
            placeholder={
              provider === "ollama"
                ? "llama3.2"
                : provider === "anthropic"
                  ? "claude-sonnet-4-20250514"
                  : "gpt-4o-mini"
            }
          />
        </label>
        <label className="block">
          <span className="label">Base URL (optional)</span>
          <input
            name="base_url"
            className="field mt-1.5"
            placeholder={
              provider === "ollama"
                ? "http://127.0.0.1:11434/v1"
                : "leave blank for provider default"
            }
          />
        </label>
        <label className="block">
          <span className="label">API key {provider === "ollama" ? "(optional)" : ""}</span>
          <input
            name="api_key"
            type="password"
            autoComplete="off"
            className="field mt-1.5"
            placeholder={provider === "ollama" ? "usually empty" : "sk-…"}
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
          <input type="checkbox" name="is_default" className="accent-[var(--accent)]" />
          Set as default for planner
        </label>
        <button type="submit" className="btn-primary" disabled={pending}>
          {pending ? "Saving…" : "Add to library"}
        </button>
        {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}
      </form>
    </section>
  );
}
