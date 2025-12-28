# Frontend Migration to Microservices Checklist

This checklist tracks the migration of the Flask frontend to use JWT-based microservices.

## Phase 1: JWT Infrastructure

### 1.1 Microservice Client
- [x] Create `services/microservice_client.py` - JWT HTTP client
- [x] Implement token storage in Flask session
- [x] Implement token refresh logic
- [x] Add service health check methods

### 1.2 Login Integration
- [x] Update Flask login to get JWT from auth microservice
- [x] Store JWT tokens in session (`jwt_access_token`, `jwt_refresh_token`, `jwt_expires_at`)
- [x] Update logout to clear JWT tokens
- [x] Keep existing LDAP/OIDC as fallback

### 1.3 Docker Configuration
- [x] Add `AUTH_SERVICE_URL` environment variable
- [x] Add `DEVICES_SERVICE_URL` environment variable
- [x] Add `CONFIG_SERVICE_URL` environment variable

**Test**: Login works, JWT stored in session
- [x] Login as admin
- [x] Verify session contains JWT tokens (check container logs)

---

## Phase 2: Platform Health Page

### 2.1 Health API Endpoint
- [x] Add `/api/platform/health` endpoint to `routes/api.py`
- [x] Return status of all microservices
- [x] Include Redis, PostgreSQL, Celery worker status

### 2.2 Platform Health UI
- [x] Create `templates/platform.html`
- [x] Add route `/platform` to `routes/pages.py`
- [x] Add "Platform Health" to Settings dropdown menu
- [x] Auto-refresh every 30 seconds
- [x] Show architecture diagram

**Test**: Platform health page works
- [ ] Navigate to Settings > Platform Health
- [ ] Verify all services show as healthy
- [ ] Verify auto-refresh works

---

## Phase 3: Auth Service Proxy (OPTIONAL - Future)

### 3.1 Proxy Auth Endpoints
- [ ] Proxy `/api/auth/configs` → auth:8011
- [ ] Proxy `/api/auth/config/<type>` → auth:8011
- [ ] Proxy `/api/users` → auth:8011

### 3.2 Proxy Settings Endpoints
- [ ] Proxy `/api/settings` → auth:8011
- [ ] Proxy `/api/menu-items` → auth:8011

**Test**: Users page, Settings page work via microservice

---

## Phase 4: Devices Service Proxy (OPTIONAL - Future)

- [ ] Proxy `/api/devices` → devices:8004
- [ ] Proxy `/api/manual-devices` → devices:8004
- [ ] Proxy `/api/device-overrides` → devices:8004
- [ ] Proxy `/api/credentials` → devices:8004

**Test**: Devices page CRUD works via microservice

---

## Phase 5: Config Service Proxy (OPTIONAL - Future)

### 5.1 Templates
- [ ] Proxy `/api/v2/templates` → config:8002
- [ ] Proxy `/api/templates/<name>/render` → config:8002

### 5.2 MOPs
- [ ] Proxy `/api/mops` → config:8002
- [ ] Proxy `/api/step-types` → config:8002

### 5.3 Service Stacks
- [ ] Proxy `/api/service-stacks` → config:8002
- [ ] Proxy `/api/scheduled-operations` → config:8002

**Test**: Templates, MOPs, Stacks pages work via microservice

---

## Phase 6: Menu Consolidation (OPTIONAL - Future)

### New Menu Structure:
```
Dashboard
Operations ▼
  - Deploy Config
  - Monitor Jobs
  - Procedures (MOP)
Configuration ▼
  - Templates
  - Service Stacks
  - Devices
  - Snapshots
AI ▼ (placeholder for future)
  - Agents
  - Incidents
  - Knowledge
Settings ▼
  - Users & Auth
  - System Settings
  - Platform Health  ← DONE
  - MOP Step Types
  - API Docs
```

- [ ] Add parent/child menu item support
- [ ] Update base.html template
- [ ] Update DEFAULT_MENU_ITEMS in models.py

---

## Phase 7: Enable Traefik Routing (OPTIONAL - Future)

- [ ] Re-enable Traefik labels for auth service
- [ ] Re-enable Traefik labels for devices service
- [ ] Re-enable Traefik labels for config service
- [ ] Set priority=10 for microservices (higher than Flask's 1)

**Test**: All pages still work with direct microservice routing

---

## Phase 8: Final Testing

### Full Test Suite:
- [ ] Login/logout flow
- [ ] Device CRUD (create, read, update, delete)
- [ ] Template CRUD and rendering
- [ ] MOP creation and viewing
- [ ] Service stack management
- [ ] User management
- [ ] Settings persistence
- [x] Platform health page
- [ ] Menu navigation
- [ ] Session timeout handling

---

## Files Modified

| File | Status | Changes |
|------|--------|---------|
| `services/microservice_client.py` | DONE | NEW - JWT HTTP client |
| `routes/auth.py` | DONE | Add JWT on login |
| `routes/api.py` | DONE | Add platform health endpoint |
| `routes/pages.py` | DONE | Add platform page route |
| `templates/base.html` | DONE | Add Platform Health menu item |
| `templates/platform.html` | DONE | NEW - health page |
| `docker-compose.yml` | DONE | Add microservice URL env vars |

---

## Current Status

| Component | Status |
|-----------|--------|
| Microservice Client | Completed |
| JWT Login Integration | Completed |
| Platform Health Page | Completed |
| Auth Service Proxy | Not Started (Optional) |
| Devices Service Proxy | Not Started (Optional) |
| Config Service Proxy | Not Started (Optional) |
| Menu Consolidation | Not Started (Optional) |
| Traefik Routing | Not Started (Optional) |

**Overall Progress**: Phase 1-2 Complete (Core Infrastructure)

The platform is now running with:
- Flask frontend serving all UI pages
- Microservices running and healthy
- Platform Health page showing service status
- JWT tokens obtained on login for future API proxy use
