# HireTitan: one image for the API, the worker and the one-shot migration.

# --- 1. Build the SPA ---------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. Backend + built SPA ---------------------------------------------------
FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
RUN uv sync --frozen --no-dev --no-editable
COPY --from=frontend /build/dist /app/frontend/dist

ENV PATH="/app/backend/.venv/bin:$PATH" \
    HIRETITAN_FRONTEND_DIST=/app/frontend/dist \
    HIRETITAN_DATA_DIR=/data

RUN useradd --system --create-home hiretitan && mkdir /data && chown hiretitan /data
USER hiretitan
EXPOSE 8000
CMD ["python", "-m", "hiretitan.api_main"]
