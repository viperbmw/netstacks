# NetStacks Microservices Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the microservices architecture by enabling existing services (auth, devices, config), creating an AI service, fixing the platform health page, and updating Swagger docs for all changes.

**Architecture:** Enable Traefik routing to microservices (auth:8011, devices:8004, config:8002). Create new AI service (agents, alerts, knowledge, incidents) on port 8003. Flask monolith becomes a thin UI layer that proxies to microservices. All services share PostgreSQL via SQLAlchemy models in `shared/netstacks_core`.

**Tech Stack:** FastAPI microservices, Flask UI layer, Traefik reverse proxy, PostgreSQL, Redis, Celery workers, OpenAPI/Swagger docs.

---

## Phase 1: Fix Platform Health and Update Swagger Docs for Recent Changes

### Task 1: Add Platform Stats to Swagger Docs

**Files:**
- Modify: `/home/cwdavis/netstacks/api_docs.py`

**Step 1: Find the swagger spec in api_docs.py**

```bash
grep -n "swagger.json" api_docs.py | head -5
```

**Step 2: Add platform stats endpoint to Swagger spec**

Add after the existing paths in the OpenAPI spec:

```python
"/api/platform/stats": {
    "get": {
        "tags": ["Platform"],
        "summary": "Get platform statistics",
        "description": "Returns aggregated platform metrics including device counts, template counts, incident counts, and system health. Cached for 60 seconds.",
        "responses": {
            "200": {
                "description": "Platform statistics",
                "schema": {
                    "type": "object",
                    "properties": {
                        "timestamp": {"type": "string", "format": "date-time"},
                        "devices": {
                            "type": "object",
                            "properties": {
                                "total": {"type": "integer"},
                                "by_type": {"type": "object"},
                                "by_status": {"type": "object"}
                            }
                        },
                        "templates": {
                            "type": "object",
                            "properties": {
                                "total": {"type": "integer"},
                                "by_type": {"type": "object"}
                            }
                        },
                        "stacks": {
                            "type": "object",
                            "properties": {
                                "total": {"type": "integer"},
                                "deployed": {"type": "integer"},
                                "by_state": {"type": "object"}
                            }
                        },
                        "incidents": {
                            "type": "object",
                            "properties": {
                                "total": {"type": "integer"},
                                "open": {"type": "integer"}
                            }
                        },
                        "agents": {
                            "type": "object",
                            "properties": {
                                "total": {"type": "integer"},
                                "active": {"type": "integer"}
                            }
                        },
                        "backups": {
                            "type": "object",
                            "properties": {
                                "schedule_enabled": {"type": "boolean"},
                                "recent_count": {"type": "integer"}
                            }
                        },
                        "system": {
                            "type": "object",
                            "properties": {
                                "redis_connected": {"type": "boolean"}
                            }
                        }
                    }
                }
            }
        }
    }
}
```

**Step 3: Verify Swagger loads**

```bash
curl -s -c /tmp/cc.txt -X POST http://localhost:8089/login -d "username=admin&password=admin" > /dev/null
curl -s -b /tmp/cc.txt http://localhost:8089/docs/swagger.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('/api/platform/stats' in d.get('paths', {}))"
```
Expected: `True`

**Step 4: Commit**

```bash
git add api_docs.py
git commit -m "docs: add platform stats endpoint to Swagger docs"
```

---

### Task 2: Add Platform Health Endpoint to Swagger Docs

**Files:**
- Modify: `/home/cwdavis/netstacks/api_docs.py`

**Step 1: Add platform health endpoint**

```python
"/api/platform/health": {
    "get": {
        "tags": ["Platform"],
        "summary": "Get platform health status",
        "description": "Returns health status of all platform services including microservices, Redis, PostgreSQL, and Celery workers.",
        "responses": {
            "200": {
                "description": "Platform health status",
                "schema": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "overall_status": {"type": "string", "enum": ["healthy", "degraded"]},
                                "services": {
                                    "type": "object",
                                    "additionalProperties": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string"},
                                            "response_ms": {"type": "integer"},
                                            "details": {"type": "object"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
```

