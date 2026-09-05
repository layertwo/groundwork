FROM node:24-slim AS frontend

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.14-slim-trixie AS builder

# Copy uv binary from the official image (faster than `pip install uv`)
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

WORKDIR /app

# Bytecompile installed packages, copy (not hardlink) into the layer, and skip
# the download/build cache so it doesn't bloat the venv we carry forward.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock README.md ./

# Install third-party deps first against just the lockfile so this layer
# stays cached across pure src/ changes. --no-install-project skips
# building our own package (which needs src/ to be present).
RUN uv sync --frozen --no-dev --no-editable --no-install-project

COPY backend/ backend/
COPY alembic/ alembic/

# Final sync builds + installs the project itself. Cheap because every
# dependency is already present from the layer above.
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14-slim-trixie AS runtime

WORKDIR /app
ENV PYTHONPATH=/app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY alembic.ini .
COPY --from=frontend /app/frontend/dist frontend/dist
COPY entrypoint.sh .

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
