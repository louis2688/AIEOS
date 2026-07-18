# AEIOS — AI Engineering Operating System

AEIOS is an OS-like control plane for AI engineering: a **kernel** that schedules agents, manages memory, and exposes tools — then a product surface (projects, pipelines, model library, knowledge base) on top.

**Strategy:** Kernel + CLI first → FastAPI control plane → Next.js dashboard.

## Quick start

```bash
cd /Users/louis/projects/AIEOS
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,api]"
# Optional: MCP bridge for external tools → pip install -e ".[mcp]"

# Smoke path (no API keys, no Docker required)
aeios doctor
aeios status
aeios run "hello"
aeios task list

# HTTP control plane
aeios serve --port 8080

# Dashboard (separate terminal)
cd apps/web && npm install && npm run dev
# → http://localhost:3000 (Clerk sign-in required — see docs/AUTH.md)
```

Auth setup: [docs/AUTH.md](docs/AUTH.md)

Staging deploy (API Docker + web on Vercel, auth required): [docs/DEPLOY.md](docs/DEPLOY.md)

Optional local infra (Postgres, Qdrant, MinIO):

```bash
docker compose up -d
cp .env.example .env
```

Set `OPENAI_API_KEY` to enable the optional LLM planner (deterministic planner is default).

## Layout

```text
AIEOS/
├── src/aeios/          # Kernel package + CLI
│   ├── core/           # Kernel, scheduler, syscalls
│   ├── memory/         # Short-term + long-term memory
│   ├── agents/         # Base + specialized agents
│   ├── tools/          # Filesystem, shell, MCP bridge
│   └── cli.py
├── apps/               # Future: api (FastAPI), web (Next.js)
├── configs/            # Runtime YAML
├── docs/               # Vision, architecture, roadmap
├── tests/
├── Dockerfile                 # Staging API image (auth required)
├── docker-compose.yml         # Optional local Postgres/Qdrant/MinIO
└── docker-compose.staging.yml # Staging API (Clerk JWT required)
```

## Docs

- [Vision](docs/VISION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [MVP](docs/MVP.md)
- [Roadmap](docs/ROADMAP.md)
- [Auth](docs/AUTH.md)
- [Deploy (staging)](docs/DEPLOY.md)
- [Security](docs/SECURITY.md)

## Phase status

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Foundation + hello path | Done |
| 1 | Kernel MVP (SQLite, shell, API, doctor) | Done |
| 2 | Product surface (dashboard + auth + models) | Done |
| 3 | Hardening (security, MCP, observability) | Later |

## License

MIT
