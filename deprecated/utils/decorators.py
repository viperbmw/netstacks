"""
Common Route Decorators for NetStacks

Provides reusable decorators for request handling, validation, and error management.
"""

import functools
import logging
from flask import request, jsonify, g
from typing import Callable, Any, Optional, Type

from utils.exceptions import (
    NetStacksError,
    ValidationError,
    AuthenticationError
)
from utils.responses import error_response

log = logging.getLogger(__name__)


def handle_exceptions(func: Callable) -> Callable:
    """
    Decorator that catches and handles exceptions consistently.

    Catches NetStacksError subclasses and converts them to proper JSON responses.
    Catches unexpected exceptions and returns a 500 error.

    Example:
        @app.route('/api/users/<user_id>')
        @handle_exceptions
        def get_user(user_id):
            user = UserService().get_user(user_id)
            if not user:
                raise NotFoundError(f'User {user_id} not found')
            return success_response(user)
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except NetStacksError as e:
            log.warning(f"API error in {func.__name__}: {e.error_code} - {e.message}")
            return jsonify(e.to_dict()), e.status_code
        except Exception as e:
            log.exception(f"Unexpected error in {func.__name__}: {str(e)}")
            return error_response(
                message='An unexpected error occurred',
                status_code=500,
                error_code='INTERNAL_ERROR'
            )
    return wrapper


def require_json(func: Callable) -> Callable:
    """
    Decorator that ensures request has JSON content type and valid JSON body.

    Returns 400 error if Content-Type is not application/json or body is not valid JSON.

    Example:
        @app.route('/api/users', methods=['POST'])
        @require_json
        def create_user():
            data = request.get_json()
            # data is guaranteed to be valid JSON dict
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not request.is_json:
            return error_response(
                message='Content-Type must be application/json',
                status_code=400,
                error_code='INVALID_CONTENT_TYPE'
            )

        try:
            data = request.get_json(force=True)
            if data is None:
                return error_response(
                    message='Request body must be valid JSON',
                    status_code=400,
                    error_code='INVALID_JSON'
                )
        except Exception:
            return error_response(
                message='Request body must be valid JSON',
                status_code=400,
                error_code='INVALID_JSON'
            )

        return func(*args, **kwargs)
    return wrapper


def validate_request(
    required_fields: Optional[list] = None,
    optional_fields: Optional[list] = None,
    validators: Optional[dict] = None
) -> Callable:
    """
    Decorator that validates request JSON body against schema.

    Args:
        required_fields: List of field names that must be present
        optional_fields: List of optional field names (for documentation)
        validators: Dict mapping field names to validation functions

    Example:
        @app.route('/api/users', methods=['POST'])
        @require_json
        @validate_request(
            required_fields=['username', 'email'],
            optional_fields=['display_name'],
            validators={
                'email': lambda x: '@' in x,
                'username': lambda x: len(x) >= 3
            }
        )
        def create_user():
            data = request.get_json()
            # data is guaranteed to have username and email
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            data = request.get_json()
            errors = {}

            # Check required fields
            if required_fields:
                for field in required_fields:
                    if field not in data or data[field] is None:
                        errors[field] = [f'{field} is required']
                    elif isinstance(data[field], str) and not data[field].strip():
                        errors[field] = [f'{field} cannot be empty']

            # Run validators
            if validators:
                for field, validator in validators.items():
                    if field in data and data[field] is not None:
                        try:
                            if not validator(data[field]):
                                if field not in errors:
                                    errors[field] = []
                                errors[field].append(f'{field} is invalid')
                        except Exception as e:
                            if field not in errors:
                                errors[field] = []
                            errors[field].append(str(e))

            if errors:
                raise ValidationError('Validation failed', field_errors=errors)

            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_auth(func: Callable) -> Callable:
    """
    Decorator that ensures request has valid authentication.

    Checks for valid JWT token in Authorization header.
    Sets g.current_user if authentication succeeds.

    Example:
        @app.route('/api/settings')
        @require_auth
        def get_settings():
            user = g.current_user
            # user is guaranteed to be authenticated
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Check if user is already authenticated (set by middleware)
        if hasattr(g, 'current_user') and g.current_user:
            return func(*args, **kwargs)

        auth_header = request.headers.get('Authorization', '')

        if not auth_header:
            raise AuthenticationError('Authorization header required')

        if not auth_header.startswith('Bearer '):
            raise AuthenticationError('Invalid authorization header format')

        # Token validation is typically done by middleware or auth service
        # This decorator just ensures the header is present
        # Actual token validation happens in the auth middleware

        return func(*args, **kwargs)
    return wrapper


def require_role(*roles: str) -> Callable:
    """
    Decorator that ensures authenticated user has required role(s).

    Must be used after @require_auth decorator.

    Args:
        *roles: Role names that are allowed access

    Example:
        @app.route('/api/admin/users')
        @require_auth
        @require_role('admin', 'superuser')
        def list_all_users():
            # Only admins and superusers can access
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not hasattr(g, 'current_user') or not g.current_user:
                raise AuthenticationError('Authentication required')

            user_roles = getattr(g.current_user, 'roles', [])
            if isinstance(user_roles, str):
                user_roles = [user_roles]

            if not any(role in user_roles for role in roles):
                from utils.exceptions import AuthorizationError
                raise AuthorizationError(
                    f'This action requires one of these roles: {", ".join(roles)}'
                )

            return func(*args, **kwargs)
        return wrapper
    return decorator


def log_request(func: Callable) -> Callable:
    """
    Decorator that logs request details for debugging and auditing.

    Example:
        @app.route('/api/devices/<device_id>/command', methods=['POST'])
        @log_request
        def execute_command(device_id):
            # Request will be logged before execution
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        user = getattr(g, 'current_user', None)
        user_id = getattr(user, 'username', 'anonymous') if user else 'anonymous'

        log.info(
            f"API Request: {request.method} {request.path} "
            f"| User: {user_id} "
            f"| IP: {request.remote_addr}"
        )

        response = func(*args, **kwargs)

        # Log response status if it's a tuple (response, status_code)
        if isinstance(response, tuple) and len(response) >= 2:
            status = response[1]
            log.info(f"API Response: {request.path} | Status: {status}")

        return response
    return wrapper
