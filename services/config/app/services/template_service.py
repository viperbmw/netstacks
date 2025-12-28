"""
Template Service

Business logic for template operations.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from jinja2 import Template as J2Template, TemplateSyntaxError, Environment, meta
from sqlalchemy.orm import Session

from netstacks_core.db import Template

from app.schemas.templates import TemplateUpdate

log = logging.getLogger(__name__)


class TemplateService:
    """Service for managing templates."""

    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> List[Dict]:
        """Get all templates (without full content)."""
        templates = self.session.query(Template).order_by(Template.name).all()

        return [{
            'name': t.name,
            'type': t.type or 'deploy',
            'description': t.description,
            'validation_template': t.validation_template,
            'delete_template': t.delete_template,
            'has_content': bool(t.content),
            'created_at': t.created_at.isoformat() if t.created_at else None,
            'updated_at': t.updated_at.isoformat() if t.updated_at else None,
        } for t in templates]

    def get(self, name: str) -> Optional[Dict]:
        """Get template by name (with full content)."""
        template = self.session.query(Template).filter(
            Template.name == name
        ).first()

        if not template:
            return None

        return {
            'name': template.name,
            'content': template.content or '',
            'type': template.type or 'deploy',
            'description': template.description,
            'validation_template': template.validation_template,
            'delete_template': template.delete_template,
            'created_at': template.created_at.isoformat() if template.created_at else None,
            'updated_at': template.updated_at.isoformat() if template.updated_at else None,
        }

    def create(
        self,
        name: str,
        content: str,
        template_type: str = 'deploy',
        description: Optional[str] = None,
        validation_template: Optional[str] = None,
        delete_template: Optional[str] = None,
    ) -> Dict:
        """Create or update a template."""
        existing = self.session.query(Template).filter(
            Template.name == name
        ).first()

        if existing:
            # Update existing
            existing.content = content
            existing.type = template_type
            existing.description = description
            existing.validation_template = validation_template
            existing.delete_template = delete_template
            existing.updated_at = datetime.utcnow()
        else:
            # Create new
            template = Template(
                name=name,
                content=content,
                type=template_type,
                description=description,
                validation_template=validation_template,
                delete_template=delete_template,
            )
            self.session.add(template)

        self.session.commit()
        log.info(f"Template saved: {name}")
        return self.get(name)

    def update(self, name: str, data: TemplateUpdate) -> Optional[Dict]:
        """Update an existing template."""
        template = self.session.query(Template).filter(
            Template.name == name
        ).first()

        if not template:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == 'type':
                setattr(template, 'type', value)
            elif hasattr(template, field):
                setattr(template, field, value)

        template.updated_at = datetime.utcnow()
        self.session.commit()

        log.info(f"Template updated: {name}")
        return self.get(name)

    def delete(self, name: str) -> bool:
        """Delete a template."""
        template = self.session.query(Template).filter(
            Template.name == name
        ).first()

        if not template:
            return False

        self.session.delete(template)
        self.session.commit()

        log.info(f"Template deleted: {name}")
        return True

    def render(self, name: str, variables: Dict[str, Any]) -> Dict:
        """Render a template with variables."""
        template = self.session.query(Template).filter(
            Template.name == name
        ).first()

        if not template or not template.content:
            return {"error": "Template not found"}

        try:
            j2_template = J2Template(template.content)
            rendered = j2_template.render(**variables)
            return {"rendered": rendered}
        except TemplateSyntaxError as e:
            return {"error": f"Template syntax error: {e}"}
        except Exception as e:
            return {"error": str(e)}
