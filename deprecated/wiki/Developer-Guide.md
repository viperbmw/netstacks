# Developer Guide

This guide covers extending and contributing to NetStacks.

## Development Setup

### Prerequisites

- Python 3.10+
- Docker and Docker Compose
- Git
- PostgreSQL (for local development)
- Redis (for local development)

### Local Development

```bash
# Clone repository
git clone https://github.com/viperbmw/netstacks.git
cd netstacks

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://netstacks:password@localhost:5432/netstacks"
export REDIS_URL="redis://localhost:6379/0"
export SECRET_KEY="dev-secret-key"
export JWT_SECRET_KEY="dev-jwt-secret"

# Run Flask
python app.py
```

### Docker Development

```bash
# Build and run
docker-compose up -d --build

# View logs
docker-compose logs -f netstacks

# Rebuild after changes
docker-compose build netstacks
docker-compose up -d netstacks
```

## Project Structure

```
netstacks/
├── app.py                  # Application entry point
├── routes/                 # Flask blueprints
│   ├── __init__.py         # Blueprint registration
│   ├── auth.py             # Authentication routes
│   ├── devices.py          # Device routes
│   └── ...
├── services/               # Business logic
│   ├── auth_service.py
│   └── ...
├── utils/                  # Shared utilities
│   ├── decorators.py
│   ├── exceptions.py
│   └── responses.py
├── models.py               # SQLAlchemy models
├── database.py             # Database operations
├── templates/              # Jinja2 templates
├── static/                 # Static assets
└── tests/                  # Test files
```

## Adding New Features

### Adding a New Route

1. Create or edit a blueprint file:

```python
# routes/myfeature.py
from flask import Blueprint, jsonify, request
from routes.auth import login_required
from utils.decorators import handle_exceptions, require_json
from utils.responses import success_response, error_response
from utils.exceptions import ValidationError, NotFoundError

myfeature_bp = Blueprint('myfeature', __name__)

@myfeature_bp.route('/api/myfeature', methods=['GET'])
@login_required
@handle_exceptions
def list_items():
    """List all items."""
    items = db.get_all_items()
    return success_response(data={'items': items})

@myfeature_bp.route('/api/myfeature', methods=['POST'])
@login_required
@handle_exceptions
@require_json
def create_item():
    """Create a new item."""
    data = request.get_json()

    if not data.get('name'):
        raise ValidationError('Name is required')

    item = db.create_item(data)
    return success_response(data={'item': item}, message='Item created')

@myfeature_bp.route('/api/myfeature/<item_id>', methods=['GET'])
@login_required
@handle_exceptions
def get_item(item_id):
    """Get a specific item."""
    item = db.get_item(item_id)
    if not item:
        raise NotFoundError(f'Item not found: {item_id}')
    return success_response(data={'item': item})
```

2. Register the blueprint:

```python
# routes/__init__.py
from .myfeature import myfeature_bp

def register_blueprints(app):
    # ... existing blueprints
    app.register_blueprint(myfeature_bp)
```

### Adding a Service

Create a service class for complex business logic:

```python
# services/myfeature_service.py
import logging
from database import get_db
from models import MyModel

log = logging.getLogger(__name__)

class MyFeatureService:
    """Service for my feature operations."""

    def get_all(self, filters=None):
        """Get all items with optional filters."""
        with get_db() as session:
            query = session.query(MyModel)
            if filters:
                if filters.get('status'):
                    query = query.filter(MyModel.status == filters['status'])
            return [item.to_dict() for item in query.all()]

    def create(self, data):
        """Create a new item."""
        with get_db() as session:
            item = MyModel(
                name=data['name'],
                description=data.get('description', '')
            )
            session.add(item)
            session.commit()
            return item.to_dict()

    def process(self, item_id):
        """Process an item (complex business logic)."""
        item = self.get(item_id)
        if not item:
            raise ValueError(f'Item not found: {item_id}')

        # Complex processing logic here
        result = self._do_processing(item)

        self._update_status(item_id, 'processed')
        return result

    def _do_processing(self, item):
        """Internal processing method."""
        log.info(f"Processing item: {item['name']}")
        # Implementation
        return {'status': 'processed'}
```

Use in routes:
```python
# routes/myfeature.py
from services.myfeature_service import MyFeatureService

myfeature_service = MyFeatureService()

@myfeature_bp.route('/api/myfeature/<item_id>/process', methods=['POST'])
@login_required
@handle_exceptions
def process_item(item_id):
    result = myfeature_service.process(item_id)
    return success_response(data=result)
```

### Adding a Database Model

1. Define the model:

```python
# models.py
class MyModel(Base):
    __tablename__ = 'my_models'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    description = Column(Text)
    status = Column(String(20), default='pending')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
```

2. Add database operations:

```python
# database.py
def get_all_items(filters=None):
    with get_db() as session:
        query = session.query(MyModel)
        # Apply filters
        return [item.to_dict() for item in query.all()]

def create_item(data):
    with get_db() as session:
        item = MyModel(**data)
        session.add(item)
        session.commit()
        return item.to_dict()

def get_item(item_id):
    with get_db() as session:
        item = session.query(MyModel).get(item_id)
        return item.to_dict() if item else None
```

### Adding a Celery Task

