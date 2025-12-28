"""
Devices Service Configuration

Service-specific settings that extend the shared config.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class DevicesSettings(BaseSettings):
    """Settings specific to the Devices service"""

    # Service info
    service_name: str = "netstacks-devices"
    service_version: str = "1.0.0"

    # Database
    database_url: str = "postgresql://netstacks:netstacks@localhost:5432/netstacks"

    # JWT settings (for token validation)
    jwt_secret_key: str = "netstacks-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"

    # Device cache settings
    cache_ttl: int = 300  # 5 minutes default

    # Timeouts
    device_connect_timeout: int = 30
    device_command_timeout: int = 60

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = DevicesSettings()
