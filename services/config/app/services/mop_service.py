"""
MOP Service

Business logic for MOP (Method of Procedures) operations.
"""

import logging
import uuid
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import yaml
from sqlalchemy.orm import Session

from netstacks_core.db import MOP, MOPExecution

from app.schemas.mops import MOPCreate, MOPUpdate

log = logging.getLogger(__name__)


class MOPService:
    """Service for managing MOPs."""

    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> List[Dict]:
        """Get all MOPs."""
        mops = self.session.query(MOP).order_by(
            MOP.created_at.desc()
        ).all()

        return [self._to_dict(m) for m in mops]

    def get(self, mop_id: str) -> Optional[Dict]:
        """Get a specific MOP."""
        mop = self.session.query(MOP).filter(
            MOP.mop_id == mop_id
        ).first()

        if not mop:
            return None

        return self._to_dict(mop, include_yaml=True)

    def create(self, data: MOPCreate, created_by: str = None) -> str:
        """Create a new MOP."""
        mop_id = str(uuid.uuid4())

        # Extract devices from YAML content
        devices = []
        yaml_content = data.yaml_content or ''
        if yaml_content:
            try:
                yaml_data = yaml.safe_load(yaml_content)
                if yaml_data:
                    devices = yaml_data.get('devices', [])
                    log.info(f"Extracted {len(devices)} devices from YAML for new MOP")
            except Exception as e:
                log.warning(f"Could not parse YAML to extract devices: {e}")

        mop = MOP(
            mop_id=mop_id,
            name=data.name,
            description=data.description,
            yaml_content=yaml_content,
            devices=devices,
            enabled=True,
            created_by=created_by,
        )

        self.session.add(mop)
        self.session.commit()

        log.info(f"MOP created: {data.name} ({mop_id})")
        return mop_id

    def update(self, mop_id: str, data: MOPUpdate) -> Optional[Dict]:
        """Update a MOP."""
        mop = self.session.query(MOP).filter(
            MOP.mop_id == mop_id
        ).first()

        if not mop:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Handle YAML content and extract devices
        if 'yaml_content' in update_data and update_data['yaml_content']:
            yaml_content = update_data['yaml_content']
            try:
                yaml_data = yaml.safe_load(yaml_content)
                if yaml_data:
                    update_data['devices'] = yaml_data.get('devices', [])
                    log.info(f"Extracted {len(update_data['devices'])} devices from YAML for MOP update")
            except Exception as e:
                log.warning(f"Could not parse YAML to extract devices: {e}")

        for field, value in update_data.items():
            if hasattr(mop, field):
                setattr(mop, field, value)

        mop.updated_at = datetime.utcnow()
        self.session.commit()

        log.info(f"MOP updated: {mop_id}")
        return self.get(mop_id)

    def delete(self, mop_id: str) -> bool:
        """Delete a MOP."""
        mop = self.session.query(MOP).filter(
            MOP.mop_id == mop_id
        ).first()

        if not mop:
            return False

        self.session.delete(mop)
        self.session.commit()

        log.info(f"MOP deleted: {mop_id}")
        return True

    def toggle(self, mop_id: str, enabled: bool) -> bool:
        """Enable or disable a MOP."""
        mop = self.session.query(MOP).filter(
            MOP.mop_id == mop_id
        ).first()

        if not mop:
            return False

        mop.enabled = enabled
        mop.updated_at = datetime.utcnow()
        self.session.commit()

        log.info(f"MOP {'enabled' if enabled else 'disabled'}: {mop_id}")
        return True

    def _to_dict(self, mop: MOP, include_yaml: bool = False) -> Dict:
        """Convert MOP model to dict."""
        result = {
            'mop_id': mop.mop_id,
            'name': mop.name,
            'description': mop.description,
            'devices': mop.devices or [],
            'enabled': mop.enabled,
            'created_at': mop.created_at.isoformat() if mop.created_at else None,
            'updated_at': mop.updated_at.isoformat() if mop.updated_at else None,
            'created_by': mop.created_by,
        }

        if include_yaml:
            result['yaml_content'] = mop.yaml_content

        return result

    # Executions
    def get_executions(self, mop_id: str) -> List[Dict]:
        """Get executions for a specific MOP."""
        executions = self.session.query(MOPExecution).filter(
            MOPExecution.mop_id == mop_id
        ).order_by(MOPExecution.started_at.desc()).all()

        return [self._execution_to_dict(e) for e in executions]

    def get_execution(self, execution_id: str) -> Optional[Dict]:
        """Get a specific execution."""
        execution = self.session.query(MOPExecution).filter(
            MOPExecution.execution_id == execution_id
        ).first()

        if not execution:
            return None

        result = self._execution_to_dict(execution)

        # Include MOP name
        if execution.mop:
            result['mop_name'] = execution.mop.name

        return result

    def get_running_executions(self) -> List[Dict]:
        """Get all running executions."""
        executions = self.session.query(MOPExecution).filter(
            MOPExecution.status == 'running'
        ).order_by(MOPExecution.started_at.desc()).all()

        results = []
        for e in executions:
            result = self._execution_to_dict(e)
            if e.mop:
                result['mop_name'] = e.mop.name
            results.append(result)

        return results

    def _execution_to_dict(self, execution: MOPExecution) -> Dict:
        """Convert execution model to dict."""
        return {
            'execution_id': execution.execution_id,
            'mop_id': execution.mop_id,
            'status': execution.status,
            'current_step': execution.current_step,
            'execution_log': execution.execution_log or [],
            'context': execution.context or {},
            'error': execution.error,
            'started_at': execution.started_at.isoformat() if execution.started_at else None,
            'completed_at': execution.completed_at.isoformat() if execution.completed_at else None,
            'started_by': execution.started_by,
        }
