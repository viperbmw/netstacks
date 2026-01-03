"""Base adapter class for databus consumers."""
import asyncio
import logging
import httpx
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DatabusSourceConfig:
    """Configuration for a databus source."""
    source_id: str
    name: str
    source_type: str  # kafka, redis_stream, nats, rabbitmq
    connection_config: Dict[str, Any]  # broker URLs, credentials, etc.
    topic_or_stream: str
    consumer_group: Optional[str] = None
    transform_type: str = "json"  # json, syslog, cef, raw
    field_mappings: Optional[Dict[str, str]] = None  # map source fields to alert fields
    is_active: bool = True


class BaseAdapter(ABC):
    """Base class for all databus adapters."""

    def __init__(self, config: DatabusSourceConfig, api_url: str):
        self.config = config
        self.api_url = api_url
        self.message_count = 0
        self.error_count = 0
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @property
    def source_id(self) -> str:
        return self.config.source_id

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def source_type(self) -> str:
        return self.config.source_type

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the databus. Returns True if successful."""
        pass

    @abstractmethod
    async def disconnect(self):
        """Disconnect from the databus."""
        pass

    @abstractmethod
    async def consume(self):
        """Main consume loop - reads messages and processes them."""
        pass

    async def start(self):
        """Start the adapter."""
        self._running = True
        connected = await self.connect()
        if connected:
            self._task = asyncio.create_task(self._consume_loop())
            logger.info(f"Started adapter: {self.name} ({self.source_type})")
        else:
            logger.error(f"Failed to connect adapter: {self.name}")
            self._running = False

    async def stop(self):
        """Stop the adapter."""
        logger.info(f"Stopping adapter: {self.name}")
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.disconnect()
        logger.info(f"Adapter stopped: {self.name}. Processed {self.message_count} messages, {self.error_count} errors")

    async def _consume_loop(self):
        """Wrapper for consume loop with error handling."""
        while self._running:
            try:
                await self.consume()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in consume loop for {self.name}: {e}", exc_info=True)
                self.error_count += 1
                # Wait before retrying
                await asyncio.sleep(5)

    def transform_message(self, raw_message: Any) -> Dict[str, Any]:
        """Transform a raw message into an alert payload."""
        if self.config.transform_type == "json":
            return self._transform_json(raw_message)
        elif self.config.transform_type == "syslog":
            return self._transform_syslog(raw_message)
        elif self.config.transform_type == "cef":
            return self._transform_cef(raw_message)
        else:
            return self._transform_raw(raw_message)

    def _transform_json(self, raw_message: Any) -> Dict[str, Any]:
        """Transform JSON message to alert payload."""
        import json

        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode('utf-8')
        if isinstance(raw_message, str):
            data = json.loads(raw_message)
        else:
            data = raw_message

        # Apply field mappings if configured
        mappings = self.config.field_mappings or {}

        # Default field mapping
        alert = {
            "title": data.get(mappings.get("title", "title"),
                            data.get("message", data.get("name", f"Alert from {self.name}"))),
            "severity": data.get(mappings.get("severity", "severity"),
                                data.get("level", data.get("priority", "warning"))),
            "description": data.get(mappings.get("description", "description"),
                                   data.get("details", None)),
            "source": f"databus:{self.config.source_type}",
            "device_name": data.get(mappings.get("device_name", "device_name"),
                                   data.get("host", data.get("hostname", None))),
            "alert_type": data.get(mappings.get("alert_type", "alert_type"),
                                  data.get("type", data.get("category", "generic"))),
            "raw_data": {
                "source_id": self.config.source_id,
                "source_name": self.config.name,
                "source_type": self.config.source_type,
                "topic": self.config.topic_or_stream,
                "original_message": data
            }
        }

        # Normalize severity
        alert["severity"] = self._normalize_severity(alert["severity"])

        return alert

    def _transform_syslog(self, raw_message: Any) -> Dict[str, Any]:
        """Transform syslog message to alert payload."""
        import re

        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode('utf-8')

        # Simple syslog parsing (RFC 3164 style)
        # <PRI>TIMESTAMP HOSTNAME TAG: MESSAGE
        match = re.match(r'<(\d+)>(\w+ +\d+ \d+:\d+:\d+) (\S+) (\S+): (.+)', str(raw_message))

        if match:
            pri, timestamp, hostname, tag, message = match.groups()
            # Calculate severity from PRI (PRI = facility * 8 + severity)
            severity_num = int(pri) % 8
            severity_map = {
                0: "critical", 1: "critical", 2: "critical", 3: "critical",
                4: "warning", 5: "info", 6: "info", 7: "info"
            }
            severity = severity_map.get(severity_num, "warning")
        else:
            hostname = "unknown"
            tag = "syslog"
            message = str(raw_message)
            severity = "info"

        return {
            "title": f"Syslog from {hostname}: {tag}",
            "severity": severity,
            "description": message,
            "source": f"databus:{self.config.source_type}",
            "device_name": hostname,
            "alert_type": "syslog",
            "raw_data": {
                "source_id": self.config.source_id,
                "source_name": self.config.name,
                "source_type": self.config.source_type,
                "topic": self.config.topic_or_stream,
                "original_message": str(raw_message)
            }
        }

    def _transform_cef(self, raw_message: Any) -> Dict[str, Any]:
        """Transform CEF (Common Event Format) message to alert payload."""
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode('utf-8')

        # CEF format: CEF:Version|Device Vendor|Device Product|Device Version|Signature ID|Name|Severity|Extension
        parts = str(raw_message).split('|', 7)

        if len(parts) >= 7:
            vendor = parts[1]
            product = parts[2]
            sig_id = parts[4]
            name = parts[5]
            severity = parts[6]
            extension = parts[7] if len(parts) > 7 else ""
        else:
            vendor = "unknown"
            product = "unknown"
            sig_id = "unknown"
            name = str(raw_message)
            severity = "5"
            extension = ""

        # CEF severity: 0-3 Low, 4-6 Medium, 7-8 High, 9-10 Very High
        try:
            sev_num = int(severity)
            if sev_num <= 3:
                sev = "info"
            elif sev_num <= 6:
                sev = "warning"
            elif sev_num <= 8:
                sev = "critical"
            else:
                sev = "critical"
        except ValueError:
            sev = "warning"

        return {
            "title": f"{vendor} {product}: {name}",
            "severity": sev,
            "description": f"Signature: {sig_id}. {extension}",
            "source": f"databus:{self.config.source_type}",
            "device_name": None,
            "alert_type": "security",
            "raw_data": {
                "source_id": self.config.source_id,
                "source_name": self.config.name,
                "source_type": self.config.source_type,
                "topic": self.config.topic_or_stream,
                "original_message": str(raw_message)
            }
        }

    def _transform_raw(self, raw_message: Any) -> Dict[str, Any]:
        """Transform raw message to alert payload."""
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode('utf-8', errors='replace')

        return {
            "title": f"Message from {self.name}",
            "severity": "info",
            "description": str(raw_message)[:1000],  # Truncate
            "source": f"databus:{self.config.source_type}",
            "device_name": None,
            "alert_type": "generic",
            "raw_data": {
                "source_id": self.config.source_id,
                "source_name": self.config.name,
                "source_type": self.config.source_type,
                "topic": self.config.topic_or_stream,
                "original_message": str(raw_message)
            }
        }

    def _normalize_severity(self, severity: Any) -> str:
        """Normalize severity to standard values."""
        if isinstance(severity, int):
            if severity <= 1:
                return "critical"
            elif severity <= 3:
                return "warning"
            else:
                return "info"

        severity = str(severity).lower()
        severity_map = {
            "critical": "critical",
            "high": "critical",
            "error": "critical",
            "err": "critical",
            "crit": "critical",
            "alert": "critical",
            "emerg": "critical",
            "emergency": "critical",
            "warning": "warning",
            "warn": "warning",
            "medium": "warning",
            "notice": "warning",
            "info": "info",
            "information": "info",
            "informational": "info",
            "low": "info",
            "debug": "info",
        }
        return severity_map.get(severity, "warning")

    async def send_alert(self, alert_payload: Dict[str, Any]):
        """Send alert to NetStacks API."""
        try:
            url = f"{self.api_url}/api/alerts/"
            logger.debug(f"Sending alert to {url}: {alert_payload.get('title')}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=alert_payload)

                if response.status_code in (200, 201):
                    logger.info(f"Alert sent: {alert_payload.get('title')}")
                    self.message_count += 1
                else:
                    logger.error(f"Failed to send alert: {response.status_code} - {response.text}")
                    self.error_count += 1

        except Exception as e:
            logger.error(f"Error sending alert: {e}")
            self.error_count += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics."""
        return {
            "source_id": self.config.source_id,
            "name": self.config.name,
            "source_type": self.config.source_type,
            "topic": self.config.topic_or_stream,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "running": self._running
        }
