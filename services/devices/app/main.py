"""
Devices Service - FastAPI Application

Handles device management, credentials, NetBox sync, and device overrides.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from netstacks_core.db import init_db, get_session, Setting

from app.config import settings
from app.routes import devices, credentials, overrides, netbox
from app.services.netbox_service import NetBoxService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# Background sync state
_sync_task: Optional[asyncio.Task] = None
_last_sync: Optional[datetime] = None


def get_cache_ttl() -> int:
    """Get cache TTL from settings (defaults to 300 seconds)."""
    try:
        session = get_session()
        setting = session.query(Setting).filter(Setting.key == 'cache_ttl').first()
        session.close()
        if setting and setting.value:
            return int(setting.value)
    except Exception as e:
        log.warning(f"Error getting cache_ttl setting: {e}")
    return 300  # Default 5 minutes


async def background_sync():
    """Background task that syncs devices from NetBox periodically."""
    global _last_sync

    log.info("Background NetBox sync task started")

    # Initial delay to let the service start up
    await asyncio.sleep(10)

    while True:
        try:
            ttl = get_cache_ttl()

            # Check if we need to sync
            if _last_sync is None or datetime.utcnow() > _last_sync + timedelta(seconds=ttl):
                log.info(f"Running background NetBox sync (TTL: {ttl}s)")

                session = get_session()
                try:
                    service = NetBoxService(session)
                    status = service.get_status()

                    if status.get('connected'):
                        result = service.sync_devices()
                        _last_sync = datetime.utcnow()
                        log.info(f"Background sync complete: {result.get('synced', 0)} devices synced")
                    else:
                        log.warning("NetBox not connected, skipping background sync")
                finally:
                    session.close()

            # Sleep for a bit before checking again
            await asyncio.sleep(60)  # Check every minute

        except asyncio.CancelledError:
            log.info("Background sync task cancelled")
            break
        except Exception as e:
            log.error(f"Error in background sync: {e}")
            await asyncio.sleep(60)  # Wait before retrying


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    global _sync_task

    log.info(f"Starting {settings.service_name} v{settings.service_version}")

    # Initialize database
    init_db()
    log.info("Database initialized")

    # Start background sync task
    _sync_task = asyncio.create_task(background_sync())
    log.info("Background sync task scheduled")

    yield

    # Cancel background sync task
    if _sync_task:
        _sync_task.cancel()
        try:
            await _sync_task
        except asyncio.CancelledError:
            pass

    log.info(f"Shutting down {settings.service_name}")


# Create FastAPI app
app = FastAPI(
    title="NetStacks Devices Service",
    description="Device management, credentials, and NetBox integration",
    version=settings.service_version,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": settings.service_name}


# Include routers
app.include_router(
    devices.router,
    prefix="/api/devices",
    tags=["Devices"]
)

app.include_router(
    credentials.router,
    prefix="/api/credentials",
    tags=["Credentials"]
)

app.include_router(
    overrides.router,
    prefix="/api/device-overrides",
    tags=["Device Overrides"]
)

app.include_router(
    netbox.router,
    prefix="/api/netbox",
    tags=["NetBox"]
)
