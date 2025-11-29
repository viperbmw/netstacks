"""
NetStacks Configuration
Centralizes all configuration and environment variables
"""
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class Config:
    """Application configuration"""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'netstacks-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    # Database - SQLite (current)
    DB_FILE = os.environ.get('DB_FILE', '/data/netstacks.db')

    # Database - PostgreSQL (future)
    USE_POSTGRES = os.environ.get('USE_POSTGRES', 'false').lower() == 'true'
    DATABASE_URL = os.environ.get(
        'DATABASE_URL',
        'postgresql://netstacks:netstacks_secret_change_me@postgres:5432/netstacks'
    )

    # Netstacker Backend (will be replaced by Celery in future)
    NETSTACKER_API_URL = os.environ.get('NETSTACKER_API_URL', 'http://netstacker-controller:9000')
    NETSTACKER_API_KEY = os.environ.get('NETSTACKER_API_KEY', '2a84465a-cf38-46b2-9d86-b84Q7d57f288')

    # Celery (future - Phase 3)
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

    # Netbox Integration
    NETBOX_URL = os.environ.get('NETBOX_URL', 'https://netbox.example.com')
    NETBOX_TOKEN = os.environ.get('NETBOX_TOKEN', '')
    VERIFY_SSL = os.environ.get('VERIFY_SSL', 'false').lower() == 'true'

    # Task History
    TASK_HISTORY_FILE = os.environ.get('TASK_HISTORY_FILE', '/tmp/netstacks_tasks.json')

    # Device Cache TTL (seconds)
    DEVICE_CACHE_TTL = int(os.environ.get('DEVICE_CACHE_TTL', '300'))

    @classmethod
    def get_netstacker_headers(cls):
        """Get headers for Netstacker API calls"""
        return {
            'x-api-key': cls.NETSTACKER_API_KEY,
            'Content-Type': 'application/json'
        }


# Singleton instance
config = Config()
