# services/ai/app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SERVICE_NAME: str = "ai-service"
    SERVICE_PORT: int = 8003
    DATABASE_URL: str = "postgresql://netstacks:netstacks@postgres:5432/netstacks"
    JWT_SECRET_KEY: str = "netstacks-dev-secret"
    REDIS_URL: str = "redis://redis:6379/0"
    CORS_ORIGINS: str = "*"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
