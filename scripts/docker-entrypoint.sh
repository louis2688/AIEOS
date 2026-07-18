#!/bin/sh
# Fail closed: refuse to start an API container without Clerk JWT config.
set -eu

disabled="$(printf '%s' "${AEIOS_AUTH_DISABLED:-}" | tr '[:upper:]' '[:lower:]')"
case "$disabled" in
  1|true|yes|on)
    echo "error: AEIOS_AUTH_DISABLED is set — refusing to start staging API" >&2
    echo "Unset AEIOS_AUTH_DISABLED and configure CLERK_ISSUER or CLERK_JWKS_URL." >&2
    exit 1
    ;;
esac

if [ -z "${CLERK_ISSUER:-}" ] && [ -z "${CLERK_JWKS_URL:-}" ]; then
  echo "error: Clerk JWT not configured — refusing to start staging API" >&2
  echo "Set CLERK_ISSUER (preferred) and/or CLERK_JWKS_URL. See docs/DEPLOY.md." >&2
  exit 1
fi

mkdir -p /app/data
if [ "$(id -u)" -eq 0 ]; then
  chown -R aeios:aeios /app/data
  exec setpriv --reuid=aeios --regid=aeios --init-groups -- "$@"
fi

exec "$@"
