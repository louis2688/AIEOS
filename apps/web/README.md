# AEIOS Web (Phase 2)

Next.js dashboard over the AEIOS FastAPI control plane.

## Prerequisites

```bash
# terminal 1 — from repo root
source .venv/bin/activate
pip install -e ".[api]"
aeios serve --port 8080
```

## Dev

```bash
cd apps/web
cp .env.example .env.local   # if needed
npm install
npm run dev
```

Open http://localhost:3000

## Pages

| Route | Purpose |
|-------|---------|
| `/` | Kernel status + run goal + recent tasks |
| `/tasks` | Task history |
| `/tasks/[id]` | Task detail |
| `/assistant` | Chat UI over kernel tasks |
| `/projects` | Simple project CRUD |
| `/pipelines` | Create / list multi-step workflows |
| `/pipelines/[id]` | Run pipeline + run history |

## Env

- `AEIOS_API_URL` / `NEXT_PUBLIC_AEIOS_API_URL` — default `http://127.0.0.1:8080`
