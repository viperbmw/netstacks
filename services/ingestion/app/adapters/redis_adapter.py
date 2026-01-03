"""Redis Streams consumer adapter for ingesting alerts."""
import asyncio
import logging
from typing import Optional, Dict, Any, List

from .base import BaseAdapter, DatabusSourceConfig

logger = logging.getLogger(__name__)


class RedisStreamsAdapter(BaseAdapter):
    """Redis Streams consumer adapter."""

    def __init__(self, config: DatabusSourceConfig, api_url: str):
        super().__init__(config, api_url)
        self._redis = None
        self._last_id = ">"  # Only new messages

    async def connect(self) -> bool:
        """Connect to Redis."""
        try:
            import redis.asyncio as aioredis

            conn_config = self.config.connection_config
            url = conn_config.get("url", "redis://localhost:6379/0")

            self._redis = aioredis.from_url(
                url,
                encoding="utf-8",
                decode_responses=True,
                password=conn_config.get("password"),
            )

            # Test connection
            await self._redis.ping()

            # Create consumer group if it doesn't exist
            group_name = self.config.consumer_group or f"netstacks-{self.config.source_id}"
            stream_name = self.config.topic_or_stream

            try:
                await self._redis.xgroup_create(
                    stream_name,
                    group_name,
                    id="0",
                    mkstream=True
                )
                logger.info(f"Created consumer group: {group_name}")
            except Exception as e:
                # Group already exists
                if "BUSYGROUP" not in str(e):
                    raise

            logger.info(f"Connected to Redis Streams: {url}, stream: {stream_name}")
            return True

        except ImportError:
            logger.error("redis package not installed. Install with: pip install redis")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}", exc_info=True)
            return False

    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis:
            try:
                await self._redis.close()
                logger.info(f"Disconnected from Redis: {self.config.name}")
            except Exception as e:
                logger.warning(f"Error disconnecting from Redis: {e}")
            self._redis = None

    async def consume(self):
        """Consume messages from Redis Stream."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")

        stream_name = self.config.topic_or_stream
        group_name = self.config.consumer_group or f"netstacks-{self.config.source_id}"
        consumer_name = f"ingestion-{self.config.source_id}"

        while self._running:
            try:
                # Read from stream using consumer group
                messages = await self._redis.xreadgroup(
                    groupname=group_name,
                    consumername=consumer_name,
                    streams={stream_name: ">"},
                    count=10,
                    block=5000  # Block for 5 seconds
                )

                if not messages:
                    continue

                for stream, stream_messages in messages:
                    for message_id, data in stream_messages:
                        if not self._running:
                            break

                        try:
                            logger.debug(f"Received Redis message: stream={stream}, id={message_id}")

                            # Transform message to alert
                            # Redis stream data is already a dict
                            alert_payload = self.transform_message(data)

                            # Add Redis-specific metadata
                            alert_payload["raw_data"]["redis_metadata"] = {
                                "stream": stream,
                                "message_id": message_id,
                            }

                            # Send to alerts API
                            await self.send_alert(alert_payload)

                            # Acknowledge message
                            await self._redis.xack(stream_name, group_name, message_id)

                        except Exception as e:
                            logger.error(f"Error processing Redis message {message_id}: {e}", exc_info=True)
                            self.error_count += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading from Redis stream: {e}", exc_info=True)
                self.error_count += 1
                await asyncio.sleep(5)  # Wait before retrying

    def transform_message(self, raw_message: Any) -> Dict[str, Any]:
        """Transform Redis stream message (already a dict) to alert payload."""
        # Redis stream messages are already dicts
        if isinstance(raw_message, dict):
            # Check if it looks like a JSON string in a field
            if "data" in raw_message:
                import json
                try:
                    parsed = json.loads(raw_message["data"])
                    return super()._transform_json(parsed)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Use the dict directly
            return super()._transform_json(raw_message)

        return super().transform_message(raw_message)
