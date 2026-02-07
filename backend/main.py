import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from backend.config import settings
from backend.database import engine
from backend.exceptions import register_exception_handlers
from backend.routers import accounts, audit, auth, jobs, roles
from backend.schemas.common import HealthResponse

logger = logging.getLogger(__name__)

VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify DB connectivity
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Database connection verified")
    yield
    # Shutdown: dispose engine
    await engine.dispose()
    logger.info("Database engine disposed")


app = FastAPI(
    title=settings.app_name,
    version=VERSION,
    lifespan=lifespan,
)

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
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
