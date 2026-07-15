import type {
  KernelStatus,
  KnowledgeSearchResult,
  ModelRecord,
  Pipeline,
  PipelineRun,
  PipelineStep,
  Project,
  Task,
} from "./types";

function apiBase(): string {
  return (
    process.env.AEIOS_API_URL ||
    process.env.NEXT_PUBLIC_AEIOS_API_URL ||
    "http://127.0.0.1:8080"
  ).replace(/\/$/, "");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `AEIOS API ${res.status}`);
  }
  return res.json() as Promise<T>;
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

export function createTask(goal: string, agent?: string) {
  return request<Task>("/v1/tasks", {
    method: "POST",
    body: JSON.stringify({ goal, agent: agent || null }),
  });
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

export function runPipeline(id: string, input_goal: string) {
  return request<PipelineRun>(`/v1/pipelines/${id}/runs`, {
    method: "POST",
    body: JSON.stringify({ input_goal }),
  });
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