**Step 2: Rebuild and verify**

```bash
docker compose build netstacks && docker compose up -d netstacks
sleep 5
curl -s -b /tmp/cc.txt http://localhost:8089/docs/swagger.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('/api/platform/health' in d.get('paths', {}))"
```

**Step 3: Commit**

```bash
git add api_docs.py
git commit -m "docs: add platform health endpoint to Swagger docs"
```

---

### Task 3: Enhance Platform Health Page with Platform Stats

**Files:**
- Modify: `/home/cwdavis/netstacks/templates/platform.html`

**Step 1: Add platform stats section to the template**

After the "Quick Stats" section, add a new card that displays platform statistics from `/api/platform/stats`:

```html
<!-- Platform Stats Section - add after quick-stats -->
<div class="row mb-4">
    <div class="col-12">
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0"><i class="fas fa-chart-bar"></i> Platform Statistics</h5>
            </div>
            <div class="card-body">
                <div class="row" id="platform-stats">
                    <div class="col-md-2 col-sm-4 text-center mb-3">
                        <div class="h3 mb-0" id="stat-devices">-</div>
                        <small class="text-muted">Devices</small>
                    </div>
                    <div class="col-md-2 col-sm-4 text-center mb-3">
                        <div class="h3 mb-0" id="stat-templates">-</div>
                        <small class="text-muted">Templates</small>
                    </div>
                    <div class="col-md-2 col-sm-4 text-center mb-3">
                        <div class="h3 mb-0" id="stat-stacks">-</div>
                        <small class="text-muted">Stacks</small>
                    </div>
                    <div class="col-md-2 col-sm-4 text-center mb-3">
                        <div class="h3 mb-0" id="stat-incidents">-</div>
                        <small class="text-muted">Open Incidents</small>
                    </div>
                    <div class="col-md-2 col-sm-4 text-center mb-3">
                        <div class="h3 mb-0" id="stat-agents">-</div>
                        <small class="text-muted">Active Agents</small>
                    </div>
                    <div class="col-md-2 col-sm-4 text-center mb-3">
                        <div class="h3 mb-0" id="stat-backups">-</div>
                        <small class="text-muted">Recent Backups</small>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
```

**Step 2: Add JavaScript to fetch and display stats**

Add to the script section:

```javascript
async function loadPlatformStats() {
    try {
        const response = await fetch('/api/platform/stats');
        const data = await response.json();

        document.getElementById('stat-devices').textContent = data.devices?.total ?? '-';
        document.getElementById('stat-templates').textContent = data.templates?.total ?? '-';
        document.getElementById('stat-stacks').textContent = `${data.stacks?.deployed ?? 0}/${data.stacks?.total ?? 0}`;
        document.getElementById('stat-incidents').textContent = data.incidents?.open ?? '-';
        document.getElementById('stat-agents').textContent = data.agents?.active ?? '-';
        document.getElementById('stat-backups').textContent = data.backups?.recent_count ?? '-';
    } catch (error) {
        console.error('Error loading platform stats:', error);
    }
}

// Call on page load
document.addEventListener('DOMContentLoaded', function() {
    loadPlatformStats();
    refreshHealth();
});
```

**Step 3: Test the page**

```bash
docker compose build netstacks && docker compose up -d netstacks
sleep 5
curl -s -b /tmp/cc.txt http://localhost:8089/platform | grep -c "Platform Statistics"
```
Expected: `1`

**Step 4: Commit**

```bash
git add templates/platform.html
git commit -m "feat: add platform statistics to health page"
```

---

## Phase 2: Enable Traefik Routing to Microservices

### Task 4: Enable Auth Service in Traefik

**Files:**
- Modify: `/home/cwdavis/netstacks/docker-compose.yml`

**Step 1: Enable Traefik labels for auth service**

Find the auth service section and update the labels:

