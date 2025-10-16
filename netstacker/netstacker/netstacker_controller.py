import logging
import filelock
# load fast api
from fastapi import FastAPI, Depends
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import JSONResponse, HTMLResponse
from starlette.requests import Request
from netstacker.backend.core.confload.confload import config
from netstacker.backend.core.security.get_api_key import get_api_key
from netstacker.netstacker_worker_common import start_broadcast_listener_process
from netstacker.routers import getconfig, setconfig, task, template, script, util, public, schedule

log = logging.getLogger(__name__)
config.setup_logging(max_debug=True)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory="netstacker/static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="netstacker/templates")

app.include_router(getconfig.router, dependencies=[Depends(get_api_key)])
app.include_router(setconfig.router, dependencies=[Depends(get_api_key)])
app.include_router(task.router, dependencies=[Depends(get_api_key)])
app.include_router(template.router, dependencies=[Depends(get_api_key)])
app.include_router(script.router, dependencies=[Depends(get_api_key)])
app.include_router(util.router, dependencies=[Depends(get_api_key)])
app.include_router(schedule.router, dependencies=[Depends(get_api_key)])
app.include_router(public.router)

broadcast_worker_lock = filelock.FileLock("broadcast_worker_lock")
try:
    broadcast_worker_lock.acquire(timeout=0.01)
    with broadcast_worker_lock:
        log.info(f"Creating broadcast listener because I got the lock!")
        start_broadcast_listener_process()
except filelock.Timeout:
    log.info(f"skipping broadcast listener creation because I couldn't get the lock")

# swaggerui routers
@app.get("/swaggerfile", tags=["swagger file"], include_in_schema=False)
async def get_open_api_endpoint():
    response = JSONResponse(
        get_openapi(
            title="Netstacker",
            version="0.4",
            openapi_version="3.0.2",  # Added this required parameter
            description="Netstacker makes it easy to push and pull state from your apps to your network devices using netmiko",
            routes=app.routes
        )
    )
    return response

@app.get("/", tags=["swaggerui"], include_in_schema=False, response_class=HTMLResponse)
async def get_documentation(request: Request):
    """Serve custom Netstacker-themed Swagger UI"""
    return templates.TemplateResponse("swagger.html", {"request": request})
