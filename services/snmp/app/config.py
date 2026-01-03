"""SNMP Trap Receiver Configuration."""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """SNMP service settings."""

    # Trap receiver settings
    trap_port: int = 162
    trap_address: str = "0.0.0.0"

    # Community strings (comma-separated for multiple)
    community_strings: str = "public,private"

    # NetStacks API endpoint for sending alerts
    netstacks_api_url: str = "http://ai:8000"

    # Default alert settings
    default_severity: str = "warning"
    default_source: str = "snmp_trap"

    # Logging
    log_level: str = "INFO"

    # Health check port (HTTP)
    health_port: int = 8162

    class Config:
        env_prefix = "SNMP_"


settings = Settings()
