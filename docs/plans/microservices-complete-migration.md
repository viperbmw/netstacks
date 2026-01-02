# NetStacks Complete Microservices Migration Plan

## Overview

This plan migrates NetStacks from a hybrid Flask monolith + microservices architecture to a **fully decoupled microservices architecture** with a modern frontend.

### Current State
- Flask monolith serving HTML templates + proxying to microservices
- 4 existing microservices (auth, devices, config, ai) - partially complete
- Celery workers for async device operations
- Dual authentication (Flask sessions + JWT) causing 401 errors
- ~210 routes, 9,900 lines of route code

### Target State
- **No Flask monolith** - all functionality in microservices
- **Static SPA frontend** (or lightweight frontend service)
- **8 microservices** handling all API logic
- **Single JWT authentication** across all services
- **WebSocket service** for real-time features

---

## Architecture Diagram

```
                                    ┌─────────────────────────────────────────────┐
                                    │              Traefik (Port 80)              │
                                    │         Reverse Proxy + Load Balancer       │
                                    └─────────────────────────────────────────────┘
                                                         │
                    ┌────────────────────────────────────┼────────────────────────────────────┐
                    │                                    │                                    │
                    ▼                                    ▼                                    ▼
    ┌───────────────────────────┐    ┌───────────────────────────────┐    ┌───────────────────────────┐
    │    Frontend Service       │    │      API Gateway (NEW)        │    │   WebSocket Service (NEW) │
    │    (Static SPA/Nginx)     │    │   - Rate limiting             │    │   - Agent chat            │
    │    - React/Vue/Vanilla    │    │   - Request validation        │    │   - Live updates          │
    │    - Port 3000            │    │   - Port 8000                 │    │   - Port 8010             │
    └───────────────────────────┘    └───────────────────────────────┘    └───────────────────────────┘
                                                         │
         ┌───────────────┬───────────────┬───────────────┼───────────────┬───────────────┬───────────────┐
         │               │               │               │               │               │               │
         ▼               ▼               ▼               ▼               ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │  Auth   │    │ Devices │    │ Config  │    │   AI    │    │ Alerts  │    │  Tasks  │    │  Backup │
    │ :8011   │    │ :8004   │    │ :8002   │    │ :8003   │    │ :8005   │    │ :8006   │    │ :8007   │
    │         │    │         │    │         │    │         │    │  (NEW)  │    │  (NEW)  │    │  (NEW)  │
    └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
         │               │               │               │               │               │               │
         └───────────────┴───────────────┴───────────────┴───────────────┴───────────────┴───────────────┘
                                                         │
                                    ┌────────────────────┴────────────────────┐
                                    │                                         │
                                    ▼                                         ▼
                         ┌─────────────────────┐                   ┌─────────────────────┐
                         │     PostgreSQL      │                   │       Redis         │
                         │   (Shared Database) │                   │  (Celery + Cache)   │
                         └─────────────────────┘                   └─────────────────────┘
                                                                              │
                                                                              ▼
                                                                   ┌─────────────────────┐
                                                                   │   Celery Workers    │
                                                                   │  (Device Operations)│
                                                                   └─────────────────────┘
```

---

## Migration Phases

### Phase 1: Foundation (Week 1)
**Goal**: Fix immediate issues, consolidate models, establish single auth

| Task | Priority | Effort |
|------|----------|--------|
| 1.1 Consolidate database models to shared library | HIGH | 2 days |
| 1.2 Remove Flask session auth, use JWT only | HIGH | 1 day |
| 1.3 Fix frontend api-client.js for pure JWT | HIGH | 1 day |
| 1.4 Create Tasks microservice for Celery management | HIGH | 2 days |
| 1.5 Update Traefik routing for new services | MEDIUM | 0.5 day |

### Phase 2: New Microservices (Week 2-3)
**Goal**: Create missing microservices, migrate business logic

| Task | Priority | Effort |
|------|----------|--------|
| 2.1 Create Alerts microservice (alerts, incidents, webhooks) | HIGH | 3 days |
| 2.2 Create Backup microservice (config backups, snapshots) | HIGH | 2 days |
| 2.3 Migrate knowledge base to AI service | MEDIUM | 2 days |
| 2.4 Migrate approvals to Auth service | MEDIUM | 1 day |
| 2.5 Create WebSocket service for real-time features | HIGH | 3 days |

