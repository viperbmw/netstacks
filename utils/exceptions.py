"""
Custom Exception Classes for NetStacks

Provides a hierarchy of exceptions for consistent error handling across the API.
"""

from typing import Optional, Dict, Any


class NetStacksError(Exception):
    """
    Base exception for all NetStacks errors.

    Attributes:
        message: Human-readable error message
        status_code: HTTP status code to return
        error_code: Machine-readable error code for programmatic handling
        details: Additional error details
    """
    status_code = 500
    error_code = 'INTERNAL_ERROR'

    def __init__(
        self,
        message: str = 'An internal error occurred',
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response."""
        result = {
            'success': False,
            'error': self.message,
            'error_code': self.error_code
        }
        if self.details:
            result['details'] = self.details
        return result


class NotFoundError(NetStacksError):
    """Resource not found (404)."""
    status_code = 404
    error_code = 'NOT_FOUND'

    def __init__(
        self,
        message: str = 'Resource not found',
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None
    ):
        details = {}
        if resource_type:
            details['resource_type'] = resource_type
        if resource_id:
            details['resource_id'] = resource_id
        super().__init__(message, details=details if details else None)


class ValidationError(NetStacksError):
    """Request validation failed (400)."""
    status_code = 400
    error_code = 'VALIDATION_ERROR'

    def __init__(
        self,
        message: str = 'Validation failed',
        field_errors: Optional[Dict[str, list]] = None
    ):
        details = {}
        if field_errors:
            details['fields'] = field_errors
        super().__init__(message, details=details if details else None)


class AuthenticationError(NetStacksError):
    """Authentication failed (401)."""
    status_code = 401
    error_code = 'AUTHENTICATION_ERROR'

    def __init__(self, message: str = 'Authentication required'):
        super().__init__(message)


class AuthorizationError(NetStacksError):
    """Authorization failed - insufficient permissions (403)."""
    status_code = 403
    error_code = 'AUTHORIZATION_ERROR'

    def __init__(self, message: str = 'Permission denied'):
        super().__init__(message)


class ConflictError(NetStacksError):
    """Resource conflict (409)."""
    status_code = 409
    error_code = 'CONFLICT'

    def __init__(
        self,
        message: str = 'Resource conflict',
        conflicting_field: Optional[str] = None
    ):
        details = {}
        if conflicting_field:
            details['conflicting_field'] = conflicting_field
        super().__init__(message, details=details if details else None)


class ServiceUnavailableError(NetStacksError):
    """External service unavailable (503)."""
    status_code = 503
    error_code = 'SERVICE_UNAVAILABLE'

    def __init__(
        self,
        message: str = 'Service temporarily unavailable',
        service_name: Optional[str] = None
    ):
        details = {}
        if service_name:
            details['service'] = service_name
        super().__init__(message, details=details if details else None)


class DeviceConnectionError(NetStacksError):
    """Failed to connect to network device."""
    status_code = 502
    error_code = 'DEVICE_CONNECTION_ERROR'

    def __init__(
        self,
        message: str = 'Failed to connect to device',
        device_name: Optional[str] = None,
        device_ip: Optional[str] = None
    ):
        details = {}
        if device_name:
            details['device_name'] = device_name
        if device_ip:
            details['device_ip'] = device_ip
        super().__init__(message, details=details if details else None)


class TaskError(NetStacksError):
    """Task execution failed."""
    status_code = 500
    error_code = 'TASK_ERROR'

    def __init__(
        self,
        message: str = 'Task execution failed',
        task_id: Optional[str] = None,
        task_type: Optional[str] = None
    ):
        details = {}
        if task_id:
            details['task_id'] = task_id
        if task_type:
            details['task_type'] = task_type
        super().__init__(message, details=details if details else None)


class ConfigurationError(NetStacksError):
    """Configuration or settings error."""
    status_code = 500
    error_code = 'CONFIGURATION_ERROR'

    def __init__(
        self,
        message: str = 'Configuration error',
        setting_name: Optional[str] = None
    ):
        details = {}
        if setting_name:
            details['setting'] = setting_name
        super().__init__(message, details=details if details else None)
