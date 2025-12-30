"""
Microservice Proxy Utilities

Helper functions for proxying Flask routes to FastAPI microservices.
Handles JWT authentication, request forwarding, and response translation.
"""

import logging
from functools import wraps
from typing import Optional, Callable

from flask import request, jsonify, Response
from services.microservice_client import microservice_client

log = logging.getLogger(__name__)


def proxy_to_auth(path: str, methods: list = None):
    """
    Decorator to proxy a Flask route to the auth microservice.

    Args:
        path: API path on the microservice (e.g., '/api/users')
        methods: HTTP methods allowed (default from route)

    Example:
        @app.route('/api/users', methods=['GET'])
        @proxy_to_auth('/api/users')
        def get_users():
            pass  # Function body is ignored, request is proxied
    """
    def decorator(f: Callable):
        @wraps(f)
        def wrapper(*args, **kwargs):
            return _proxy_request(microservice_client.call_auth, path, **kwargs)
        return wrapper
    return decorator


def proxy_to_devices(path: str, methods: list = None):
    """
    Decorator to proxy a Flask route to the devices microservice.
    """
    def decorator(f: Callable):
        @wraps(f)
        def wrapper(*args, **kwargs):
            return _proxy_request(microservice_client.call_devices, path, **kwargs)
        return wrapper
    return decorator


def proxy_to_config(path: str, methods: list = None):
    """
    Decorator to proxy a Flask route to the config microservice.
    """
    def decorator(f: Callable):
        @wraps(f)
        def wrapper(*args, **kwargs):
            return _proxy_request(microservice_client.call_config, path, **kwargs)
        return wrapper
    return decorator


def _proxy_request(
    call_func: Callable,
    path: str,
    **path_params
) -> Response:
    """
    Internal function to proxy a request to a microservice.

    Args:
        call_func: The microservice client method to call
        path: API path template (can include {param} placeholders)
        **path_params: URL path parameters from Flask route

    Returns:
        Flask Response object
    """
    # Substitute path parameters
    actual_path = path
    for key, value in path_params.items():
        actual_path = actual_path.replace(f'{{{key}}}', str(value))

    # Get query string if present
    if request.query_string:
        actual_path = f"{actual_path}?{request.query_string.decode('utf-8')}"

    # Get request body for POST/PUT/PATCH
    json_data = None
    if request.method in ['POST', 'PUT', 'PATCH']:
        try:
            json_data = request.get_json(silent=True)
        except Exception:
            pass

    # Check for Authorization header from incoming request
    auth_header = request.headers.get('Authorization')
    extra_headers = {}
    if auth_header:
        extra_headers['Authorization'] = auth_header

    # Make the proxied request
    response, error = call_func(
        method=request.method,
        path=actual_path,
        json=json_data,
        extra_headers=extra_headers
    )

    if error:
        log.error(f"Proxy error for {request.method} {actual_path}: {error}")
        return jsonify({
            'success': False,
            'error': error
        }), 502

    if response is None:
        return jsonify({
            'success': False,
            'error': 'No response from microservice'
        }), 502

    # Return the microservice response
    try:
        return Response(
            response.content,
            status=response.status_code,
            content_type=response.headers.get('Content-Type', 'application/json')
        )
    except Exception as e:
        log.error(f"Error creating proxy response: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def proxy_auth_request(path: str, **path_params) -> Response:
    """
    Directly proxy a request to the auth microservice.

    Use this for more complex routing logic where decorator isn't suitable.

    Example:
        return proxy_auth_request('/api/users/{username}', username=username)
    """
    return _proxy_request(microservice_client.call_auth, path, **path_params)


def proxy_devices_request(path: str, **path_params) -> Response:
    """Directly proxy a request to the devices microservice."""
    return _proxy_request(microservice_client.call_devices, path, **path_params)


def proxy_config_request(path: str, **path_params) -> Response:
    """Directly proxy a request to the config microservice."""
    return _proxy_request(microservice_client.call_config, path, **path_params)
