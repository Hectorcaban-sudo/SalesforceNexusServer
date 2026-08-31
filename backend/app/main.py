import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import settings
from .logging_config import setup_logging, log_event
from .auth import bootstrap_default_admin
from .database import flush
from .broker import broker
from .worker import inbound_worker, outbound_publisher
from .cometd_client import cometd_manager
from .tracing import setup_tracing
from .routers import auth as auth_router
from .routers import orgs as orgs_router
from .routers import events as events_router
from .routers import transactions as transactions_router
from .routers import logs as logs_router
from .routers import dashboard as dashboard_router
from .routers import admin_config as admin_config_router
from .routers import users as users_router
from .routers import integrations as integrations_router

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"

background_tasks = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = setup_logging()
    bootstrap_default_admin()
    log_event("info", f"{settings.app_name} starting up")

    background_tasks.append(asyncio.create_task(inbound_worker()))
    background_tasks.append(asyncio.create_task(outbound_publisher()))
    await cometd_manager.sync()

    log_event("info", f"{settings.app_name} startup complete")
    yield

    log_event("info", f"{settings.app_name} shutting down")
    await cometd_manager.stop_all()
    for t in background_tasks:
        t.cancel()
    flush()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Logging + tracing instrumentation must happen before the app starts (OTel's
# FastAPI instrumentor adds middleware, which Starlette forbids once the
# lifespan has begun) - setup_logging() is idempotent so it's safe to call
# again inside lifespan() above too.
setup_logging()
setup_tracing(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(orgs_router.router)
app.include_router(events_router.router)
app.include_router(transactions_router.router)
app.include_router(logs_router.router)
app.include_router(dashboard_router.router)
app.include_router(admin_config_router.router)
app.include_router(users_router.router)
app.include_router(integrations_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name}


# ---- Serve the built React admin interface ----
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
