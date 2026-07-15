# AEIOS MVP

## Product MVP (Phase 2 surface)

From the ChatGPT product design thread:

| Feature | Description | Depends on |
|---------|-------------|------------|
| User profiles | Auth + identity (Clerk) | API + web |
| Projects | Workspace containers for engineering work | Kernel + DB |
| Pipelines | Multi-step agent workflows | Kernel + scheduler |
| Model library | Provider/model registry (OpenAI / Anthropic / Ollama) | Drivers — **shipped** |
| Knowledge base | Searchable project memory / docs | Memory + Qdrant |
| Assistant engine | Chat UI wired to kernel | API + web |

## Kernel MVP (Phase 0–1 — build this first)

Must work offline with no API keys:

1. `aeios status` — show kernel health + registered agents/tools
2. `aeios run "<goal>"` — plan → act → observe loop
3. At least one agent (`EchoAgent` / `SoftwareEngineer` stub)
4. At least two tools (`echo`, `filesystem.read`)
5. Task log persisted locally
6. Unit tests for kernel dispatch + memory

LLM-backed planning is **optional** until keys exist; Phase 0 uses a deterministic planner.

## Explicitly out of MVP

- Kubernetes
- GraphQL (start with REST/JSON)
- gRPC service mesh
- Plugin marketplace
- Rust rewrites
- Full self-healing production loops
