# /home/cwdavis/netstacks/tasks/__init__.py
"""
NetStacks Tasks Package
Exports celery_app and utility functions for backward compatibility.
"""

from .celery_config import (
    celery_app,
    get_redis_client,
    store_task_metadata,
    get_task_metadata,
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
)

from .utils import (
    get_textfsm_template_path,
    parse_with_textfsm,
    parse_with_ttp,
    render_jinja2_template,
    get_device_queue,
)

__all__ = [
    'celery_app',
    'get_redis_client',
    'store_task_metadata',
    'get_task_metadata',
    'CELERY_BROKER_URL',
    'CELERY_RESULT_BACKEND',
    'get_textfsm_template_path',
    'parse_with_textfsm',
    'parse_with_ttp',
    'render_jinja2_template',
    'get_device_queue',
]
