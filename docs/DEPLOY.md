# Staging deploy

Deploy AEIOS with **auth required** on the FastAPI control plane. Do not expose an unauthenticated API on a shared host.

| Component | Recommended path |
|-----------|------------------|
| API (`aeios serve`) | Docker image in this repo (`Dockerfile` + optional `docker-compose.staging.yml`) |
| Web (`apps/web`) | [Vercel](https://vercel.com) (or any Node host running `next start`) |

Details for Clerk setup: [`AUTH.md`](AUTH.md). Threat model: [`SECURITY.md`](SECURITY.md).

## Non-negotiable: staging auth

Staging (and any non-localhost shared host) **must**:

1. Leave `AEIOS_AUTH_DISABLED` **unset** / false.
2. Set `CLERK_ISSUER` and/or `CLERK_JWKS_URL` (same Clerk app as the dashboard).
3. Point the web app at the staging API URL and use the same Clerk keys.

Local-only escape hatches (`AEIOS_AUTH_DISABLED=1` or omitting Clerk JWKS) are for CLI/pytest — never for staging.

The API container **refuses to start** if `AEIOS_AUTH_DISABLED` is truthy or if both Clerk issuer and JWKS URL are missing (`scripts/docker-entrypoint.sh`).

## Staging checklist

- [ ] Clerk application created; note Frontend API URL (issuer)
- [ ] Staging API env: `CLERK_ISSUER` (and optional `CLERK_JWKS_URL`) set; **no** `AEIOS_AUTH_DISABLED`
- [ ] Staging web env: Clerk publishable + secret keys; `AEIOS_API_URL` / `NEXT_PUBLIC_AEIOS_API_URL` → staging API
- [ ] API `/health` returns 200 without a token
- [ ] API `/v1/*` returns 401 without `Authorization: Bearer`
- [ ] Signed-in dashboard can call the API (Bearer forwarded from Next.js)
- [ ] No secrets committed (use host env, Vercel env, or a local `.env.staging` that is gitignored)

## API: Docker

### Build and run (compose)

```bash
cp .env.staging.example .env.staging
# Edit .env.staging — set real CLERK_ISSUER; do not set AEIOS_AUTH_DISABLED

docker compose -f docker-compose.staging.yml --env-file .env.staging up --build
```

API listens on `http://localhost:8080` by default (`AEIOS_API_PORT` overrides the host port).

### Build and run (plain Docker)

```bash
docker build -t aeios-api:staging .

docker run --rm -p 8080:8080 \
  -e CLERK_ISSUER=https://your-app.clerk.accounts.dev \
  -e AEIOS_ENV=staging \
  -v aeios_staging_data:/app/data \
  aeios-api:staging
```

### Smoke checks

```bash
# Public
curl -sS http://127.0.0.1:8080/health

# Must be 401 when auth is on
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/v1/status
```

### Hosting notes

- Publish only port 8080 (or put TLS termination / reverse proxy in front).
- Persist `/app/data` if you use the default SQLite URL.
- Optional LLM keys (`OPENAI_API_KEY`, …) and `AEIOS_SECRETS_KEY` via env — never bake into the image.
- `/docs` and OpenAPI are currently public paths; restrict at the reverse proxy if you do not want them on the internet.

### Hosting on Render (free tier)

Repo root includes [`render.yaml`](../render.yaml) for:

- Docker Web Service `aeios-api` (health check `/health`)
- Render Postgres `aeios-db` (`plan: free`)
- `DATABASE_URL` synced from the DB via Blueprint `fromDatabase` → `connectionString` (internal URL)

The image installs `aeios[api,postgres]` so psycopg is available at runtime.

#### Persistence: SQLite (ephemeral) vs Postgres

| Backend | When | Durability on Render free web |
|---------|------|-------------------------------|
| SQLite (`sqlite:///./data/aeios.db`) | Local / Docker with a volume | **Ephemeral** — free Web Services have no disks; data is wiped on redeploy and spin-down |
| Postgres (`DATABASE_URL` from `aeios-db`) | Staging / production on Render | **Durable** across web redeploys (schema is create-if-not-exists) |

**Free Postgres caveat:** Render’s free Postgres instance type expires ~30 days after creation. For anything you need longer-term, upgrade the database plan in the dashboard (e.g. Basic / starter) or recreate and re-link `DATABASE_URL`.

#### Apply / re-apply the Blueprint

Render does not reliably provision new Blueprint resources from git push alone when the service already exists. Prefer the dashboard:

1. Sign in at [dashboard.render.com](https://dashboard.render.com).
2. **New → Blueprint** → connect `louis2688/AIEOS` (or your fork) → select the branch with the updated `render.yaml` → **Apply**.
   - If a Blueprint already tracks this repo: open the Blueprint → **Manual Deploy** / sync so it picks up `databases:` and the new `DATABASE_URL` `fromDatabase` binding.
3. Confirm resources: Postgres `aeios-db` and Web Service `aeios-api`.
4. On `aeios-api` → **Environment**: `DATABASE_URL` should be set from the database (not a hard-coded SQLite URL). Also confirm `CLERK_ISSUER`, `AEIOS_ENV=staging`. Leave `AEIOS_AUTH_DISABLED` unset.
5. Wait for a successful deploy, then note the public URL (e.g. `https://aeios-api.onrender.com`).
6. Point Vercel at that URL (from `apps/web`):

   ```bash
   printf '%s' 'https://aeios-api.onrender.com' | npx vercel env add AEIOS_API_URL production --force --yes
   printf '%s' 'https://aeios-api.onrender.com' | npx vercel env add NEXT_PUBLIC_AEIOS_API_URL production --force --yes
   npx vercel --prod --yes
   ```

7. Smoke checks:

   ```bash
   curl -sS https://aeios-api.onrender.com/health
   curl -sS -o /dev/null -w "%{http_code}\n" https://aeios-api.onrender.com/v1/status
   # expect 401
   ```

#### Manual fallback (no Blueprint re-apply)

If Blueprint sync cannot add the database (or you lack CLI/API access):

1. Dashboard → **New → Postgres** → name `aeios-db` → Free (or Basic) → create. Prefer **private network only** if the only client is `aeios-api` on Render.
2. Open `aeios-api` → **Environment** → set `DATABASE_URL` to the database’s **Internal Database URL** (Connect menu), or link the DB so Render injects it.
3. Remove any old `DATABASE_URL=sqlite:///./data/aeios.db` override.
4. **Manual Deploy** the web service so the image rebuilds with `.[api,postgres]` and picks up the new env.

CLI note: `render` CLI / Blueprint apply typically needs a logged-in account or API key (`render login`). There is no unauthenticated way to provision the DB from this repo alone.

## Live progress & artifacts

- Tasks / pipeline runs support `?wait=false` — returns immediately; poll `GET /v1/tasks/{id}` or `GET /v1/pipeline-runs/{id}` until `completed` / `failed` / `cancelled`.
- SSE: `GET /v1/tasks/{id}/events` streams task JSON until terminal; dashboard proxies via `/api/tasks/{id}/events`.
- Cancel: `POST /v1/tasks/{id}/cancel` (Assistant Cancel button).
- Tasks and models are scoped per Clerk `sub` (`owner_id`), same as projects/pipelines.
- `GET /v1/tasks/{id}/artifacts` merges durable DB rows with on-disk files. **Filesystem under `/app` on Render free is ephemeral**; artifact **content** is stored in Postgres/SQLite so it survives redeploy/sleep.

## Model library in production

1. In Render → `aeios-api` → Environment, set `AEIOS_SECRETS_KEY` (random secret) so model API keys can be stored encrypted.
2. Optionally set `OPENAI_API_KEY` as a planner fallback when no library default exists.
3. In the Vercel dashboard → **Models**, register a provider model, paste the key, **Set default**.
4. Confirm `GET /v1/status` shows `llm_planner: true` and `default_model` (authenticated).

## Ops hardening (Render)

Runbook for keeping staging alive on free-tier Render. Blueprint: [`render.yaml`](../render.yaml).

### Free Postgres expiry (~30 days)

Render’s **free** Postgres plan is temporary: instances expire about **30 days after creation**. After expiry the DB is deleted — `DATABASE_URL` breaks and the API cannot persist tasks/projects.

| Before expiry | Action |
|---------------|--------|
| ~7 days left | Decide: upgrade or accept recreate + data loss |
| Keep data | Dashboard → `aeios-db` → **Upgrade** to a paid plan (e.g. **Basic**) |
| Accept wipe | Create a new Postgres, re-link `DATABASE_URL` on `aeios-api`, redeploy |

Upgrade path (recommended for anything you dogfood longer than a month):

1. [dashboard.render.com](https://dashboard.render.com) → Postgres `aeios-db`.
2. Upgrade to **Basic** (or higher). Connection string usually stays valid; confirm `DATABASE_URL` on `aeios-api` still points at this instance.
3. Optional: change `plan: free` → `plan: basic` in `render.yaml` so future Blueprint applies match the paid DB (do this only after the dashboard upgrade).
4. Smoke: `GET /health` and a signed-in dashboard list of projects/tasks.

Do **not** put production secrets in git when upgrading — change plans and env only in the Render dashboard.

### Cold starts (free Web Service)

Free web services **spin down** after idle time. Expect:

- First request after sleep: often **~30–60s** (sometimes longer under load).
- Subsequent requests: normal latency until the next idle sleep.
- Health checks from Render itself can wake the service; external monitors that hit rarely will still see cold starts.

Mitigations (pick when staging pain is real):

- Upgrade the web service off the free plan (always-on).
- Or accept cold starts for dogfooding; retry once if the dashboard times out on the first call after a long idle.
- Optional **keep-alive ping**: schedule an external cron (GitHub Actions, cron-job.org, UptimeRobot) to `GET /health` every **10–14 minutes**. This reduces sleep on free tier but is not guaranteed forever — Render may still throttle. Prefer upgrading the web plan if always-on matters.

Example GitHub Actions keep-alive (optional; store host as a repo variable):

```yaml
# .github/workflows/keepalive.yml
name: keepalive-api
on:
  schedule:
    - cron: "*/12 * * * *"
  workflow_dispatch:
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - run: curl -fsS -o /dev/null -w "%{http_code}\n" "${{ vars.AEIOS_API_HEALTH_URL }}"
```

Set `AEIOS_API_HEALTH_URL` to `https://aeios-api.onrender.com/health` (or your host).

### Healthcheck URL

| Check | URL | Expected |
|-------|-----|----------|
| Liveness (public) | `https://<aeios-api-host>/health` | `200` JSON, no auth |
| Auth gate | `https://<aeios-api-host>/v1/status` | `401` without Bearer |

Render Blueprint sets `healthCheckPath: /health` (see `render.yaml`). Use the same `/health` URL for any external uptime ping.

```bash
# Replace host with your service URL
curl -sS -o /dev/null -w "%{http_code}\n" https://aeios-api.onrender.com/health
# expect 200
```

### What to monitor

| Signal | Where | Why |
|--------|--------|-----|
| Deploy success / failed builds | Render → `aeios-api` → Events / Logs | Image or entrypoint regressions (auth refuse, missing deps) |
| `/health` uptime + latency | Render health check + optional external ping | Distinguishes cold start vs real outage |
| Postgres status / expiry date | Render → `aeios-db` | Free-tier clock; upgrade before delete |
| `DATABASE_URL` present | `aeios-api` → Environment | Drift after DB recreate |
| Auth misconfig | Logs at boot; `/v1/*` → 401 | Missing `CLERK_ISSUER` or accidental `AEIOS_AUTH_DISABLED` |
| Dashboard → API errors | Vercel logs + browser network | Wrong `AEIOS_API_URL` / CORS / cold-start timeouts |
| Disk / SQLite | N/A on free web | Never rely on SQLite on Render free (ephemeral) |

Optional: hit `/v1/metrics` when signed in for process-local token/cost counters (resets on restart — not a multi-instance store).

### Operator checklist

- [ ] Note Postgres creation / expiry date; calendar reminder ~7 days before
- [ ] Plan Basic (or higher) upgrade if staging must outlive free expiry
- [ ] Bookmark health URL: `https://<host>/health`
- [ ] After any DB change: confirm `DATABASE_URL`, redeploy, smoke `/health` + dashboard
- [ ] Expect ~30–60s cold start on free web after idle; upgrade web plan if always-on is required
- [ ] Never commit Render/Clerk/LLM secrets; set optional keys only in the dashboard

## Web: Vercel (recommended)

1. Import the repo; set root directory to `apps/web`.
2. Configure env (Production / Preview as appropriate):

| Variable | Value |
|----------|--------|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk publishable key |
| `CLERK_SECRET_KEY` | Clerk secret key |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL` | `/sign-in` |
| `NEXT_PUBLIC_CLERK_SIGN_UP_URL` | `/sign-up` |
| `NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL` | `/` |
| `NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL` | `/` |
| `AEIOS_API_URL` | Staging API base URL (server-side), e.g. `https://api.staging.example.com` |
| `NEXT_PUBLIC_AEIOS_API_URL` | Same URL if the browser needs it |

3. In Clerk, allow the Vercel deployment URL as an authorized origin / redirect.
4. Deploy. The dashboard forwards the Clerk session JWT to FastAPI as `Authorization: Bearer`.

### Web: container alternative

If you prefer a container instead of Vercel:

```bash
cd apps/web
# Build with Clerk + API URL build args / runtime env as required by Next.js
npm ci && npm run build && npm run start -- --hostname 0.0.0.0 --port 3000
```

Point `AEIOS_API_URL` at the staging API. Do not run the web UI against an auth-disabled API on a shared network.

## Example topology

```text
Browser ──HTTPS──► Vercel (apps/web + Clerk)
                      │ Bearer JWT
                      ▼
               Host / VM (Docker aeios-api:staging)
               CLERK_ISSUER set, AEIOS_AUTH_DISABLED unset
```

## What not to do

- Do not ship `.env` / `.env.staging` with real secrets in git.
- Do not set `AEIOS_AUTH_DISABLED=1` in staging compose or host env.
- Do not bind a bare `aeios serve` on `0.0.0.0` without Clerk JWT config.
