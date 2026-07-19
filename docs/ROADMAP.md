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
- [x] Knowledge base search (API + UI)
- [x] Clerk auth (dashboard + server actions)
- [x] Model library registry (OpenAI / Anthropic / Ollama)

## Phase 3 — Hardening

- [x] Security: sandbox + secrets hygiene shipped; RBAC still deferred
- [x] Observability MVP: request IDs + token/cost counters (`/v1/metrics`)
- [x] Reflection / retry loop on tool failure
- [x] MCP bridge for external tools
- [x] Staging deploy path (Docker + Render Blueprint + Vercel) — see [`DEPLOY.md`](DEPLOY.md)
- [x] Ops hardening docs (Render free Postgres expiry, cold starts, healthcheck, monitors)
- [x] CI (GitHub Actions)
- [x] Optional LLM observe→act→reflect loop for SoftwareEngineer / Architect (library model; heuristic fallback)

## Phase 4 — Scale

- [ ] Multi-tenant isolation — row isolation for projects/pipelines/tasks/models done; memory/vectors partial
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
| 2026-07-15 | Knowledge search over tasks, pipelines, runs, projects, memory |
| 2026-07-15 | Clerk auth for Next.js dashboard (FastAPI JWT later) |
| 2026-07-15 | Model library: SQLite registry drives planner via ModelClient |
| 2026-07-18 | Persistence: SQLite default; Postgres via DATABASE_URL + `aeios[postgres]` |
| 2026-07-18 | Knowledge: optional Qdrant vector index (`aeios[vector]`); lexical fallback |
| 2026-07-19 | Staging on Render free tier: upgrade Postgres before ~30-day expiry; expect web cold starts |
| 2026-07-19 | Pipeline control + tenant hardening in progress; task cancel/SSE and per-user task/model isolation shipped |
| 2026-07-19 | Agents: optional LLM act loop via model library JSON tool protocol; heuristics when no library model |
