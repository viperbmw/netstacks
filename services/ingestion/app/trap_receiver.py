"""SNMP Trap Receiver Adapter.

Listens for SNMP traps and converts them to NetStacks alerts.
Uses pysnmp with a separate thread for the dispatcher.
"""
import asyncio
import logging
import threading
import httpx
from typing import Optional, Dict, Any
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import engine, config
from pysnmp.entity.rfc3413 import ntfrcv

from .config import settings
from .trap_mappings import trap_mapper

logger = logging.getLogger(__name__)


class SNMPTrapReceiver:
    """SNMP Trap Receiver that forwards traps as alerts to NetStacks API."""

    def __init__(self, api_url: str):
        self.api_url = api_url
        self.snmp_engine: Optional[engine.SnmpEngine] = None
        self.trap_count = 0
        self.error_count = 0
        self._running = False
        self._dispatcher_thread: Optional[threading.Thread] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self, loop: asyncio.AbstractEventLoop):
        """Start the SNMP trap receiver."""
        trap_address = settings.snmp_trap_address
        trap_port = settings.snmp_trap_port

        logger.info(f"Starting SNMP Trap Receiver on {trap_address}:{trap_port}")

        self._running = True
        self._main_loop = loop

        # Create SNMP engine
        self.snmp_engine = engine.SnmpEngine()

        # Configure transport - UDP over IPv4 (synchronous mode)
        config.addTransport(
            self.snmp_engine,
            udp.domainName,
            udp.UdpTransport().openServerMode((trap_address, trap_port))
        )

        # Configure community strings for SNMPv1/v2c
        for community in settings.snmp_community_strings.split(','):
            community = community.strip()
            if community:
                config.addV1System(self.snmp_engine, community, community)
                logger.info(f"Added community string: {community}")

        # Register callback for incoming notifications
        ntfrcv.NotificationReceiver(self.snmp_engine, self._trap_callback)

        logger.info("SNMP Trap Receiver started successfully")
        logger.info(f"Will forward alerts to: {self.api_url}/api/alerts/")

        # Start dispatcher in a separate thread
        self.snmp_engine.transportDispatcher.jobStarted(1)
        self._dispatcher_thread = threading.Thread(target=self._run_dispatcher, daemon=True)
        self._dispatcher_thread.start()

    def _run_dispatcher(self):
        """Run the SNMP dispatcher in a separate thread."""
        try:
            logger.info("SNMP dispatcher thread started")
            # Run dispatcher loop manually to prevent immediate exit
            while self._running:
                try:
                    self.snmp_engine.transportDispatcher.runDispatcher(timeout=1.0)
                except Exception as e:
                    if self._running:
                        logger.debug(f"Dispatcher iteration: {e}")
        except Exception as e:
            logger.error(f"Dispatcher error: {e}", exc_info=True)
        finally:
            logger.info("SNMP dispatcher thread stopped")

    def _trap_callback(self, snmp_engine, state_reference, context_engine_id,
                       context_name, var_binds, cb_ctx):
        """Callback function for received SNMP traps."""
        try:
            # Get transport info
            transport_domain, transport_address = snmp_engine.msgAndPduDsp.getTransportInfo(state_reference)
            agent_address = transport_address[0] if transport_address else "unknown"

            logger.info(f"Received trap from {agent_address}")

            # Parse varbinds
            trap_oid = None
            enterprise_oid = None
            varbinds_dict: Dict[str, Any] = {}

            for oid, val in var_binds:
                oid_str = str(oid)
                val_str = str(val)

                # Check for snmpTrapOID.0 (1.3.6.1.6.3.1.1.4.1.0)
                if oid_str == "1.3.6.1.6.3.1.1.4.1.0":
                    trap_oid = val_str
                # Check for snmpTrapEnterprise.0 (1.3.6.1.6.3.1.1.4.3.0)
                elif oid_str == "1.3.6.1.6.3.1.1.4.3.0":
                    enterprise_oid = val_str
                else:
                    varbinds_dict[oid_str] = val_str

                logger.debug(f"  {oid_str} = {val_str}")

            # If no trap OID found, use generic
            if not trap_oid:
                trap_oid = "unknown"
                logger.warning("No snmpTrapOID found in trap, using 'unknown'")

            # Map trap to alert
            alert_payload = trap_mapper.map_trap_to_alert(
                trap_oid=trap_oid,
                agent_address=agent_address,
                varbinds=varbinds_dict,
                enterprise_oid=enterprise_oid
            )

            logger.info(f"Mapped trap to alert: {alert_payload['title']} (severity: {alert_payload['severity']})")

            # Send alert (thread-safe)
            if self._main_loop:
                asyncio.run_coroutine_threadsafe(self._send_alert(alert_payload), self._main_loop)

            self.trap_count += 1

        except Exception as e:
            logger.error(f"Error processing trap: {e}", exc_info=True)
            self.error_count += 1

    async def _send_alert(self, alert_payload: Dict[str, Any]):
        """Send alert to NetStacks API."""
        try:
            url = f"{self.api_url}/api/alerts/"
            logger.debug(f"Sending alert to {url}: {alert_payload}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=alert_payload)

                if response.status_code in (200, 201):
                    logger.info(f"Alert sent successfully: {alert_payload['title']}")
                else:
                    logger.error(f"Failed to send alert: {response.status_code} - {response.text}")
                    self.error_count += 1

        except Exception as e:
            logger.error(f"Error sending alert: {e}")
            self.error_count += 1

    async def stop(self):
        """Stop the trap receiver."""
        logger.info("Stopping SNMP Trap Receiver...")
        self._running = False

        if self.snmp_engine:
            try:
                self.snmp_engine.transportDispatcher.jobFinished(1)
            except Exception as e:
                logger.warning(f"Error stopping dispatcher job: {e}")

        logger.info(f"Trap Receiver stopped. Processed {self.trap_count} traps, {self.error_count} errors")

    def get_stats(self) -> Dict[str, Any]:
        """Get receiver statistics."""
        return {
            "source_type": "snmp_trap",
            "trap_count": self.trap_count,
            "error_count": self.error_count,
            "listening_address": settings.snmp_trap_address,
            "listening_port": settings.snmp_trap_port,
            "running": self._running
        }
