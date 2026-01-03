"""SNMP Trap Receiver Service - Main Entry Point.

Runs both the SNMP trap receiver and a health check HTTP server.
"""
import asyncio
import logging
import signal
import sys
from aiohttp import web
from typing import Optional

from .config import settings
from .trap_receiver import trap_receiver

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def health_handler(request: web.Request) -> web.Response:
    """Health check endpoint."""
    stats = trap_receiver.get_stats()
    return web.json_response({
        "status": "healthy",
        "service": "snmp-trap-receiver",
        **stats
    })


async def stats_handler(request: web.Request) -> web.Response:
    """Statistics endpoint."""
    stats = trap_receiver.get_stats()
    return web.json_response(stats)


async def mappings_handler(request: web.Request) -> web.Response:
    """List configured trap mappings."""
    from .trap_mappings import DEFAULT_TRAP_MAPPINGS
    mappings = []
    for m in DEFAULT_TRAP_MAPPINGS:
        mappings.append({
            "oid_pattern": m.oid_pattern,
            "alert_type": m.alert_type,
            "title_template": m.title_template,
            "severity": m.severity
        })
    return web.json_response({"mappings": mappings})


class SNMPService:
    """Main SNMP service that runs trap receiver and health server."""

    def __init__(self):
        self.health_app: Optional[web.Application] = None
        self.health_runner: Optional[web.AppRunner] = None
        self.shutdown_event = asyncio.Event()

    async def start_health_server(self):
        """Start the HTTP health check server."""
        self.health_app = web.Application()
        self.health_app.router.add_get('/health', health_handler)
        self.health_app.router.add_get('/stats', stats_handler)
        self.health_app.router.add_get('/mappings', mappings_handler)

        self.health_runner = web.AppRunner(self.health_app)
        await self.health_runner.setup()
        site = web.TCPSite(self.health_runner, '0.0.0.0', settings.health_port)
        await site.start()
        logger.info(f"Health check server started on port {settings.health_port}")

    async def stop_health_server(self):
        """Stop the health check server."""
        if self.health_runner:
            await self.health_runner.cleanup()
            logger.info("Health check server stopped")

    async def run(self):
        """Run the SNMP service."""
        logger.info("=" * 60)
        logger.info("NetStacks SNMP Trap Receiver Service")
        logger.info("=" * 60)
        logger.info(f"Trap Port: {settings.trap_port}")
        logger.info(f"Health Port: {settings.health_port}")
        logger.info(f"API URL: {settings.netstacks_api_url}")
        logger.info("=" * 60)

        # Start health server
        await self.start_health_server()

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        try:
            # Start trap receiver (blocking)
            loop = asyncio.get_running_loop()
            await trap_receiver.start(loop)
        except Exception as e:
            logger.error(f"Trap receiver error: {e}", exc_info=True)
        finally:
            await self.cleanup()

    async def shutdown(self):
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        await trap_receiver.stop()
        self.shutdown_event.set()

    async def cleanup(self):
        """Clean up resources."""
        await self.stop_health_server()
        logger.info("SNMP Service shutdown complete")


def main():
    """Main entry point."""
    service = SNMPService()
    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Service error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
