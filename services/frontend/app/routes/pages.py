# services/frontend/app/routes/pages.py
"""
Page routes for the frontend service.

Serves HTML pages using Jinja2 templates. Authentication is handled client-side via JWT.
Pages check for valid JWT in localStorage and redirect to login if missing.
"""

import logging
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

log = logging.getLogger(__name__)

router = APIRouter()

BASE_DIR = Path(__file__).parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

# Initialize Jinja2 templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def render_page(request: Request, template_name: str) -> HTMLResponse:
    """Render a Jinja2 template."""
    try:
        return templates.TemplateResponse(f"{template_name}.html", {"request": request})
    except Exception as e:
        log.error(f"Error rendering template {template_name}: {e}")
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)


# Login page (no auth required)
@router.get("/login")
async def login_page(request: Request):
    return render_page(request, "login")


# Logout endpoint
@router.get("/logout")
async def logout_page(request: Request):
    return render_page(request, "logout")


# Dashboard (index)
@router.get("/")
async def index(request: Request):
    return render_page(request, "index")


# Operations
@router.get("/deploy")
async def deploy(request: Request):
    return render_page(request, "deploy")


@router.get("/monitor")
async def monitor(request: Request):
    return render_page(request, "monitor")


@router.get("/mop")
async def mop(request: Request):
    return render_page(request, "mop")


# Configuration
@router.get("/devices")
async def devices(request: Request):
    return render_page(request, "config_backups")  # config_backups.html is the devices page


@router.get("/templates")
async def templates_page(request: Request):
    return render_page(request, "templates")


@router.get("/service-stacks")
async def service_stacks(request: Request):
    return render_page(request, "service-stacks")


# AI
@router.get("/agents")
async def agents(request: Request):
    return render_page(request, "agents")


@router.get("/agents/chat")
async def agent_chat(request: Request):
    return render_page(request, "agent_chat")


@router.get("/alerts")
async def alerts(request: Request):
    return render_page(request, "alerts")


@router.get("/alerts/incidents")
async def incidents_redirect(request: Request):
    return render_page(request, "incidents")


@router.get("/incidents")
async def incidents(request: Request):
    return render_page(request, "incidents")


@router.get("/approvals")
async def approvals(request: Request):
    return render_page(request, "approvals")


@router.get("/knowledge")
async def knowledge(request: Request):
    return render_page(request, "knowledge")


@router.get("/tools")
async def tools(request: Request):
    return render_page(request, "tools")


# Settings
@router.get("/admin")
async def admin(request: Request):
    return render_page(request, "admin")


@router.get("/users")
async def users(request: Request):
    return render_page(request, "users")


@router.get("/settings")
async def settings_page(request: Request):
    return render_page(request, "settings")


@router.get("/settings/ai")
async def ai_settings(request: Request):
    return render_page(request, "ai_settings")


@router.get("/settings/ingestion")
async def ingestion_settings(request: Request):
    return render_page(request, "settings-ingestion")


@router.get("/platform")
async def platform(request: Request):
    return render_page(request, "platform")


@router.get("/step-types")
async def step_types(request: Request):
    return render_page(request, "step_types")


@router.get("/workers")
async def workers(request: Request):
    return render_page(request, "workers")


@router.get("/config-backups")
async def config_backups(request: Request):
    return render_page(request, "config_backups")


# Authentication page (for OIDC config display)
@router.get("/authentication")
async def authentication(request: Request):
    return render_page(request, "authentication")


# API Documentation - create a docs index page
@router.get("/docs")
async def api_docs(request: Request):
    return render_page(request, "docs")
