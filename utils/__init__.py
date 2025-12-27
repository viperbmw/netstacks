"""
NetStacks Utilities Package

Common utilities for API responses, error handling, and route decorators.
"""

from utils.responses import success_response, error_response, paginated_response
from utils.exceptions import (
    NetStacksError,
    NotFoundError,
    ValidationError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ServiceUnavailableError,
    DeviceConnectionError,
    TaskError,
    ConfigurationError
)
from utils.decorators import (
    handle_exceptions,
    require_json,
    validate_request,
    require_auth,
    require_role,
    log_request
)

__all__ = [
    # Response helpers
    'success_response',
    'error_response',
    'paginated_response',
    # Exceptions
    'NetStacksError',
    'NotFoundError',
    'ValidationError',
    'AuthenticationError',
    'AuthorizationError',
    'ConflictError',
    'ServiceUnavailableError',
    'DeviceConnectionError',
    'TaskError',
    'ConfigurationError',
    # Decorators
    'handle_exceptions',
    'require_json',
    'validate_request',
    'require_auth',
    'require_role',
    'log_request',
]
