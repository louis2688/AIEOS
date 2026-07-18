/** Helpers for rendering task / pipeline step records without dumping raw JSON. */

export type StepLike = Record<string, unknown>;

export function stepName(step: StepLike): string {
  const raw = step.step ?? step.tool ?? step.name ?? step.agent;
  return typeof raw === "string" && raw.trim() ? raw : "step";
}

export function stepTool(step: StepLike): string | null {
  const tool = step.tool;
  if (typeof tool === "string" && tool.trim()) return tool;
  const name = step.step;
  if (typeof name === "string" && name.trim()) return name;
  return null;
}

export function stepStatus(step: StepLike): string {
  const status = step.status;
  return typeof status === "string" && status.trim() ? status : "unknown";
}

function truncate(text: string, max = 280): string {
  const trimmed = text.trim();
  if (trimmed.length <= max) return trimmed;
  return `${trimmed.slice(0, max)}…`;
}

function summarizeValue(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === "string") return truncate(value);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    if (value.length === 0) return "empty list";
    if (value.every((v) => typeof v === "string")) {
      const preview = value.slice(0, 6).join(", ");
      const more = value.length > 6 ? ` (+${value.length - 6} more)` : "";
      return truncate(`${value.length} items: ${preview}${more}`);
    }
    return `${value.length} items`;
  }
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    if (typeof obj.status_code === "number") {
      const preview =
        typeof obj.body_preview === "string"
          ? obj.body_preview
          : typeof obj.truncated === "boolean"
            ? obj.truncated
              ? "truncated"
              : "complete"
            : null;
      return preview
        ? truncate(`HTTP ${obj.status_code} · ${preview}`)
        : `HTTP ${obj.status_code}`;
    }
    if (typeof obj.stdout === "string") {
      const out = obj.stdout.trim() || "(empty stdout)";
      return truncate(out);
    }
    if (Array.isArray(obj.modules)) {
      return truncate(`modules: ${obj.modules.join(", ")}`);
    }
    if (typeof obj.recommendation === "string") {
      return truncate(obj.recommendation);
    }
    const keys = Object.keys(obj);
    if (keys.length === 0) return "empty object";
    return truncate(`fields: ${keys.slice(0, 8).join(", ")}`);
  }
  return truncate(String(value));
}

/** One-line human summary for a task step record (errors rendered separately). */
export function stepSummary(step: StepLike): string | null {
  if (typeof step.reflection === "string" && step.reflection.trim()) {
    return truncate(step.reflection);
  }
  if (typeof step.goal === "string" && step.goal.trim()) {
    return truncate(step.goal);
  }
  if (typeof step.path === "string" && step.path.trim()) {
    const out = summarizeValue(step.output);
    return out ? truncate(`${step.path} · ${out}`) : truncate(String(step.path));
  }
  if (typeof step.url === "string" && step.url.trim()) {
    const out = summarizeValue(step.output);
    return out ? truncate(`${step.url} · ${out}`) : truncate(String(step.url));
  }
  const fromOutput = summarizeValue(step.output);
  if (fromOutput) return fromOutput;
  if (typeof step.result === "string" && step.result.trim()) {
    return truncate(step.result);
  }
  return null;
}

export function stepError(step: StepLike): string | null {
  if (typeof step.error === "string" && step.error.trim()) {
    return truncate(step.error, 400);
  }
  return null;
}

/** Readable preview for pipeline step result / error strings. */
export function textPreview(text: string | null | undefined, max = 320): string | null {
  if (!text || !text.trim()) return null;
  return truncate(text, max);
}
