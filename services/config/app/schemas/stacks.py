"""
Service Stack Schemas
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class ServiceDefinition(BaseModel):
    """Schema for a service within a stack."""
    name: str
    template: str
    device: str
    variables: Dict[str, Any] = {}


class StackCreate(BaseModel):
    """Schema for creating a service stack."""
    name: str
    description: Optional[str] = None
    services: List[ServiceDefinition] = []
    shared_variables: Dict[str, Any] = {}


class StackUpdate(BaseModel):
    """Schema for updating a service stack."""
    name: Optional[str] = None
    description: Optional[str] = None
    services: Optional[List[ServiceDefinition]] = None
    shared_variables: Optional[Dict[str, Any]] = None
