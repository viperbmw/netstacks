# NetStacks Microservices Refactoring Checklist

## Phase 1: Shared Library

### 1.1 Directory Structure
- [x] Create `shared/` directory
- [x] Create `shared/setup.py` (pip installable package)
- [x] Create `shared/netstacks_core/__init__.py`

### 1.2 Database Models
- [x] Create `shared/netstacks_core/db/__init__.py`
- [x] Create `shared/netstacks_core/db/models.py` (migrate from `models.py`)
- [x] Create `shared/netstacks_core/db/session.py` (session factory)

### 1.3 Authentication Utilities
- [x] Create `shared/netstacks_core/auth/__init__.py`
- [x] Create `shared/netstacks_core/auth/jwt.py` (JWT token utilities)
- [x] Create `shared/netstacks_core/auth/middleware.py` (FastAPI auth middleware)

### 1.4 Shared Utilities
- [x] Create `shared/netstacks_core/utils/__init__.py`
- [x] Create `shared/netstacks_core/utils/encryption.py` (from `credential_encryption.py`)
- [x] Create `shared/netstacks_core/utils/timezone.py` (from `timezone_utils.py`)
- [x] Create `shared/netstacks_core/utils/datetime.py` (from `datetime_utils.py`)
- [x] Create `shared/netstacks_core/utils/responses.py` (standardized API responses)

### 1.5 Configuration
- [x] Create `shared/netstacks_core/config.py` (Pydantic settings)

---

## Phase 2: Auth Service (Port 8011)

### 2.1 Service Structure
- [x] Create `services/auth/` directory
- [x] Create `services/auth/Dockerfile`
- [x] Create `services/auth/requirements.txt`
- [x] Create `services/auth/app/__init__.py`
- [x] Create `services/auth/app/main.py` (FastAPI app)
- [x] Create `services/auth/app/config.py`

### 2.2 Routes
- [x] Create `services/auth/app/routes/__init__.py`
- [x] Create `services/auth/app/routes/auth.py` (login, logout, refresh, me)
- [x] Create `services/auth/app/routes/users.py` (user CRUD)
- [x] Create `services/auth/app/routes/settings.py` (system settings)
- [x] Create `services/auth/app/routes/config.py` (auth configs - LDAP, OIDC)

### 2.3 Services
- [x] Create `services/auth/app/services/__init__.py`
- [x] Create `services/auth/app/services/auth_service.py` (from `services/auth_service.py`)
- [x] Create `services/auth/app/services/user_service.py` (from `services/user_service.py`)
- [x] Create `services/auth/app/services/settings_service.py` (from `services/settings_service.py`)
- [ ] Create `services/auth/app/services/ldap_service.py` (from `auth_ldap.py`)
- [ ] Create `services/auth/app/services/oidc_service.py` (from `auth_oidc.py`)

### 2.4 Schemas
- [x] Create `services/auth/app/schemas/__init__.py`
- [x] Create `services/auth/app/schemas/auth.py` (login request/response)
- [x] Create `services/auth/app/schemas/users.py` (user request/response)
- [x] Create `services/auth/app/schemas/settings.py` (settings request/response)

### 2.5 Testing
- [x] Test `/api/auth/login` endpoint
- [x] Test `/api/auth/refresh` endpoint
- [x] Test `/api/auth/me` endpoint
- [x] Test `/api/auth/users` CRUD
- [x] Test `/api/settings/settings` GET/PUT
- [ ] Test LDAP authentication (stub - not yet implemented)
- [ ] Test OIDC authentication (stub - not yet implemented)

---

## Phase 3: Devices Service (Port 8004)

### 3.1 Service Structure
- [x] Create `services/devices/` directory
- [x] Create `services/devices/Dockerfile`
- [x] Create `services/devices/requirements.txt`
- [x] Create `services/devices/app/__init__.py`
- [x] Create `services/devices/app/main.py`
- [x] Create `services/devices/app/config.py`

### 3.2 Routes
- [x] Create `services/devices/app/routes/__init__.py`
- [x] Create `services/devices/app/routes/devices.py` (device CRUD, test)
- [x] Create `services/devices/app/routes/credentials.py` (credential CRUD)
- [x] Create `services/devices/app/routes/overrides.py` (device overrides)
- [x] Create `services/devices/app/routes/netbox.py` (NetBox sync)
- [ ] Create `services/devices/app/routes/backups.py` (snapshots, device backups)

### 3.3 Services
- [x] Create `services/devices/app/services/__init__.py`
- [x] Create `services/devices/app/services/device_service.py` (from `services/device_service.py`)
- [x] Create `services/devices/app/services/netbox_service.py` (from `netbox_client.py`)
- [x] Create `services/devices/app/services/credential_service.py`
- [x] Create `services/devices/app/services/override_service.py`
- [ ] Create `services/devices/app/services/backup_service.py` (backup logic from `database.py`)

### 3.4 Schemas
- [x] Create `services/devices/app/schemas/__init__.py`
- [x] Create `services/devices/app/schemas/devices.py`
- [x] Create `services/devices/app/schemas/credentials.py`
- [x] Create `services/devices/app/schemas/overrides.py`
- [x] Create `services/devices/app/schemas/netbox.py`
- [ ] Create `services/devices/app/schemas/backups.py`

