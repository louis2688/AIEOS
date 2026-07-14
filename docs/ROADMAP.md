# AEIOS Roadmap

## Phase 0 — Foundation

- [x] Repo scaffold + docs
- [x] Python package + CLI entrypoint
- [x] Kernel / memory / agents / tools skeleton
- [x] `aeios run "hello"` smoke path
- [x] docker-compose for Postgres / Qdrant / MinIO
- [x] Initial git commit + GitHub repo

## Phase 1 — Kernel MVP

- [x] Task state machine + scheduler queue
- [x] SQLite persistence for tasks + audit log
- [x] Architect + SoftwareEngineer agents (LLM-optional planner)
- [x] Sandboxed shell + filesystem tools
- [x] Syscall surface stabilized (`get_task`, `list_tasks`, `doctor`)
- [x] FastAPI control plane (`aeios serve`)
- [x] `aeios doctor` health checks

## Phase 2 — Product surface

- [x] Next.js app (`apps/web`) scaffold
- [x] Dashboard: status + run goal + task history/detail
- [x] Assistant chat UI wired to kernel
- [x] Projects CRUD (SQLite + API + UI)
- [x] CORS for local web ↔ API
- [x] Pipelines (create / run / history UI + API)
- [ ] Clerk auth
- [ ] Model library registry
- [ ] Knowledge base search UI

## Phase 3 — Hardening

- [ ] Security: sandbox, RBAC, secrets hygiene
- [ ] Observability: traces, token/cost metrics
- [ ] Reflection / retry loop on tool failure
- [ ] MCP bridge for external tools
- [ ] CI (GitHub Actions) + staging deploy

## Phase 4 — Scale

- [ ] Multi-tenant isolation
- [ ] gRPC between kernel services (if needed)
- [ ] Plugin / driver marketplace
- [ ] Optional Rust for hot paths (only after Python proves the model)

## Decision log

| Date | Decision |
|------|----------|
| 2026-07-15 | Strategy **B → A**: kernel/CLI first, product UI second |
| 2026-07-15 | Python kernel; Next.js later; Compose before K8s |
| 2026-07-15 | Phase 1: SQLite + FastAPI + sandboxed shell; LLM planner optional |
| 2026-07-15 | Phase 2: thin dashboard first; Clerk/pipelines after core loop works |
| 2026-07-15 | Pipelines: sequential kernel steps with `{input}` / `{previous}` templates |
