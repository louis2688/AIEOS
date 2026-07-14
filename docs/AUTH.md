# AEIOS Auth (Clerk)

The Next.js dashboard is protected with [Clerk](https://clerk.com).

## Setup

1. Create an application at https://dashboard.clerk.com  
2. Copy **Publishable key** and **Secret key**  
3. In `apps/web/.env.local`:

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

4. In the Clerk dashboard → **Paths**, set sign-in/sign-up to `/sign-in` and `/sign-up`  
5. Restart `npm run dev`

## What is protected

| Layer | Behavior |
|-------|----------|
| Dashboard routes | Redirect to `/sign-in` via `src/proxy.ts` |
| Server actions | Require signed-in user (`requireUser`) |
| Sign-in / sign-up | Public |

## Not yet protected

The FastAPI kernel (`aeios serve`) remains open on localhost for local development. Protecting it with Clerk JWTs is a follow-up.

## Run

```bash
# terminal 1
source .venv/bin/activate
aeios serve --port 8080

# terminal 2
cd apps/web
npm run dev
```

Open http://localhost:3000 — you should be prompted to sign in.
