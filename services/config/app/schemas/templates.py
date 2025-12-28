"""
Template Schemas
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel


class TemplateCreate(BaseModel):
    """Schema for creating a template."""
    name: str
    content: str
    type: str = "deploy"
    description: Optional[str] = None
    validation_template: Optional[str] = None
    delete_template: Optional[str] = None


class TemplateUpdate(BaseModel):
    """Schema for updating a template."""
    content: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    validation_template: Optional[str] = None
    delete_template: Optional[str] = None


class TemplateRenderRequest(BaseModel):
    """Schema for rendering a template."""
    variables: Dict[str, Any] = {}
