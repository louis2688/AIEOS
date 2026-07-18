# AEIOS Architecture

## Strategy: B → A

1. **B — Local OS runtime** (now): Python kernel + CLI
2. **A — Platform product** (next): FastAPI + Next.js (projects, pipelines, models, KB)

## High-level diagram

```text
┌─────────────────────────────────────────────────────────┐
│  Interfaces                                             │
│  CLI (now)  →  FastAPI (Phase 1.5)  →  Next.js (Phase 2)│
└───────────────────────────┬─────────────────────────────┘
                            │ syscalls / HTTP
┌───────────────────────────▼─────────────────────────────┐
│  Kernel                                                 │
│  ├── Scheduler   (queue, priority, concurrency)         │
│  ├── Registry    (agents, tools, models)                │
│  └── Lifecycle   (task create → run → complete/fail)    │
└───────┬─────────────────┬─────────────────┬─────────────┘
        │                 │                 │
   ┌────▼────┐      ┌─────▼─────┐     ┌─────▼─────┐
   │ Agents  │      │  Memory   │     │   Tools   │
   │ Architect│     │ short-term│     │ filesystem│
   │ Engineer │     │ long-term │     │ shell     │
   │ Tester   │     │ (Qdrant+) │     │ http/mcp  │
   └─────────┘      └───────────┘     └───────────┘
```

## Core modules

### Kernel (`aeios.core`)

- Owns task state machine
- Dispatches work to agents
- Enforces syscall boundary (agents don't touch infra directly)

### Scheduler (`aeios.core.scheduler`)

- In-process queue for Phase 0–1
- Later: Redis/BullMQ-style queue if multi-worker

### Memory (`aeios.memory`)

- **Short-term:** session/task context in process + SQLite
- **Long-term:** embeddings in Qdrant (optional until Docker is available)
- Phase 0 default: in-memory + local JSON/SQLite fallback

### Agents (`aeios.agents`)

- `BaseAgent`: receive → think → act → observe
- Specialists register with the kernel by role

### Tools (`aeios.tools`)

- Registered capabilities with typed inputs/outputs
- Sandboxed shell (strict allowlist + cwd jail in Phase 1)
- **MCP bridge** (`aeios.tools.mcp`): optional external MCP servers from YAML
  `tools.mcp.servers`. Each remote tool is wrapped as a `BaseTool` named
  `mcp_<server>_<tool>` and invoked only through the `call_tool` syscall.
  Install optional deps with `pip install 'aeios[mcp]'`. No servers configured
  → kernel boots unchanged.

### Syscalls (`aeios.core.syscalls`)

Stable contract:

| Syscall | Purpose |
|---------|---------|
| `execute_task` | Submit a goal/task to the kernel |
| `request_memory` | Read/write memory scopes |
| `call_tool` | Invoke a registered tool |
| `list_agents` / `list_tools` | Introspection |

## Data stores (when infra is up)

| Store | Role |
|-------|------|
| PostgreSQL | Projects, pipelines, tasks, models, audit log |
| Qdrant | Optional vector memory / knowledge index |
| S3/MinIO | Artifacts, uploads (not wired yet) |
| SQLite | **Default** local-dev persistence |

### Choosing a backend

**SQLite (default)** — set `DATABASE_URL=sqlite:///./data/aeios.db` (or omit).
No Docker required. Used by kernel + FastAPI for tasks, projects, pipelines,
and the model library. Best for local CLI / dashboard development.

**Postgres** — start Compose (`docker compose up -d postgres`), install
`pip install 'aeios[postgres]'`, then:

```bash
DATABASE_URL=postgresql://aeios:aeios@localhost:5432/aeios
```

The same store interfaces open a thin `psycopg` connection; schema is
`CREATE TABLE IF NOT EXISTS` on boot (MVP — no migration framework; do not
rely on automatic upgrades across breaking schema changes).

**Qdrant (optional)** — start Compose Qdrant, install `pip install 'aeios[vector]'`,
keep `QDRANT_URL=http://localhost:6333` and `QDRANT_ENABLED=1`. Knowledge search
upserts memory/task snippets with a local hash embedder and merges vector hits
with lexical results. If Qdrant is down or the client is missing, search
soft-fails and lexical search continues — the kernel never breaks.

`aeios doctor` reports `sqlite` or `postgres` (whichever is active) and probes
Qdrant as a soft check.

## Security boundaries (Phase 1+)

- Tools run with cwd jail + command allowlist (Windows-aware; see [`SECURITY.md`](SECURITY.md))
- Model API keys: env override and/or `AEIOS_SECRETS_KEY` encrypt-at-rest — never returned raw from the API
- Auth (Clerk JWT) at API/UI boundary, not inside kernel loop

Full threat model: [`SECURITY.md`](SECURITY.md).

## Observability (MVP)

- **Request IDs** — `X-Request-ID` generated or echoed on every HTTP response (`aeios.observability`).
- **Counters** — in-process metrics for LLM calls (tokens + rough cost placeholder), tool calls/failures, tasks, and HTTP volume.
- **Export** — `GET /v1/metrics` (auth-protected when Clerk JWT is on). Not OpenTelemetry yet.

## Evolution

| Stage | Interface | Persistence |
|-------|-----------|-------------|
| Phase 0 | CLI | In-memory / SQLite |
| Phase 1 | CLI + FastAPI | SQLite → Postgres |
| Phase 2 | Next.js dashboard | Postgres + Qdrant |
| Phase 3 | MCP drivers, multi-tenant | Full stack + observability |
