# AEIOS API

FastAPI control plane over the same kernel syscalls as the CLI.

## Run

From repo root:

```bash
source .venv/bin/activate
pip install -e ".[api]"
aeios serve --host 127.0.0.1 --port 8080
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| GET | `/v1/metrics` | Process counters (tokens, tools, tasks) |
| GET | `/v1/status` | Kernel status |
| GET | `/v1/agents` | Registered agents |
| GET | `/v1/tools` | Registered tools |
| POST | `/v1/tasks` | Execute a goal `{ "goal": "...", "agent": optional }` (`?wait=false` for async) |
| GET | `/v1/tasks` | List recent tasks (owner-scoped) |
| GET | `/v1/tasks/{id}` | Get one task (owner-scoped) |
| POST | `/v1/tasks/{id}/cancel` | Request cancel; returns updated task or `404` |
| GET | `/v1/tasks/{id}/events` | SSE stream of task snapshots until terminal status |
| GET | `/v1/tasks/{id}/artifacts` | Files written during the task |
| GET/POST | `/v1/pipelines` | List / create pipelines |
| GET/DELETE | `/v1/pipelines/{id}` | Get / delete pipeline |
| POST | `/v1/pipelines/{id}/runs` | Run pipeline `{ "input_goal": "..." }` (`?wait=false` for async) |
| GET | `/v1/pipelines/{id}/runs` | List runs for a pipeline |
| GET | `/v1/pipeline-runs/{id}` | Get one run |
| POST | `/v1/pipeline-runs/{id}/cancel` | Request cancel; returns updated run or `404` |
| GET | `/v1/pipeline-runs/{id}/events` | SSE stream of run snapshots until terminal status |
| GET | `/v1/pipeline-runs` | List recent runs |
| GET | `/v1/knowledge/search?q=` | Search tasks / pipelines / runs / projects / memory / artifacts |
| GET/POST | `/v1/models` | List / register models (owner-scoped) |
| PATCH/DELETE | `/v1/models/{id}` | Update / delete |
| POST | `/v1/models/{id}/default` | Set planner default |
| POST | `/v1/models/{id}/test` | Smoke-test provider |

### Task cancel + SSE

- `POST /v1/tasks/{id}/cancel` — owner-scoped; asks the kernel to cancel a running task.
- `GET /v1/tasks/{id}/events` — `text/event-stream` of JSON task snapshots (same shape as `GET /v1/tasks/{id}`) until `completed` / `failed` / `cancelled`.

### Pipeline cancel + SSE

- `POST /v1/pipeline-runs/{id}/cancel` — owner-scoped; cancels the active child task and stops between steps.
- `GET /v1/pipeline-runs/{id}/events` — `text/event-stream` of JSON run snapshots (same shape as `GET /v1/pipeline-runs/{id}`) until `completed` / `failed` / `cancelled`.

## Example

```bash
curl -s http://127.0.0.1:8080/v1/status | jq
curl -s -X POST http://127.0.0.1:8080/v1/tasks \
  -H 'content-type: application/json' \
  -d '{"goal":"hello"}' | jq

# async task + cancel / live events
TASK=$(curl -s -X POST 'http://127.0.0.1:8080/v1/tasks?wait=false' \
  -H 'content-type: application/json' \
  -d '{"goal":"hello","agent":"echo"}' | jq -r .id)
curl -s -X POST "http://127.0.0.1:8080/v1/tasks/${TASK}/cancel" | jq
curl -sN "http://127.0.0.1:8080/v1/tasks/${TASK}/events"

# pipeline run cancel / live events
curl -s -X POST "http://127.0.0.1:8080/v1/pipeline-runs/${RUN}/cancel" | jq
curl -sN "http://127.0.0.1:8080/v1/pipeline-runs/${RUN}/events"
```
