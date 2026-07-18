# AEIOS Threat Model (local-first)

Short security model for the Phase 3 hardening baseline (sandbox + secrets hygiene shipped; RBAC deferred), plus Phase 4 per-user row isolation for projects/pipelines/tasks/models. AEIOS remains primarily a local control plane; multi-tenant isolation applies when the FastAPI layer is shared behind Clerk.

## Trust boundaries

```text
┌──────────────┐     Bearer JWT (Clerk)      ┌──────────────┐
│ Next.js UI   │ ──────────────────────────► │ FastAPI      │
│ (Clerk)      │                             │ aeios serve  │
└──────────────┘                             └──────┬───────┘
                                                    │ syscalls
                                             ┌──────▼───────┐
                                             │ Kernel       │
                                             │ agents/tools │
                                             └──────┬───────┘
                                    ┌───────────────┼───────────────┐
                                    ▼               ▼               ▼
                               SQLite          Shell jail      Provider APIs
                           (sealed keys)     (cwd + allowlist)  (OpenAI/…)
```

| Actor | Can do | Must not |
|-------|--------|----------|
| Local CLI user | Full kernel/syscalls on their machine | Assumed trusted for that workspace |
| Dashboard user (Clerk) | Call API only after JWT validation (when auth enabled) | Bypass shell jail or read raw keys from API |
| Agent / planner | `call_tool` / memory via syscalls only | Direct subprocess, filesystem outside tools, or raw DB access |
| Unauthenticated HTTP client | Nothing when Clerk JWT is required; localhost escape hatch via `AEIOS_AUTH_DISABLED` / missing JWKS for local pytest | Reach staging/production API |

API authentication lives in the FastAPI layer (`aeios.api`); the kernel does not implement RBAC. See [`AUTH.md`](AUTH.md) for Clerk setup.

## Who can call syscalls

- **CLI** and **FastAPI** construct a `Kernel` and invoke `Syscalls` (`execute_task`, `call_tool`, `request_memory`, …).
- Agents never import tools or open sockets directly — they go through `kernel.call_tool` / planner clients.
- There is no remote agent protocol yet; anyone who can run `aeios` or hit an open API has syscall power for that process/workspace.

## Shell sandbox

Implemented in `aeios.tools.shell.ShellTool`:

1. **Allowlist** — only named binaries (e.g. `ls`, `cat`, `rg`, `python`/`py`, `git`, …). Windows executable suffixes (`.exe`, …) are normalized before matching.
2. **Read-only git** — `SAFE_GIT` subcommands only (`status`, `log`, `diff`, …). Write operations (`push`, `commit`, …) are denied. Path-escaping flags (`-C`, `--git-dir`, `--work-tree`) are denied.
3. **Path jail** — path-like arguments (absolute, `..`, `/` or `\`) must resolve under the workspace root (`Path.relative_to`).
4. **cwd** — subprocess runs with `cwd=workspace`.
5. **Timeout** — default 15s.

### Windows DX

- Prefer allowlisted cross-platform binaries already used by the kernel (`python` / `py`, `git`, `rg` if installed).
- **Not allowlisted:** `cmd`, `powershell`, or builtins like `dir` / `type` — they need `cmd /c` and would widen the jail. Use Git Bash/WSL `ls`/`cat`, or a short `python -c` / filesystem tool instead.
- `where` / `which` are allowlisted for locating binaries (no write).

## Model API key storage

| Mode | Behavior |
|------|----------|
| Env override | If a model row has no key, `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` are used at call time (`resolve_api_key`). `seed_from_env` creates library rows **without** copying keys into SQLite. |
| Encrypt-at-rest | Set `AEIOS_SECRETS_KEY`. Keys submitted via the API are sealed (`enc:v1:…`) before INSERT/UPDATE. |
| Without secrets key | Persisting a raw `api_key` is rejected — use env vars or set `AEIOS_SECRETS_KEY`. |
| API responses | Never include raw keys — only `api_key_set` and `api_key_masked` (or `env:OPENAI_API_KEY`). |

Legacy plaintext rows (if any) remain readable until updated; new writes with `AEIOS_SECRETS_KEY` are sealed.

## API auth (note)

Clerk JWT validation lives in FastAPI (`aeios.api.auth`). Do not duplicate auth logic inside the kernel or model store. Local escape hatch: disable or omit JWKS for CLI/pytest. Staging must require auth — see [`DEPLOY.md`](DEPLOY.md).

## Multi-tenant row isolation (Phase 4)

When the API is shared across Clerk users, **projects**, **pipelines**, **tasks**, and **models** rows carry `owner_id` (= JWT `sub`). List/get/delete/cancel and pipeline-run access are filtered by that owner so users cannot read or mutate each other's data. Memory and knowledge vectors are only partially isolated. With `AEIOS_AUTH_DISABLED` (or no Clerk config), every request uses the fixed owner `"local"` so local pytest/CLI stay single-tenant. Details: [`AUTH.md`](AUTH.md#per-user-data-isolation-phase-4).

## Observability (MVP)

- Correlation: every response includes `X-Request-ID` (client-supplied or server-generated).
- Metrics: process counters at `GET /v1/metrics` (LLM tokens/calls, tool/task counts). Protected by the same Clerk JWT middleware as other `/v1/*` routes; `/health` stays public.
- Cost figures are rough placeholders, not provider invoices. Full OpenTelemetry is out of scope for this MVP.

## Residual risks

- Local process compromise ⇒ full workspace + decrypted keys in memory.
- Shell allowlist is not a full OS sandbox (no seccomp/containers).
- `AEIOS_SECRETS_KEY` in `.env` is only as safe as the host filesystem.
- Open FastAPI without JWT is acceptable only on localhost for development.
- Metrics are process-local and reset on restart — fine for local ops, not a multi-instance store.
