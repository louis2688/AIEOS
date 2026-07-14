# AEIOS API (Phase 1.5)

FastAPI control plane will live here.

Planned endpoints:

- `POST /v1/tasks` — execute_task
- `GET /v1/tasks/{id}` — task status
- `GET /v1/agents` / `GET /v1/tools`
- `GET /v1/memory/search` — knowledge base (Phase 2)

Install optional deps from repo root:

```bash
pip install -e ".[api]"
```
