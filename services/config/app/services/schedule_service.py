"""
Schedule Service

Business logic for scheduled stack operations.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from netstacks_core.db import ScheduledStackOperation

from app.schemas.schedules import ScheduleCreate, ScheduleUpdate

log = logging.getLogger(__name__)


class ScheduleService:
    """Service for managing scheduled operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_all(self, stack_id: Optional[str] = None) -> List[Dict]:
        """Get all scheduled operations, optionally filtered by stack."""
        query = self.session.query(ScheduledStackOperation)

        if stack_id:
            query = query.filter(ScheduledStackOperation.stack_id == stack_id)

        schedules = query.order_by(ScheduledStackOperation.next_run).all()

        return [self._to_dict(s) for s in schedules]

    def get(self, schedule_id: str) -> Optional[Dict]:
        """Get a specific schedule."""
        schedule = self.session.query(ScheduledStackOperation).filter(
            ScheduledStackOperation.schedule_id == schedule_id
        ).first()

        if not schedule:
            return None

        return self._to_dict(schedule)

    def create(self, data: ScheduleCreate, created_by: str = None) -> str:
        """Create a new scheduled operation."""
        schedule_id = str(uuid.uuid4())

        # Calculate next run time
        next_run = self._calculate_next_run(
            schedule_type=data.schedule_type,
            scheduled_time=data.scheduled_time,
            day_of_week=data.day_of_week,
            day_of_month=data.day_of_month,
        )

        schedule = ScheduledStackOperation(
            schedule_id=schedule_id,
            stack_id=data.stack_id,
            operation_type=data.operation_type,
            schedule_type=data.schedule_type,
            scheduled_time=data.scheduled_time,
            day_of_week=data.day_of_week,
            day_of_month=data.day_of_month,
            config_data=data.config_data,
            enabled=True,
            next_run=next_run,
            created_by=created_by,
        )

        self.session.add(schedule)
        self.session.commit()

        log.info(f"Schedule created: {schedule_id}")
        return schedule_id

    def update(self, schedule_id: str, data: ScheduleUpdate) -> Optional[Dict]:
        """Update a scheduled operation."""
        schedule = self.session.query(ScheduledStackOperation).filter(
            ScheduledStackOperation.schedule_id == schedule_id
        ).first()

        if not schedule:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(schedule, field):
                setattr(schedule, field, value)

        # Recalculate next run if schedule parameters changed
        if any(k in update_data for k in ['schedule_type', 'scheduled_time', 'day_of_week', 'day_of_month']):
            schedule.next_run = self._calculate_next_run(
                schedule_type=schedule.schedule_type,
                scheduled_time=schedule.scheduled_time,
                day_of_week=schedule.day_of_week,
                day_of_month=schedule.day_of_month,
            )

        self.session.commit()

        log.info(f"Schedule updated: {schedule_id}")
        return self.get(schedule_id)

    def delete(self, schedule_id: str) -> bool:
        """Delete a scheduled operation."""
        schedule = self.session.query(ScheduledStackOperation).filter(
            ScheduledStackOperation.schedule_id == schedule_id
        ).first()

        if not schedule:
            return False

        self.session.delete(schedule)
        self.session.commit()

        log.info(f"Schedule deleted: {schedule_id}")
        return True

    def toggle(self, schedule_id: str, enabled: bool) -> bool:
        """Enable or disable a scheduled operation."""
        schedule = self.session.query(ScheduledStackOperation).filter(
            ScheduledStackOperation.schedule_id == schedule_id
        ).first()

        if not schedule:
            return False

        schedule.enabled = enabled

        # Recalculate next run when enabling
        if enabled:
            schedule.next_run = self._calculate_next_run(
                schedule_type=schedule.schedule_type,
                scheduled_time=schedule.scheduled_time,
                day_of_week=schedule.day_of_week,
                day_of_month=schedule.day_of_month,
            )

        self.session.commit()

        log.info(f"Schedule {'enabled' if enabled else 'disabled'}: {schedule_id}")
        return True

    def _to_dict(self, schedule: ScheduledStackOperation) -> Dict:
        """Convert schedule model to dict."""
        return {
            'schedule_id': schedule.schedule_id,
            'stack_id': schedule.stack_id,
            'operation_type': schedule.operation_type,
            'schedule_type': schedule.schedule_type,
            'scheduled_time': schedule.scheduled_time,
            'day_of_week': schedule.day_of_week,
            'day_of_month': schedule.day_of_month,
            'config_data': schedule.config_data,
            'enabled': schedule.enabled,
            'last_run': schedule.last_run.isoformat() if schedule.last_run else None,
            'next_run': schedule.next_run.isoformat() if schedule.next_run else None,
            'run_count': schedule.run_count,
            'created_at': schedule.created_at.isoformat() if schedule.created_at else None,
            'created_by': schedule.created_by,
        }

    def _calculate_next_run(
        self,
        schedule_type: str,
        scheduled_time: str,
        day_of_week: Optional[int] = None,
        day_of_month: Optional[int] = None,
    ) -> Optional[datetime]:
        """Calculate the next run time for a schedule."""
        now = datetime.utcnow()

        try:
            if schedule_type == 'once':
                # Parse ISO datetime
                return datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))

            # Parse time (HH:MM)
            parts = scheduled_time.split(':')
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0

            if schedule_type == 'daily':
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)
                return next_run

            elif schedule_type == 'weekly':
                if day_of_week is None:
                    day_of_week = 0  # Default to Monday

                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                days_ahead = day_of_week - now.weekday()
                if days_ahead < 0 or (days_ahead == 0 and next_run <= now):
                    days_ahead += 7
                next_run += timedelta(days=days_ahead)
                return next_run

            elif schedule_type == 'monthly':
                if day_of_month is None:
                    day_of_month = 1

                # Start with first of next month if current month's day has passed
                next_run = now.replace(
                    day=min(day_of_month, 28),  # Safe day for all months
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0
                )
                if next_run <= now:
                    # Move to next month
                    if now.month == 12:
                        next_run = next_run.replace(year=now.year + 1, month=1)
                    else:
                        next_run = next_run.replace(month=now.month + 1)
                return next_run

        except Exception as e:
            log.error(f"Error calculating next run: {e}")
            return None

        return None