### Phase 3: Frontend Transformation (Week 3-4)
**Goal**: Convert Flask templates to static SPA

| Task | Priority | Effort |
|------|----------|--------|
| 3.1 Create frontend build pipeline (Vite/Webpack) | HIGH | 1 day |
| 3.2 Convert templates to static HTML + JS | HIGH | 5 days |
| 3.3 Update all API calls to use microservices directly | HIGH | 2 days |
| 3.4 Implement client-side routing | MEDIUM | 1 day |
| 3.5 Create Nginx/static file server container | MEDIUM | 0.5 day |

### Phase 4: Cleanup & Optimization (Week 4-5)
**Goal**: Remove monolith, optimize performance

| Task | Priority | Effort |
|------|----------|--------|
| 4.1 Remove Flask monolith container | HIGH | 1 day |
| 4.2 Remove duplicate code paths | MEDIUM | 2 days |
| 4.3 Add service health checks | MEDIUM | 1 day |
| 4.4 Add API documentation (OpenAPI) | LOW | 2 days |
| 4.5 Performance testing and optimization | MEDIUM | 2 days |

---

## Phase 1 Detailed Implementation

### 1.1 Consolidate Database Models

**Problem**: Models defined in two places:
- `/models.py` (monolith, 1,096 lines)
- `/shared/netstacks_core/db/models.py` (services)

**Solution**:

```bash
# Step 1: Compare models for differences
diff models.py shared/netstacks_core/db/models.py

# Step 2: Merge all models into shared library
# Keep shared/netstacks_core/db/models.py as source of truth

# Step 3: Update monolith imports (temporary, until monolith removed)
# In app.py, database.py, routes/*.py:
# FROM: from models import User, Device, ...
# TO:   from shared.netstacks_core.db.models import User, Device, ...

# Step 4: Delete /models.py
```

**Files to update**:
- `app.py` - Update all model imports
- `database.py` - Update imports
- `routes/*.py` - Update imports in all route files
- `ai/tools/*.py` - Update imports
- `tasks/*.py` - Update imports

### 1.2 Remove Flask Session Auth, Use JWT Only

**Problem**: Dual auth (Flask session + JWT) causing 401 errors

**Current flow**:
```
Login → Flask session created → JWT token issued → Both stored
API call → Check session OR JWT → Confusion about which to use
```

**Target flow**:
```
Login → JWT token issued → Stored in localStorage only
API call → JWT in Authorization header → Validated by service
```

**Changes needed**:

**A. Update `routes/auth.py`**:
```python
# Remove Flask session creation
# Before:
session['username'] = user.username
session['user_id'] = user.id

# After:
# Only return JWT tokens, no session
return jsonify({
    'access_token': access_token,
    'refresh_token': refresh_token,
    'expires_in': 3600,
    'user': {'username': user.username, 'id': user.id}
})
```

**B. Update `login_required` decorator**:
```python
# Before: Checks session first, then JWT
# After: JWT only

from functools import wraps
from flask import request, jsonify
import jwt

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]

        if not token:
            return jsonify({'error': 'Authentication required'}), 401

        try:
            payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
            request.current_user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        return f(*args, **kwargs)
    return decorated
```

**C. Update frontend `api-client.js`**:
```javascript
// Remove all session fallback logic
// Remove cookie-based auth
// Pure JWT only

class NetStacksAPI {
    async login(username, password) {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, password})
        });

        if (!response.ok) throw new Error('Login failed');

        const data = await response.json();
        this.storeTokens(data.access_token, data.refresh_token, data.expires_in);
        return data;
    }

    // Remove session cookie handling
    // Remove hybrid auth mode
}
```

### 1.3 Create Tasks Microservice

**Purpose**: Centralize Celery task management, remove from monolith

**Location**: `/services/tasks/`

**Structure**:
```
services/tasks/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── tasks.py      # Task status, history
│   │   └── workers.py    # Worker info
│   └── services/
│       ├── __init__.py
│       ├── celery_client.py  # Celery interaction
│       └── task_history.py   # Task history storage
```

**Endpoints**:
```
GET  /api/tasks              - List task history
GET  /api/tasks/{task_id}    - Get task status
GET  /api/tasks/{task_id}/result - Get task result
POST /api/tasks/{task_id}/cancel - Cancel task
GET  /api/workers            - List Celery workers
GET  /api/workers/stats      - Worker statistics
```

