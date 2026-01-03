"""Ingestion Service - Main Entry Point.

Unified service for ingesting alerts from multiple sources:
- SNMP Traps
- Kafka topics
- Redis Streams
- Other databus sources (configurable)
"""
import asyncio
import logging
import signal
import sys
import json
import httpx
from aiohttp import web
from typing import Optional, Dict, List, Any

from .config import settings
from .trap_receiver import SNMPTrapReceiver
from .adapters.base import BaseAdapter, DatabusSourceConfig
from .adapters.kafka_adapter import KafkaAdapter
from .adapters.redis_adapter import RedisStreamsAdapter

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IngestionService:
    """Main ingestion service that manages all alert sources."""

    def __init__(self):
        self.health_app: Optional[web.Application] = None
        self.health_runner: Optional[web.AppRunner] = None
        self.shutdown_event = asyncio.Event()

        # SNMP trap receiver
        self.snmp_receiver: Optional[SNMPTrapReceiver] = None

        # Databus adapters
        self.adapters: Dict[str, BaseAdapter] = {}

        # Adapter factory
        self.adapter_types = {
            "kafka": KafkaAdapter,
            "redis_stream": RedisStreamsAdapter,
        }

    def _create_adapter(self, config: DatabusSourceConfig) -> Optional[BaseAdapter]:
        """Create an adapter based on source type."""
        adapter_class = self.adapter_types.get(config.source_type)
        if adapter_class:
            return adapter_class(config, settings.netstacks_api_url)
        else:
            logger.warning(f"Unknown adapter type: {config.source_type}")
            return None

    async def load_databus_sources(self) -> List[DatabusSourceConfig]:
        """Load databus source configurations.

        Sources are loaded from:
        1. Database via API (primary - configured via UI)
        2. Environment variable INGESTION_DATABUS_SOURCES (fallback)
        """
        sources = []

        # Try to load from API (database)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{settings.netstacks_api_url}/api/databus-sources/active")
                if response.status_code == 200:
                    data = response.json()
                    for s in data.get("sources", []):
                        sources.append(DatabusSourceConfig(
                            source_id=s.get("source_id", "unknown"),
                            name=s.get("name", "Unknown Source"),
                            source_type=s.get("source_type", "kafka"),
                            connection_config=s.get("connection_config", {}),
                            topic_or_stream=s.get("topic_or_stream", "alerts"),
                            consumer_group=s.get("consumer_group"),
                            transform_type=s.get("transform_type", "json"),
                            field_mappings=s.get("field_mappings"),
                            is_active=s.get("is_active", True),
                        ))
                    if sources:
                        logger.info(f"Loaded {len(sources)} databus sources from database")
                        return sources
        except Exception as e:
            logger.warning(f"Could not load sources from API: {e}")

        # Fallback to environment variable
        import os
        env_json = os.environ.get("INGESTION_DATABUS_SOURCES")
        if env_json:
            try:
                source_list = json.loads(env_json)
                for s in source_list:
                    sources.append(DatabusSourceConfig(
                        source_id=s.get("source_id", s.get("name", "unknown")),
                        name=s.get("name", "Unknown Source"),
                        source_type=s.get("source_type", "kafka"),
                        connection_config=s.get("connection_config", {}),
                        topic_or_stream=s.get("topic", s.get("stream", "alerts")),
                        consumer_group=s.get("consumer_group"),
                        transform_type=s.get("transform_type", "json"),
                        field_mappings=s.get("field_mappings"),
                        is_active=s.get("is_active", True),
                    ))
                logger.info(f"Loaded {len(sources)} databus sources from environment")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse INGESTION_DATABUS_SOURCES: {e}")

        return sources

    async def start_adapters(self):
        """Start all configured databus adapters."""
        sources = await self.load_databus_sources()

        for source_config in sources:
            if not source_config.is_active:
                logger.info(f"Skipping inactive source: {source_config.name}")
                continue

            adapter = self._create_adapter(source_config)
            if adapter:
                try:
                    await adapter.start()
                    self.adapters[source_config.source_id] = adapter
                    logger.info(f"Started adapter: {source_config.name} ({source_config.source_type})")
                except Exception as e:
                    logger.error(f"Failed to start adapter {source_config.name}: {e}")

    async def stop_adapters(self):
        """Stop all running adapters."""
        for source_id, adapter in self.adapters.items():
            try:
                await adapter.stop()
            except Exception as e:
                logger.error(f"Error stopping adapter {source_id}: {e}")
        self.adapters.clear()

    def get_all_stats(self) -> Dict[str, Any]:
        """Get stats from all sources."""
        stats = {
            "service": "ingestion",
            "sources": {}
        }

        # SNMP stats
        if self.snmp_receiver:
            snmp_stats = self.snmp_receiver.get_stats()
            stats["sources"]["snmp_trap"] = snmp_stats
            stats["trap_count"] = snmp_stats.get("trap_count", 0)
            stats["snmp_errors"] = snmp_stats.get("error_count", 0)

        # Databus adapter stats
        total_messages = 0
        total_errors = 0
        for source_id, adapter in self.adapters.items():
            adapter_stats = adapter.get_stats()
            stats["sources"][source_id] = adapter_stats
            total_messages += adapter_stats.get("message_count", 0)
            total_errors += adapter_stats.get("error_count", 0)

        stats["databus_message_count"] = total_messages
        stats["databus_errors"] = total_errors

        return stats

    async def health_handler(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        stats = self.get_all_stats()
        return web.json_response({
            "status": "healthy",
            **stats
        })

    async def stats_handler(self, request: web.Request) -> web.Response:
        """Detailed statistics endpoint."""
        stats = self.get_all_stats()
        return web.json_response(stats)

    async def sources_handler(self, request: web.Request) -> web.Response:
        """List all configured sources and their status."""
        sources = []

        # SNMP source
        if self.snmp_receiver:
            sources.append({
                "source_id": "snmp_trap",
                "name": "SNMP Trap Receiver",
                "source_type": "snmp_trap",
                "status": "running" if self.snmp_receiver._running else "stopped",
                **self.snmp_receiver.get_stats()
            })

        # Databus sources
        for source_id, adapter in self.adapters.items():
            sources.append({
                "status": "running" if adapter._running else "stopped",
                **adapter.get_stats()
            })

        return web.json_response({"sources": sources})

    async def mappings_handler(self, request: web.Request) -> web.Response:
        """List configured SNMP trap mappings."""
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

    async def start_health_server(self):
        """Start the HTTP health check server."""
        self.health_app = web.Application()
        self.health_app.router.add_get('/health', self.health_handler)
        self.health_app.router.add_get('/stats', self.stats_handler)
        self.health_app.router.add_get('/sources', self.sources_handler)
        self.health_app.router.add_get('/mappings', self.mappings_handler)

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
        """Run the ingestion service."""
        logger.info("=" * 60)
        logger.info("NetStacks Ingestion Service")
        logger.info("=" * 60)
        logger.info(f"SNMP Enabled: {settings.snmp_enabled}")
        if settings.snmp_enabled:
            logger.info(f"SNMP Trap Port: {settings.snmp_trap_port}")
        logger.info(f"Health Port: {settings.health_port}")
        logger.info(f"API URL: {settings.netstacks_api_url}")
        logger.info("=" * 60)

        # Start health server
        await self.start_health_server()

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        try:
            # Start SNMP trap receiver if enabled
            if settings.snmp_enabled:
                self.snmp_receiver = SNMPTrapReceiver(settings.netstacks_api_url)
                await self.snmp_receiver.start(loop)

            # Start databus adapters
            await self.start_adapters()

            # Keep running until shutdown
            while not self.shutdown_event.is_set():
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Ingestion service error: {e}", exc_info=True)
        finally:
            await self.cleanup()

    async def shutdown(self):
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")

        # Stop SNMP receiver
        if self.snmp_receiver:
            await self.snmp_receiver.stop()

        # Stop all adapters
        await self.stop_adapters()

        self.shutdown_event.set()

    async def cleanup(self):
        """Clean up resources."""
        await self.stop_health_server()
        logger.info("Ingestion Service shutdown complete")


def main():
    """Main entry point."""
    service = IngestionService()
    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Service error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