```yaml
  auth:
    # ... existing config ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.auth.rule=PathPrefix(`/api/auth`)"
      - "traefik.http.routers.auth.entrypoints=web"
      - "traefik.http.services.auth.loadbalancer.server.port=8011"
```

**Step 2: Verify auth service health**

```bash
docker compose up -d
sleep 5
curl -s http://localhost:80/api/auth/health | python3 -m json.tool
```
Expected: `{"service": "auth", "status": "healthy"}`

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: enable auth service routing via Traefik"
```

---

### Task 5: Enable Devices Service in Traefik

**Files:**
- Modify: `/home/cwdavis/netstacks/docker-compose.yml`

**Step 1: Enable Traefik labels for devices service**

```yaml
  devices:
    # ... existing config ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.devices.rule=PathPrefix(`/api/devices`) || PathPrefix(`/api/credentials`) || PathPrefix(`/api/device-overrides`) || PathPrefix(`/api/backups`)"
      - "traefik.http.routers.devices.entrypoints=web"
      - "traefik.http.services.devices.loadbalancer.server.port=8004"
```

**Step 2: Verify devices service**

```bash
docker compose up -d
sleep 5
curl -s http://localhost:80/api/devices/health | python3 -m json.tool
```

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: enable devices service routing via Traefik"
```

---

### Task 6: Enable Config Service in Traefik

**Files:**
- Modify: `/home/cwdavis/netstacks/docker-compose.yml`

**Step 1: Enable Traefik labels for config service**

```yaml
  config:
    # ... existing config ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.config.rule=PathPrefix(`/api/templates`) || PathPrefix(`/api/service-stacks`) || PathPrefix(`/api/mops`) || PathPrefix(`/api/step-types`) || PathPrefix(`/api/scheduled-operations`)"
      - "traefik.http.routers.config.entrypoints=web"
      - "traefik.http.services.config.loadbalancer.server.port=8002"
```

**Step 2: Verify config service**

```bash
docker compose up -d
sleep 5
curl -s http://localhost:80/api/templates/health 2>/dev/null || curl -s http://localhost:80/api/config/health
```

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: enable config service routing via Traefik"
```

---

## Phase 3: Create AI Microservice

### Task 7: Create AI Service Directory Structure

**Files:**
- Create: `/home/cwdavis/netstacks/services/ai/Dockerfile`
- Create: `/home/cwdavis/netstacks/services/ai/requirements.txt`
- Create: `/home/cwdavis/netstacks/services/ai/app/__init__.py`
- Create: `/home/cwdavis/netstacks/services/ai/app/main.py`
- Create: `/home/cwdavis/netstacks/services/ai/app/config.py`

**Step 1: Create directory structure**

```bash
mkdir -p services/ai/app/routes
mkdir -p services/ai/app/services
mkdir -p services/ai/app/schemas
touch services/ai/app/__init__.py
touch services/ai/app/routes/__init__.py
touch services/ai/app/services/__init__.py
touch services/ai/app/schemas/__init__.py
```

**Step 2: Create Dockerfile**

```dockerfile
# services/ai/Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library
COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared/

# Copy and install service requirements
COPY services/ai/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/ai/app /app/app

# Copy AI module for agent/tool logic
COPY ai/ /app/ai/

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
```

**Step 3: Create requirements.txt**

```
fastapi>=0.100.0
uvicorn>=0.23.0
pydantic>=2.0.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
python-multipart>=0.0.6
httpx>=0.24.0
redis>=4.5.0
celery>=5.3.0
openai>=1.0.0
anthropic>=0.5.0
```

**Step 4: Create config.py**

```python
# services/ai/app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SERVICE_NAME: str = "ai-service"
    SERVICE_PORT: int = 8003
    DATABASE_URL: str = "postgresql://netstacks:netstacks@postgres:5432/netstacks"
    JWT_SECRET_KEY: str = "netstacks-dev-secret"
    REDIS_URL: str = "redis://redis:6379/0"

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**Step 5: Create main.py**

