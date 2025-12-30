# /home/cwdavis/netstacks/tasks/device_tasks.py
"""
Device Tasks for NetStacks
Network device operations using Netmiko
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

from .celery_config import celery_app, store_task_metadata
from .utils import parse_with_textfsm, get_device_queue
from timezone_utils import utc_now

log = logging.getLogger(__name__)


@celery_app.task(bind=True, name='tasks.device_tasks.get_config')
def get_config(self, connection_args: Dict, commands: List[str],
               parse_output: bool = False, device_name: str = None) -> Dict:
    """
    Execute show commands on a network device.

    Args:
        connection_args: Netmiko connection parameters
        commands: List of commands to execute
        parse_output: Whether to parse output with TextFSM
        device_name: Optional device name for metadata

    Returns:
        Dict with command outputs and metadata
    """
    task_id = self.request.id
    device_type = connection_args.get('device_type', 'unknown')

    # Store task metadata
    if device_name:
        store_task_metadata(task_id, {
            'device_name': device_name,
            'operation': 'get_config',
            'commands': commands,
            'started_at': utc_now().isoformat()
        })

    results = {}
    errors = []

    try:
        log.info(f"Task {task_id}: Connecting to {connection_args.get('host')}")

        with ConnectHandler(**connection_args) as conn:
            for command in commands:
                try:
                    output = conn.send_command(command, read_timeout=60)
                    result = {'output': output, 'success': True}

                    # Parse output if requested
                    if parse_output:
                        parsed = parse_with_textfsm(output, device_type, command)
                        if parsed:
                            result['parsed'] = parsed

                    results[command] = result

                except Exception as e:
                    log.error(f"Command '{command}' failed: {e}")
                    results[command] = {'output': str(e), 'success': False}
                    errors.append(f"Command '{command}': {str(e)}")

        return {
            'status': 'success' if not errors else 'partial',
            'results': results,
            'errors': errors,
            'device': device_name or connection_args.get('host'),
            'completed_at': utc_now().isoformat()
        }

    except NetmikoTimeoutException as e:
        log.error(f"Connection timeout: {e}")
        return {
            'status': 'error',
            'error': f"Connection timeout: {str(e)}",
            'device': device_name or connection_args.get('host')
        }
    except NetmikoAuthenticationException as e:
        log.error(f"Authentication failed: {e}")
        return {
            'status': 'error',
            'error': f"Authentication failed: {str(e)}",
            'device': device_name or connection_args.get('host')
        }
    except Exception as e:
        log.error(f"Unexpected error: {e}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e),
            'device': device_name or connection_args.get('host')
        }


@celery_app.task(bind=True, name='tasks.device_tasks.set_config')
def set_config(self, connection_args: Dict, config_commands: List[str],
               device_name: str = None, dry_run: bool = False) -> Dict:
    """
    Push configuration commands to a network device.

    Args:
        connection_args: Netmiko connection parameters
        config_commands: List of configuration commands
        device_name: Optional device name for metadata
        dry_run: If True, only validate without applying

    Returns:
        Dict with result status and output
    """
    task_id = self.request.id

    if device_name:
        store_task_metadata(task_id, {
            'device_name': device_name,
            'operation': 'set_config',
            'dry_run': dry_run,
            'started_at': utc_now().isoformat()
        })

    try:
        log.info(f"Task {task_id}: Connecting to {connection_args.get('host')}")

        with ConnectHandler(**connection_args) as conn:
            if dry_run:
                # For dry run, just return the commands that would be sent
                return {
                    'status': 'dry_run',
                    'commands': config_commands,
                    'device': device_name or connection_args.get('host'),
                    'message': 'Dry run - commands not applied'
                }

            # Apply configuration
            output = conn.send_config_set(config_commands)

            # Save configuration if supported
            try:
                save_output = conn.save_config()
                output += f"\n{save_output}"
            except Exception as e:
                log.warning(f"Could not save config: {e}")
                output += f"\nWarning: Could not save config: {e}"

            return {
                'status': 'success',
                'output': output,
                'device': device_name or connection_args.get('host'),
                'completed_at': utc_now().isoformat()
            }

    except NetmikoTimeoutException as e:
        return {'status': 'error', 'error': f"Connection timeout: {str(e)}"}
    except NetmikoAuthenticationException as e:
        return {'status': 'error', 'error': f"Authentication failed: {str(e)}"}
    except Exception as e:
        log.error(f"Error in set_config: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, name='tasks.device_tasks.run_commands')
def run_commands(self, connection_args: Dict, commands: List[str],
                 device_name: str = None) -> Dict:
    """
    Execute arbitrary commands on a network device.
    Similar to get_config but without parsing.
    """
    task_id = self.request.id

    if device_name:
        store_task_metadata(task_id, {
            'device_name': device_name,
            'operation': 'run_commands',
            'started_at': utc_now().isoformat()
        })

    results = {}

    try:
        with ConnectHandler(**connection_args) as conn:
            for command in commands:
                try:
                    output = conn.send_command(command, read_timeout=60)
                    results[command] = {'output': output, 'success': True}
                except Exception as e:
                    results[command] = {'output': str(e), 'success': False}

        return {
            'status': 'success',
            'results': results,
            'device': device_name or connection_args.get('host')
        }

    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, name='tasks.device_tasks.validate_config')
def validate_config(self, connection_args: Dict, patterns: List[str],
                    device_name: str = None) -> Dict:
    """
    Validate that specific patterns exist in device configuration.
    """
    task_id = self.request.id

    if device_name:
        store_task_metadata(task_id, {
            'device_name': device_name,
            'operation': 'validate_config',
            'started_at': utc_now().isoformat()
        })

    try:
        import re

        with ConnectHandler(**connection_args) as conn:
            # Get running config
            config = conn.send_command('show running-config', read_timeout=120)

            results = {}
            all_found = True

            for pattern in patterns:
                match = re.search(pattern, config, re.MULTILINE)
                results[pattern] = {
                    'found': bool(match),
                    'match': match.group(0) if match else None
                }
                if not match:
                    all_found = False

            return {
                'status': 'success',
                'all_patterns_found': all_found,
                'results': results,
                'device': device_name or connection_args.get('host')
            }

    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, name='tasks.device_tasks.test_connectivity')
def test_connectivity(self, connection_args: Dict, device_name: str = None) -> Dict:
    """
    Test connectivity to a network device.
    """
    task_id = self.request.id

    try:
        with ConnectHandler(**connection_args) as conn:
            # Try a simple command
            prompt = conn.find_prompt()
            return {
                'status': 'success',
                'reachable': True,
                'prompt': prompt,
                'device': device_name or connection_args.get('host')
            }

    except NetmikoTimeoutException:
        return {'status': 'error', 'reachable': False, 'error': 'Connection timeout'}
    except NetmikoAuthenticationException:
        return {'status': 'error', 'reachable': False, 'error': 'Authentication failed'}
    except Exception as e:
        return {'status': 'error', 'reachable': False, 'error': str(e)}
