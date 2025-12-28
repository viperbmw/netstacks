"""
MOP (Method of Procedures) Schemas
"""

from typing import Optional, List
from pydantic import BaseModel


class MOPCreate(BaseModel):
    """Schema for creating a MOP."""
    name: str
    description: Optional[str] = None
    yaml_content: Optional[str] = None


class MOPUpdate(BaseModel):
    """Schema for updating a MOP."""
    name: Optional[str] = None
    description: Optional[str] = None
    yaml_content: Optional[str] = None
    enabled: Optional[bool] = None
