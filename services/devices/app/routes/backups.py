"""
Config backup management routes.

Provides endpoints for managing device configuration backups.
"""

import logging
from typing import Optional, List
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from netstacks_core.db import get_db, ConfigBackup, ConfigSnapshot, BackupSchedule

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config-backups", tags=["backups"])


# Pydantic response models
class BackupResponse(BaseModel):
    backup_id: str
    device_name: str
    device_ip: Optional[str] = None
    platform: Optional[str] = None
    config_content: Optional[str] = None
    config_format: str = "native"
    config_hash: Optional[str] = None
    backup_type: str = "scheduled"
    status: str = "success"
    error_message: Optional[str] = None
    file_size: Optional[int] = None
    snapshot_id: Optional[str] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class BackupSummary(BaseModel):
    total_backups: int = 0
    total_devices: int = 0
    last_backup: Optional[datetime] = None
    total_size_bytes: int = 0


class BackupListResponse(BaseModel):
    backups: List[BackupResponse]
    summary: BackupSummary
    limit: int
    offset: int


class ScheduleResponse(BaseModel):
    schedule_id: str = "default"
    enabled: bool = False
    interval_hours: int = 24
    retention_days: int = 30
    juniper_set_format: bool = True
    include_filters: List[str] = []
    exclude_patterns: List[str] = []
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None


class ScheduleUpdateRequest(BaseModel):
    enabled: bool = False
    interval_hours: int = Field(default=24, ge=1, le=168)
    retention_days: int = Field(default=30, ge=1, le=365)
    juniper_set_format: bool = True
    include_filters: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None


class CleanupRequest(BaseModel):
    retention_days: Optional[int] = Field(default=None, ge=1, le=365)


def get_backup_summary(db: Session) -> BackupSummary:
    """Get summary statistics for backups."""
    total = db.query(func.count(ConfigBackup.backup_id)).scalar() or 0
    devices = db.query(func.count(func.distinct(ConfigBackup.device_name))).scalar() or 0
    last = db.query(func.max(ConfigBackup.created_at)).scalar()
    size = db.query(func.sum(ConfigBackup.file_size)).scalar() or 0

    return BackupSummary(
        total_backups=total,
        total_devices=devices,
        last_backup=last,
        total_size_bytes=size
    )


