# ---- Stage 1: build the Next.js static site ----
FROM node:22-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: slim Python runtime with uv ----
FROM python:3.12-slim AS backend
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY backend/ .
RUN uv sync --frozen --no-dev

COPY --from=frontend-build /frontend/out ./app/static

COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown -R app:app /app /data

USER app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"

ENTRYPOINT ["/entrypoint.sh"]
