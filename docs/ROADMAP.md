# AEIOS Roadmap

## Phase 0 — Foundation (now)

- [x] Repo scaffold + docs
- [x] Python package + CLI entrypoint
- [x] Kernel / memory / agents / tools skeleton
- [x] `aeios run "hello"` smoke path
- [x] docker-compose for Postgres / Qdrant / MinIO
- [ ] Initial git commit (on request)

## Phase 1 — Kernel MVP (weeks 2–4)

- [ ] Task state machine + scheduler queue
- [ ] SQLite persistence for tasks + audit log
- [ ] Architect + SoftwareEngineer agents (LLM-optional)
- [ ] Sandboxed shell + filesystem tools
- [ ] Syscall surface stabilized
- [ ] FastAPI control plane (`apps/api`)
- [ ] `aeios doctor` health checks

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
