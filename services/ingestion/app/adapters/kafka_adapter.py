"""Kafka consumer adapter for ingesting alerts from Kafka topics."""
import asyncio
import logging
from typing import Optional, Dict, Any

from .base import BaseAdapter, DatabusSourceConfig

logger = logging.getLogger(__name__)


class KafkaAdapter(BaseAdapter):
    """Kafka consumer adapter."""

    def __init__(self, config: DatabusSourceConfig, api_url: str):
        super().__init__(config, api_url)
        self._consumer = None

    async def connect(self) -> bool:
        """Connect to Kafka."""
        try:
            from aiokafka import AIOKafkaConsumer

            conn_config = self.config.connection_config
            brokers = conn_config.get("brokers", ["localhost:9092"])
            if isinstance(brokers, str):
                brokers = [b.strip() for b in brokers.split(",")]

            self._consumer = AIOKafkaConsumer(
                self.config.topic_or_stream,
                bootstrap_servers=",".join(brokers),
                group_id=self.config.consumer_group or f"netstacks-{self.config.source_id}",
                auto_offset_reset=conn_config.get("auto_offset_reset", "latest"),
                enable_auto_commit=conn_config.get("enable_auto_commit", True),
                # Security settings if provided
                security_protocol=conn_config.get("security_protocol", "PLAINTEXT"),
                sasl_mechanism=conn_config.get("sasl_mechanism"),
                sasl_plain_username=conn_config.get("sasl_username"),
                sasl_plain_password=conn_config.get("sasl_password"),
            )

            await self._consumer.start()
            logger.info(f"Connected to Kafka: {brokers}, topic: {self.config.topic_or_stream}")
            return True

        except ImportError:
            logger.error("aiokafka not installed. Install with: pip install aiokafka")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}", exc_info=True)
            return False

    async def disconnect(self):
        """Disconnect from Kafka."""
        if self._consumer:
            try:
                await self._consumer.stop()
                logger.info(f"Disconnected from Kafka: {self.config.name}")
            except Exception as e:
                logger.warning(f"Error disconnecting from Kafka: {e}")
            self._consumer = None

    async def consume(self):
        """Consume messages from Kafka topic."""
        if not self._consumer:
            raise RuntimeError("Not connected to Kafka")

        async for message in self._consumer:
            if not self._running:
                break

            try:
                logger.debug(f"Received Kafka message: topic={message.topic}, "
                           f"partition={message.partition}, offset={message.offset}")

                # Transform message to alert
                alert_payload = self.transform_message(message.value)

                # Add Kafka-specific metadata
                alert_payload["raw_data"]["kafka_metadata"] = {
                    "topic": message.topic,
                    "partition": message.partition,
                    "offset": message.offset,
                    "timestamp": message.timestamp,
                    "key": message.key.decode() if message.key else None
                }

                # Send to alerts API
                await self.send_alert(alert_payload)

            except Exception as e:
                logger.error(f"Error processing Kafka message: {e}", exc_info=True)
                self.error_count += 1
