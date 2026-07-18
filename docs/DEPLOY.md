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

**Cold starts:** free Web Services sleep after inactivity; the first request after sleep can take ~30–60s.

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
