# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands require `PYTHONPATH=/Users/lucas/groundwork` (or `PYTHONPATH=.` from repo root) and an activated venv.

```bash
# Setup
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
docker compose up -d db

# Database migrations
PYTHONPATH=. alembic revision --autogenerate -m "description"
PYTHONPATH=. alembic upgrade head

# Run server
GW_DEBUG=true PYTHONPATH=. uvicorn backend.main:app --reload --reload-dir backend

# Tests (requires postgres running + migration applied)
PYTHONPATH=. pytest                                    # full suite (parallel, coverage)
PYTHONPATH=. pytest tests/unit/routers/test_auth.py    # single file
PYTHONPATH=. pytest -o "addopts=" tests/               # skip xdist/coverage for speed
PYTHONPATH=. pytest -k "test_create_user"              # single test by name

# Linting & formatting
black backend/ tests/ && isort backend/ tests/
flake8 backend/ tests/
mypy backend/ tests/
```

## Architecture

**Stack:** FastAPI + async SQLAlchemy 2.0 + asyncpg + PostgreSQL 16 + Alembic

**Config:** `backend/config.py` uses pydantic-settings with `GW_` env prefix, reads from `.env` file. All settings accessed via the `settings` singleton.

**Database layer:** `backend/database.py` exposes `engine` and `get_db()` FastAPI dependency that yields an async session with auto-commit on success, rollback on exception. Sessions use `expire_on_commit=False` to avoid MissingGreenlet errors.

**Models** inherit from `Base(AsyncAttrs, DeclarativeBase)` with two mixins:
- `UUIDPrimaryKeyMixin` — UUID PK with `gen_random_uuid()` server default
- `TimestampMixin` — `created_at`/`updated_at` with `func.now()` server defaults

All 6 models are re-exported from `backend/models/__init__.py` (required for Alembic autogenerate).

**Routers** are currently 501 stubs. Each returns `Response(status_code=501, content='{"detail":"Not implemented"}')`. Implementation is planned across 5 phases (see `docs/plans/`).

**Services** (planned): `backend/services/` will contain `oidc.py` (OIDC auth), `aws.py` (IAM/STS/Organizations), `jobs.py` (background task executor), `audit.py` (audit logging).

**Exception hierarchy:** `GroundworkError` base class with `NotFoundError(404)`, `ConflictError(409)`, `ForbiddenError(403)`. Handlers registered in `main.py` return `{"detail": message}`.

**Alembic** runs async via `async_engine_from_config` with `NullPool`. Imports `Base.metadata` from `backend.models`.

## Build Phases

Detailed plans in `docs/plans/`. Summary:

1. **Phase 1 -- Auth**: OIDC login flow, session management, `get_current_user`/`get_current_admin` dependencies, role templates model + CRUD, audit helper
2. **Phase 2 -- Account Provisioning**: Organizations account creation, OIDC provider + admin role bootstrap, job executor, account/job endpoints
3. **Phase 3 -- Role Management**: IAM role CRUD (create/update/delete), trust policies with aud+groups+users conditions, role templates
4. **Phase 4 -- Role Assumption**: `AssumeRoleWithWebIdentity`, console federation URLs, token refresh, dual-layer access control
5. **Phase 5 -- React UI**: Vite + React + TypeScript frontend, auth context, account/role/job pages

## Testing

Tests mirror the cortex repo pattern: `tests/unit/`, `tests/integration/`, `tests/property/` directories with fixtures in `tests/fixtures/`.

**DB test isolation:** `db_session` fixture wraps each test in a transaction that rolls back — safe for parallel xdist execution. Tables must exist (created by migration), they are not created/dropped per test.

**`client` fixture:** async httpx `AsyncClient` with `ASGITransport` for testing FastAPI endpoints without a running server.

**Coverage threshold:** 70% (schemas are defined but not yet exercised by tests).

## Development Workflow

These rules are mandatory for all code changes:

1. **Security review after every implementation.** After finishing a feature or set of changes, perform a security-focused code review before considering the work complete. Use the code-reviewer agent with a security focus covering auth, input validation, injection, information disclosure, and token/secret handling.
2. **All security findings must be resolved before pushing to a PR.** Do not push code with known security issues. Critical and high findings must be fixed immediately. Medium and lower findings must also be resolved — do not defer them.
3. **All integration and unit tests must pass.** Run the full test suite (`PYTHONPATH=. pytest`) and confirm all tests pass before committing. If a test fails, fix the implementation — never edit a test to make it pass.
4. **Run linting and formatting before every commit.** Run `black backend/ tests/ && isort backend/ tests/` to auto-format, then run `flake8 backend/ tests/` and fix all reported issues. Code must be clean of lint errors before committing.

## Conventions

- Line length: 100 (black/isort/flake8)
- asyncio_mode: auto (no need for `@pytest.mark.asyncio`)
- Test classes group related tests (e.g., `class TestAccountRoutes`)
- CORS enabled only in debug mode (for Vite dev server at localhost:5173)
- Frontend static files served from `frontend/dist/` if that directory exists
