# NetStacks Microservices Refactoring Checklist

## Phase 1: Shared Library

### 1.1 Directory Structure
- [ ] Create `shared/` directory
- [ ] Create `shared/setup.py` (pip installable package)
- [ ] Create `shared/netstacks_core/__init__.py`

### 1.2 Database Models
- [ ] Create `shared/netstacks_core/db/__init__.py`
- [ ] Create `shared/netstacks_core/db/models.py` (migrate from `models.py`)
- [ ] Create `shared/netstacks_core/db/session.py` (session factory)

### 1.3 Authentication Utilities
- [ ] Create `shared/netstacks_core/auth/__init__.py`
- [ ] Create `shared/netstacks_core/auth/jwt.py` (JWT token utilities)
- [ ] Create `shared/netstacks_core/auth/middleware.py` (FastAPI auth middleware)

### 1.4 Shared Utilities
- [ ] Create `shared/netstacks_core/utils/__init__.py`
- [ ] Create `shared/netstacks_core/utils/encryption.py` (from `credential_encryption.py`)
- [ ] Create `shared/netstacks_core/utils/timezone.py` (from `timezone_utils.py`)
- [ ] Create `shared/netstacks_core/utils/datetime.py` (from `datetime_utils.py`)
- [ ] Create `shared/netstacks_core/utils/responses.py` (standardized API responses)

### 1.5 Configuration
- [ ] Create `shared/netstacks_core/config.py` (Pydantic settings)

---

## Phase 2: Auth Service (Port 8011)

### 2.1 Service Structure
- [ ] Create `services/auth/` directory
- [ ] Create `services/auth/Dockerfile`
- [ ] Create `services/auth/requirements.txt`
- [ ] Create `services/auth/app/__init__.py`
- [ ] Create `services/auth/app/main.py` (FastAPI app)
- [ ] Create `services/auth/app/config.py`

### 2.2 Routes
- [ ] Create `services/auth/app/routes/__init__.py`
- [ ] Create `services/auth/app/routes/auth.py` (login, logout, refresh, me)
- [ ] Create `services/auth/app/routes/users.py` (user CRUD)
- [ ] Create `services/auth/app/routes/settings.py` (system settings)
- [ ] Create `services/auth/app/routes/config.py` (auth configs - LDAP, OIDC)

### 2.3 Services
- [ ] Create `services/auth/app/services/__init__.py`
- [ ] Create `services/auth/app/services/auth_service.py` (from `services/auth_service.py`)
- [ ] Create `services/auth/app/services/user_service.py` (from `services/user_service.py`)
- [ ] Create `services/auth/app/services/settings_service.py` (from `services/settings_service.py`)
- [ ] Create `services/auth/app/services/ldap_service.py` (from `auth_ldap.py`)
- [ ] Create `services/auth/app/services/oidc_service.py` (from `auth_oidc.py`)

### 2.4 Schemas
- [ ] Create `services/auth/app/schemas/__init__.py`
- [ ] Create `services/auth/app/schemas/auth.py` (login request/response)
- [ ] Create `services/auth/app/schemas/users.py` (user request/response)
- [ ] Create `services/auth/app/schemas/settings.py` (settings request/response)

### 2.5 Testing
- [ ] Test `/api/auth/login` endpoint
- [ ] Test `/api/auth/refresh` endpoint
- [ ] Test `/api/auth/me` endpoint
- [ ] Test `/api/auth/users` CRUD
- [ ] Test `/api/settings/settings` GET/PUT
- [ ] Test LDAP authentication
- [ ] Test OIDC authentication

---

## Phase 3: Devices Service (Port 8004)

### 3.1 Service Structure
- [ ] Create `services/devices/` directory
- [ ] Create `services/devices/Dockerfile`
- [ ] Create `services/devices/requirements.txt`
- [ ] Create `services/devices/app/__init__.py`
- [ ] Create `services/devices/app/main.py`
- [ ] Create `services/devices/app/config.py`

### 3.2 Routes
- [ ] Create `services/devices/app/routes/__init__.py`
- [ ] Create `services/devices/app/routes/devices.py` (device CRUD, test)
- [ ] Create `services/devices/app/routes/credentials.py` (credential CRUD)
- [ ] Create `services/devices/app/routes/backups.py` (snapshots, device backups)

### 3.3 Services
- [ ] Create `services/devices/app/services/__init__.py`
- [ ] Create `services/devices/app/services/device_service.py` (from `services/device_service.py`)
- [ ] Create `services/devices/app/services/netbox_service.py` (from `netbox_client.py`)
- [ ] Create `services/devices/app/services/backup_service.py` (backup logic from `database.py`)

### 3.4 Schemas
- [ ] Create `services/devices/app/schemas/__init__.py`
- [ ] Create `services/devices/app/schemas/devices.py`
- [ ] Create `services/devices/app/schemas/credentials.py`
- [ ] Create `services/devices/app/schemas/backups.py`

### 3.5 Testing
- [ ] Test `/api/devices` CRUD
- [ ] Test `/api/devices/{id}/test` connectivity
- [ ] Test `/api/credentials` CRUD
- [ ] Test `/api/backups/snapshots` CRUD
- [ ] Test `/api/backups/devices/{name}` history
- [ ] Test `/api/backups/schedule` GET/PUT

---

## Phase 4: Config Service (Port 8002)

### 4.1 Service Structure
- [ ] Create `services/config/` directory
- [ ] Create `services/config/Dockerfile`
- [ ] Create `services/config/requirements.txt`
- [ ] Create `services/config/app/__init__.py`
- [ ] Create `services/config/app/main.py`
- [ ] Create `services/config/app/config.py`

