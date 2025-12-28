"""
Configuration Management for NetStacks

Provides Pydantic settings for configuration management across all services.
Settings are loaded from environment variables with sensible defaults.
"""

import os
from typing import Optional
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection settings"""

    model_config = SettingsConfigDict(env_prefix='')

    DATABASE_URL: str = 'postgresql://netstacks:netstacks_secret_change_me@postgres:5432/netstacks'
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False


class JWTSettings(BaseSettings):
    """JWT authentication settings"""

    model_config = SettingsConfigDict(env_prefix='')

    JWT_SECRET_KEY: str = 'netstacks-dev-secret-change-in-production'
    JWT_ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7


class RedisSettings(BaseSettings):
    """Redis connection settings"""

    model_config = SettingsConfigDict(env_prefix='')

    REDIS_URL: str = 'redis://redis:6379/0'
    REDIS_PASSWORD: Optional[str] = None


class CelerySettings(BaseSettings):
    """Celery task queue settings"""

    model_config = SettingsConfigDict(env_prefix='')

    CELERY_BROKER_URL: str = 'redis://redis:6379/0'
    CELERY_RESULT_BACKEND: str = 'redis://redis:6379/0'


class EncryptionSettings(BaseSettings):
    """Credential encryption settings"""

    model_config = SettingsConfigDict(env_prefix='')

    NETSTACKS_ENCRYPTION_KEY: Optional[str] = None
    SECRET_KEY: str = 'netstacks_default_fallback'


class ServiceSettings(BaseSettings):
    """Individual service settings"""

    model_config = SettingsConfigDict(env_prefix='')

    SERVICE_NAME: str = 'netstacks'
    SERVICE_PORT: int = 8000
    DEBUG: bool = False
    LOG_LEVEL: str = 'INFO'
    CORS_ORIGINS: str = '*'


class NetStacksSettings(BaseSettings):
    """
    Main settings class that combines all settings.

    Usage:
        from netstacks_core.config import get_settings

        settings = get_settings()
        print(settings.DATABASE_URL)
    """

    model_config = SettingsConfigDict(
        env_prefix='',
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    # Database
    DATABASE_URL: str = 'postgresql://netstacks:netstacks_secret_change_me@postgres:5432/netstacks'
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    # JWT
    JWT_SECRET_KEY: str = 'netstacks-dev-secret-change-in-production'
    JWT_ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Redis
    REDIS_URL: str = 'redis://redis:6379/0'
    REDIS_PASSWORD: Optional[str] = None

    # Celery
    CELERY_BROKER_URL: str = 'redis://redis:6379/0'
    CELERY_RESULT_BACKEND: str = 'redis://redis:6379/0'

    # Encryption
    NETSTACKS_ENCRYPTION_KEY: Optional[str] = None
    SECRET_KEY: str = 'netstacks_default_fallback'

    # Service
    SERVICE_NAME: str = 'netstacks'
    SERVICE_PORT: int = 8000
    DEBUG: bool = False
    LOG_LEVEL: str = 'INFO'
    CORS_ORIGINS: str = '*'

    # NetBox integration
    NETBOX_URL: Optional[str] = None
    NETBOX_TOKEN: Optional[str] = None

    # Timezone
    TZ: str = 'UTC'


@lru_cache()
def get_settings() -> NetStacksSettings:
    """
    Get the application settings (cached).

    Returns:
        NetStacksSettings instance with values from environment
    """
    return NetStacksSettings()


def get_database_settings() -> DatabaseSettings:
    """Get database-specific settings."""
    return DatabaseSettings()


def get_jwt_settings() -> JWTSettings:
    """Get JWT-specific settings."""
    return JWTSettings()


def get_redis_settings() -> RedisSettings:
    """Get Redis-specific settings."""
    return RedisSettings()


def get_celery_settings() -> CelerySettings:
    """Get Celery-specific settings."""
    return CelerySettings()


def get_encryption_settings() -> EncryptionSettings:
    """Get encryption-specific settings."""
    return EncryptionSettings()


def get_service_settings() -> ServiceSettings:
    """Get service-specific settings."""
    return ServiceSettings()
