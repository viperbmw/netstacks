"""
Platform health and statistics routes.

Provides endpoints for checking health of all platform services.
"""

import logging
import os
import time
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, Depends
import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/platform", tags=["platform"])

# Service endpoints for health checks
SERVICE_ENDPOINTS = {
    'auth': os.environ.get('AUTH_SERVICE_URL', 'http://auth:8011'),
    'devices': os.environ.get('DEVICES_SERVICE_URL', 'http://devices:8004'),
    'config': os.environ.get('CONFIG_SERVICE_URL', 'http://config:8002'),
    'ai': os.environ.get('AI_SERVICE_URL', 'http://ai:8003'),
    'tasks': os.environ.get('TASKS_SERVICE_URL', 'http://tasks:8006'),
}


async def check_service_health(service_name: str, base_url: str) -> Dict[str, Any]:
    """Check health of a single service."""
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base_url}/health")
            response_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                return {
                    'status': 'healthy',
                    'response_ms': response_ms
                }
            else:
                return {
                    'status': 'unhealthy',
                    'error': f'HTTP {response.status_code}',
                    'response_ms': response_ms
                }
    except httpx.ConnectError:
        return {'status': 'unhealthy', 'error': 'connection refused'}
    except httpx.TimeoutException:
        return {'status': 'unhealthy', 'error': 'timeout'}
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}


async def check_redis_health() -> Dict[str, Any]:
    """Check Redis health."""
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


async def check_postgres_health() -> Dict[str, Any]:
    """Check PostgreSQL health."""
    try:
        from netstacks_core.db import get_session
        from sqlalchemy import text

        session = get_session()
        try:
            session.execute(text('SELECT 1'))
            return {'status': 'healthy'}
        finally:
            session.close()
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}


async def check_workers_health() -> Dict[str, Any]:
    """Check Celery worker health."""
    try:
        from celery import Celery

        broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
        app = Celery(broker=broker_url)

        # Get worker stats with short timeout
        inspect = app.control.inspect(timeout=2.0)
        active = inspect.active() or {}
        stats = inspect.stats() or {}

        worker_count = len(stats)
        active_tasks = sum(len(tasks) for tasks in active.values())

        if worker_count > 0:
            return {
                'status': 'healthy',
                'workers': worker_count,
                'active_tasks': active_tasks
            }
        else:
            return {
                'status': 'unhealthy',
                'error': 'No workers available',
                'workers': 0,
                'active_tasks': 0
            }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e),
            'workers': 0,
            'active_tasks': 0
        }


@router.get("/health")
async def get_platform_health():
    """
    Get health status of all platform services.

    Returns status of:
    - Auth microservice
    - Devices microservice
    - Config microservice
    - AI microservice
    - Tasks microservice
    - Redis
    - PostgreSQL
    - Celery workers
    """
    results = {}

    # Check all microservices
    for service_name, base_url in SERVICE_ENDPOINTS.items():
        results[service_name] = await check_service_health(service_name, base_url)

    # Check Redis
    results['redis'] = await check_redis_health()

    # Check PostgreSQL
    results['postgres'] = await check_postgres_health()

    # Check Celery workers
    results['workers'] = await check_workers_health()

    # Determine overall status
    all_healthy = all(
        s.get('status') == 'healthy'
        for s in results.values()
    )

    return {
        'success': True,
        'data': {
            'overall_status': 'healthy' if all_healthy else 'degraded',
            'services': results
        }
    }


@router.get("/stats")
async def get_platform_stats():
    """
    Get aggregated platform statistics.

    Returns counts and summaries for:
    - Devices
    - Templates
    - Service Stacks
    - Incidents
    - AI Agents
    - Config Backups
    """
    from netstacks_core.db import get_session, Device, ConfigBackup, ConfigSnapshot
    from netstacks_core.db import Template, ServiceStack, Agent, Incident

    session = get_session()
    try:
        # Device stats
        try:
            device_count = session.query(Device).count()
            devices = {'total': device_count}
        except Exception:
            devices = {'total': 0}

        # Template stats
        try:
            template_count = session.query(Template).count()
            templates = {'total': template_count}
        except Exception:
            templates = {'total': 0}

        # Stack stats
        try:
            total_stacks = session.query(ServiceStack).count()
            deployed_stacks = session.query(ServiceStack).filter(
                ServiceStack.state == 'deployed'
            ).count()
            stacks = {'total': total_stacks, 'deployed': deployed_stacks}
        except Exception:
            stacks = {'total': 0, 'deployed': 0}

        # Incident stats
        try:
            open_incidents = session.query(Incident).filter(
                Incident.status == 'open'
            ).count()
            incidents = {'open': open_incidents}
        except Exception:
            incidents = {'open': 0}

        # Agent stats
        try:
            active_agents = session.query(Agent).filter(
                Agent.is_active == True
            ).count()
            agents = {'active': active_agents}
        except Exception:
            agents = {'active': 0}

        # Backup stats
        try:
            recent_backups = session.query(ConfigBackup).count()
            backups = {'recent_count': recent_backups}
        except Exception:
            backups = {'recent_count': 0}

        return {
            'timestamp': datetime.utcnow().isoformat(),
            'devices': devices,
            'templates': templates,
            'stacks': stacks,
            'incidents': incidents,
            'agents': agents,
            'backups': backups,
        }

    finally:
        session.close()
