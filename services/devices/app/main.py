"""
Devices Service - FastAPI Application

Handles device management, credentials, NetBox sync, and device overrides.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from netstacks_core.db import init_db

from app.config import settings
from app.routes import devices, credentials, overrides, netbox

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    log.info(f"Starting {settings.service_name} v{settings.service_version}")

    # Initialize database
    init_db()
    log.info("Database initialized")

    yield

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
