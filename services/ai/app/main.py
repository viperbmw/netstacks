# services/ai/app/main.py
"""
NetStacks AI Service - FastAPI Application

Provides AI agents, alerts, incidents, and knowledge base APIs.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from netstacks_core.db import init_db

from app.config import get_settings
from app.routes import agents, alerts, incidents, knowledge, approvals, sessions, llm, webhooks

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(f"Starting {settings.SERVICE_NAME} on port {settings.SERVICE_PORT}")
    init_db()
    log.info("Database initialized")
    yield
    log.info("Shutting down AI service")


app = FastAPI(
    title="NetStacks AI Service",
    description="AI agents, alerts, incidents, and knowledge base management",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

origins = settings.CORS_ORIGINS.split(',') if settings.CORS_ORIGINS != '*' else ['*']
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(incidents.router, prefix="/api/incidents", tags=["Incidents"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["Knowledge"])
app.include_router(approvals.router, prefix="/api/approvals", tags=["Approvals"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["Sessions"])
app.include_router(llm.router, prefix="/api/llm", tags=["LLM Providers"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])


@app.get("/health")
async def health_check():
    return {"service": settings.SERVICE_NAME, "status": "healthy"}


@app.get("/")
async def root():
    return {
        "service": "NetStacks AI Service",
        "version": "1.0.0",
        "endpoints": [
            "/api/agents",
            "/api/alerts",
            "/api/incidents",
            "/api/knowledge",
            "/api/approvals",
            "/api/sessions",
            "/api/llm",
            "/api/webhooks",
        ]
    }
