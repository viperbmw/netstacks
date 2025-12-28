"""
Configuration for Config Service
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Config service settings."""

    # Service info
    SERVICE_NAME: str = "config-service"
    VERSION: str = "1.0.0"

    # Database
    DATABASE_URL: str = os.environ.get(
        'DATABASE_URL',
        'postgresql://netstacks:netstacks_secret_change_me@postgres:5432/netstacks'
    )

    # JWT
    JWT_SECRET_KEY: str = os.environ.get('JWT_SECRET_KEY', 'change-me-in-production')
    JWT_ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
