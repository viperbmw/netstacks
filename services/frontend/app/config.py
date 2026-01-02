# services/frontend/app/config.py
"""
Frontend service configuration.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SERVICE_NAME: str = "frontend"
    SERVICE_PORT: int = 8020
    DEBUG: bool = False

    # Auth service for OIDC check
    AUTH_SERVICE_URL: str = "http://auth:8011"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
