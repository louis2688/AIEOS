# AEIOS Auth (Clerk)

The Next.js dashboard and the FastAPI control plane are protected with [Clerk](https://clerk.com).

## Setup

1. Create an application at https://dashboard.clerk.com  
2. Copy **Publishable key** and **Secret key**  
3. In Clerk → **API Keys**, note your **Frontend API** URL (issuer), e.g. `https://verb-noun-00.clerk.accounts.dev`  
4. In `apps/web/.env.local`:

```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/
AEIOS_API_URL=http://127.0.0.1:8080
NEXT_PUBLIC_AEIOS_API_URL=http://127.0.0.1:8080
```

5. In the repo root `.env` (for `aeios serve`):

```env
# Enable API JWT checks (leave AEIOS_AUTH_DISABLED unset/false)
CLERK_ISSUER=https://verb-noun-00.clerk.accounts.dev
# Optional — defaults to {CLERK_ISSUER}/.well-known/jwks.json
# CLERK_JWKS_URL=https://verb-noun-00.clerk.accounts.dev/.well-known/jwks.json
# Optional audience check (usually leave unset for Clerk session tokens)
# CLERK_AUDIENCE=
```

6. In the Clerk dashboard → **Paths**, set sign-in/sign-up to `/sign-in` and `/sign-up`  
7. Restart `aeios serve` and `npm run dev`

## What is protected

| Layer | Behavior |
|-------|----------|
| Dashboard routes | Redirect to `/sign-in` via `src/proxy.ts` |
| Server actions | Require signed-in user (`requireUser`) |
| Server → API calls | Forward Clerk session JWT (`Authorization: Bearer`) from `apps/web/src/lib/aeios.ts` |
| FastAPI `/v1/*` (incl. `/v1/metrics`) | Validate Clerk JWT when auth is enabled |
| `/health` | Always public (no JWT) |
| Sign-in / sign-up | Public |

## Enabling / disabling API auth

| Mode | How | Use when |
|------|-----|----------|
| **Enabled** | Set `CLERK_ISSUER` and/or `CLERK_JWKS_URL`; do **not** set `AEIOS_AUTH_DISABLED` | Dashboard + staging / shared hosts |
| **Disabled (escape hatch)** | `AEIOS_AUTH_DISABLED=1` | CLI smoke tests, pytest, local kernel-only work |
| **Disabled (default local)** | Leave both Clerk JWKS/issuer unset | Same as escape hatch — no Bearer required |

When auth is enabled, requests without a valid Bearer token receive `401`. `/health` stays open.

Pytest sets `AEIOS_AUTH_DISABLED=1` in `tests/conftest.py` so existing API tests keep working. Dedicated auth tests override that and exercise reject/accept paths.

## Per-user data isolation (Phase 4)

Projects, pipelines, tasks, and model library rows are scoped to an **owner id**:

| Mode | `owner_id` value | Source |
|------|------------------|--------|
| Auth enabled | Clerk JWT `sub` | Set on `request.state.user_id` by `ClerkAuthMiddleware` |
| Auth disabled | `"local"` | Fixed escape-hatch owner for CLI / pytest |

- **Create** stamps `owner_id` from the request.
- **List / get / delete / cancel** filter by that owner (cross-user access returns `404`, not the other user's row).
- Pipeline runs inherit isolation via a join on the parent pipeline's `owner_id`.
- Schema: `owner_id TEXT NOT NULL DEFAULT 'local'` on `projects`, `pipelines`, `tasks`, and `models`. Existing SQLite/Postgres DBs get an additive `ALTER TABLE … ADD COLUMN` on store init (`SqlDb.ensure_column`).
- Memory / knowledge vectors are only partially owner-scoped (shared lexical/vector hits may still cross users until hardening lands).

## Run

```bash
# terminal 1 — API (auth on when CLERK_ISSUER is set)
# Windows PowerShell: .\.venv\Scripts\activate
source .venv/bin/activate
aeios serve --port 8080

# terminal 2 — dashboard
cd apps/web
npm run dev
```

Open http://localhost:3000 — you should be prompted to sign in. Server components and actions send the session JWT to FastAPI.

### Local API without Clerk

```bash
# PowerShell
$env:AEIOS_AUTH_DISABLED="1"
aeios serve --port 8080
```
