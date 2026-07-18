import { getSessionToken } from "./auth";
import type {
  KernelStatus,
  KnowledgeSearchResult,
  ModelRecord,
  Pipeline,
  PipelineRun,
  PipelineStep,
  Project,
  Task,
  TaskArtifact,
} from "./types";

export type { TaskArtifact };

const REQUEST_TIMEOUT_MS = 20_000;
const RETRY_DELAY_MS = 2_000;

function apiBase(): string {
  return (
    process.env.AEIOS_API_URL ||
    process.env.NEXT_PUBLIC_AEIOS_API_URL ||
    "http://127.0.0.1:8080"
  ).replace(/\/$/, "");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function extractDetail(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "";
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown; message?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail) return parsed.detail;
    if (typeof parsed.message === "string" && parsed.message) return parsed.message;
  } catch {
    // plain text body
  }
  return trimmed.length > 280 ? `${trimmed.slice(0, 277)}…` : trimmed;
}

function isTimeoutError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  if (err.name === "TimeoutError" || err.name === "AbortError") return true;
  return /timeout|timed out|aborted/i.test(err.message);
}

function isNetworkError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  if (isTimeoutError(err)) return false;
  // Undici / fetch failures when the host is unreachable or still booting.
  return (
    err.name === "TypeError" ||
    /fetch failed|network|ECONNREFUSED|ENOTFOUND|ECONNRESET|socket/i.test(err.message)
  );
}

function networkMessage(): string {
  return (
    "Can't reach the AEIOS API. If the API is on Render free tier it may be cold-starting " +
    "(often 30–60s) — wait and retry. Or start the kernel locally with aeios serve."
  );
}

function timeoutMessage(): string {
  return (
    "The API timed out. The server may be cold-starting — wait a moment and hit Retry, " +
    "or start the kernel locally with aeios serve."
  );
}

function authMessage(detail?: string): string {
  const hint =
    detail ||
    "Missing or invalid session token. Sign in again (top right), then refresh.";
  return `Authentication failed (401). ${hint}`;
}

function httpMessage(status: number, body: string): string {
  const detail = extractDetail(body);
  if (status === 401) return authMessage(detail || undefined);
  if (status === 403) {
    return detail
      ? `Access denied (403). ${detail}`
      : "Access denied (403). Your account may lack permission for this API.";
  }
  if (status === 502 || status === 503 || status === 504) {
    return (
      `API unavailable (${status})${detail ? `: ${detail}` : ""}. ` +
      "The service may still be starting — wait and retry."
    );
  }
  return detail || `AEIOS API ${status}`;
}

function toUserError(err: unknown): Error {
  if (err instanceof Error && err.message.startsWith("Authentication failed")) return err;
  if (err instanceof Error && err.message.startsWith("Can't reach")) return err;
  if (err instanceof Error && err.message.startsWith("The API timed out")) return err;
  if (err instanceof Error && err.message.startsWith("API unavailable")) return err;
  if (err instanceof Error && err.message.startsWith("Access denied")) return err;
  if (err instanceof Error && err.message.startsWith("AEIOS API")) return err;

  if (isTimeoutError(err)) return new Error(timeoutMessage());
  if (isNetworkError(err)) return new Error(networkMessage());
  if (err instanceof Error) return err;
  return new Error(networkMessage());
}