**Docker Compose addition**:
```yaml
netstacks-tasks:
  build:
    context: .
    dockerfile: services/tasks/Dockerfile
  environment:
    - CELERY_BROKER_URL=redis://redis:6379/0
    - CELERY_RESULT_BACKEND=redis://redis:6379/0
    - JWT_SECRET_KEY=${JWT_SECRET_KEY}
  depends_on:
    - redis
  labels:
    - "traefik.enable=true"
    - "traefik.http.routers.tasks.rule=PathPrefix(`/api/tasks`) || PathPrefix(`/api/workers`)"
    - "traefik.http.routers.tasks.priority=10"
    - "traefik.http.services.tasks.loadbalancer.server.port=8006"
```

### 1.4 Update Traefik Routing

**Current routing** (from docker-compose.yml):
```yaml
# Routes go to monolith by default (priority 1)
# Microservices have priority 10
```

**Updated routing**:
```yaml
# Remove monolith as default
# All routes explicitly mapped to microservices

netstacks-auth:
  labels:
    - "traefik.http.routers.auth.rule=PathPrefix(`/api/auth`) || PathPrefix(`/api/users`) || PathPrefix(`/api/settings`)"
    - "traefik.http.routers.auth.priority=10"

netstacks-devices:
  labels:
    - "traefik.http.routers.devices.rule=PathPrefix(`/api/devices`) || PathPrefix(`/api/credentials`) || PathPrefix(`/api/netbox`)"
    - "traefik.http.routers.devices.priority=10"

netstacks-config:
  labels:
    - "traefik.http.routers.config.rule=PathPrefix(`/api/templates`) || PathPrefix(`/api/service-stacks`) || PathPrefix(`/api/mops`) || PathPrefix(`/api/step-types`)"
    - "traefik.http.routers.config.priority=10"

netstacks-ai:
  labels:
    - "traefik.http.routers.ai.rule=PathPrefix(`/api/agents`) || PathPrefix(`/api/knowledge`)"
    - "traefik.http.routers.ai.priority=10"

netstacks-alerts:
  labels:
    - "traefik.http.routers.alerts.rule=PathPrefix(`/api/alerts`) || PathPrefix(`/api/incidents`) || PathPrefix(`/api/webhooks`)"
    - "traefik.http.routers.alerts.priority=10"

netstacks-tasks:
  labels:
    - "traefik.http.routers.tasks.rule=PathPrefix(`/api/tasks`) || PathPrefix(`/api/workers`)"
    - "traefik.http.routers.tasks.priority=10"

netstacks-backup:
  labels:
    - "traefik.http.routers.backup.rule=PathPrefix(`/api/config-backups`) || PathPrefix(`/api/backup-schedule`) || PathPrefix(`/api/snapshots`)"
    - "traefik.http.routers.backup.priority=10"

netstacks-frontend:
  labels:
    - "traefik.http.routers.frontend.rule=PathPrefix(`/`)"
    - "traefik.http.routers.frontend.priority=1"  # Catch-all for static files
```

---

## Phase 2 Detailed Implementation

### 2.1 Create Alerts Microservice

**Location**: `/services/alerts/`

**Migrate from**:
- `routes/alerts.py` (585 lines)
- `routes/approvals.py` (347 lines)

**Structure**:
```
services/alerts/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── models.py          # Alert, Incident, Approval models
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── alerts.py      # Alert CRUD
│   │   ├── incidents.py   # Incident management
│   │   ├── webhooks.py    # Webhook ingestion
│   │   └── approvals.py   # Approval workflows
│   └── services/
│       ├── __init__.py
│       ├── alert_processor.py   # Alert processing logic
│       ├── incident_correlator.py # Incident correlation
│       └── approval_service.py  # Approval workflow logic
```

**Endpoints**:
```
# Alerts
GET    /api/alerts              - List alerts
POST   /api/alerts              - Create alert (internal)
GET    /api/alerts/{id}         - Get alert
PATCH  /api/alerts/{id}         - Update alert
POST   /api/alerts/{id}/ack     - Acknowledge alert
POST   /api/alerts/{id}/process - Process with AI

# Incidents
GET    /api/incidents           - List incidents
POST   /api/incidents           - Create incident
GET    /api/incidents/{id}      - Get incident
PATCH  /api/incidents/{id}      - Update incident
DELETE /api/incidents/{id}      - Delete incident

# Webhooks (no auth required)
POST   /api/webhooks/generic    - Generic webhook
POST   /api/webhooks/prometheus - Prometheus alertmanager
POST   /api/webhooks/grafana    - Grafana alerts
POST   /api/webhooks/pagerduty  - PagerDuty events

# Approvals
GET    /api/approvals           - List pending approvals
GET    /api/approvals/{id}      - Get approval
POST   /api/approvals/{id}/approve - Approve action
POST   /api/approvals/{id}/reject  - Reject action
```

