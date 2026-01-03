# Architecture

This document describes the NetStacks system architecture, components, and design patterns.

## System Overview

NetStacks is a Flask-based web application with a modular architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    NetStacks Platform                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Flask Application (app.py)               │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│  │  │  Blueprints │  │  Services   │  │    Utils    │   │   │
│  │  │  routes/*   │  │ services/*  │  │   utils/*   │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│           │                    │                             │
│  ┌────────▼────────┐  ┌───────▼───────┐                     │
│  │    Database     │  │    Celery     │                     │
│  │   PostgreSQL    │  │    Workers    │                     │
│  └─────────────────┘  └───────┬───────┘                     │
│                               │                              │
│                      ┌───────▼───────┐                      │
│                      │     Redis     │                      │
│                      └───────────────┘                      │
└──────────────────────────────────────────────────────────────┘
                               │
                               │ SSH/Netmiko
                               ▼
                      Network Devices
```

## Component Layers

### Presentation Layer

The web interface served by Flask:

| Component | Purpose |
|-----------|---------|
| `templates/` | Jinja2 HTML templates |
| `static/` | CSS, JavaScript, images |
| Flask routes | HTTP request handling |

### Application Layer

Business logic organized into blueprints and services:

#### Blueprints (`routes/`)

Route handlers organized by domain:

| Blueprint | File | Purpose |
|-----------|------|---------|
| `pages_bp` | `pages.py` | Dashboard, deploy, monitor pages |
| `auth_bp` | `auth.py` | Login, logout, password |
| `admin_bp` | `admin.py` | User CRUD, auth config |
| `devices_bp` | `devices.py` | Device CRUD |
| `templates_bp` | `templates.py` | Template management |
| `stacks_bp` | `stacks.py` | Stack operations |
| `mop_bp` | `mop.py` | MOP CRUD and execution |
| `agents_bp` | `agents.py` | AI agent management |
| `settings_bp` | `settings.py` | Settings, LLM providers |
| `api_bp` | `api.py` | General API endpoints |
| `alerts_bp` | `alerts.py` | Alert handling |

#### Services (`services/`)

Business logic separated from routes:

| Service | File | Purpose |
|---------|------|---------|
| `AuthService` | `auth_service.py` | Authentication logic |
| `UserService` | `user_service.py` | User management |
| `SettingsService` | `settings_service.py` | Settings operations |
| `StackService` | `stack_service.py` | Stack business logic |
| `DeviceService` | `device_service.py` | Device operations |
| `PlatformStatsService` | `platform_stats_service.py` | Statistics |

#### Utilities (`utils/`)

Shared utilities and patterns:

| Utility | File | Purpose |
|---------|------|---------|
| Decorators | `decorators.py` | `@handle_exceptions`, `@require_json` |
| Exceptions | `exceptions.py` | Custom exception classes |
| Responses | `responses.py` | `success_response`, `error_response` |

### Data Layer

Database and persistence:

| Component | Purpose |
|-----------|---------|
| `database.py` | SQLAlchemy operations |
| `models.py` | ORM model definitions |
| PostgreSQL | Primary data store |

### Task Layer

Background job processing:

| Component | Purpose |
|-----------|---------|
| `tasks/` | Celery task definitions |
| Celery Workers | Execute background jobs |
| Celery Beat | Scheduled task runner |
| Redis | Message broker & result backend |

## Key Files

```
netstacks/
├── app.py                      # Flask app + Celery endpoints
├── database.py                 # Database operations
├── models.py                   # SQLAlchemy models
├── mop_engine.py               # MOP execution engine
├── netbox_client.py            # Netbox integration
├── auth_ldap.py                # LDAP authentication
├── auth_oidc.py                # OIDC authentication
├── credential_encryption.py    # Credential encryption
├── timezone_utils.py           # Timezone handling
│
├── routes/                     # Flask Blueprints
│   ├── __init__.py             # Blueprint registration
│   ├── auth.py                 # Authentication routes
│   ├── devices.py              # Device routes
│   ├── templates.py            # Template routes
│   └── ...
│
├── services/                   # Business Logic
│   ├── auth_service.py
│   ├── settings_service.py
│   └── ...
│
├── utils/                      # Shared Utilities
│   ├── decorators.py
│   ├── exceptions.py
│   └── responses.py
│
├── tasks/                      # Celery Tasks
│   └── ...
│
└── ai/                         # AI Agent Implementation
    └── ...
```

## Design Patterns

### Blueprint Pattern

Routes are organized into blueprints for modularity:

```python
# routes/devices.py
from flask import Blueprint

devices_bp = Blueprint('devices', __name__)

@devices_bp.route('/api/devices', methods=['GET'])
@login_required
@handle_exceptions
def list_devices():
    devices = db.get_all_devices()
    return success_response(data={'devices': devices})
```

Registration in `routes/__init__.py`:
```python
def register_blueprints(app):
    from .devices import devices_bp
    app.register_blueprint(devices_bp)
```

### Service Layer Pattern

Business logic separated from routes:

```python
# services/device_service.py
class DeviceService:
    def get_all(self, filters=None):
        """Get devices with optional filtering."""
        return db.get_all_devices(filters)

    def test_connection(self, device_id):
        """Test device SSH connectivity."""
        device = db.get_device(device_id)
        return self._connect_and_test(device)
```

Usage in routes:
```python
# routes/devices.py
device_service = DeviceService()

@devices_bp.route('/api/devices/{id}/test')
def test_device(id):
    result = device_service.test_connection(id)
    return success_response(data=result)
```

### Decorator Pattern

Common functionality via decorators:

```python
# utils/decorators.py
def handle_exceptions(func):
    """Catch exceptions and return error responses."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValidationError as e:
            return error_response(str(e), 400)
        except NotFoundError as e:
            return error_response(str(e), 404)
        except Exception as e:
            log.error(f"Unhandled error: {e}")
            return error_response("Internal error", 500)
    return wrapper
```

### Repository Pattern

Database operations abstracted:

```python
# database.py
def get_device(device_id):
    with get_db() as session:
        device = session.query(Device).get(device_id)
        return device.to_dict() if device else None

def create_device(data):
    with get_db() as session:
        device = Device(**data)
        session.add(device)
        session.commit()
        return device.to_dict()
```

## Data Flow

### HTTP Request Flow

```
Client Request
      │
      ▼
┌──────────────┐
│    Flask     │
│   Routing    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Decorators  │ ← @login_required, @handle_exceptions
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Blueprint  │ ← Route handler
│    Route     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Service    │ ← Business logic
│    Layer     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Database   │ ← Data operations
│    Layer     │
└──────┬───────┘
       │
       ▼
   Response
```

### Background Task Flow

```
API Request
      │
      ▼
┌──────────────┐
│   Trigger    │ ← POST /api/config-backups/run-single
│    Task      │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Redis     │ ← Task queued
│    Queue     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Celery     │ ← Task executed
│   Worker     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Device     │ ← SSH connection
│  Operation   │
└──────┬───────┘
       │
       ▼
   Task Result → Redis → API Response
```

## Database Schema

### Core Models

```
┌─────────────────┐       ┌─────────────────┐
│     Device      │       │    Template     │
├─────────────────┤       ├─────────────────┤
│ id              │       │ id              │
│ name            │       │ name            │
│ ip_address      │       │ content         │
│ device_type     │       │ description     │
│ username        │       │ template_type   │
│ password (enc)  │       │ validation_id   │
│ tags            │       │ delete_id       │
└─────────────────┘       └─────────────────┘
         │                         │
         ▼                         ▼
┌─────────────────┐       ┌─────────────────┐
│  ConfigBackup   │       │  ServiceStack   │
├─────────────────┤       ├─────────────────┤
│ id              │       │ id              │
│ device_name     │       │ name            │
│ config_content  │       │ templates       │
│ created_at      │       │ variables       │
└─────────────────┘       └─────────────────┘
```

### AI Models

```
┌─────────────────┐       ┌─────────────────┐
│     Agent       │       │   LLMProvider   │
├─────────────────┤       ├─────────────────┤
│ id              │       │ id              │
│ name            │       │ name            │
│ type            │       │ api_key (enc)   │
│ llm_provider    │◄──────│ base_url        │
│ system_prompt   │       │ default_model   │
│ tools           │       │ is_enabled      │
│ is_active       │       │ is_default      │
└─────────────────┘       └─────────────────┘
         │
         ▼
┌─────────────────┐
│PendingApproval  │
├─────────────────┤
│ id              │
│ agent_id        │
│ action          │
│ status          │
│ created_at      │
└─────────────────┘
```

## Security Architecture

### Authentication Flow

```
┌────────┐     ┌─────────┐     ┌──────────────┐
│ Client │────▶│  Login  │────▶│ Auth Service │
└────────┘     └─────────┘     └──────┬───────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
              ┌──────────┐     ┌──────────┐     ┌──────────┐
              │  Local   │     │   LDAP   │     │   OIDC   │
              │   Auth   │     │   Auth   │     │   Auth   │
              └──────────┘     └──────────┘     └──────────┘
                    │                 │                 │
                    └─────────────────┴─────────────────┘
                                      │
                                      ▼
                              ┌──────────────┐
                              │  JWT Token   │
                              │   Session    │
                              └──────────────┘
```

### Credential Encryption

Sensitive data encrypted at rest:

```python
# credential_encryption.py
from cryptography.fernet import Fernet

def encrypt_credential(value):
    """Encrypt a credential value."""
    f = Fernet(get_encryption_key())
    return f.encrypt(value.encode()).decode()

def decrypt_credential(encrypted):
    """Decrypt a credential value."""
    f = Fernet(get_encryption_key())
    return f.decrypt(encrypted.encode()).decode()
```

## Scalability

### Horizontal Scaling

```
                    ┌─────────────────┐
                    │   Load Balancer │
                    │    (Traefik)    │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   NetStacks 1   │ │   NetStacks 2   │ │   NetStacks 3   │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼────────┐
                    │   PostgreSQL    │
                    │    (Primary)    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │     Redis       │
                    │   (Cluster)     │
                    └─────────────────┘
```

### Worker Scaling

```yaml
# docker-compose.yml
netstacks-workers:
  deploy:
    replicas: 4
```

## Extension Points

### Adding New Routes

1. Create blueprint in `routes/`
2. Register in `routes/__init__.py`
3. Use decorators from `utils/`

### Adding New Services

1. Create service in `services/`
2. Import and use in routes

### Adding MOP Step Types

1. Add method to `mop_engine.py`:
```python
def execute_custom_step(self, step, context):
    """Execute custom step type."""
    # Implementation
    return {"status": "success"}
```

2. Step type auto-discovered by introspection

### Adding LLM Providers

1. Add provider in settings
2. Implement provider client if needed
3. Configure in AI settings

## Next Steps

- [[Developer Guide]] - Extending NetStacks
- [[API Reference]] - API details
- [[Troubleshooting]] - Common issues
