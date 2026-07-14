# AEIOS — AI Engineering Operating System

AEIOS is an OS-like control plane for AI engineering: a **kernel** that schedules agents, manages memory, and exposes tools — then a product surface (projects, pipelines, model library, knowledge base) on top.

**Strategy:** Kernel + CLI first → FastAPI control plane → Next.js dashboard.

## Quick start

```bash
cd /Users/louis/projects/AIEOS
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Smoke path (no API keys, no Docker required)
aeios status
aeios run "hello"
```

Optional local infra (Postgres, Qdrant, MinIO):

```bash
docker compose up -d
cp .env.example .env
```

## Layout

```text
AIEOS/
├── src/aeios/          # Kernel package + CLI
│   ├── core/           # Kernel, scheduler, syscalls
│   ├── memory/         # Short-term + long-term memory
│   ├── agents/         # Base + specialized agents
│   ├── tools/          # Filesystem, shell, HTTP
│   └── cli.py
├── apps/               # Future: api (FastAPI), web (Next.js)
├── configs/            # Runtime YAML
├── docs/               # Vision, architecture, roadmap
├── tests/
└── docker-compose.yml
```

## Docs

- [Vision](docs/VISION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [MVP](docs/MVP.md)
- [Roadmap](docs/ROADMAP.md)

## Phase status

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Foundation + hello path | In progress |
| 1 | Kernel MVP (scheduler, memory, agents, tools) | Next |
| 2 | Product surface (Next.js + projects/pipelines) | Later |
| 3 | Hardening (security, MCP, observability) | Later |

## License

MIT