### 2.2 Create Backup Microservice

**Location**: `/services/backup/`

**Migrate from**:
- `app.py` lines 703-947 (backup execution)
- `app.py` lines 999-1173 (snapshots)
- `routes/api.py` (backup CRUD)

**Structure**:
```
services/backup/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── models.py          # ConfigBackup, ConfigSnapshot models
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── backups.py     # Backup CRUD and execution
│   │   ├── snapshots.py   # Snapshot management
│   │   └── schedule.py    # Backup scheduling
│   └── services/
│       ├── __init__.py
│       ├── backup_executor.py   # Celery task submission
│       ├── snapshot_analyzer.py # Config diff analysis
│       └── schedule_manager.py  # Schedule management
```

**Endpoints**:
```
# Backups
GET    /api/config-backups              - List backups
GET    /api/config-backups/{id}         - Get backup
DELETE /api/config-backups/{id}         - Delete backup
POST   /api/config-backups/run-single   - Run single backup (Celery)
POST   /api/config-backups/run-all      - Run all backups (Celery)
POST   /api/config-backups/run-selected - Run selected backups (Celery)
POST   /api/config-backups/cleanup      - Cleanup old backups
GET    /api/config-backups/task/{id}    - Get backup task status

# Snapshots
GET    /api/snapshots                   - List snapshots
GET    /api/snapshots/{id}              - Get snapshot
PUT    /api/snapshots/{id}              - Update snapshot
DELETE /api/snapshots/{id}              - Delete snapshot
POST   /api/snapshots/{id}/recalculate  - Recalculate diffs
GET    /api/snapshots/{id}/compare/{id2} - Compare two snapshots

# Schedule
GET    /api/backup-schedule             - Get schedule
PUT    /api/backup-schedule             - Update schedule
```

### 2.3 Create WebSocket Microservice

**Location**: `/services/websocket/`

**Migrate from**:
- `routes/agent_websocket.py` (559 lines)
- SocketIO handlers in `app.py`

**Structure**:
```
services/websocket/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── agent_chat.py    # Agent chat handlers
│   │   ├── assistant.py     # Assistant sidebar handlers
│   │   └── live_updates.py  # Dashboard live updates
│   └── services/
│       ├── __init__.py
│       ├── session_manager.py  # WebSocket session management
│       └── redis_pubsub.py     # Redis pub/sub for scaling
```

**Technology**: FastAPI with WebSocket support (or Socket.IO with eventlet)

**Endpoints**:
```
WS /ws/agents/{session_id}    - Agent chat WebSocket
WS /ws/assistant              - Assistant sidebar WebSocket
WS /ws/dashboard              - Dashboard live updates
WS /ws/tasks/{task_id}        - Task progress updates
```

---

## Phase 3 Detailed Implementation

### 3.1 Frontend Architecture

**Option A: Vanilla JS + Build Pipeline (Recommended for minimal changes)**
- Keep existing JS files
- Add Vite/Webpack for bundling
- Convert Jinja2 templates to static HTML

**Option B: React/Vue SPA (More work, better long-term)**
- Rewrite frontend in modern framework
- Better state management
- Component reusability

**Recommended: Option A** for faster migration, consider Option B later.

### 3.2 Template Conversion

**Current**: Jinja2 templates with server-side rendering

**Target**: Static HTML loaded from Nginx, data fetched via API

**Example conversion**:

**Before (Jinja2)**:
```html
<!-- templates/index.html -->
{% extends "base.html" %}
{% block content %}
<h1>Welcome {{ session.username }}</h1>
<div id="agents-count">{{ agents_count }}</div>
{% endblock %}
```

**After (Static HTML)**:
```html
<!-- frontend/public/index.html -->
<!DOCTYPE html>
<html>
<head>
  <title>NetStacks</title>
  <link rel="stylesheet" href="/css/style.css">
</head>
<body>
  <div id="app">
    <h1>Welcome <span id="username"></span></h1>
    <div id="agents-count">Loading...</div>
  </div>
  <script type="module" src="/js/main.js"></script>
</body>
</html>
```

