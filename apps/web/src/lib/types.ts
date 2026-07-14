export type KernelStatus = {
  version: string;
  env: string;
  workspace: string;
  agents: string[];
  tools: string[];
  scheduler: { pending: number; active: number };
  tasks_tracked: number;
  last_task_id: string | null;
  db_path?: string;
  llm_planner?: boolean;
};

export type Task = {
  id: string;
  goal: string;
  status: string;
  agent: string | null;
  plan: string[];
  steps: Record<string, unknown>[];
  result: string | null;
  error: string | null;
};

export type Project = {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
};
