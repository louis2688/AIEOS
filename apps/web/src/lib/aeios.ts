import type { KernelStatus, Project, Task } from "./types";

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
