"""
Microservice Client

HTTP client for calling microservices with JWT authentication.
For JWT-only auth, tokens are passed via Authorization headers from the frontend.
This client forwards the incoming JWT for server-to-server calls.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from functools import wraps

import requests
from flask import request, current_app

log = logging.getLogger(__name__)

# Service URLs (configured via environment or defaults for Docker networking)
AUTH_SERVICE_URL = os.environ.get('AUTH_SERVICE_URL', 'http://auth:8011')
DEVICES_SERVICE_URL = os.environ.get('DEVICES_SERVICE_URL', 'http://devices:8004')
CONFIG_SERVICE_URL = os.environ.get('CONFIG_SERVICE_URL', 'http://config:8002')
AI_SERVICE_URL = os.environ.get('AI_SERVICE_URL', 'http://ai:8003')
TASKS_SERVICE_URL = os.environ.get('TASKS_SERVICE_URL', 'http://tasks:8006')

# Request timeout in seconds (short timeout since we fall back to local auth)
REQUEST_TIMEOUT = 2


class MicroserviceClient:
    """
    HTTP client for calling microservices with JWT authentication.

    Handles:
    - Forwarding JWT from incoming request Authorization header
    - Service URL routing
    - Error handling and logging

    For JWT-only auth, tokens come from the frontend via Authorization headers.
    This client forwards that token for server-to-server microservice calls.
    """

    def __init__(self):
        self.timeout = REQUEST_TIMEOUT
        self._login_tokens = {}  # Temporary storage for login flow

    @staticmethod
    def get_jwt_token() -> Optional[str]:
        """Get JWT token from incoming request Authorization header."""
        try:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                return auth_header[7:]
        except RuntimeError:
            # Outside request context
            pass
        return None

    @staticmethod
    def get_refresh_token() -> Optional[str]:
        """Get refresh token - not available in JWT-only mode."""
        # In JWT-only mode, refresh tokens are handled by the frontend
        return None

    def store_tokens(self, access_token: str, refresh_token: str, expires_in: int):
        """
        Temporarily store tokens from login response.
        These are returned to the frontend which stores them in localStorage.
        """
        self._login_tokens = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': expires_in
        }
        log.debug("JWT tokens stored temporarily for login response")

    def clear_tokens(self):
        """Clear temporary token storage."""
        self._login_tokens = {}
        log.debug("JWT tokens cleared")

    def _get_headers(self, include_auth: bool = True) -> Dict[str, str]:
        """Get request headers with optional JWT authentication."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        if include_auth:
            token = self.get_jwt_token()
            if token:
                headers['Authorization'] = f'Bearer {token}'

        return headers

    def _ensure_valid_token(self) -> bool:
        """Check if we have a valid token from the incoming request."""
        # In JWT-only mode, we just check if a token was provided
        # Token refresh is handled by the frontend
        return self.get_jwt_token() is not None

    def _make_request(
        self,
        method: str,
        url: str,
        include_auth: bool = True,
        extra_headers: Dict[str, str] = None,
        **kwargs
    ) -> Tuple[Optional[requests.Response], Optional[str]]:
        """
        Make an HTTP request with error handling.

        Returns:
            Tuple of (response, error_message)
        """
        # Check if Authorization is provided via extra_headers (from proxy)
        has_proxy_auth = extra_headers and 'Authorization' in extra_headers

        # For JWT-only auth, we forward the token from incoming request
        # If no token and auth required, return error
        if include_auth and not has_proxy_auth and not self._ensure_valid_token():
            return None, "No valid authentication token"

        headers = self._get_headers(include_auth and not has_proxy_auth)

        # Apply extra headers (these override incoming auth if present)
        if extra_headers:
            headers.update(extra_headers)

        kwargs['headers'] = headers
        kwargs['timeout'] = kwargs.get('timeout', self.timeout)

        try:
            response = requests.request(method, url, **kwargs)
            # In JWT-only mode, 401 responses are returned to frontend
            # Frontend handles token refresh via its own refresh endpoint
            return response, None

        except requests.exceptions.Timeout:
            error = f"Request timeout: {url}"
            log.error(error)
            return None, error
        except requests.exceptions.ConnectionError:
            error = f"Connection error: {url}"
            log.error(error)
            return None, error
        except Exception as e:
            error = f"Request error: {str(e)}"
            log.error(error, exc_info=True)
            return None, error

    # ========================================================================
    # Auth Service Methods
    # ========================================================================

    def login(self, username: str, password: str) -> Tuple[bool, Optional[Dict]]:
        """
        Authenticate with auth microservice and get JWT tokens.

        Returns:
            Tuple of (success, user_info)
        """
        try:
            response = requests.post(
                f"{AUTH_SERVICE_URL}/api/auth/login",
                json={"username": username, "password": password},
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()
                self.store_tokens(
                    access_token=data['access_token'],
                    refresh_token=data['refresh_token'],
                    expires_in=data.get('expires_in', 1800)
                )
                return True, data.get('user')
            else:
                log.warning(f"Microservice login failed: {response.status_code}")
                return False, None

        except Exception as e:
            log.error(f"Error calling auth microservice: {e}")
            return False, None

    def call_auth(
        self,
        method: str,
        path: str,
        extra_headers: Dict[str, str] = None,
        **kwargs
    ) -> Tuple[Optional[requests.Response], Optional[str]]:
        """
        Call auth microservice.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., '/api/auth/users')
            extra_headers: Additional headers to include (e.g., Authorization from proxy)
            **kwargs: Additional request arguments

        Returns:
            Tuple of (response, error_message)
        """
        url = f"{AUTH_SERVICE_URL}{path}"
        return self._make_request(method, url, extra_headers=extra_headers, **kwargs)

    # ========================================================================
    # Devices Service Methods
    # ========================================================================

    def call_devices(
        self,
        method: str,
        path: str,
        extra_headers: Dict[str, str] = None,
        **kwargs
    ) -> Tuple[Optional[requests.Response], Optional[str]]:
        """
        Call devices microservice.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., '/api/devices')
            extra_headers: Additional headers to include (e.g., Authorization from proxy)
            **kwargs: Additional request arguments

        Returns:
            Tuple of (response, error_message)
        """
        url = f"{DEVICES_SERVICE_URL}{path}"
        return self._make_request(method, url, extra_headers=extra_headers, **kwargs)

    # ========================================================================
    # Config Service Methods
    # ========================================================================

    def call_config(
        self,
        method: str,
        path: str,
        extra_headers: Dict[str, str] = None,
        **kwargs
    ) -> Tuple[Optional[requests.Response], Optional[str]]:
        """
        Call config microservice.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., '/api/templates')
            extra_headers: Additional headers to include (e.g., Authorization from proxy)
            **kwargs: Additional request arguments

        Returns:
            Tuple of (response, error_message)
        """
        url = f"{CONFIG_SERVICE_URL}{path}"
        return self._make_request(method, url, extra_headers=extra_headers, **kwargs)

    # ========================================================================
    # Tasks Service Methods
    # ========================================================================

    def call_tasks(
        self,
        method: str,
        path: str,
        extra_headers: Dict[str, str] = None,
        **kwargs
    ) -> Tuple[Optional[requests.Response], Optional[str]]:
        """
        Call tasks microservice.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., '/api/tasks')
            extra_headers: Additional headers to include (e.g., Authorization from proxy)
            **kwargs: Additional request arguments

        Returns:
            Tuple of (response, error_message)
        """
        url = f"{TASKS_SERVICE_URL}{path}"
        return self._make_request(method, url, extra_headers=extra_headers, **kwargs)

    # ========================================================================
    # Health Check Methods
    # ========================================================================

    def check_service_health(self, service: str) -> Dict[str, Any]:
        """
        Check health of a specific service.

        Args:
            service: Service name ('auth', 'devices', 'config')

        Returns:
            Dict with status and response time
        """
        url_map = {
            'auth': f"{AUTH_SERVICE_URL}/health",
            'devices': f"{DEVICES_SERVICE_URL}/health",
            'config': f"{CONFIG_SERVICE_URL}/health",
            'ai': f"{AI_SERVICE_URL}/health",
            'tasks': f"{TASKS_SERVICE_URL}/health",
        }

        url = url_map.get(service)
        if not url:
            return {'status': 'unknown', 'error': f'Unknown service: {service}'}

        try:
            start = datetime.utcnow()
            response = requests.get(url, timeout=5)
            elapsed_ms = int((datetime.utcnow() - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json() if response.content else {}
                return {
                    'status': 'healthy',
                    'response_ms': elapsed_ms,
                    'details': data
                }
            else:
                return {
                    'status': 'unhealthy',
                    'response_ms': elapsed_ms,
                    'error': f'HTTP {response.status_code}'
                }

        except requests.exceptions.Timeout:
            return {'status': 'unhealthy', 'error': 'timeout'}
        except requests.exceptions.ConnectionError:
            return {'status': 'unhealthy', 'error': 'connection refused'}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}

    def check_all_services_health(self) -> Dict[str, Any]:
        """
        Check health of all services.

        For standalone monolith, checks local Flask app health.
        For microservices, checks external service endpoints.

        Returns:
            Dict with status of each service
        """
        results = {}

        # Check if we're in monolith mode (microservices not available)
        # by testing if auth service responds
        auth_health = self.check_service_health('auth')

        if auth_health.get('status') == 'unhealthy' and 'connection refused' in auth_health.get('error', ''):
            # Monolith mode - check local Flask app components
            results['flask'] = self._check_flask_health()
        else:
            # Microservices mode - check external services
            for service in ['auth', 'devices', 'config', 'ai', 'tasks']:
                results[service] = self.check_service_health(service)

        # Check Redis
        results['redis'] = self._check_redis_health()

        # Check PostgreSQL
        results['postgres'] = self._check_postgres_health()

        # Check Celery workers
        results['workers'] = self._check_workers_health()

        return results

    def _check_flask_health(self) -> Dict[str, Any]:
        """Check local Flask app health."""
        try:
            # Flask is healthy if we're running (this code is executing)
            # Check that routes are registered
            from flask import current_app
            route_count = len(list(current_app.url_map.iter_rules()))
            return {
                'status': 'healthy',
                'routes': route_count,
                'mode': 'monolith'
            }
        except Exception as e:
            return {'status': 'healthy', 'mode': 'monolith', 'note': 'Running'}

    def _check_redis_health(self) -> Dict[str, Any]:
        """Check Redis health via workers or direct connection."""
        try:
            import redis
            redis_url = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
            r = redis.from_url(redis_url)
            r.ping()
            return {'status': 'healthy'}
        except ImportError:
            return {'status': 'unknown', 'error': 'redis package not installed'}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}

    def _check_postgres_health(self) -> Dict[str, Any]:
        """Check PostgreSQL health via database connection."""
        try:
            # Try using the local database module first
            try:
                import database as db
                from sqlalchemy import text
                # Use the context manager pattern
                with db.get_db() as db_session:
                    db_session.execute(text('SELECT 1'))
                    return {'status': 'healthy'}
            except Exception as db_err:
                log.debug(f"Database module health check failed: {db_err}")

            # Fallback to direct connection test
            import psycopg2
            database_url = os.environ.get('DATABASE_URL', '')
            if database_url:
                conn = psycopg2.connect(database_url)
                conn.close()
                return {'status': 'healthy'}
            return {'status': 'unknown', 'error': 'No DATABASE_URL configured'}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}

    def _check_workers_health(self) -> Dict[str, Any]:
        """Check Celery worker health."""
        try:
            from celery import Celery

            broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
            app = Celery(broker=broker_url)

            # Get active workers
            inspect = app.control.inspect()
            active = inspect.active()

            if active:
                worker_count = len(active)
                task_count = sum(len(tasks) for tasks in active.values())
                return {
                    'status': 'healthy',
                    'workers': worker_count,
                    'active_tasks': task_count
                }
            else:
                return {'status': 'unhealthy', 'error': 'No active workers'}

        except Exception as e:
            return {'status': 'unknown', 'error': str(e)}


# Global client instance
microservice_client = MicroserviceClient()
