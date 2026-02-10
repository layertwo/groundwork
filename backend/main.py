import asyncio
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import settings
from backend.database import async_session_factory, engine
from backend.exceptions import register_exception_handlers
from backend.models.job import Job
from backend.models.user import User
from backend.routers import accounts, audit, auth, events, jobs, roles
from backend.schemas.common import HealthResponse
from backend.services.aws import ensure_bootstrap_stackset
from backend.services.jobs import execute_job, recover_stale_jobs, verify_account_bootstraps

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


VERSION = "0.1.0"

BANNER = """
   ╔═══════════╗   ___                     _                 _
   ║           ║  / __|_ _ ___ _  _ _ _  __| |_ __ _____ _ _| |__
   ╠═══════════╣ | (_ | '_/ _ \\ || | ' \\/ _` \\ V  V / _ \\ '_| / /
   ╠═══════════╣  \\___|_| \\___/\\_,_|_||_\\__,_|\\_/\\_/\\___/_| |_\\_\\
   ╚═══════════╝
"""


SYSTEM_USER_SUB = "system:scheduler"


async def _get_or_create_system_user() -> uuid.UUID:
    """Ensure a system user exists for scheduler-initiated jobs."""
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.sub == SYSTEM_USER_SUB))
        user = result.scalar_one_or_none()
        if user is not None:
            return user.id
        user = User(
            sub=SYSTEM_USER_SUB,
            email="system@groundwork.local",
            display_name="System Scheduler",
            groups=[],
            is_admin=True,
        )
        db.add(user)
        await db.commit()
        return user.id


async def _run_scheduled_sync(system_user_id: uuid.UUID) -> None:
    """Create and execute a sync_accounts job if one is not already running."""
    async with async_session_factory() as db:
        existing = await db.execute(
            select(Job).where(
                Job.job_type == "sync_accounts",
                Job.status.in_(["pending", "in_progress"]),
            )
        )
        if existing.scalar_one_or_none() is not None:
            logger.info("Skipping scheduled sync — one is already running")
            return

        job = Job(
            job_type="sync_accounts",
            status="pending",
            started_by=system_user_id,
        )
        db.add(job)
        await db.commit()
        logger.info("Scheduled sync_accounts job %s", job.id)

    await execute_job(job.id)


async def _sync_scheduler(app: FastAPI) -> None:
    """Background loop that runs sync_accounts on a configurable interval."""
    interval = settings.sync_interval_minutes * 60
    try:
        system_user_id = await _get_or_create_system_user()
        # Initial sync after short startup delay
        await asyncio.sleep(30)
        while True:
            try:
                await _run_scheduled_sync(system_user_id)
            except Exception:
                logger.exception("Scheduled sync failed")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("Sync scheduler shutting down")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(BANNER)
    # Validate session secret is not the default in non-debug mode
    if not settings.debug and settings.session_secret == "change-me-to-a-random-string":
        raise RuntimeError("GW_SESSION_SECRET must be set to a secure random value in production")
    # Startup: verify DB connectivity
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Database connection verified")

    # Ensure bootstrap StackSet is created/updated with latest template
    if settings.aws_groundwork_account_id:
        await ensure_bootstrap_stackset()
        repairs = await verify_account_bootstraps(app.state.background_tasks)
        if repairs:
            logger.info("Scheduled %d bootstrap repair(s)", repairs)
    # Recover orphaned jobs from a previous server lifecycle
    recovered = await recover_stale_jobs(app.state.background_tasks)
    if recovered:
        logger.info("Recovered %d stale job(s)", recovered)

    # Start sync scheduler if configured
    scheduler_task = None
    if settings.sync_interval_minutes > 0:
        scheduler_task = asyncio.create_task(_sync_scheduler(app))
        app.state.background_tasks.add(scheduler_task)
        scheduler_task.add_done_callback(app.state.background_tasks.discard)
        logger.info("Sync scheduler started (interval=%dm)", settings.sync_interval_minutes)

    yield

    # Shutdown: cancel scheduler
    if scheduler_task is not None:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
    # Shutdown: dispose engine
    await engine.dispose()
    logger.info("Database engine disposed")


app = FastAPI(
    title=settings.app_name,
    version=VERSION,
    lifespan=lifespan,
)

# Set for retaining references to background tasks (prevents GC of in-flight tasks)
app.state.background_tasks = set()

# CSRF protection: require X-Requested-With header on mutating API requests.
# Browsers will not send custom headers cross-origin without CORS preflight,
# so this blocks cross-site form/fetch attacks on cookie-authenticated endpoints.
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT_PATHS = {"/api/auth/callback"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if (
            request.url.path.startswith("/api/")
            and request.method not in CSRF_SAFE_METHODS
            and request.url.path not in CSRF_EXEMPT_PATHS
            and "x-requested-with" not in request.headers
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "Missing X-Requested-With header"},
            )
        return await call_next(request)


app.add_middleware(CSRFMiddleware)

# Exception handlers
register_exception_handlers(app)

# CORS for Vite dev server in debug mode
if settings.debug:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Routers
app.include_router(accounts.router)
app.include_router(auth.router)
app.include_router(roles.router)
app.include_router(jobs.router)
app.include_router(audit.router)
app.include_router(events.router)


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    return HealthResponse(status="ok", version=VERSION, database=db_status)


# Serve frontend static files if built
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    # Serve Vite hashed assets at /assets
    assets_dir = frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    # SPA catch-all: return index.html for any non-API GET request.
    # All /api/* routers are registered above, so they take priority.
    index_html = frontend_dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        return FileResponse(str(index_html))
