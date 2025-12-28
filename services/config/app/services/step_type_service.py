"""
Step Type Service

Business logic for MOP step type operations.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from netstacks_core.db import StepType

from app.schemas.step_types import StepTypeCreate, StepTypeUpdate

log = logging.getLogger(__name__)


class StepTypeService:
    """Service for managing step types."""

    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> List[Dict]:
        """Get all step types."""
        step_types = self.session.query(StepType).order_by(
            StepType.category,
            StepType.name,
        ).all()

        return [self._to_dict(s) for s in step_types]

    def get(self, step_type_id: str) -> Optional[Dict]:
        """Get a specific step type."""
        step_type = self.session.query(StepType).filter(
            StepType.step_type_id == step_type_id
        ).first()

        if not step_type:
            return None

        return self._to_dict(step_type)

    def create(self, data: StepTypeCreate) -> str:
        """Create a new step type."""
        # Generate ID from name if not provided
        step_type_id = data.name.lower().replace(' ', '_').replace('-', '_')

        # Check for existing
        existing = self.session.query(StepType).filter(
            StepType.step_type_id == step_type_id
        ).first()

        if existing:
            # Add suffix to make unique
            step_type_id = f"{step_type_id}_{str(uuid.uuid4())[:8]}"

        step_type = StepType(
            step_type_id=step_type_id,
            name=data.name,
            action_type=data.action_type,
            description=data.description,
            category=data.category,
            icon=data.icon,
            config=data.config or {},
            parameters_schema=data.parameters_schema or {},
            enabled=True,
            is_builtin=False,
        )

        self.session.add(step_type)
        self.session.commit()

        log.info(f"Step type created: {data.name} ({step_type_id})")
        return step_type_id

    def update(self, step_type_id: str, data: StepTypeUpdate) -> Optional[Dict]:
        """Update a step type."""
        step_type = self.session.query(StepType).filter(
            StepType.step_type_id == step_type_id
        ).first()

        if not step_type:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(step_type, field):
                setattr(step_type, field, value)

        step_type.updated_at = datetime.utcnow()
        self.session.commit()

        log.info(f"Step type updated: {step_type_id}")
        return self.get(step_type_id)

    def delete(self, step_type_id: str) -> bool:
        """Delete a step type."""
        step_type = self.session.query(StepType).filter(
            StepType.step_type_id == step_type_id
        ).first()

        if not step_type:
            return False

        self.session.delete(step_type)
        self.session.commit()

        log.info(f"Step type deleted: {step_type_id}")
        return True

    def toggle(self, step_type_id: str, enabled: bool) -> bool:
        """Enable or disable a step type."""
        step_type = self.session.query(StepType).filter(
            StepType.step_type_id == step_type_id
        ).first()

        if not step_type:
            return False

        step_type.enabled = enabled
        step_type.updated_at = datetime.utcnow()
        self.session.commit()

        log.info(f"Step type {'enabled' if enabled else 'disabled'}: {step_type_id}")
        return True

    def _to_dict(self, step_type: StepType) -> Dict:
        """Convert step type model to dict."""
        return {
            'step_type_id': step_type.step_type_id,
            'name': step_type.name,
            'description': step_type.description,
            'category': step_type.category,
            'icon': step_type.icon,
            'enabled': step_type.enabled,
            'is_builtin': step_type.is_builtin,
            'action_type': step_type.action_type,
            'config': step_type.config or {},
            'parameters_schema': step_type.parameters_schema or {},
            'created_at': step_type.created_at.isoformat() if step_type.created_at else None,
            'updated_at': step_type.updated_at.isoformat() if step_type.updated_at else None,
        }
