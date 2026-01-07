"""
Config Snapshots Routes

CRUD operations for configuration snapshots and their associated backups.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from netstacks_core.db import get_db
from netstacks_core.db.models import ConfigSnapshot, ConfigBackup

log = logging.getLogger(__name__)

router = APIRouter()


def snapshot_to_dict(snapshot: ConfigSnapshot) -> dict:
    """Convert a ConfigSnapshot model to a dictionary."""
    return {
        'snapshot_id': snapshot.snapshot_id,
        'name': snapshot.name,
        'description': snapshot.description,
        'snapshot_type': snapshot.snapshot_type,
        'status': snapshot.status,
        'total_devices': snapshot.total_devices,
        'success_count': snapshot.success_count,
        'failed_count': snapshot.failed_count,
        'skipped_count': snapshot.skipped_count or 0,
        'created_at': snapshot.created_at.isoformat() if snapshot.created_at else None,
        'completed_at': snapshot.completed_at.isoformat() if snapshot.completed_at else None,
        'created_by': snapshot.created_by,
    }


def backup_to_dict(backup: ConfigBackup) -> dict:
    """Convert a ConfigBackup model to a dictionary."""
    return {
        'backup_id': backup.backup_id,
        'device_name': backup.device_name,
        'device_ip': backup.device_ip,
        'platform': backup.platform,
        'config_format': backup.config_format,
        'config_hash': backup.config_hash,
        'backup_type': backup.backup_type,
        'status': backup.status,
        'error_message': backup.error_message,
        'file_size': backup.file_size,
        'snapshot_id': backup.snapshot_id,
        'created_at': backup.created_at.isoformat() if backup.created_at else None,
    }


@router.get("")
async def get_config_snapshots(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db)
):
    """Get all config snapshots with pagination."""
    try:
        snapshots = session.query(ConfigSnapshot)\
            .order_by(ConfigSnapshot.created_at.desc())\
            .offset(offset)\
            .limit(limit)\
            .all()

        return {
            'success': True,
            'snapshots': [snapshot_to_dict(s) for s in snapshots]
        }
    except Exception as e:
        log.error(f"Error getting config snapshots: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{snapshot_id}")
async def get_config_snapshot(
    snapshot_id: str,
    session: Session = Depends(get_db)
):
    """Get a specific config snapshot with its backups."""
    try:
        snapshot = session.query(ConfigSnapshot)\
            .filter(ConfigSnapshot.snapshot_id == snapshot_id)\
            .first()

        if not snapshot:
            raise HTTPException(status_code=404, detail='Snapshot not found')

        # Get all backups for this snapshot
        backups = session.query(ConfigBackup)\
            .filter(ConfigBackup.snapshot_id == snapshot_id)\
            .order_by(ConfigBackup.device_name)\
            .all()

        result = snapshot_to_dict(snapshot)
        result['backups'] = [backup_to_dict(b) for b in backups]

        return {'success': True, 'snapshot': result}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error getting config snapshot {snapshot_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{snapshot_id}")
async def update_config_snapshot(
    snapshot_id: str,
    data: dict,
    session: Session = Depends(get_db)
):
    """Update a config snapshot (name, description)."""
    try:
        snapshot = session.query(ConfigSnapshot)\
            .filter(ConfigSnapshot.snapshot_id == snapshot_id)\
            .first()

        if not snapshot:
            raise HTTPException(status_code=404, detail='Snapshot not found')

        # Update allowed fields
        if 'name' in data:
            snapshot.name = data['name']
        if 'description' in data:
            snapshot.description = data['description']

        session.commit()
        return {'success': True, 'message': 'Snapshot updated'}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error updating config snapshot {snapshot_id}: {e}", exc_info=True)
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{snapshot_id}")
async def delete_config_snapshot(
    snapshot_id: str,
    session: Session = Depends(get_db)
):
    """Delete a config snapshot and all its backups."""
    try:
        snapshot = session.query(ConfigSnapshot)\
            .filter(ConfigSnapshot.snapshot_id == snapshot_id)\
            .first()

        if not snapshot:
            raise HTTPException(status_code=404, detail='Snapshot not found')

        # Delete the snapshot (cascade will handle backups)
        session.delete(snapshot)
        session.commit()

        log.info(f"Deleted snapshot {snapshot_id} and all its backups")
        return {'success': True, 'message': 'Snapshot deleted'}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error deleting config snapshot {snapshot_id}: {e}", exc_info=True)
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{snapshot_id}/recalculate")
async def recalculate_snapshot_counts(
    snapshot_id: str,
    session: Session = Depends(get_db)
):
    """Recalculate snapshot counts from actual backups in database."""
    try:
        snapshot = session.query(ConfigSnapshot)\
            .filter(ConfigSnapshot.snapshot_id == snapshot_id)\
            .first()

        if not snapshot:
            raise HTTPException(status_code=404, detail='Snapshot not found')

        # Count backups by status
        backups = session.query(ConfigBackup)\
            .filter(ConfigBackup.snapshot_id == snapshot_id)\
            .all()

        total = len(backups)
        success = sum(1 for b in backups if b.status == 'success')
        failed = sum(1 for b in backups if b.status == 'failed')

        # Update snapshot
        snapshot.total_devices = total
        snapshot.success_count = success
        snapshot.failed_count = failed

        # Update status if needed
        if total > 0 and (success + failed) >= total:
            snapshot.status = 'complete' if failed == 0 else 'partial'
            if not snapshot.completed_at:
                snapshot.completed_at = datetime.utcnow()

        session.commit()

        return {
            'success': True,
            'message': 'Counts recalculated',
            'snapshot': snapshot_to_dict(snapshot)
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error recalculating snapshot counts {snapshot_id}: {e}", exc_info=True)
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fix-stale")
async def fix_stale_snapshots(
    session: Session = Depends(get_db)
):
    """Fix snapshots stuck in in_progress state for over 30 minutes."""
    try:
        stale_time = datetime.utcnow() - timedelta(minutes=30)

        stale_snapshots = session.query(ConfigSnapshot)\
            .filter(ConfigSnapshot.status == 'in_progress')\
            .filter(ConfigSnapshot.created_at < stale_time)\
            .all()

        fixed_count = 0
        for snapshot in stale_snapshots:
            # Recalculate counts
            backups = session.query(ConfigBackup)\
                .filter(ConfigBackup.snapshot_id == snapshot.snapshot_id)\
                .all()

            total = len(backups)
            success = sum(1 for b in backups if b.status == 'success')
            failed = sum(1 for b in backups if b.status == 'failed')

            snapshot.total_devices = total
            snapshot.success_count = success
            snapshot.failed_count = failed
            snapshot.status = 'partial' if failed > 0 else 'complete'
            snapshot.completed_at = datetime.utcnow()
            fixed_count += 1

        session.commit()

        return {
            'success': True,
            'fixed_count': fixed_count,
            'message': f'Fixed {fixed_count} stale snapshots'
        }
    except Exception as e:
        log.error(f"Error fixing stale snapshots: {e}", exc_info=True)
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{snapshot_id}/compare/{other_snapshot_id}")
async def compare_config_snapshots(
    snapshot_id: str,
    other_snapshot_id: str,
    session: Session = Depends(get_db)
):
    """Compare two snapshots across all devices."""
    try:
        snapshot1 = session.query(ConfigSnapshot)\
            .filter(ConfigSnapshot.snapshot_id == snapshot_id)\
            .first()
        snapshot2 = session.query(ConfigSnapshot)\
            .filter(ConfigSnapshot.snapshot_id == other_snapshot_id)\
            .first()

        if not snapshot1:
            raise HTTPException(status_code=404, detail=f'Snapshot {snapshot_id} not found')
        if not snapshot2:
            raise HTTPException(status_code=404, detail=f'Snapshot {other_snapshot_id} not found')

        # Get backups for both snapshots
        backups1 = session.query(ConfigBackup)\
            .filter(ConfigBackup.snapshot_id == snapshot_id)\
            .all()
        backups2 = session.query(ConfigBackup)\
            .filter(ConfigBackup.snapshot_id == other_snapshot_id)\
            .all()

        # Create lookup by device name
        backup_map1 = {b.device_name: b for b in backups1}
        backup_map2 = {b.device_name: b for b in backups2}

        # Find all devices
        all_devices = set(backup_map1.keys()) | set(backup_map2.keys())

        comparison = []
        for device in sorted(all_devices):
            b1 = backup_map1.get(device)
            b2 = backup_map2.get(device)

            if b1 and b2:
                # Both have backups - compare hashes
                changed = b1.config_hash != b2.config_hash
                comparison.append({
                    'device_name': device,
                    'in_snapshot1': True,
                    'in_snapshot2': True,
                    'changed': changed,
                    'backup1_id': b1.backup_id,
                    'backup2_id': b2.backup_id,
                })
            elif b1:
                comparison.append({
                    'device_name': device,
                    'in_snapshot1': True,
                    'in_snapshot2': False,
                    'changed': True,
                    'backup1_id': b1.backup_id,
                    'backup2_id': None,
                })
            else:
                comparison.append({
                    'device_name': device,
                    'in_snapshot1': False,
                    'in_snapshot2': True,
                    'changed': True,
                    'backup1_id': None,
                    'backup2_id': b2.backup_id,
                })

        return {
            'success': True,
            'snapshot1': snapshot_to_dict(snapshot1),
            'snapshot2': snapshot_to_dict(snapshot2),
            'comparison': comparison,
            'summary': {
                'total_devices': len(all_devices),
                'changed': sum(1 for c in comparison if c['changed']),
                'unchanged': sum(1 for c in comparison if not c['changed']),
                'only_in_snapshot1': sum(1 for c in comparison if c['in_snapshot1'] and not c['in_snapshot2']),
                'only_in_snapshot2': sum(1 for c in comparison if not c['in_snapshot1'] and c['in_snapshot2']),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error comparing snapshots: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
