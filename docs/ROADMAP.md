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

### Phase 1 follow-ups (optional polish)

- [ ] Postgres backend behind same store interface
- [ ] Richer LLM implementation loop (not just planning)
- [ ] Auth middleware on API

## Phase 2 — Product surface (weeks 5–7)

- [ ] Next.js app (`apps/web`) + Clerk auth
- [ ] Projects CRUD
- [ ] Pipelines UI + run viewer
- [ ] Model library registry
- [ ] Knowledge base search UI
- [ ] Assistant chat wired to kernel

## Phase 3 — Hardening (weeks 8–10)

- [ ] Security: sandbox, RBAC, secrets hygiene
- [ ] Observability: traces, token/cost metrics
- [ ] Reflection / retry loop on tool failure
- [ ] MCP bridge for external tools
- [ ] CI (GitHub Actions) + staging deploy

## Phase 4 — Scale (week 11+)

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
