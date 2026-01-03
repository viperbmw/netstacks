# Ingestion Adapters
from .base import BaseAdapter
from .kafka_adapter import KafkaAdapter
from .redis_adapter import RedisStreamsAdapter

__all__ = ['BaseAdapter', 'KafkaAdapter', 'RedisStreamsAdapter']
