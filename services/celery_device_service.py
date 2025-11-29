"""
Celery-based Device Service
Handles device operations via Celery tasks
"""
import logging
from typing import Dict, List, Any, Optional
from celery.result import AsyncResult

from tasks import celery_app, get_config, set_config, run_commands, validate_config

log = logging.getLogger(__name__)


class CeleryDeviceService:
    """
    Service for device operations using Celery tasks.
    """

    def __init__(self):
        self.app = celery_app

    def execute_get_config(self, connection_args: Dict, command: str,
                           use_textfsm: bool = False, use_genie: bool = False) -> str:
        """
        Execute a show command on a device asynchronously.

        Args:
            connection_args: Device connection parameters
            command: CLI command to execute
            use_textfsm: Parse with TextFSM
            use_genie: Parse with Genie

        Returns:
            Task ID for polling results
        """
        # Remove any None values from connection_args
        clean_args = {k: v for k, v in connection_args.items() if v is not None}

        task = get_config.delay(
            connection_args=clean_args,
            command=command,
            use_textfsm=use_textfsm,
            use_genie=use_genie
        )

        log.info(f"Dispatched get_config task {task.id} to {clean_args.get('host')}")
        return task.id

    def execute_set_config(self, connection_args: Dict, config_lines: List[str] = None,
                           template_content: str = None, variables: Dict = None,
                           save_config: bool = True) -> str:
        """
        Push configuration to a device asynchronously.

        Args:
            connection_args: Device connection parameters
            config_lines: List of config commands
            template_content: Jinja2 template string
            variables: Template variables
            save_config: Save config after push

        Returns:
            Task ID for polling results
        """
        clean_args = {k: v for k, v in connection_args.items() if v is not None}

        task = set_config.delay(
            connection_args=clean_args,
            config_lines=config_lines,
            template_content=template_content,
            variables=variables,
            save_config=save_config
        )

        log.info(f"Dispatched set_config task {task.id} to {clean_args.get('host')}")
        return task.id

    def execute_commands(self, connection_args: Dict, commands: List[str],
                         use_textfsm: bool = False) -> str:
        """
        Execute multiple commands on a device.

        Args:
            connection_args: Device connection parameters
            commands: List of CLI commands
            use_textfsm: Parse output with TextFSM

        Returns:
            Task ID for polling results
        """
        clean_args = {k: v for k, v in connection_args.items() if v is not None}

        task = run_commands.delay(
            connection_args=clean_args,
            commands=commands,
            use_textfsm=use_textfsm
        )

        log.info(f"Dispatched run_commands task {task.id} to {clean_args.get('host')}")
        return task.id

    def execute_validate(self, connection_args: Dict, expected_patterns: List[str],
                         validation_command: str = 'show running-config') -> str:
        """
        Validate configuration patterns on a device.

        Args:
            connection_args: Device connection parameters
            expected_patterns: Regex patterns to look for
            validation_command: Command to run for validation

        Returns:
            Task ID for polling results
        """
        clean_args = {k: v for k, v in connection_args.items() if v is not None}

        task = validate_config.delay(
            connection_args=clean_args,
            expected_patterns=expected_patterns,
            validation_command=validation_command
        )

        log.info(f"Dispatched validate_config task {task.id} to {clean_args.get('host')}")
        return task.id

    def get_task_result(self, task_id: str) -> Dict:
        """
        Get the result of a Celery task.

        Args:
            task_id: Celery task ID

        Returns:
            Dict with task status and result
        """
        result = AsyncResult(task_id, app=self.app)

        response = {
            'task_id': task_id,
            'status': result.status,
        }

        if result.ready():
            if result.successful():
                response['result'] = result.result
                response['status'] = result.result.get('status', 'success')
            else:
                response['status'] = 'failed'
                response['error'] = str(result.result)
        else:
            response['status'] = result.status.lower()

        return response

    def get_task_status(self, task_id: str) -> str:
        """
        Get just the status of a task.

        Args:
            task_id: Celery task ID

        Returns:
            Status string: PENDING, STARTED, SUCCESS, FAILURE
        """
        result = AsyncResult(task_id, app=self.app)
        return result.status


# Global instance
celery_device_service = CeleryDeviceService()


def get_device_service():
    """Get the device service instance"""
    return celery_device_service
