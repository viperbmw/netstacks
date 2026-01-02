"""
NetStacks Tasks Service - FastAPI Application

Provides Celery task management and worker monitoring APIs.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import tasks, workers, deploy, bulk

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    log.info(f"Starting {settings.SERVICE_NAME} service on port {settings.SERVICE_PORT}")
    log.info(f"Celery broker: {settings.CELERY_BROKER_URL}")

    yield

    # Shutdown
    log.info("Shutting down tasks service")


# Create FastAPI application
app = FastAPI(
    title="NetStacks Tasks Service",
    description="Celery task management and worker monitoring API",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
origins = settings.CORS_ORIGINS.split(',') if settings.CORS_ORIGINS != '*' else ['*']
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (routers already have their prefixes defined)
app.include_router(tasks.router)
app.include_router(workers.router)
app.include_router(deploy.router)
app.include_router(bulk.router)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": settings.SERVICE_NAME}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "NetStacks Tasks Service",
        "version": "1.0.0",
        "endpoints": [
            "/api/tasks",
            "/api/workers",
            "/api/celery",
            "/api/devices/bulk",
        ]
    }
