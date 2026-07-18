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
