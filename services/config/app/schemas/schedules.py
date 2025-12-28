"""
Scheduled Operations Schemas
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel


class ScheduleCreate(BaseModel):
    """Schema for creating a scheduled operation."""
    stack_id: str
    operation_type: str  # deploy, validate, delete
    schedule_type: str  # once, daily, weekly, monthly
    scheduled_time: str  # HH:MM or ISO datetime
    day_of_week: Optional[int] = None  # 0-6 for weekly
    day_of_month: Optional[int] = None  # 1-31 for monthly
    config_data: Optional[Dict[str, Any]] = None


class ScheduleUpdate(BaseModel):
    """Schema for updating a scheduled operation."""
    operation_type: Optional[str] = None
    schedule_type: Optional[str] = None
    scheduled_time: Optional[str] = None
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    config_data: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