```python
# tasks/myfeature_tasks.py
from celery import shared_task
import logging

log = logging.getLogger(__name__)

@shared_task(bind=True)
def process_item_async(self, item_id):
    """Process an item asynchronously."""
    try:
        log.info(f"Processing item: {item_id}")

        # Get item
        item = db.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        # Process
        result = do_processing(item)

        # Update status
        db.update_item(item_id, {'status': 'completed'})

        return {'success': True, 'result': result}

    except Exception as e:
        log.error(f"Error processing item {item_id}: {e}")
        db.update_item(item_id, {'status': 'failed', 'error': str(e)})
        raise
```

Trigger from route:
```python
@myfeature_bp.route('/api/myfeature/<item_id>/process-async', methods=['POST'])
@login_required
@handle_exceptions
def process_item_async(item_id):
    from tasks.myfeature_tasks import process_item_async

    task = process_item_async.delay(item_id)
    return success_response(data={'task_id': task.id})
```

### Adding MOP Step Types

Add a new step type to the MOP engine:

```python
# mop_engine.py
class MOPEngine:
    # ... existing code

    def execute_my_step(self, step, context):
        """
        Execute my custom step type.

        Parameters:
            - param1: First parameter
            - param2: Second parameter (optional)

        Returns:
            Step result dict
        """
        param1 = step.get('param1')
        param2 = step.get('param2', 'default')

        if not param1:
            return {
                'status': 'error',
                'error': 'param1 is required'
            }

        try:
            # Implementation
            result = self._process_my_step(param1, param2)

            return {
                'status': 'success',
                'output': result
            }

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
```

Step type is auto-discovered and available in Visual Builder.

## Custom Decorators

Create custom decorators:

```python
# utils/decorators.py
from functools import wraps
from flask import request

def require_admin(func):
    """Require admin role for route."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if 'admin' not in user.get('roles', []):
            return error_response('Admin access required', 403)
        return func(*args, **kwargs)
    return wrapper

def rate_limit(max_requests=100, window_seconds=60):
    """Rate limit decorator."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"rate_limit:{request.remote_addr}:{func.__name__}"
            current = redis.incr(key)
            if current == 1:
                redis.expire(key, window_seconds)
            if current > max_requests:
                return error_response('Rate limit exceeded', 429)
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

## Custom Exceptions

Add custom exceptions:

```python
# utils/exceptions.py
class MyCustomError(Exception):
    """Custom error for my feature."""

    def __init__(self, message, code=None, details=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
```

Handle in decorator:
```python
# utils/decorators.py
def handle_exceptions(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except MyCustomError as e:
            return error_response(
                e.message,
                400,
                details={'code': e.code, **e.details}
            )
        # ... other exceptions
    return wrapper
```

## Testing

### Unit Tests

```python
# tests/test_myfeature.py
import pytest
from services.myfeature_service import MyFeatureService

class TestMyFeatureService:
    def setup_method(self):
        self.service = MyFeatureService()

    def test_create_item(self, db_session):
        data = {'name': 'Test Item', 'description': 'Test'}
        result = self.service.create(data)

        assert result['name'] == 'Test Item'
        assert result['id'] is not None

    def test_get_item_not_found(self, db_session):
        result = self.service.get('nonexistent')
        assert result is None
```

### Integration Tests

```python
# tests/test_api_myfeature.py
import pytest
from app import app

class TestMyFeatureAPI:
    def setup_method(self):
        self.client = app.test_client()
        # Login and get token

    def test_list_items(self):
        response = self.client.get('/api/myfeature')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_myfeature.py

# Run with coverage
pytest --cov=. --cov-report=html
```

## Code Style

### Python Style

- Follow PEP 8
- Use type hints where helpful
- Document public methods with docstrings
- Use logging, not print statements

```python
def process_item(item_id: str, options: dict = None) -> dict:
    """
    Process an item with the given options.

    Args:
        item_id: The item identifier
        options: Optional processing options

    Returns:
        Processing result dictionary

    Raises:
        NotFoundError: If item doesn't exist
        ValidationError: If options are invalid
    """
    log.info(f"Processing item: {item_id}")
    # Implementation
```

### Route Style

- Use RESTful conventions
- Return consistent response format
- Use decorators for cross-cutting concerns
- Validate input at route level

### JavaScript Style

- Use modern ES6+ syntax
- Document complex functions
- Handle errors appropriately

## Git Workflow

### Branch Naming

- `feature/description` - New features
- `bugfix/description` - Bug fixes
- `refactor/description` - Code refactoring

### Commit Messages

```
type: short description

Longer description if needed.

- Bullet points for multiple changes
- Reference issues with #123
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

### Pull Request Process

1. Create feature branch
2. Implement changes
3. Write/update tests
4. Update documentation
5. Create pull request
6. Address review feedback
7. Merge when approved

## Documentation

### Code Documentation

- Docstrings for all public methods
- Comments for complex logic
- Type hints for parameters and returns

### Wiki Documentation

- Update relevant wiki pages
- Add new pages for new features
- Include examples

## Troubleshooting Development

### Common Issues

**Import Errors:**
```bash
# Check Python path
echo $PYTHONPATH

# Run from project root
cd netstacks
python -c "from routes import devices_bp"
```

**Database Connection:**
```bash
# Verify PostgreSQL is running
docker-compose ps netstacks-postgres

# Check connection string
echo $DATABASE_URL
```

**Celery Tasks Not Running:**
```bash
# Check worker logs
docker-compose logs netstacks-workers

# Verify Redis connection
redis-cli ping
```

## Next Steps

- [[Architecture]] - System design
- [[API Reference]] - API details
- [[Troubleshooting]] - Common issues