```python
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
from app.routes import agents, alerts, incidents, knowledge

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(incidents.router, prefix="/api/incidents", tags=["Incidents"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["Knowledge"])

@app.get("/health")
async def health_check():
    return {"service": settings.SERVICE_NAME, "status": "healthy"}
```

**Step 6: Commit**

```bash
git add services/ai/
git commit -m "feat: create AI microservice directory structure"
```

---

### Task 8: Create AI Service Route Stubs

**Files:**
- Create: `/home/cwdavis/netstacks/services/ai/app/routes/agents.py`
- Create: `/home/cwdavis/netstacks/services/ai/app/routes/alerts.py`
- Create: `/home/cwdavis/netstacks/services/ai/app/routes/incidents.py`
- Create: `/home/cwdavis/netstacks/services/ai/app/routes/knowledge.py`
- Modify: `/home/cwdavis/netstacks/services/ai/app/routes/__init__.py`

**Step 1: Create agents router**

```python
# services/ai/app/routes/agents.py
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter()

class Agent(BaseModel):
    agent_id: str
    name: str
    agent_type: str
    is_active: bool = False
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

class AgentCreate(BaseModel):
    name: str
    agent_type: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

@router.get("/", response_model=List[Agent])
async def list_agents():
    """List all agents."""
    # TODO: Implement database query
    return []

@router.post("/", response_model=Agent)
async def create_agent(agent: AgentCreate):
    """Create a new agent."""
    # TODO: Implement
    raise HTTPException(status_code=501, detail="Not implemented")

@router.get("/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str):
    """Get agent by ID."""
    raise HTTPException(status_code=404, detail="Agent not found")

@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete an agent."""
    raise HTTPException(status_code=501, detail="Not implemented")

@router.post("/{agent_id}/start")
async def start_agent(agent_id: str):
    """Start an agent."""
    raise HTTPException(status_code=501, detail="Not implemented")

@router.post("/{agent_id}/stop")
async def stop_agent(agent_id: str):
    """Stop an agent."""
    raise HTTPException(status_code=501, detail="Not implemented")
```

**Step 2: Create alerts router**

```python
# services/ai/app/routes/alerts.py
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class Alert(BaseModel):
    alert_id: str
    title: str
    severity: str
    status: str
    source: Optional[str] = None
    created_at: datetime

@router.get("/", response_model=List[Alert])
async def list_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100
):
    """List alerts with optional filters."""
    return []

@router.post("/")
async def create_alert(alert: dict):
    """Create alert (webhook endpoint)."""
    # TODO: Implement alert processing
    return {"status": "received"}

@router.get("/{alert_id}", response_model=Alert)
async def get_alert(alert_id: str):
    """Get alert by ID."""
    raise HTTPException(status_code=404, detail="Alert not found")

@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an alert."""
    raise HTTPException(status_code=501, detail="Not implemented")
```

**Step 3: Create incidents router**

```python
# services/ai/app/routes/incidents.py
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class Incident(BaseModel):
    incident_id: str
    title: str
    severity: str
    status: str
    created_at: datetime

@router.get("/", response_model=List[Incident])
async def list_incidents(status: Optional[str] = None, limit: int = 100):
    """List incidents."""
    return []

@router.post("/")
async def create_incident(incident: dict):
    """Create a new incident."""
    raise HTTPException(status_code=501, detail="Not implemented")

@router.get("/{incident_id}", response_model=Incident)
async def get_incident(incident_id: str):
    """Get incident by ID."""
    raise HTTPException(status_code=404, detail="Incident not found")

@router.patch("/{incident_id}")
async def update_incident(incident_id: str, updates: dict):
    """Update an incident."""
    raise HTTPException(status_code=501, detail="Not implemented")
```

**Step 4: Create knowledge router**

