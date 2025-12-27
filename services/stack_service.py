"""
Stack Service for NetStacks

Business logic for service stacks, deployments, and scheduled operations.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import database as db
from utils.exceptions import NotFoundError, ValidationError

log = logging.getLogger(__name__)


class StackService:
    """
    Service for managing service stacks.

    Handles:
    - Stack CRUD operations
    - Stack metadata and state management
    """

    def get_all(self) -> List[Dict]:
        """
        Get all service stacks.

        Returns:
            List of stack dicts sorted by creation date (newest first)
        """
        stacks = db.get_all_service_stacks()
        stacks.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        # Add summary information
        for stack in stacks:
            stack['service_count'] = len(stack.get('services', []))
            stack['devices'] = list(set([
                s.get('device') for s in stack.get('services', [])
                if s.get('device')
            ]))

        return stacks

    def get(self, stack_id: str) -> Optional[Dict]:
        """
        Get a service stack by ID.

        Args:
            stack_id: Stack ID

        Returns:
            Stack dict or None
        """
        stack = db.get_service_stack(stack_id)
        if stack:
            # Add additional details
            stack['service_count'] = len(stack.get('services', []))
            stack['devices'] = list(set([
                s.get('device') for s in stack.get('services', [])
                if s.get('device')
            ]))
            stack['templates'] = list(set([
                s.get('template') for s in stack.get('services', [])
                if s.get('template')
            ]))
        return stack

    def create(self, data: Dict) -> str:
        """
        Create a new service stack.

        Args:
            data: Stack data dict

        Returns:
            Stack ID

        Raises:
            ValidationError: If validation fails
        """
        # Validate required fields
        if not data.get('name'):
            raise ValidationError('Stack name is required')

        if not data.get('services') or not isinstance(data['services'], list):
            raise ValidationError('Services list is required')

        # Create stack data structure
        stack_data = {
            'stack_id': str(uuid.uuid4()),
            'name': data['name'],
            'description': data.get('description', ''),
            'services': data['services'],
            'shared_variables': data.get('shared_variables', {}),
            'state': 'pending',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        # Validate service structure
        for i, service in enumerate(stack_data['services']):
            if not service.get('name'):
                raise ValidationError(f'Service {i} missing name')
            if not service.get('template'):
                raise ValidationError(f'Service {i} missing template')

            # Accept both 'device' (old format) and 'devices' (new format)
            if not service.get('device') and not service.get('devices'):
                raise ValidationError(f'Service {i} missing device(s)')

            # Set defaults
            service.setdefault('order', i)
            service.setdefault('variables', {})
            service.setdefault('depends_on', [])

        # Save stack
        return self._save(stack_data)

    def update(self, stack_id: str, data: Dict) -> bool:
        """
        Update a service stack.

        Args:
            stack_id: Stack ID
            data: Updated fields

        Returns:
            True if successful

        Raises:
            NotFoundError: If stack not found
        """
        stack = db.get_service_stack(stack_id)
        if not stack:
            raise NotFoundError(
                f'Service stack not found: {stack_id}',
                resource_type='ServiceStack',
                resource_id=stack_id
            )

        # Track if any deployment-related fields changed
        has_changes = False

        # Update fields
        if 'name' in data:
            stack['name'] = data['name']
        if 'description' in data:
            stack['description'] = data['description']
        if 'services' in data:
            stack['services'] = data['services']
            has_changes = True
        if 'shared_variables' in data:
            stack['shared_variables'] = data['shared_variables']
            has_changes = True
        if 'state' in data:
            stack['state'] = data['state']

        # Mark as having pending changes if deployed stack was modified
        if has_changes and stack.get('state') in ['deployed', 'partial', 'failed']:
            stack['has_pending_changes'] = True
            stack['pending_since'] = datetime.now().isoformat()

        stack['updated_at'] = datetime.now().isoformat()
        self._save(stack)
        return True

    def delete(self, stack_id: str) -> bool:
        """
        Delete a service stack.

        Args:
            stack_id: Stack ID

        Returns:
            True if successful

        Raises:
            NotFoundError: If stack not found
        """
        stack = db.get_service_stack(stack_id)
        if not stack:
            raise NotFoundError(
                f'Service stack not found: {stack_id}',
                resource_type='ServiceStack',
                resource_id=stack_id
            )

        db.delete_service_stack(stack_id)
        log.info(f"Deleted service stack: {stack_id}")
        return True

    def _save(self, stack_data: Dict) -> str:
        """Save a service stack to database."""
        stack_id = stack_data.get('stack_id', str(uuid.uuid4()))
        stack_data['stack_id'] = stack_id
        stack_data['updated_at'] = datetime.now().isoformat()

        if 'created_at' not in stack_data:
            stack_data['created_at'] = stack_data['updated_at']

        db.save_service_stack(stack_data)
        log.info(f"Saved service stack: {stack_id}")
        return stack_id


class ScheduledOperationService:
    """
    Service for managing scheduled stack operations.

    Handles:
    - Scheduled operation CRUD
    - Next run time calculation
    """

    VALID_OPERATION_TYPES = ['deploy', 'validate', 'delete', 'config_deploy']
    VALID_SCHEDULE_TYPES = ['once', 'daily', 'weekly', 'monthly']

    def get_all(self, stack_id: Optional[str] = None) -> List[Dict]:
        """
        Get scheduled operations, optionally filtered by stack.

        Args:
            stack_id: Optional stack ID filter

        Returns:
            List of scheduled operation dicts
        """
        return db.get_scheduled_operations(stack_id=stack_id)

    def get(self, schedule_id: str) -> Optional[Dict]:
        """
        Get a scheduled operation by ID.

        Args:
            schedule_id: Schedule ID

        Returns:
            Schedule dict or None
        """
        return db.get_scheduled_operation(schedule_id)

    def create(
        self,
        stack_id: str,
        operation_type: str,
        schedule_type: str,
        scheduled_time: str,
        created_by: str,
        day_of_week: Optional[int] = None,
        day_of_month: Optional[int] = None,
        config_data: Optional[Dict] = None
    ) -> str:
        """
        Create a new scheduled operation.

        Args:
            stack_id: Stack ID
            operation_type: Type of operation (deploy, validate, delete)
            schedule_type: Schedule type (once, daily, weekly, monthly)
            scheduled_time: Time string (HH:MM for recurring, ISO datetime for once)
            created_by: Username creating the schedule
            day_of_week: Day of week for weekly schedules (0=Monday)
            day_of_month: Day of month for monthly schedules
            config_data: Optional config data for config_deploy operations

        Returns:
            Schedule ID

        Raises:
            ValidationError: If validation fails
        """
        if operation_type not in self.VALID_OPERATION_TYPES:
            raise ValidationError(f'Invalid operation_type: {operation_type}')

        if schedule_type not in self.VALID_SCHEDULE_TYPES:
            raise ValidationError(f'Invalid schedule_type: {schedule_type}')

        # Calculate next_run time
        now = datetime.now()
        next_run = self._calculate_next_run(
            schedule_type, scheduled_time, now,
            day_of_week, day_of_month
        )

        # Reject scheduling in the past for one-time operations
        if schedule_type == 'once' and next_run <= now:
            raise ValidationError(
                f'Cannot schedule operation in the past. '
                f'Scheduled: {next_run.strftime("%Y-%m-%d %H:%M")}, '
                f'Current: {now.strftime("%Y-%m-%d %H:%M")}'
            )

        schedule_id = str(uuid.uuid4())

        db.create_scheduled_operation(
            schedule_id=schedule_id,
            stack_id=stack_id,
            operation_type=operation_type,
            schedule_type=schedule_type,
            scheduled_time=scheduled_time,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            created_by=created_by
        )

        # Update next_run
        db.update_scheduled_operation(schedule_id, next_run=next_run.isoformat())

        log.info(f"Created scheduled operation: {schedule_id} for stack {stack_id}")
        return schedule_id

    def update(self, schedule_id: str, **data) -> bool:
        """
        Update a scheduled operation.

        Args:
            schedule_id: Schedule ID
            **data: Fields to update

        Returns:
            True if successful

        Raises:
            NotFoundError: If schedule not found
        """
        schedule = db.get_scheduled_operation(schedule_id)
        if not schedule:
            raise NotFoundError(
                f'Schedule not found: {schedule_id}',
                resource_type='ScheduledOperation',
                resource_id=schedule_id
            )

        # Recalculate next_run if schedule changed
        if 'schedule_type' in data or 'scheduled_time' in data:
            schedule_type = data.get('schedule_type', schedule['schedule_type'])
            scheduled_time = data.get('scheduled_time', schedule['scheduled_time'])
            day_of_week = data.get('day_of_week', schedule.get('day_of_week'))
            day_of_month = data.get('day_of_month', schedule.get('day_of_month'))

            next_run = self._calculate_next_run(
                schedule_type, scheduled_time, datetime.now(),
                day_of_week, day_of_month
            )
            data['next_run'] = next_run.isoformat()

        success = db.update_scheduled_operation(schedule_id, **data)
        if not success:
            raise NotFoundError(
                f'Schedule not found: {schedule_id}',
                resource_type='ScheduledOperation',
                resource_id=schedule_id
            )
        return True

    def delete(self, schedule_id: str) -> bool:
        """
        Delete a scheduled operation.

        Args:
            schedule_id: Schedule ID

        Returns:
            True if successful

        Raises:
            NotFoundError: If schedule not found
        """
        success = db.delete_scheduled_operation(schedule_id)
        if not success:
            raise NotFoundError(
                f'Schedule not found: {schedule_id}',
                resource_type='ScheduledOperation',
                resource_id=schedule_id
            )
        log.info(f"Deleted scheduled operation: {schedule_id}")
        return True

    def _calculate_next_run(
        self,
        schedule_type: str,
        scheduled_time: str,
        now: datetime,
        day_of_week: Optional[int] = None,
        day_of_month: Optional[int] = None
    ) -> datetime:
        """Calculate the next run time for a schedule."""
        if schedule_type == 'once':
            return datetime.fromisoformat(scheduled_time.replace('Z', ''))

        # Parse time for recurring schedules
        time_parts = scheduled_time.split(':')
        hour = int(time_parts[0])
        minute = int(time_parts[1])

        if schedule_type == 'daily':
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run

        elif schedule_type == 'weekly':
            days_ahead = day_of_week - now.weekday()
            if days_ahead < 0:
                days_ahead += 7
            next_run = now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            ) + timedelta(days=days_ahead)
            if next_run <= now:
                next_run += timedelta(weeks=1)
            return next_run

        elif schedule_type == 'monthly':
            next_run = now.replace(
                day=day_of_month, hour=hour, minute=minute,
                second=0, microsecond=0
            )
            if next_run <= now:
                if now.month == 12:
                    next_run = next_run.replace(year=now.year + 1, month=1)
                else:
                    next_run = next_run.replace(month=now.month + 1)
            return next_run

        return now


class ServiceInstanceService:
    """
    Service for managing service instances (deployed services).

    Handles:
    - Service instance CRUD
    - Instance state management
    """

    def get_all(self) -> List[Dict]:
        """
        Get all service instances.

        Returns:
            List of service instance dicts sorted by creation date
        """
        instances = db.get_all_service_instances()
        instances.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return instances

    def get(self, service_id: str) -> Optional[Dict]:
        """
        Get a service instance by ID.

        Args:
            service_id: Service instance ID

        Returns:
            Service instance dict or None
        """
        return db.get_service_instance(service_id)

    def save(self, service_data: Dict) -> str:
        """
        Save a service instance.

        Args:
            service_data: Service instance data

        Returns:
            Service instance ID
        """
        service_id = service_data.get('service_id', str(uuid.uuid4()))
        service_data['service_id'] = service_id
        service_data['updated_at'] = datetime.now().isoformat()

        if 'created_at' not in service_data:
            service_data['created_at'] = service_data['updated_at']

        db.save_service_instance(service_data)
        log.info(f"Saved service instance: {service_id}")
        return service_id

    def delete(self, service_id: str) -> bool:
        """
        Delete a service instance.

        Args:
            service_id: Service instance ID

        Returns:
            True if successful

        Raises:
            NotFoundError: If service not found
        """
        service = db.get_service_instance(service_id)
        if not service:
            raise NotFoundError(
                f'Service instance not found: {service_id}',
                resource_type='ServiceInstance',
                resource_id=service_id
            )

        db.delete_service_instance(service_id)
        log.info(f"Deleted service instance: {service_id}")
        return True