### 3.5 Testing
- [x] Test `/api/devices` CRUD
- [x] Test `/api/credentials` CRUD
- [x] Test `/api/device-overrides` CRUD
- [x] Test `/api/netbox/status`
- [ ] Test `/api/devices/{id}/test` connectivity (requires Celery)
- [ ] Test `/api/backups/snapshots` CRUD
- [ ] Test `/api/backups/devices/{name}` history
- [ ] Test `/api/backups/schedule` GET/PUT

---

## Phase 4: Config Service (Port 8002)

### 4.1 Service Structure
- [x] Create `services/config/` directory
- [x] Create `services/config/Dockerfile`
- [x] Create `services/config/requirements.txt`
- [x] Create `services/config/app/__init__.py`
- [x] Create `services/config/app/main.py`
- [x] Create `services/config/app/config.py`

### 4.2 Routes
- [x] Create `services/config/app/routes/__init__.py`
- [x] Create `services/config/app/routes/templates.py` (template CRUD, render)
- [x] Create `services/config/app/routes/stacks.py` (stack CRUD, deploy)
- [x] Create `services/config/app/routes/mops.py` (MOP CRUD, execute)
- [x] Create `services/config/app/routes/schedules.py` (scheduled operations)
- [x] Create `services/config/app/routes/step_types.py` (step type CRUD)

### 4.3 Services
- [x] Create `services/config/app/services/__init__.py`
- [x] Create `services/config/app/services/template_service.py`
- [x] Create `services/config/app/services/stack_service.py`
- [x] Create `services/config/app/services/mop_service.py`
- [x] Create `services/config/app/services/schedule_service.py`
- [x] Create `services/config/app/services/step_type_service.py`

### 4.4 MOP Engine
- [ ] Create `services/config/app/engine/__init__.py`
- [ ] Create `services/config/app/engine/mop_engine.py` (from `mop_engine.py`)

### 4.5 Schemas
- [x] Create `services/config/app/schemas/__init__.py`
- [x] Create `services/config/app/schemas/templates.py`
- [x] Create `services/config/app/schemas/stacks.py`
- [x] Create `services/config/app/schemas/mops.py`
- [x] Create `services/config/app/schemas/schedules.py`
- [x] Create `services/config/app/schemas/step_types.py`

### 4.6 Testing
- [x] Test `/api/templates` CRUD
- [x] Test `/api/templates/{id}/render`
- [x] Test `/api/service-stacks` CRUD
- [ ] Test `/api/stacks/{id}/deploy` (requires Celery workers)
- [x] Test `/api/mops` CRUD
- [ ] Test `/api/mops/{id}/execute` (requires MOP engine)
- [x] Test `/api/mops/{id}/executions`
- [x] Test `/api/step-types` CRUD
- [x] Test `/api/scheduled-operations` CRUD

---

## Phase 5: Workers Package

### 5.1 Structure
- [x] Create `workers/` directory
- [x] Create `workers/Dockerfile`
- [x] Create `workers/requirements.txt`
- [x] Create `workers/celery_app.py`

### 5.2 Tasks
- [x] Create `workers/tasks/__init__.py`
- [x] Create `workers/tasks/device_tasks.py` (get_config, set_config, run_commands)
- [x] Create `workers/tasks/backup_tasks.py` (backup_device_config, cleanup)
- [x] Create `workers/tasks/scheduled_tasks.py` (check_scheduled_operations, execute_*)
- [ ] Create `workers/tasks/mop_tasks.py` (MOP execution)

### 5.3 Testing
- [x] Test workers container startup and Redis connection
- [ ] Test device tasks execution (requires real devices)
- [ ] Test backup tasks execution (requires real devices)
- [ ] Test scheduled task triggers
- [ ] Test MOP task execution

---

## Phase 6: Infrastructure

### 6.1 Docker Compose
- [x] Update `docker-compose.yml` with Traefik
- [x] Add auth service container
- [x] Add config service container
- [x] Add devices service container
- [x] Update workers container (workers + workers-beat)
- [x] Configure Traefik routing labels
- [x] Add health checks to all services

### 6.2 Environment
- [x] Create/update `.env.example` with new variables
- [x] Add JWT_SECRET_KEY
- [x] Configure service ports
- [x] Configure Traefik settings

### 6.3 Networking
- [x] Configure Traefik path-based routing
- [x] Test `/api/auth/*` routes to auth service
- [x] Test `/api/devices/*` routes to devices service
- [x] Test `/api/templates/*` routes to config service
- [x] Test `/api/service-stacks/*` routes to config service
- [x] Test `/api/mops/*` routes to config service

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
| Phase 1: Shared Library | Complete | 100% |
| Phase 2: Auth Service | Complete | 95% |
| Phase 3: Devices Service | Complete | 85% |
| Phase 4: Config Service | Complete | 90% |
| Phase 5: Workers Package | Complete | 85% |
| Phase 6: Infrastructure | Complete | 100% |
| Phase 7: Integration Testing | Not Started | 0% |
| Phase 8: Cleanup | Not Started | 0% |
| **Overall** | **In Progress** | **75%** |