```python
# services/ai/app/routes/knowledge.py
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter()

class Document(BaseModel):
    doc_id: str
    title: str
    filename: str
    collection: str

@router.get("/", response_model=List[Document])
async def list_documents(collection: Optional[str] = None):
    """List knowledge base documents."""
    return []

@router.post("/")
async def upload_document(file: UploadFile = File(...), collection: str = "default"):
    """Upload a document to knowledge base."""
    raise HTTPException(status_code=501, detail="Not implemented")

@router.get("/{doc_id}", response_model=Document)
async def get_document(doc_id: str):
    """Get document by ID."""
    raise HTTPException(status_code=404, detail="Document not found")

@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document."""
    raise HTTPException(status_code=501, detail="Not implemented")

@router.post("/search")
async def search_documents(query: str, collection: Optional[str] = None, limit: int = 10):
    """Search documents using vector similarity."""
    return {"results": []}
```

**Step 5: Update routes __init__.py**

```python
# services/ai/app/routes/__init__.py
from . import agents, alerts, incidents, knowledge
```

**Step 6: Commit**

```bash
git add services/ai/app/routes/
git commit -m "feat: create AI service route stubs"
```

---

### Task 9: Add AI Service to Docker Compose

**Files:**
- Modify: `/home/cwdavis/netstacks/docker-compose.yml`

**Step 1: Add AI service definition**

Add after the config service:

```yaml
  # AI Service (Microservice)
  ai:
    build:
      context: .
      dockerfile: services/ai/Dockerfile
    container_name: netstacks-ai
    environment:
      - DATABASE_URL=postgresql://netstacks:${POSTGRES_PASSWORD:-netstacks_secret_change_me}@postgres:5432/netstacks
      - JWT_SECRET_KEY=${JWT_SECRET_KEY:-netstacks-dev-secret-change-in-production}
      - REDIS_URL=redis://redis:6379/0
      - TZ=${TZ:-America/New_York}
    networks:
      - netstacks-network
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.ai.rule=PathPrefix(`/api/agents`) || PathPrefix(`/api/alerts`) || PathPrefix(`/api/incidents`) || PathPrefix(`/api/knowledge`)"
      - "traefik.http.routers.ai.entrypoints=web"
      - "traefik.http.services.ai.loadbalancer.server.port=8003"
```

**Step 2: Build and test AI service**

```bash
docker compose build ai
docker compose up -d ai
sleep 10
curl -s http://localhost:80/api/agents/ | python3 -m json.tool
```
Expected: `[]` (empty list)

**Step 3: Verify health endpoint**

```bash
curl -s http://localhost:8003/health
```
Expected: `{"service": "ai-service", "status": "healthy"}`

**Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add AI microservice to Docker Compose"
```

---

### Task 10: Update Platform Health to Include AI Service

**Files:**
- Modify: `/home/cwdavis/netstacks/services/microservice_client.py`

**Step 1: Add AI service URL constant**

```python
AI_SERVICE_URL = os.environ.get('AI_SERVICE_URL', 'http://ai:8003')
```

**Step 2: Update check_all_services_health to include AI service**

In the `check_all_services_health` method, add 'ai' to the services list:

```python
for service in ['auth', 'devices', 'config', 'ai']:
    results[service] = self.check_service_health(service)
```

**Step 3: Update check_service_health URL mapping**

```python
url_map = {
    'auth': f"{AUTH_SERVICE_URL}/health",
    'devices': f"{DEVICES_SERVICE_URL}/health",
    'config': f"{CONFIG_SERVICE_URL}/health",
    'ai': f"{AI_SERVICE_URL}/health",
}
```

**Step 4: Rebuild and verify**

```bash
docker compose build netstacks && docker compose up -d netstacks
sleep 5
curl -s -b /tmp/cc.txt http://localhost:8089/api/platform/health | python3 -c "import json,sys; d=json.load(sys.stdin); print('ai' in d['data']['services'])"
```
Expected: `True`

**Step 5: Commit**

```bash
git add services/microservice_client.py
git commit -m "feat: add AI service to platform health checks"
```

---

### Task 11: Update Platform Health Page Architecture Diagram

**Files:**
- Modify: `/home/cwdavis/netstacks/templates/platform.html`

**Step 1: Add AI service node to SVG architecture diagram**

Find the SVG section and add an AI service node between devices and config:

```svg
<!-- AI Service Node -->
<g id="node-ai" class="service-node" data-service="ai" transform="translate(575, 160)">
    <rect x="-60" y="-25" width="120" height="50" rx="8" fill="url(#unknownGradient)" filter="url(#shadow)" class="node-bg"/>
    <text x="0" y="-5" text-anchor="middle" fill="white" font-size="12" font-weight="bold">AI Service</text>
    <text x="0" y="12" text-anchor="middle" fill="#9ca3af" font-size="10">:8003</text>
