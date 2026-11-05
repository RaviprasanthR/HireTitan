# HireTitan: one image for the API, the worker and the one-shot migration.

# --- 1. Build the SPA ---------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. The pinned career-ops job-board providers (research R1, R2) ----------
# Fetched by commit hash (tag career-ops-v1.38.0). Upstream ships no lockfile, so HireTitan's own
# backend/scanner/package-lock.json decides which packages are installed, and --ignore-scripts
# means no browser is ever downloaded.
FROM node:22-slim AS scanner
ARG CAREER_OPS_COMMIT=115bc9873e3d43e23883f3c8f16436617facc62c
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/career-ops
RUN git init -q . \
    && git remote add origin https://github.com/santifer/career-ops.git \
    && git fetch -q --depth 1 origin "$CAREER_OPS_COMMIT" \
    && git checkout -q FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$CAREER_OPS_COMMIT" \
    && echo "$CAREER_OPS_COMMIT" > PINNED_COMMIT \
    && rm -rf .git docs tests web dashboard examples interview-prep jds reports output \
        writing-samples fonts evals test-fixtures
COPY backend/scanner/package.json backend/scanner/package-lock.json /opt/scanner-deps/
RUN cd /opt/scanner-deps \
    && npm ci --omit=dev --ignore-scripts \
    && mv node_modules /opt/career-ops/node_modules

# --- 3. Backend + built SPA ---------------------------------------------------
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

# Node and the pinned providers for reading company job boards. career-ops is MIT licensed: its
# licence and copyright notice travel with it.
COPY --from=scanner /usr/local/bin/node /usr/local/bin/node
COPY --from=scanner /opt/career-ops /opt/career-ops
COPY --from=scanner /opt/career-ops/LICENSE /usr/share/doc/career-ops/LICENSE

ENV PATH="/app/backend/.venv/bin:$PATH" \
    HIRETITAN_FRONTEND_DIST=/app/frontend/dist \
    HIRETITAN_DATA_DIR=/data \
    HIRETITAN_CAREER_OPS_DIR=/opt/career-ops

RUN useradd --system --create-home hiretitan && mkdir /data && chown hiretitan /data
USER hiretitan
EXPOSE 8000
CMD ["python", "-m", "hiretitan.api_main"]
