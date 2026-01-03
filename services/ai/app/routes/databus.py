# services/ai/app/routes/databus.py
"""Databus source configuration routes for alert ingestion."""

import logging
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from netstacks_core.db import get_session, DatabusSource
from netstacks_core.auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter()


class DatabusSourceCreate(BaseModel):
    """Create a new databus source."""
    name: str
    source_type: str  # 'kafka', 'redis_stream'
    is_enabled: bool = True
    connection_config: dict = {}
    topic_or_stream: str
    consumer_group: Optional[str] = None
    transform_type: str = "json"
    field_mappings: Optional[dict] = None


class DatabusSourceUpdate(BaseModel):
    """Update an existing databus source."""
    name: Optional[str] = None
    is_enabled: Optional[bool] = None
    connection_config: Optional[dict] = None
    topic_or_stream: Optional[str] = None
    consumer_group: Optional[str] = None
    transform_type: Optional[str] = None
    field_mappings: Optional[dict] = None


def source_to_dict(source: DatabusSource) -> dict:
    """Convert DatabusSource model to dict."""
    return {
        "source_id": source.source_id,
        "name": source.name,
        "source_type": source.source_type,
        "is_enabled": source.is_enabled,
        "connection_config": source.connection_config or {},
        "topic_or_stream": source.topic_or_stream,
        "consumer_group": source.consumer_group,
        "transform_type": source.transform_type,
        "field_mappings": source.field_mappings or {},
        "message_count": source.message_count or 0,
        "error_count": source.error_count or 0,
        "last_message_at": source.last_message_at.isoformat() if source.last_message_at else None,
        "last_error": source.last_error,
        "created_at": source.created_at.isoformat() if source.created_at else None,
        "updated_at": source.updated_at.isoformat() if source.updated_at else None,
    }


@router.get("/")
async def list_databus_sources(
    source_type: Optional[str] = Query(None),
    is_enabled: Optional[bool] = Query(None),
    user=Depends(get_current_user)
):
    """List all databus sources."""
    session = get_session()
    try:
        query = session.query(DatabusSource)

        if source_type:
            query = query.filter(DatabusSource.source_type == source_type)
        if is_enabled is not None:
            query = query.filter(DatabusSource.is_enabled == is_enabled)

        sources = query.order_by(DatabusSource.name).all()

        return {
            "success": True,
            "sources": [source_to_dict(s) for s in sources]
        }
    finally:
        session.close()


@router.get("/active")
async def list_active_sources():
    """List active databus sources (for ingestion service to poll)."""
    session = get_session()
    try:
        sources = session.query(DatabusSource).filter(
            DatabusSource.is_enabled == True
        ).all()

        return {
            "success": True,
            "sources": [
                {
                    "source_id": s.source_id,
                    "name": s.name,
                    "source_type": s.source_type,
                    "connection_config": s.connection_config or {},
                    "topic_or_stream": s.topic_or_stream,
                    "consumer_group": s.consumer_group,
                    "transform_type": s.transform_type,
                    "field_mappings": s.field_mappings or {},
                    "is_active": True,
                }
                for s in sources
            ]
        }
    finally:
        session.close()


@router.post("/")
async def create_databus_source(source: DatabusSourceCreate, user=Depends(get_current_user)):
    """Create a new databus source."""
    session = get_session()
    try:
        # Check for duplicate name
        existing = session.query(DatabusSource).filter(
            DatabusSource.name == source.name
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Source with this name already exists")

        # Validate source type
        valid_types = ['kafka', 'redis_stream']
        if source.source_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid source_type. Must be one of: {', '.join(valid_types)}"
            )

        new_source = DatabusSource(
            source_id=str(uuid.uuid4()),
            name=source.name,
            source_type=source.source_type,
            is_enabled=source.is_enabled,
            connection_config=source.connection_config,
            topic_or_stream=source.topic_or_stream,
            consumer_group=source.consumer_group,
            transform_type=source.transform_type,
            field_mappings=source.field_mappings or {},
            created_by=user.get("sub") if isinstance(user, dict) else getattr(user, "sub", None),
        )
        session.add(new_source)
        session.commit()
        session.refresh(new_source)

        log.info(f"Created databus source: {source.name} ({source.source_type})")

        return {
            "success": True,
            "source": source_to_dict(new_source)
        }
    finally:
        session.close()


@router.get("/{source_id}")
async def get_databus_source(source_id: str, user=Depends(get_current_user)):
    """Get a databus source by ID."""
    session = get_session()
    try:
        source = session.query(DatabusSource).filter(
            DatabusSource.source_id == source_id
        ).first()

        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        return {
            "success": True,
            "source": source_to_dict(source)
        }
    finally:
        session.close()


