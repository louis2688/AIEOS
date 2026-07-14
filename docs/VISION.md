# AEIOS Vision

## One-liner

**AEIOS** is the AI Engineering Operating System — a control plane that orchestrates agents, memory, and tools so engineering work can be planned, executed, verified, and remembered.

## Problem

AI coding tools are powerful but fragmented:

- Context resets between sessions
- Agents don't share a common runtime contract
- Tools, models, and workflows are wired ad hoc per project
- There is no durable "OS" layer for AI engineering work

## Solution

Treat AI engineering like an operating system:

| OS concept | AEIOS concept |
|------------|---------------|
| Kernel | Orchestration, scheduling, lifecycle |
| Processes | Agents |
| Syscalls | `execute_task`, `request_memory`, `call_tool` |
| Drivers | Model providers + tool adapters (+ MCP later) |
| Filesystem / VFS | Project knowledge + memory store |
| Shell | CLI now; API + dashboard later |

## Principles

1. **Kernel before UI** — prove plan → act → observe before building product chrome
2. **Local-first** — useful on a laptop without cloud infra
3. **Pluggable drivers** — models and tools are adapters, not hard-coded cores
4. **Memory is first-class** — short-term context + long-term retrieval
5. **Observable by default** — every task leaves an audit trail
6. **YAGNI on infra** — Compose before Kubernetes; REST before GraphQL

## Non-goals (for now)

- Competing with academic AIOS research kernels
- Replacing Cursor / Claude Code as the editor
- Full multi-tenant SaaS in Phase 0–1
- Rewriting hot paths in Rust before Python proves the model

## Success definition (90 days)

A developer can:

1. Install AEIOS locally
2. Create a project
3. Run a multi-step agent pipeline against a repo
4. Search what was decided and done
5. See the same flow in a basic web dashboard
