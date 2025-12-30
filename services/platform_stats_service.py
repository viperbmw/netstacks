# /home/cwdavis/netstacks/services/platform_stats_service.py
"""
Platform Statistics Service
Provides aggregated platform metrics with caching.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from functools import lru_cache
import time

log = logging.getLogger(__name__)

# Simple TTL cache
_cache: Dict[str, Any] = {}
_cache_expiry: Dict[str, float] = {}
CACHE_TTL = 60  # seconds


def _get_cached(key: str) -> Optional[Any]:
    """Get value from cache if not expired."""
    if key in _cache and time.time() < _cache_expiry.get(key, 0):
        return _cache[key]
    return None


def _set_cached(key: str, value: Any):
    """Set value in cache with TTL."""
    _cache[key] = value
    _cache_expiry[key] = time.time() + CACHE_TTL


def get_platform_stats() -> Dict[str, Any]:
    """
    Get aggregated platform statistics.
    Cached for 60 seconds.
    """
    cached = _get_cached('platform_stats')
    if cached:
        return cached

    import database as db
    from timezone_utils import utc_now

    try:
        stats = {
            'timestamp': utc_now().isoformat(),
            'devices': _get_device_stats(db),
            'templates': _get_template_stats(db),
            'stacks': _get_stack_stats(db),
            'incidents': _get_incident_stats(db),
            'agents': _get_agent_stats(db),
            'backups': _get_backup_stats(db),
            'system': _get_system_stats(),
        }
        _set_cached('platform_stats', stats)
        return stats
    except Exception as e:
        log.error(f"Error getting platform stats: {e}", exc_info=True)
        return {'error': str(e), 'timestamp': utc_now().isoformat()}


def _get_device_stats(db) -> Dict:
    """Device statistics."""
    devices = db.get_all_devices() or []
    return {
        'total': len(devices),
        'by_type': _count_by_field(devices, 'device_type'),
        'by_status': _count_by_field(devices, 'status'),
    }


def _get_template_stats(db) -> Dict:
    """Template statistics."""
    templates = db.get_all_templates() or []
    return {
        'total': len(templates),
        'by_type': _count_by_field(templates, 'template_type'),
    }


def _get_stack_stats(db) -> Dict:
    """Service stack statistics."""
    stacks = db.get_all_service_stacks() or []
    return {
        'total': len(stacks),
        'deployed': len([s for s in stacks if s.get('state') == 'deployed']),
        'by_state': _count_by_field(stacks, 'state'),
    }


def _get_incident_stats(db) -> Dict:
    """Incident statistics."""
    incidents = db.get_all_incidents() or []
    return {
        'total': len(incidents),
        'open': len([i for i in incidents if i.get('status') == 'open']),
        'by_severity': _count_by_field(incidents, 'severity'),
        'by_status': _count_by_field(incidents, 'status'),
    }


def _get_agent_stats(db) -> Dict:
    """Agent statistics."""
    agents = db.get_all_agents() or []
    return {
        'total': len(agents),
        'active': len([a for a in agents if a.get('is_active')]),
        'by_type': _count_by_field(agents, 'agent_type'),
    }


def _get_backup_stats(db) -> Dict:
    """Backup statistics."""
    try:
        schedule = db.get_backup_schedule() or {}
        recent_backups = db.get_recent_backups(limit=100) or []
        return {
            'schedule_enabled': schedule.get('enabled', False),
            'recent_count': len(recent_backups),
        }
    except:
        return {'schedule_enabled': False, 'recent_count': 0}


def _get_system_stats() -> Dict:
    """System health statistics."""
    try:
        import redis
        import os

        redis_url = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
        r = redis.from_url(redis_url)
        redis_ok = r.ping()
    except:
        redis_ok = False

    return {
        'redis_connected': redis_ok,
    }


def _count_by_field(items: list, field: str) -> Dict[str, int]:
    """Count items by field value."""
    counts = {}
    for item in items:
        value = item.get(field, 'unknown') or 'unknown'
        counts[value] = counts.get(value, 0) + 1
    return counts
