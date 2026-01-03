"""Ingestion Service Configuration."""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Ingestion service settings."""

    # SNMP Trap receiver settings
    snmp_enabled: bool = True
    snmp_trap_port: int = 162
    snmp_trap_address: str = "0.0.0.0"
    snmp_community_strings: str = "public,private"

    # NetStacks API endpoint for sending alerts
    netstacks_api_url: str = "http://ai:8000"

    # Default alert settings
    default_severity: str = "warning"

    # Logging
    log_level: str = "INFO"

    # Health check port (HTTP)
    health_port: int = 8162

    # Database URL for fetching databus source configs
    database_url: Optional[str] = None

    # Databus polling interval (seconds) - how often to check for config changes
    config_poll_interval: int = 60

    class Config:
        env_prefix = "INGESTION_"


settings = Settings()
