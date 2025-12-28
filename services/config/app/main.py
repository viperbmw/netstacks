"""
Config Service - Main Application

Handles templates, service stacks, MOPs, and scheduled operations.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from netstacks_core.db import init_db, seed_defaults, get_session

from app.config import settings
from app.routes import templates, stacks, stack_templates, mops, schedules, step_types

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    log.info(f"Starting {settings.SERVICE_NAME} v{settings.VERSION}")
    try:
        engine = init_db()
        session = get_session(engine)
        try:
            seed_defaults(session)
        finally:
            session.close()
        log.info("Database initialized successfully")
    except Exception as e:
        log.error(f"Database initialization failed: {e}")
    yield
    log.info("Shutting down...")


app = FastAPI(
    title="NetStacks Config Service",
    description="Templates, Service Stacks, MOPs, and Scheduled Operations",
    version=settings.VERSION,
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


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
    }


# Include routers
app.include_router(templates.router, prefix="/api/templates", tags=["Templates"])
app.include_router(stacks.router, prefix="/api/service-stacks", tags=["Service Stacks"])
app.include_router(stack_templates.router, prefix="/api/stack-templates", tags=["Stack Templates"])
app.include_router(mops.router, prefix="/api/mops", tags=["MOPs"])
app.include_router(schedules.router, prefix="/api/scheduled-operations", tags=["Schedules"])
app.include_router(step_types.router, prefix="/api/step-types", tags=["Step Types"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
