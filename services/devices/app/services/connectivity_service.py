"""
Connectivity Service

Handles device connectivity testing using Netmiko.
"""

import logging
import socket
from datetime import datetime
from typing import Any, Dict, Optional

from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)

log = logging.getLogger(__name__)


class ConnectivityService:
    """Service for testing device connectivity."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def test_connectivity(
        self,
        host: str,
        device_type: str,
        username: str,
        password: str,
        port: int = 22,
        secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Test connectivity to a device.

        Args:
            host: Device hostname or IP
            device_type: Netmiko device type (e.g., cisco_ios)
            username: SSH username
            password: SSH password
            port: SSH port (default 22)
            secret: Enable secret (optional)

        Returns:
            Dict with success status, timing, and device info
        """
        start_time = datetime.utcnow()
        result = {
            "host": host,
            "device_type": device_type,
            "port": port,
            "success": False,
            "message": "",
            "response_ms": 0,
            "device_info": {},
        }

        # First check if port is reachable
        if not self._check_port(host, port):
            result["message"] = f"Port {port} not reachable on {host}"
            result["response_ms"] = self._elapsed_ms(start_time)
            return result

        try:
            connection_params = {
                "device_type": device_type,
                "host": host,
                "username": username,
                "password": password,
                "port": port,
                "timeout": self.timeout,
                "conn_timeout": self.timeout,
                "auth_timeout": self.timeout,
            }

            if secret:
                connection_params["secret"] = secret

            with ConnectHandler(**connection_params) as conn:
                # Try to get basic info
                prompt = conn.find_prompt()
                result["device_info"]["prompt"] = prompt

                # Try to get hostname
                try:
                    if "cisco" in device_type.lower():
                        output = conn.send_command("show version | include uptime", read_timeout=5)
                        if output:
                            result["device_info"]["version_snippet"] = output.strip()[:200]
                    elif "juniper" in device_type.lower():
                        output = conn.send_command("show version | match Hostname", read_timeout=5)
                        if output:
                            result["device_info"]["version_snippet"] = output.strip()[:200]
                except Exception:
                    pass  # Version info is optional

                result["success"] = True
                result["message"] = "Connection successful"

        except NetmikoAuthenticationException as e:
            result["message"] = f"Authentication failed: {str(e)}"
            log.warning(f"Auth failed for {host}: {e}")

        except NetmikoTimeoutException as e:
            result["message"] = f"Connection timeout: {str(e)}"
            log.warning(f"Timeout for {host}: {e}")

        except Exception as e:
            result["message"] = f"Connection error: {str(e)}"
            log.error(f"Connection error for {host}: {e}", exc_info=True)

        result["response_ms"] = self._elapsed_ms(start_time)
        return result

    def _check_port(self, host: str, port: int, timeout: int = 3) -> bool:
        """Check if a port is reachable."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _elapsed_ms(self, start_time: datetime) -> int:
        """Calculate elapsed milliseconds."""
        return int((datetime.utcnow() - start_time).total_seconds() * 1000)