async function requestOnce<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getSessionToken();
  const headers: Record<string, string> = {
    "content-type": "application/json",
  };
  if (init?.headers) {
    const incoming = new Headers(init.headers);
    incoming.forEach((value, key) => {
      headers[key] = value;
    });
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${apiBase()}${path}`, {
      ...init,
      headers,
      cache: "no-store",
      signal: init?.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (err) {
    throw toUserError(err);
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(httpMessage(res.status, text));
  }
  return res.json() as Promise<T>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    return await requestOnce<T>(path, init);
  } catch (err) {
    // One automatic retry for cold-start / transient network failures (GET only).
    const method = (init?.method ?? "GET").toUpperCase();
    const retryable =
      method === "GET" &&
      err instanceof Error &&
      (err.message.startsWith("Can't reach") ||
        err.message.startsWith("The API timed out") ||
        err.message.startsWith("API unavailable"));
    if (!retryable) throw err;
    await sleep(RETRY_DELAY_MS);
    return requestOnce<T>(path, init);
  }
}

export function getStatus() {
  return request<KernelStatus>("/v1/status");
}

export function listTasks(limit = 30) {
  return request<Task[]>(`/v1/tasks?limit=${limit}`);
}

export function getTask(id: string) {
  return request<Task>(`/v1/tasks/${id}`);
}

export function createTask(
  goal: string,
  agent?: string,
  opts?: { wait?: boolean },
) {
  const wait = opts?.wait ?? true;
  const q = wait ? "" : "?wait=false";
  return request<Task>(`/v1/tasks${q}`, {
    method: "POST",
    body: JSON.stringify({ goal, agent: agent || null }),
  });
}

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

export async function pollTask(
  id: string,
  opts?: { intervalMs?: number; maxMs?: number; onUpdate?: (task: Task) => void },
): Promise<Task> {
  const intervalMs = opts?.intervalMs ?? 1000;
  const maxMs = opts?.maxMs ?? 180_000;
  const started = Date.now();
  let task = await getTask(id);
  opts?.onUpdate?.(task);
  while (!TERMINAL.has(task.status) && Date.now() - started < maxMs) {
    await sleep(intervalMs);
    task = await getTask(id);
    opts?.onUpdate?.(task);
  }
  return task;
}

export function getTaskArtifacts(id: string) {
  return request<{
    task_id: string;
    workspace: string;
    count: number;
    artifacts: TaskArtifact[];
  }>(`/v1/tasks/${id}/artifacts`);
}

export function cancelTask(id: string) {
  return request<Task>(`/v1/tasks/${id}/cancel`, { method: "POST" });
}

export function listProjects(limit = 30) {
  return request<Project[]>(`/v1/projects?limit=${limit}`);
}

export function createProject(name: string, description = "") {
  return request<Project>("/v1/projects", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
}

export function deleteProject(id: string) {
  return request<{ ok: boolean }>(`/v1/projects/${id}`, { method: "DELETE" });
}

export function listPipelines(limit = 30) {
  return request<Pipeline[]>(`/v1/pipelines?limit=${limit}`);
}

export function getPipeline(id: string) {
  return request<Pipeline>(`/v1/pipelines/${id}`);
}

export function createPipeline(input: {
  name: string;
  description?: string;
  project_id?: string | null;
  steps: PipelineStep[];
}) {
  return request<Pipeline>("/v1/pipelines", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deletePipeline(id: string) {
  return request<{ ok: boolean }>(`/v1/pipelines/${id}`, { method: "DELETE" });
}

export function runPipeline(
  id: string,
  input_goal: string,
  opts?: { wait?: boolean },
) {
  const wait = opts?.wait ?? true;
  const q = wait ? "" : "?wait=false";
  return request<PipelineRun>(`/v1/pipelines/${id}/runs${q}`, {
    method: "POST",
    body: JSON.stringify({ input_goal }),
  });
}

export async function pollPipelineRun(
  id: string,
  opts?: {
    intervalMs?: number;
    maxMs?: number;
    onUpdate?: (run: PipelineRun) => void;
  },
): Promise<PipelineRun> {
  const intervalMs = opts?.intervalMs ?? 1000;
  const maxMs = opts?.maxMs ?? 300_000;
  const started = Date.now();
  let run = await getPipelineRun(id);
  opts?.onUpdate?.(run);
  while (!TERMINAL.has(run.status) && Date.now() - started < maxMs) {
    await sleep(intervalMs);
    run = await getPipelineRun(id);
    opts?.onUpdate?.(run);
  }
  return run;
}

export function listPipelineRuns(pipelineId: string, limit = 30) {
  return request<PipelineRun[]>(`/v1/pipelines/${pipelineId}/runs?limit=${limit}`);
}

export function getPipelineRun(runId: string) {
  return request<PipelineRun>(`/v1/pipeline-runs/${runId}`);
}

export function searchKnowledge(query: string, limit = 30, kinds?: string[]) {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
  });
  if (kinds?.length) params.set("kinds", kinds.join(","));
  return request<KnowledgeSearchResult>(`/v1/knowledge/search?${params}`);
}

export function listModels(limit = 100) {
  return request<ModelRecord[]>(`/v1/models?limit=${limit}`);
}

export function createModel(input: {
  name: string;
  provider: string;
  model_id: string;
  base_url?: string | null;
  api_key?: string | null;
  is_default?: boolean;
  enabled?: boolean;
}) {
  return request<ModelRecord>("/v1/models", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function setDefaultModel(id: string) {
  return request<ModelRecord>(`/v1/models/${id}/default`, { method: "POST" });
}

export function deleteModel(id: string) {
  return request<{ ok: boolean }>(`/v1/models/${id}`, { method: "DELETE" });
}

export function testModel(id: string) {
  return request<{ ok: boolean; reply: string }>(`/v1/models/${id}/test`, {
    method: "POST",
  });
}
