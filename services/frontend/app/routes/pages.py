# services/frontend/app/routes/pages.py
"""
Page routes for the frontend service.

Serves HTML pages. Authentication is handled client-side via JWT.
Pages check for valid JWT in localStorage and redirect to login if missing.
"""

import logging
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

log = logging.getLogger(__name__)

router = APIRouter()

BASE_DIR = Path(__file__).parent.parent.parent
PAGES_DIR = BASE_DIR / "pages"


def serve_page(page_name: str) -> FileResponse:
    """Serve an HTML page from the pages directory."""
    page_path = PAGES_DIR / f"{page_name}.html"
    if page_path.exists():
        return FileResponse(page_path, media_type="text/html")
    # Fallback to 404 page
    return FileResponse(PAGES_DIR / "404.html", media_type="text/html", status_code=404)


# Login page (no auth required)
@router.get("/login")
async def login_page():
    return serve_page("login")


# Logout endpoint
@router.get("/logout")
async def logout_page():
    return serve_page("logout")


# Dashboard (index)
@router.get("/")
async def index():
    return serve_page("index")


# Operations
@router.get("/deploy")
async def deploy():
    return serve_page("deploy")


@router.get("/monitor")
async def monitor():
    return serve_page("monitor")


@router.get("/mop")
async def mop():
    return serve_page("mop")


# Configuration
@router.get("/devices")
async def devices():
    return serve_page("config_backups")  # config_backups.html is the devices page


@router.get("/templates")
async def templates():
    return serve_page("templates")


@router.get("/service-stacks")
async def service_stacks():
    return serve_page("service-stacks")


# AI
@router.get("/agents")
async def agents():
    return serve_page("agents")


@router.get("/agents/chat")
async def agent_chat():
    return serve_page("agent_chat")


@router.get("/alerts")
async def alerts():
    return serve_page("alerts")


@router.get("/alerts/incidents")
async def incidents_redirect():
    return serve_page("incidents")


@router.get("/incidents")
async def incidents():
    return serve_page("incidents")


@router.get("/approvals")
async def approvals():
    return serve_page("approvals")


@router.get("/knowledge")
async def knowledge():
    return serve_page("knowledge")


@router.get("/tools")
async def tools():
    return serve_page("tools")


# Settings
@router.get("/admin")
async def admin():
    return serve_page("admin")


@router.get("/users")
async def users():
    return serve_page("users")


@router.get("/settings")
async def settings_page():
    return serve_page("settings")


@router.get("/settings/ai")
async def ai_settings():
    return serve_page("ai_settings")


@router.get("/settings/ingestion")
async def ingestion_settings():
    return serve_page("settings-ingestion")


@router.get("/platform")
async def platform():
    return serve_page("platform")


@router.get("/step-types")
async def step_types():
    return serve_page("step_types")


@router.get("/workers")
async def workers():
    return serve_page("workers")


@router.get("/config-backups")
async def config_backups():
    return serve_page("config_backups")


# Authentication page (for OIDC config display)
@router.get("/authentication")
async def authentication():
    return serve_page("authentication")


# API Documentation - create a docs index page
@router.get("/docs")
async def api_docs():
    return serve_page("docs")