@router.get("")
async def list_config_backups(
    device: Optional[str] = Query(None, description="Filter by device name"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List config backups with optional filters."""
    query = db.query(ConfigBackup).order_by(desc(ConfigBackup.created_at))

    if device:
        query = query.filter(ConfigBackup.device_name == device)

    backups = query.offset(offset).limit(limit).all()
    summary = get_backup_summary(db)

    # Convert to response dicts (exclude config_content for list view)
    backup_list = []
    for b in backups:
        backup_list.append({
            "backup_id": b.backup_id,
            "device_name": b.device_name,
            "device_ip": b.device_ip,
            "platform": b.platform,
            "config_content": None,  # Exclude content in list
            "config_format": b.config_format or "native",
            "config_hash": b.config_hash,
            "backup_type": b.backup_type or "scheduled",
            "status": b.status or "success",
            "error_message": b.error_message,
            "file_size": b.file_size,
            "snapshot_id": b.snapshot_id,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "created_by": b.created_by
        })

    return {
        "success": True,
        "backups": backup_list,
        "summary": {
            "total_backups": summary.total_backups,
            "unique_devices": summary.total_devices,
            "latest_backup": summary.last_backup.isoformat() if summary.last_backup else None,
            "total_size_bytes": summary.total_size_bytes
        },
        "limit": limit,
        "offset": offset
    }


@router.get("/{backup_id}")
async def get_config_backup(
    backup_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific backup by ID, including full config content."""
    backup = db.query(ConfigBackup).filter(
        ConfigBackup.backup_id == backup_id
    ).first()

    if not backup:
        raise HTTPException(status_code=404, detail=f"Backup not found: {backup_id}")

    return {
        "success": True,
        "backup": {
            "backup_id": backup.backup_id,
            "device_name": backup.device_name,
            "device_ip": backup.device_ip,
            "platform": backup.platform,
            "config_content": backup.config_content,
            "config_format": backup.config_format or "native",
            "config_hash": backup.config_hash,
            "backup_type": backup.backup_type or "scheduled",
            "status": backup.status or "success",
            "error_message": backup.error_message,
            "file_size": backup.file_size,
            "snapshot_id": backup.snapshot_id,
            "created_at": backup.created_at.isoformat() if backup.created_at else None,
            "created_by": backup.created_by
        }
    }


@router.delete("/{backup_id}")
async def delete_config_backup(
    backup_id: str,
    db: Session = Depends(get_db)
):
    """Delete a specific backup."""
    backup = db.query(ConfigBackup).filter(
        ConfigBackup.backup_id == backup_id
    ).first()

    if not backup:
        raise HTTPException(status_code=404, detail=f"Backup not found: {backup_id}")

    db.delete(backup)
    db.commit()

    log.info(f"Config backup deleted: {backup_id}")
    return {"message": "Backup deleted", "backup_id": backup_id}


@router.get("/device/{device_name}/latest", response_model=BackupResponse)
async def get_latest_device_backup(
    device_name: str,
    db: Session = Depends(get_db)
):
    """Get the latest backup for a specific device."""
    backup = db.query(ConfigBackup).filter(
        ConfigBackup.device_name == device_name
    ).order_by(desc(ConfigBackup.created_at)).first()

    if not backup:
        raise HTTPException(
            status_code=404,
            detail=f"No backup found for device: {device_name}"
        )

    return BackupResponse(
        backup_id=backup.backup_id,
        device_name=backup.device_name,
        device_ip=backup.device_ip,
        platform=backup.platform,
        config_content=backup.config_content,
        config_format=backup.config_format or "native",
        config_hash=backup.config_hash,
        backup_type=backup.backup_type or "scheduled",
        status=backup.status or "success",
        error_message=backup.error_message,
        file_size=backup.file_size,
        snapshot_id=backup.snapshot_id,
        created_at=backup.created_at,
        created_by=backup.created_by
    )


# Backup schedule endpoints (separate prefix)
schedule_router = APIRouter(prefix="/api/backup-schedule", tags=["backup-schedule"])


@schedule_router.get("", response_model=ScheduleResponse)
async def get_backup_schedule(db: Session = Depends(get_db)):
    """Get the backup schedule configuration."""
    schedule = db.query(BackupSchedule).filter(
        BackupSchedule.schedule_id == "default"
    ).first()

    if not schedule:
        # Return defaults
        return ScheduleResponse()

    return ScheduleResponse(
        schedule_id=schedule.schedule_id,
        enabled=schedule.enabled or False,
        interval_hours=schedule.interval_hours or 24,
        retention_days=schedule.retention_days or 30,
        juniper_set_format=schedule.juniper_set_format if schedule.juniper_set_format is not None else True,
        include_filters=schedule.include_filters or [],
        exclude_patterns=schedule.exclude_patterns or [],
        last_run=schedule.last_run,
        next_run=schedule.next_run
    )


@schedule_router.put("", response_model=ScheduleResponse)
async def update_backup_schedule(
    request: ScheduleUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update the backup schedule configuration."""
    schedule = db.query(BackupSchedule).filter(
        BackupSchedule.schedule_id == "default"
    ).first()

    if not schedule:
        schedule = BackupSchedule(schedule_id="default")
        db.add(schedule)

    schedule.enabled = request.enabled
    schedule.interval_hours = request.interval_hours
    schedule.retention_days = request.retention_days
    schedule.juniper_set_format = request.juniper_set_format

    if request.include_filters is not None:
        schedule.include_filters = request.include_filters
    if request.exclude_patterns is not None:
        schedule.exclude_patterns = request.exclude_patterns

    # Calculate next run if enabled
    if schedule.enabled:
        schedule.next_run = datetime.utcnow() + timedelta(hours=schedule.interval_hours)

    db.commit()
    db.refresh(schedule)

    log.info(f"Backup schedule updated: enabled={schedule.enabled}, interval={schedule.interval_hours}h")

    return ScheduleResponse(
        schedule_id=schedule.schedule_id,
        enabled=schedule.enabled or False,
        interval_hours=schedule.interval_hours or 24,
        retention_days=schedule.retention_days or 30,
        juniper_set_format=schedule.juniper_set_format if schedule.juniper_set_format is not None else True,
        include_filters=schedule.include_filters or [],
        exclude_patterns=schedule.exclude_patterns or [],
        last_run=schedule.last_run,
        next_run=schedule.next_run
    )


@router.post("/cleanup")
async def cleanup_old_backups(
    request: CleanupRequest = None,
    db: Session = Depends(get_db)
):
    """Delete backups older than retention period."""
    retention_days = None

    if request and request.retention_days:
        retention_days = request.retention_days
    else:
        # Get from schedule
        schedule = db.query(BackupSchedule).filter(
            BackupSchedule.schedule_id == "default"
        ).first()
        retention_days = schedule.retention_days if schedule else 30

    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    result = db.query(ConfigBackup).filter(
        ConfigBackup.created_at < cutoff_date
    ).delete()

    db.commit()

    log.info(f"Cleaned up {result} old backups (older than {retention_days} days)")

    return {
        "deleted_count": result,
        "retention_days": retention_days
    }