### 4.2 Routes
- [ ] Create `services/config/app/routes/__init__.py`
- [ ] Create `services/config/app/routes/templates.py` (template CRUD, render)
- [ ] Create `services/config/app/routes/stacks.py` (stack CRUD, deploy)
- [ ] Create `services/config/app/routes/mops.py` (MOP CRUD, execute)
- [ ] Create `services/config/app/routes/schedules.py` (scheduled operations)

### 4.3 Services
- [ ] Create `services/config/app/services/__init__.py`
- [ ] Create `services/config/app/services/template_service.py`
- [ ] Create `services/config/app/services/stack_service.py` (from `services/stack_service.py`)
- [ ] Create `services/config/app/services/mop_service.py`

### 4.4 MOP Engine
- [ ] Create `services/config/app/engine/__init__.py`
- [ ] Create `services/config/app/engine/mop_engine.py` (from `mop_engine.py`)

### 4.5 Schemas
- [ ] Create `services/config/app/schemas/__init__.py`
- [ ] Create `services/config/app/schemas/templates.py`
- [ ] Create `services/config/app/schemas/stacks.py`
- [ ] Create `services/config/app/schemas/mops.py`

### 4.6 Testing
- [ ] Test `/api/templates` CRUD
- [ ] Test `/api/templates/{id}/render`
- [ ] Test `/api/stacks` CRUD
- [ ] Test `/api/stacks/{id}/deploy`
- [ ] Test `/api/mops` CRUD
- [ ] Test `/api/mops/{id}/execute`
- [ ] Test `/api/mops/{id}/executions`

---

## Phase 5: Workers Package

### 5.1 Structure
- [ ] Create `workers/` directory
- [ ] Create `workers/Dockerfile`
- [ ] Create `workers/requirements.txt`
- [ ] Create `workers/celery_app.py`

### 5.2 Tasks
- [ ] Create `workers/tasks/__init__.py`
- [ ] Create `workers/tasks/device_tasks.py` (get_config, set_config, run_commands)
- [ ] Create `workers/tasks/backup_tasks.py` (backup_device_config, cleanup)
- [ ] Create `workers/tasks/scheduled_tasks.py` (check_scheduled_operations, execute_*)
- [ ] Create `workers/tasks/mop_tasks.py` (MOP execution)

### 5.3 Testing
- [ ] Test device tasks execution
- [ ] Test backup tasks execution
- [ ] Test scheduled task triggers
- [ ] Test MOP task execution

---

## Phase 6: Infrastructure

### 6.1 Docker Compose
- [ ] Update `docker-compose.yml` with Traefik
- [ ] Add auth service container
- [ ] Add config service container
- [ ] Add devices service container
- [ ] Update workers container
- [ ] Configure Traefik routing labels
- [ ] Add health checks to all services

### 6.2 Environment
- [ ] Create/update `.env.example` with new variables
- [ ] Add JWT_SECRET_KEY
- [ ] Configure service ports
- [ ] Configure Traefik settings

### 6.3 Networking
- [ ] Configure Traefik path-based routing
- [ ] Test `/api/auth/*` routes to auth service
- [ ] Test `/api/devices/*` routes to devices service
- [ ] Test `/api/templates/*` routes to config service
- [ ] Test `/api/stacks/*` routes to config service
- [ ] Test `/api/mops/*` routes to config service

---

## Phase 7: Integration Testing

### 7.1 Auth Flow
- [ ] Test login → get JWT token
- [ ] Test authenticated request to devices service
- [ ] Test authenticated request to config service
- [ ] Test token refresh flow
- [ ] Test invalid/expired token rejection

### 7.2 Cross-Service
- [ ] Test stack deployment (config → workers → devices)
- [ ] Test MOP execution (config → workers → devices)
- [ ] Test backup creation (devices → workers)
- [ ] Test scheduled operation execution

### 7.3 Data Migration
- [ ] Verify existing data accessible via new APIs
- [ ] Test CRUD operations don't corrupt data
- [ ] Verify backup compatibility

---

## Phase 8: Cleanup

### 8.1 Deprecation
- [ ] Mark old Flask routes as deprecated
- [ ] Update Flask templates to call new APIs
- [ ] Remove duplicate code from monolith
- [ ] Update documentation

### 8.2 Documentation
- [ ] Document new API endpoints
- [ ] Update README with new architecture
- [ ] Document deployment process
- [ ] Create API migration guide

---

## Future: AI Service (Port 8003)

### AI Service Structure (after microservices complete)
- [ ] Create `services/ai/` directory
- [ ] Create `services/ai/app/routes/agents.py`
- [ ] Create `services/ai/app/routes/alerts.py`
- [ ] Create `services/ai/app/routes/incidents.py`
- [ ] Create `services/ai/app/routes/knowledge.py`
- [ ] Create `services/ai/app/routes/tools.py`
- [ ] Add pgvector extension to PostgreSQL
- [ ] Implement agent execution engine
- [ ] Implement RAG/knowledge base
- [ ] Implement alert intake webhooks

---

## Progress Summary

| Phase | Status | Completion |
|-------|--------|------------|
| Phase 1: Shared Library | Not Started | 0% |
| Phase 2: Auth Service | Not Started | 0% |
| Phase 3: Devices Service | Not Started | 0% |
| Phase 4: Config Service | Not Started | 0% |
| Phase 5: Workers Package | Not Started | 0% |
| Phase 6: Infrastructure | Not Started | 0% |
| Phase 7: Integration Testing | Not Started | 0% |
| Phase 8: Cleanup | Not Started | 0% |
| **Overall** | **Not Started** | **0%** |
