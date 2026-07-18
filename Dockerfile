# AEIOS FastAPI control plane — staging / shared-host image.
# Auth is required at runtime: set CLERK_ISSUER or CLERK_JWKS_URL and do not
# set AEIOS_AUTH_DISABLED. See docs/DEPLOY.md.

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AEIOS_ENV=staging \
    DATABASE_URL=sqlite:///./data/aeios.db

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin aeios \
    && mkdir -p /app/data \
    && chown -R aeios:aeios /app

COPY pyproject.toml README.md ./
COPY configs ./configs
COPY src ./src
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN pip install --upgrade pip \
    && pip install ".[api,postgres]" \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

# Entrypoint starts as root to fix volume ownership, then drops to uid 10001.
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["aeios", "serve", "--host", "0.0.0.0", "--port", "8080"]
