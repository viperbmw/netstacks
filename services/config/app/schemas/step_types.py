"""
Step Type Schemas
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel


class StepTypeCreate(BaseModel):
    """Schema for creating a step type."""
    name: str
    action_type: str  # get_config, set_config, api_call, validate, wait, manual, deploy_stack
    description: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    parameters_schema: Optional[Dict[str, Any]] = None


class StepTypeUpdate(BaseModel):
    """Schema for updating a step type."""
    name: Optional[str] = None
    action_type: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