@router.put("/{source_id}")
async def update_databus_source(
    source_id: str,
    update: DatabusSourceUpdate,
    user=Depends(get_current_user)
):
    """Update a databus source."""
    session = get_session()
    try:
        source = session.query(DatabusSource).filter(
            DatabusSource.source_id == source_id
        ).first()

        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Update fields
        if update.name is not None:
            # Check for duplicate
            existing = session.query(DatabusSource).filter(
                DatabusSource.name == update.name,
                DatabusSource.source_id != source_id
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail="Source with this name already exists")
            source.name = update.name

        if update.is_enabled is not None:
            source.is_enabled = update.is_enabled
        if update.connection_config is not None:
            source.connection_config = update.connection_config
        if update.topic_or_stream is not None:
            source.topic_or_stream = update.topic_or_stream
        if update.consumer_group is not None:
            source.consumer_group = update.consumer_group
        if update.transform_type is not None:
            source.transform_type = update.transform_type
        if update.field_mappings is not None:
            source.field_mappings = update.field_mappings

        session.commit()
        session.refresh(source)

        log.info(f"Updated databus source: {source.name}")

        return {
            "success": True,
            "source": source_to_dict(source)
        }
    finally:
        session.close()


@router.delete("/{source_id}")
async def delete_databus_source(source_id: str, user=Depends(get_current_user)):
    """Delete a databus source."""
    session = get_session()
    try:
        source = session.query(DatabusSource).filter(
            DatabusSource.source_id == source_id
        ).first()

        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        name = source.name
        session.delete(source)
        session.commit()

        log.info(f"Deleted databus source: {name}")

        return {
            "success": True,
            "message": f"Source '{name}' deleted"
        }
    finally:
        session.close()


@router.post("/{source_id}/toggle")
async def toggle_databus_source(source_id: str, user=Depends(get_current_user)):
    """Toggle enabled/disabled state of a databus source."""
    session = get_session()
    try:
        source = session.query(DatabusSource).filter(
            DatabusSource.source_id == source_id
        ).first()

        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        source.is_enabled = not source.is_enabled
        session.commit()

        state = "enabled" if source.is_enabled else "disabled"
        log.info(f"Toggled databus source {source.name}: {state}")

        return {
            "success": True,
            "is_enabled": source.is_enabled,
            "message": f"Source {state}"
        }
    finally:
        session.close()


@router.post("/{source_id}/test")
async def test_databus_source(source_id: str, user=Depends(get_current_user)):
    """Test connection to a databus source."""
    session = get_session()
    try:
        source = session.query(DatabusSource).filter(
            DatabusSource.source_id == source_id
        ).first()

        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Test connection based on type
        if source.source_type == 'kafka':
            return await _test_kafka_connection(source)
        elif source.source_type == 'redis_stream':
            return await _test_redis_connection(source)
        else:
            return {
                "success": False,
                "error": f"Unknown source type: {source.source_type}"
            }
    finally:
        session.close()


async def _test_kafka_connection(source: DatabusSource) -> dict:
    """Test Kafka connection."""
    try:
        from aiokafka import AIOKafkaConsumer
        import asyncio

        conn_config = source.connection_config or {}
        bootstrap_servers = conn_config.get("bootstrap_servers", "localhost:9092")

        consumer = AIOKafkaConsumer(
            source.topic_or_stream,
            bootstrap_servers=bootstrap_servers,
            group_id=source.consumer_group or f"test-{source.source_id}",
            auto_offset_reset="latest",
            enable_auto_commit=False,
            **{k: v for k, v in conn_config.items() if k not in ['bootstrap_servers']}
        )

        await asyncio.wait_for(consumer.start(), timeout=10)
        await consumer.stop()

        return {
            "success": True,
            "message": f"Connected to Kafka: {bootstrap_servers}, topic: {source.topic_or_stream}"
        }
    except ImportError:
        return {
            "success": False,
            "error": "aiokafka not installed on ingestion service"
        }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Connection timeout"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def _test_redis_connection(source: DatabusSource) -> dict:
    """Test Redis Streams connection."""
    try:
        import redis.asyncio as aioredis

        conn_config = source.connection_config or {}
        url = conn_config.get("url", "redis://localhost:6379/0")

        client = aioredis.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
            password=conn_config.get("password"),
        )

        await client.ping()

        # Check if stream exists
        stream_info = await client.xinfo_stream(source.topic_or_stream)
        msg_count = stream_info.get("length", 0)

        await client.close()

        return {
            "success": True,
            "message": f"Connected to Redis, stream: {source.topic_or_stream} ({msg_count} messages)"
        }
    except ImportError:
        return {
            "success": False,
            "error": "redis package not installed on ingestion service"
        }
    except Exception as e:
        error_msg = str(e)
        if "no such key" in error_msg.lower():
            return {
                "success": True,
                "message": f"Connected to Redis (stream '{source.topic_or_stream}' does not exist yet, will be created)"
            }
        return {
            "success": False,
            "error": error_msg
        }