```javascript
// frontend/src/js/main.js
import { NetStacksAPI } from './api-client.js';

const api = new NetStacksAPI();

async function init() {
  // Check auth
  if (!api.isAuthenticated()) {
    window.location.href = '/login.html';
    return;
  }

  // Load user info
  const user = await api.get('/api/auth/me');
  document.getElementById('username').textContent = user.username;

  // Load dashboard data
  const stats = await api.get('/api/platform/stats');
  document.getElementById('agents-count').textContent = stats.agents_count;
}

init();
```

### 3.3 Frontend Service Container

```dockerfile
# frontend/Dockerfile
FROM nginx:alpine

# Copy static files
COPY frontend/dist/ /usr/share/nginx/html/

# Copy nginx config
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
```

```nginx
# frontend/nginx.conf
server {
    listen 80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    # SPA routing - serve index.html for all routes
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

---

## New Services Summary

| Service | Port | Responsibility | New/Existing |
|---------|------|----------------|--------------|
| **auth** | 8011 | Authentication, users, settings | Existing (enhance) |
| **devices** | 8004 | Device management, NetBox | Existing (enhance) |
| **config** | 8002 | Templates, stacks, MOPs | Existing (enhance) |
| **ai** | 8003 | Agents, knowledge base | Existing (enhance) |
| **alerts** | 8005 | Alerts, incidents, approvals | **NEW** |
| **tasks** | 8006 | Celery task management | **NEW** |
| **backup** | 8007 | Config backups, snapshots | **NEW** |
| **websocket** | 8010 | Real-time WebSocket | **NEW** |
| **frontend** | 3000 | Static files (Nginx) | **NEW** |

---

## Database Migration

### Current: Mixed access patterns
- Monolith: Direct SQLAlchemy access
- Services: Direct SQLAlchemy access
- Potential conflicts and race conditions

### Target: Service-owned data
Each service owns its data domain:

| Service | Tables Owned |
|---------|-------------|
| auth | users, settings, auth_configs |
| devices | devices, credentials, device_overrides |
| config | templates, service_stacks, mops, step_types, scheduled_operations |
| ai | agents, agent_sessions, agent_messages, knowledge_*, llm_providers |
| alerts | alerts, incidents, alert_sources, pending_approvals |
| backup | config_backups, config_snapshots, backup_schedules |
| tasks | task_history (new table) |

### Migration approach:
1. Keep shared PostgreSQL database (simpler)
2. Services access only their owned tables
3. Cross-service data via API calls, not direct DB access

---

## Testing Strategy

### Unit Tests
- Each service has its own test suite
- Mock external dependencies

### Integration Tests
- Test service-to-service communication
- Test Traefik routing
- Test JWT auth flow

### End-to-End Tests
- Test complete user workflows
- Test WebSocket functionality
- Test Celery task execution

---

## Rollback Plan

### Phase 1 Rollback
- Revert model imports
- Re-enable Flask sessions
- Restore original Traefik config

### Phase 2 Rollback
- Keep new services running
- Restore monolith routes
- Update Traefik to route back to monolith

### Phase 3 Rollback
- Restore Flask template rendering
- Re-enable monolith container
- Frontend falls back to server-rendered pages

---

## Success Criteria

- [ ] All 401 errors resolved
- [ ] No Flask monolith container running
- [ ] All API calls go directly to microservices
- [ ] WebSocket functionality working
- [ ] Celery tasks executing correctly
- [ ] Frontend loading from static server
- [ ] JWT authentication working across all services
- [ ] All existing functionality preserved

---

## Timeline Summary

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| Phase 1 | Week 1 | Consolidated models, JWT-only auth, Tasks service |
| Phase 2 | Week 2-3 | Alerts, Backup, WebSocket services |
| Phase 3 | Week 3-4 | Static frontend, remove monolith |
| Phase 4 | Week 4-5 | Cleanup, testing, documentation |

**Total: 4-5 weeks**

---

## Next Steps

1. **Review this plan** and confirm approach
2. **Start Phase 1.1** - Consolidate database models
3. **Create feature branches** for parallel work
4. **Set up CI/CD** for new services

Ready to begin implementation?
