"""
Stack Service

Business logic for service stack operations.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from netstacks_core.db import ServiceStack, StackTemplate

from app.schemas.stacks import StackCreate, StackUpdate

log = logging.getLogger(__name__)


class StackService:
    """Service for managing service stacks."""

    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> List[Dict]:
        """Get all service stacks."""
        stacks = self.session.query(ServiceStack).order_by(
            ServiceStack.created_at.desc()
        ).all()

        return [self._to_dict(s) for s in stacks]

    def get(self, stack_id: str) -> Optional[Dict]:
        """Get a specific stack."""
        stack = self.session.query(ServiceStack).filter(
            ServiceStack.stack_id == stack_id
        ).first()

        if not stack:
            return None

        return self._to_dict(stack)

    def create(self, data: StackCreate) -> str:
        """Create a new service stack."""
        stack_id = str(uuid.uuid4())

        # Convert services to dicts
        services = [s.model_dump() for s in data.services]

        stack = ServiceStack(
            stack_id=stack_id,
            name=data.name,
            description=data.description,
            services=services,
            shared_variables=data.shared_variables,
            state='pending',
        )

        self.session.add(stack)
        self.session.commit()

        log.info(f"Stack created: {data.name} ({stack_id})")
        return stack_id

    def update(self, stack_id: str, data: StackUpdate) -> Optional[Dict]:
        """Update a service stack."""
        stack = self.session.query(ServiceStack).filter(
            ServiceStack.stack_id == stack_id
        ).first()

        if not stack:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Convert services if provided
        if 'services' in update_data and update_data['services'] is not None:
            update_data['services'] = [s.model_dump() if hasattr(s, 'model_dump') else s for s in update_data['services']]

        for field, value in update_data.items():
            if hasattr(stack, field):
                setattr(stack, field, value)

        stack.updated_at = datetime.utcnow()
        stack.has_pending_changes = True
        stack.pending_since = datetime.utcnow()

        self.session.commit()

        log.info(f"Stack updated: {stack_id}")
        return self.get(stack_id)

    def delete(self, stack_id: str) -> bool:
        """Delete a service stack."""
        stack = self.session.query(ServiceStack).filter(
            ServiceStack.stack_id == stack_id
        ).first()

        if not stack:
            return False

        self.session.delete(stack)
        self.session.commit()

        log.info(f"Stack deleted: {stack_id}")
        return True

    def _to_dict(self, stack: ServiceStack) -> Dict:
        """Convert stack model to dict."""
        return {
            'stack_id': stack.stack_id,
            'name': stack.name,
            'description': stack.description,
            'services': stack.services or [],
            'shared_variables': stack.shared_variables or {},
            'state': stack.state,
            'has_pending_changes': stack.has_pending_changes,
            'pending_since': stack.pending_since.isoformat() if stack.pending_since else None,
            'deployed_services': stack.deployed_services or [],
            'deployment_errors': stack.deployment_errors or [],
            'created_at': stack.created_at.isoformat() if stack.created_at else None,
            'updated_at': stack.updated_at.isoformat() if stack.updated_at else None,
            'deploy_started_at': stack.deploy_started_at.isoformat() if stack.deploy_started_at else None,
            'deploy_completed_at': stack.deploy_completed_at.isoformat() if stack.deploy_completed_at else None,
            'last_validated': stack.last_validated.isoformat() if stack.last_validated else None,
            'validation_status': stack.validation_status,
        }

    # Stack Templates
    def get_all_templates(self) -> List[Dict]:
        """Get all stack templates."""
        templates = self.session.query(StackTemplate).order_by(
            StackTemplate.name
        ).all()

        return [{
            'template_id': t.template_id,
            'name': t.name,
            'description': t.description,
            'services': t.services,
            'required_variables': t.required_variables or [],
            'api_variables': t.api_variables or {},
            'per_device_variables': t.per_device_variables or [],
            'tags': t.tags or [],
            'created_at': t.created_at.isoformat() if t.created_at else None,
            'updated_at': t.updated_at.isoformat() if t.updated_at else None,
            'created_by': t.created_by,
        } for t in templates]

    def get_template(self, template_id: str) -> Optional[Dict]:
        """Get a specific stack template."""
        template = self.session.query(StackTemplate).filter(
            StackTemplate.template_id == template_id
        ).first()

        if not template:
            return None

        return {
            'template_id': template.template_id,
            'name': template.name,
            'description': template.description,
            'services': template.services,
            'required_variables': template.required_variables or [],
            'api_variables': template.api_variables or {},
            'per_device_variables': template.per_device_variables or [],
            'tags': template.tags or [],
            'created_at': template.created_at.isoformat() if template.created_at else None,
            'updated_at': template.updated_at.isoformat() if template.updated_at else None,
            'created_by': template.created_by,
        }

    def delete_template(self, template_id: str) -> bool:
        """Delete a stack template."""
        template = self.session.query(StackTemplate).filter(
            StackTemplate.template_id == template_id
        ).first()

        if not template:
            return False

        self.session.delete(template)
        self.session.commit()

        log.info(f"Stack template deleted: {template_id}")
        return True
