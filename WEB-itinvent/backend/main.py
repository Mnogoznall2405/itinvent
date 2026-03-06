"""
Main FastAPI application entry point.
"""
import sys
import os
from pathlib import Path

# Add parent directory to path for bot imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import config
from backend.api.v1 import auth, equipment, database, json_operations, settings, networks, discovery, inventory, kb, mfu, hub, mail, ad_users, vcs
from backend.services.ad_sync_service import background_ad_sync_loop
from backend.services.mfu_monitor_service import mfu_runtime_monitor
from local_store import get_local_store


def _env_flag(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


MAIL_MODULE_ENABLED = _env_flag("MAIL_MODULE_ENABLED", "0")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    sync_task = asyncio.create_task(background_ad_sync_loop())
    await mfu_runtime_monitor.start()
    print(f"Starting {config.app.app_name} v{config.app.version}")
    print(f"Database: {config.database.host} / {config.database.database}")
    print(f"Debug mode: {config.app.debug}")
    if config.jwt.secret_key == "your-secret-key-change-in-production":
        print("WARNING: insecure default JWT secret is configured. Set JWT_SECRET_KEYS or JWT_SECRET_KEY.")
    try:
        store = get_local_store()
        print(f"Local SQLite store: {store.db_path}")
    except Exception as exc:
        print(f"SQLite init warning: {exc}")
    yield
    # Shutdown
    print("Shutting down...")
    sync_task.cancel()
    await mfu_runtime_monitor.stop()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass


# Create FastAPI app
app = FastAPI(
    title=config.app.app_name,
    version=config.app.version,
    debug=config.app.debug,
    lifespan=lifespan,
    docs_url="/docs" if config.app.debug else None,
    redoc_url="/redoc" if config.app.debug else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.app.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": config.app.version}


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) if config.app.debug else "Internal server error"}
    )


# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(equipment.router, prefix="/api/v1/equipment", tags=["Equipment"])
app.include_router(database.router, prefix="/api/v1/database", tags=["Database Management"])
app.include_router(json_operations.router, prefix="/api/v1/json", tags=["JSON Operations"])
app.include_router(settings.router, prefix="/api/v1/settings", tags=["User Settings"])
app.include_router(networks.router, prefix="/api/v1/networks", tags=["Networks"])
app.include_router(discovery.router, prefix="/api/v1/discovery", tags=["Discovery"])
app.include_router(inventory.router, prefix="/api/v1/inventory", tags=["Inventory"])
app.include_router(kb.router, prefix="/api/v1/kb", tags=["Knowledge Base"])
app.include_router(mfu.router, prefix="/api/v1/mfu", tags=["MFU"])
app.include_router(hub.router, prefix="/api/v1/hub", tags=["Hub"])
app.include_router(ad_users.router, prefix="/api/v1/ad-users", tags=["AD Users"])
app.include_router(mail.router, prefix="/api/v1/mail", tags=["Mail"])
app.include_router(vcs.router, prefix="/api/v1/vcs", tags=["VCS"])

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": config.app.app_name,
        "version": config.app.version,
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    backend_port = int(os.getenv("BACKEND_PORT", "8001"))
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=backend_port,
        reload=config.app.debug,
    )
