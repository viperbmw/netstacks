"""
Configuration for Auth Service
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Auth service configuration"""

    model_config = SettingsConfigDict(
        env_prefix='',
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    # Service
    SERVICE_NAME: str = 'auth'
    SERVICE_PORT: int = 8011
    DEBUG: bool = False
    LOG_LEVEL: str = 'INFO'

    # Database
    DATABASE_URL: str = 'postgresql://netstacks:netstacks_secret_change_me@postgres:5432/netstacks'

    # JWT
    JWT_SECRET_KEY: str = 'netstacks-dev-secret-change-in-production'
    JWT_ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: str = '*'

    # Timezone
    TZ: str = 'UTC'


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
