# Phase 1 Kernel MVP Implementation Plan

> **For agentic workers:** Execute task-by-task. Steps use checkbox syntax.

**Goal:** Make AEIOS a durable local kernel with SQLite task persistence, sandboxed shell, optional LLM planning, FastAPI control plane, and `aeios doctor`.

**Architecture:** Kernel remains the center. Tasks transition through a state machine and persist in SQLite. Tools stay behind syscalls. FastAPI is a thin HTTP adapter over the same syscall surface as the CLI.

**Tech Stack:** Python 3.11+, sqlite3, Typer, FastAPI/Uvicorn (optional extra), httpx for optional LLM calls.

---

### Task 1: Task state machine + SQLite store

**Files:**
- Create: `src/aeios/core/state_machine.py`
- Create: `src/aeios/persistence/sqlite_store.py`
- Modify: `src/aeios/core/kernel.py`
- Modify: `src/aeios/core/syscalls.py`
- Test: `tests/test_persistence.py`

- [x] Valid transitions: pending → planning → running → completed|failed
- [x] Persist tasks + audit events to `data/aeios.db`
- [x] `get_task` / `list_tasks` syscalls

### Task 2: Sandboxed shell tool

**Files:**
- Create: `src/aeios/tools/shell.py`
- Modify: `src/aeios/core/kernel.py`, `configs/default.yaml`
- Test: `tests/test_shell.py`

- [x] Allowlisted binaries only, cwd jail, timeout
- [x] Enabled in default config; still allowlisted/sandboxed

### Task 3: LLM-optional planner

**Files:**
- Create: `src/aeios/planning/planner.py`
- Modify: `src/aeios/agents/base.py`, software_engineer/architect
- Test: `tests/test_planner.py`

- [x] Deterministic planner always available
- [x] Optional OpenAI-compatible HTTP plan when `OPENAI_API_KEY` set

### Task 4: FastAPI + doctor CLI

**Files:**
- Create: `src/aeios/api/app.py`
- Modify: `src/aeios/cli.py`, `apps/api/README.md`, `pyproject.toml`
- Test: `tests/test_api.py`

- [x] `POST /v1/tasks`, `GET /v1/tasks`, `GET /v1/tasks/{id}`, `GET /v1/status`
- [x] `aeios serve`, `aeios doctor`, `aeios task get|list`

### Task 5: Docs + version bump

- [x] Update ROADMAP Phase 1 checkboxes
- [x] Bump to 0.2.0
- [x] README Phase 1 usage
