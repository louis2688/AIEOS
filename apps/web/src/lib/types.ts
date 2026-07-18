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
  default_model?: {
    id: string;
    name: string;
    provider: string;
    model_id: string;
  } | null;
  models_count?: number;
};

export type TaskStep = {
  step?: string;
  status?: string;
  tool?: string;
  output?: unknown;
  error?: string | null;
  result?: string | null;
  goal?: string;
  path?: string;
  url?: string;
  reflection?: string;
  [key: string]: unknown;
};

export type Task = {
  id: string;
  goal: string;
  status: string;
  agent: string | null;
  plan: string[];
  steps: TaskStep[];
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

export type PipelineStep = {
  goal: string;
  agent: string;
};

export type Pipeline = {
  id: string;
  name: string;
  description: string;
  project_id: string | null;
  steps: PipelineStep[];
  created_at: string;
  updated_at: string;
};

export type PipelineRun = {
  id: string;
  pipeline_id: string;
  status: string;
  input_goal: string;
  step_results: {
    index: number;
    agent: string;
    goal: string;
    task_id: string;
    status: string;
    result?: string | null;
    error?: string | null;
  }[];
  result: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type KnowledgeHit = {
  kind: string;
  id: string;
  title: string;
  snippet: string;
  score: number;
  href: string | null;
  meta: Record<string, unknown>;
};

export type KnowledgeSearchResult = {
  query: string;
  count: number;
  results: KnowledgeHit[];
};

export type ModelRecord = {
  id: string;
  name: string;
  provider: string;
  model_id: string;
  base_url: string | null;
  api_key_set: boolean;
  api_key_masked: string | null;
  is_default: boolean;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};
