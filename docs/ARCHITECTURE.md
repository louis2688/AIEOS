# Architecture outline

**Goal:** design the pipeline module

## Modules

- `agents`
- `api`
- `apps`
- `configs`
- `docs`
- `kernel`
- `memory`
- `src`
- `tests`
- `tools`
- `web`

## Plan

1. Clarify constraints and success criteria
2. Inspect workspace module boundaries
3. Propose module boundaries
4. List risks and open questions
5. Write short ARCHITECTURE.md in workspace jail

## Recommendation

Keep CLI/kernel local-first; defer GraphQL/K8s.

## Observations

- workspace modules: apps, configs, docs, src, tests
