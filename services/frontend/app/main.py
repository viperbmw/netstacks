# services/frontend/app/main.py
"""
NetStacks Frontend Service - FastAPI Application

Serves static HTML pages and assets using Jinja2 templates.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import get_settings
from app.routes import pages

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

settings = get_settings()

# Paths
BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(f"Starting {settings.SERVICE_NAME} on port {settings.SERVICE_PORT}")
    yield
    log.info("Shutting down Frontend service")


app = FastAPI(
    title="NetStacks Frontend Service",
    description="Serves static HTML pages and assets",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,  # Disable docs for frontend service
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include page routes
app.include_router(pages.router)


@app.get("/health")
async def health_check():
    return {"service": settings.SERVICE_NAME, "status": "healthy"}


@app.get("/favicon.svg")
async def favicon():
    return FileResponse(STATIC_DIR / "favicon.svg")
