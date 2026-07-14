# Phase 2 Product Surface Implementation Plan

**Goal:** Ship a thin Next.js dashboard over the AEIOS kernel API: status, run task, task history, assistant chat, and basic projects.

**Architecture:** `apps/web` (Next.js App Router) talks to FastAPI via server-side fetch (`AEIOS_API_URL`). FastAPI gains CORS + a simple projects store. Auth (Clerk) deferred until the dashboard loop works.

**Tech Stack:** Next.js 15, TypeScript, Tailwind CSS, FastAPI, SQLite projects table.

---

### Task 1: Scaffold web app
- [x] `create-next-app` in `apps/web`
- [x] Env: `AEIOS_API_URL=http://127.0.0.1:8080`

### Task 2: API additions
- [x] CORS middleware
- [x] Projects CRUD (SQLite)
- [x] Wire into shared `data/aeios.db`

### Task 3: Dashboard UI
- [x] Shell layout + nav
- [x] Home: kernel status + run goal
- [x] Tasks list + detail
- [x] Assistant chat panel
- [x] Projects list/create

### Task 4: Docs + verify
- [x] README scripts, ROADMAP Phase 2 progress
- [x] `npm run build` + API smoke
