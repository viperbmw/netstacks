"""
Configuration for Tasks Service
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Tasks service configuration"""

    model_config = SettingsConfigDict(
        env_prefix='',
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    # Service
    SERVICE_NAME: str = 'tasks'
    SERVICE_PORT: int = 8006
    DEBUG: bool = False
    LOG_LEVEL: str = 'INFO'

    # Database
    DATABASE_URL: str = 'postgresql://netstacks:netstacks_secret_change_me@postgres:5432/netstacks'

    # JWT (for authentication)
    JWT_SECRET_KEY: str = 'netstacks-dev-secret-change-in-production'
    JWT_ALGORITHM: str = 'HS256'

    # Celery
    CELERY_BROKER_URL: str = 'redis://redis:6379/0'
    CELERY_RESULT_BACKEND: str = 'redis://redis:6379/0'

    # CORS
    CORS_ORIGINS: str = '*'

    # Timezone
    TZ: str = 'UTC'

    # Microservice URLs (for inter-service communication)
    DEVICES_SERVICE_URL: str = 'http://devices:8004'
    AUTH_SERVICE_URL: str = 'http://auth:8011'
    CONFIG_SERVICE_URL: str = 'http://config:8002'


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
