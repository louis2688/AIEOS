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
| GET | `/v1/status` | Kernel status |
| GET | `/v1/agents` | Registered agents |
| GET | `/v1/tools` | Registered tools |
| POST | `/v1/tasks` | Execute a goal `{ "goal": "...", "agent": optional }` |
| GET | `/v1/tasks` | List recent tasks |
| GET | `/v1/tasks/{id}` | Get one task |
| GET/POST | `/v1/pipelines` | List / create pipelines |
| GET/DELETE | `/v1/pipelines/{id}` | Get / delete pipeline |
| POST | `/v1/pipelines/{id}/runs` | Run pipeline `{ "input_goal": "..." }` |
| GET | `/v1/pipelines/{id}/runs` | List runs for a pipeline |
| GET | `/v1/pipeline-runs/{id}` | Get one run |

## Example

```bash
curl -s http://127.0.0.1:8080/v1/status | jq
curl -s -X POST http://127.0.0.1:8080/v1/tasks \
  -H 'content-type: application/json' \
  -d '{"goal":"hello"}' | jq
```
