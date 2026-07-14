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
| PostgreSQL | Projects, pipelines, users, audit log |
| Qdrant | Vector memory / knowledge base |
| S3/MinIO | Artifacts, uploads |
| SQLite | Local-dev fallback for kernel state |

## Security boundaries (Phase 1+)

- Tools run with cwd jail + command allowlist
- Secrets only via env / secret store — never in memory dumps to logs
- Auth (Clerk) at API/UI boundary, not inside kernel loop

## Evolution

| Stage | Interface | Persistence |
|-------|-----------|-------------|
| Phase 0 | CLI | In-memory / SQLite |
| Phase 1 | CLI + FastAPI | SQLite → Postgres |
| Phase 2 | Next.js dashboard | Postgres + Qdrant |
| Phase 3 | MCP drivers, multi-tenant | Full stack + observability |
