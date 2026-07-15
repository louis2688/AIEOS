import { ModelForm } from "@/components/ModelForm";
import { ModelList } from "@/components/ModelList";
import { getStatus, listModels } from "@/lib/aeios";
import type { ModelRecord } from "@/lib/types";

export default async function ModelsPage() {
  let models: ModelRecord[] = [];
  let defaultLabel = "deterministic planner (no default model)";

  try {
    const [listed, status] = await Promise.all([listModels(100), getStatus()]);
    models = listed;
    if (status.default_model) {
      const dm = status.default_model;
      defaultLabel = `${dm.name || "model"} · ${dm.provider}/${dm.model_id}`;
    }
  } catch {
    models = [];
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-2xl text-[var(--ink)]">Model library</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Active planner: <span className="text-[var(--ink)]">{defaultLabel}</span>
        </p>
      </div>
      <div className="grid gap-5 lg:grid-cols-[0.95fr_1.05fr]">
        <ModelForm />
        <ModelList models={models} />
      </div>
    </div>
  );
}