</g>
```

**Step 2: Add connection line from Traefik to AI**

```svg
<path id="conn-traefik-ai" class="connection-line" d="M 450,80 L 575,160" stroke="#4b5563" stroke-width="2" fill="none" stroke-dasharray="5,5"/>
```

**Step 3: Update JavaScript to handle AI service status**

In the `updateArchitectureDiagram` function, ensure it handles the 'ai' service key.

**Step 4: Commit**

```bash
git add templates/platform.html
git commit -m "feat: add AI service to platform health architecture diagram"
```

---

## Phase 4: Update Swagger Documentation

### Task 12: Generate OpenAPI Spec from Microservices

**Files:**
- Modify: `/home/cwdavis/netstacks/api_docs.py`

**Step 1: Add AI service endpoints to Swagger spec**

Add the AI service paths to the OpenAPI specification in api_docs.py. Include all agent, alert, incident, and knowledge endpoints with proper schemas.

**Step 2: Verify updated Swagger docs**

```bash
docker compose build netstacks && docker compose up -d netstacks
sleep 5
curl -s -b /tmp/cc.txt http://localhost:8089/docs/swagger.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Total paths: {len(d[\"paths\"])}')"
```

**Step 3: Commit**

```bash
git add api_docs.py
git commit -m "docs: add AI service endpoints to Swagger documentation"
```

---

### Task 13: Final Verification and Cleanup

**Step 1: Verify all services are healthy**

```bash
curl -s -c /tmp/cc.txt -X POST http://localhost:8089/login -d "username=admin&password=admin" > /dev/null
curl -s -b /tmp/cc.txt http://localhost:8089/api/platform/health | python3 -m json.tool
```

Expected: All services show `"status": "healthy"`

**Step 2: Verify platform stats work**

```bash
curl -s -b /tmp/cc.txt http://localhost:8089/api/platform/stats | python3 -m json.tool
```

**Step 3: Verify Swagger docs are accessible**

```bash
curl -s http://localhost:8089/docs/ | grep -c "swagger-ui"
```
Expected: `1`

**Step 4: Verify AI service routes via Traefik**

```bash
curl -s http://localhost:80/api/agents/ | python3 -m json.tool
curl -s http://localhost:80/api/alerts/ | python3 -m json.tool
curl -s http://localhost:80/api/incidents/ | python3 -m json.tool
curl -s http://localhost:80/api/knowledge/ | python3 -m json.tool
```

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: microservices refactoring complete

- Enabled Traefik routing for auth, devices, config, ai services
- Created AI microservice with agents, alerts, incidents, knowledge APIs
- Updated platform health page with statistics and AI service
- Updated Swagger docs with all new endpoints"
```

---

## Summary

After completing all tasks:

1. **Microservices Architecture**: Traefik routes requests to appropriate services
   - Auth: `/api/auth/*` -> auth:8011
   - Devices: `/api/devices/*`, `/api/credentials/*` -> devices:8004
   - Config: `/api/templates/*`, `/api/service-stacks/*`, `/api/mops/*` -> config:8002
   - AI: `/api/agents/*`, `/api/alerts/*`, `/api/incidents/*`, `/api/knowledge/*` -> ai:8003
   - UI: All other routes -> netstacks:8088

2. **Platform Health**: Shows all service statuses plus platform statistics

3. **Swagger Docs**: Complete API documentation at `/docs/`

4. **Flask Monolith**: Now a thin UI layer that can be gradually deprecated
