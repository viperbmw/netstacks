"""
Celery Tasks for NetStacks
Network automation tasks using Netmiko, TextFSM, and Genie

Each task handles network device operations directly via Celery workers.
"""
import os
import logging
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional
from celery import Celery

# Network automation imports
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException
import textfsm
from jinja2 import Template, Environment, BaseLoader

log = logging.getLogger(__name__)

# Celery configuration
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

# Create Celery app
celery_app = Celery(
    'netstacks',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max
    task_soft_time_limit=540,  # 9 minutes soft limit
    worker_prefetch_multiplier=1,  # One task at a time per worker
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=3600,  # Results expire after 1 hour
)

# Per-device routing for serial execution
celery_app.conf.task_routes = {
    'tasks.get_config': {'queue': 'device_tasks'},
    'tasks.set_config': {'queue': 'device_tasks'},
    'tasks.run_commands': {'queue': 'device_tasks'},
    'tasks.validate_config': {'queue': 'device_tasks'},
    'tasks.backup_device_config': {'queue': 'device_tasks'},
    'tasks.validate_config_from_backup': {'queue': 'default'},
}


def get_textfsm_template_path(device_type: str, command: str) -> Optional[str]:
    """
    Find TextFSM template for a given device type and command

    Args:
        device_type: Netmiko device type (e.g., 'cisco_ios')
        command: CLI command (e.g., 'show version')

    Returns:
        Path to template file or None if not found
    """
    try:
        from ntc_templates.parse import _get_template_dir
        template_dir = _get_template_dir()

        # Normalize command for template lookup
        command_normalized = command.lower().replace(' ', '_')

        # Try exact match first
        template_name = f"{device_type}_{command_normalized}.textfsm"
        template_path = os.path.join(template_dir, template_name)

        if os.path.exists(template_path):
            return template_path

        # Try ntc-templates index lookup
        try:
            from ntc_templates.parse import get_template
            return get_template(platform=device_type, command=command)
        except Exception:
            pass

        return None
    except ImportError:
        log.warning("ntc-templates not installed")
        return None


def parse_with_textfsm(output: str, template_path: str) -> List[Dict]:
    """
    Parse CLI output using TextFSM template

    Args:
        output: Raw CLI output
        template_path: Path to TextFSM template

    Returns:
        List of parsed records as dicts
    """
    try:
        with open(template_path) as f:
            fsm = textfsm.TextFSM(f)
            result = fsm.ParseText(output)
            headers = fsm.header
            return [dict(zip(headers, row)) for row in result]
    except Exception as e:
        log.error(f"TextFSM parsing error: {e}")
        return []


def parse_with_genie(output: str, command: str, device_type: str) -> Dict:
    """
    Parse CLI output using Cisco Genie parser

    Args:
        output: Raw CLI output
        command: CLI command that was executed
        device_type: Device OS type

    Returns:
        Parsed structured data
    """
    try:
        from genie.libs.parser.utils import get_parser
        from genie.conf.base import Device

        # Map netmiko device types to Genie OS
        os_map = {
            'cisco_ios': 'ios',
            'cisco_xe': 'iosxe',
            'cisco_xr': 'iosxr',
            'cisco_nxos': 'nxos',
            'juniper_junos': 'junos',
            'arista_eos': 'eos',
        }

        genie_os = os_map.get(device_type, device_type)

        # Create a mock device for parsing
        device = Device('mock_device', os=genie_os)
        device.custom.setdefault('abstraction', {})['order'] = [genie_os]

        # Get parser and parse
        parser_class = get_parser(command, device)
        parser = parser_class(device=device)
        return parser.parse(output=output)

    except ImportError:
        log.warning("Genie not available")
        return {'raw_output': output}
    except Exception as e:
        log.warning(f"Genie parsing failed: {e}")
        return {'raw_output': output}


def parse_with_ttp(output: str, ttp_template: str) -> List[Dict]:
    """
    Parse CLI output using TTP (Template Text Parser)

    Args:
        output: Raw CLI output
        ttp_template: TTP template string

    Returns:
        List of parsed records
    """
    try:
        from ttp import ttp

        parser = ttp(data=output, template=ttp_template)
        parser.parse()
        results = parser.result()

        # TTP returns nested list structure [[results]]
        if results and len(results) > 0 and len(results[0]) > 0:
            return results[0]
        return []

    except ImportError:
        log.warning("TTP not available")
        return []
    except Exception as e:
        log.error(f"TTP parsing error: {e}")
        return []


def render_jinja2_template(template_content: str, variables: Dict) -> str:
    """
    Render a Jinja2 template with variables

    Args:
        template_content: Jinja2 template string
        variables: Dict of variables to substitute

    Returns:
        Rendered template string
    """
    env = Environment(loader=BaseLoader())
    template = env.from_string(template_content)
    return template.render(**variables)


@celery_app.task(bind=True, name='tasks.get_config')
def get_config(self, connection_args: Dict, command: str,
               use_textfsm: bool = False, use_genie: bool = False,
               use_ttp: bool = False, ttp_template: str = None) -> Dict:
    """
    Get configuration or command output from a device

    Args:
        connection_args: Dict with device_type, host, username, password, etc.
        command: CLI command to execute
        use_textfsm: Parse output with TextFSM
        use_genie: Parse output with Genie
        use_ttp: Parse output with TTP
        ttp_template: TTP template string (required if use_ttp=True)

    Returns:
        Dict with output, parsed_output (if parsing enabled), and metadata
    """
    result = {
        'status': 'started',
        'host': connection_args.get('host'),
        'command': command,
    }

    try:
        log.info(f"Connecting to {connection_args.get('host')} for get_config")

        with ConnectHandler(**connection_args) as conn:
            output = conn.send_command(command)

            result['output'] = output
            result['status'] = 'success'

            # Parse with TTP if requested (user-provided template)
            if use_ttp and ttp_template:
                parsed = parse_with_ttp(output, ttp_template)
                if parsed:
                    result['parsed_output'] = parsed
                    result['parser'] = 'ttp'
                else:
                    log.warning("TTP parsing returned no results")

            # Parse with TextFSM if requested
            if use_textfsm and not result.get('parsed_output'):
                device_type = connection_args.get('device_type', 'cisco_ios')
                template_path = get_textfsm_template_path(device_type, command)
                if template_path:
                    result['parsed_output'] = parse_with_textfsm(output, template_path)
                    result['parser'] = 'textfsm'
                else:
                    log.warning(f"No TextFSM template found for {device_type} / {command}")

            # Parse with Genie if requested
            if use_genie and not result.get('parsed_output'):
                device_type = connection_args.get('device_type', 'cisco_ios')
                parsed = parse_with_genie(output, command, device_type)
                if parsed and parsed != {'raw_output': output}:
                    result['parsed_output'] = parsed
                    result['parser'] = 'genie'

    except NetmikoTimeoutException as e:
        log.error(f"Timeout connecting to {connection_args.get('host')}: {e}")
        result['status'] = 'failed'
        result['error'] = f"Connection timeout: {str(e)}"

    except NetmikoAuthenticationException as e:
        log.error(f"Authentication failed for {connection_args.get('host')}: {e}")
        result['status'] = 'failed'
        result['error'] = f"Authentication failed: {str(e)}"

    except Exception as e:
        log.error(f"Error in get_config: {e}", exc_info=True)
        result['status'] = 'failed'
        result['error'] = str(e)

    return result


@celery_app.task(bind=True, name='tasks.set_config')
def set_config(self, connection_args: Dict, config_lines: List[str] = None,
               template_content: str = None, variables: Dict = None,
               save_config: bool = True) -> Dict:
    """
    Push configuration to a device

    Args:
        connection_args: Dict with device_type, host, username, password, etc.
        config_lines: List of config commands to send
        template_content: Jinja2 template string (alternative to config_lines)
        variables: Variables for template rendering
        save_config: Whether to save config after changes

    Returns:
        Dict with output and metadata
    """
    result = {
        'status': 'started',
        'host': connection_args.get('host'),
    }

    try:
        # Render template if provided
        if template_content and variables:
            rendered = render_jinja2_template(template_content, variables)
            config_lines = rendered.strip().split('\n')
            result['rendered_config'] = rendered

        if not config_lines:
            result['status'] = 'failed'
            result['error'] = 'No configuration provided'
            return result

        log.info(f"Connecting to {connection_args.get('host')} for set_config")

        with ConnectHandler(**connection_args) as conn:
            output = conn.send_config_set(config_lines)
            result['output'] = output

            if save_config:
                save_output = conn.save_config()
                result['save_output'] = save_output

            result['status'] = 'success'
            result['config_lines'] = config_lines

    except NetmikoTimeoutException as e:
        log.error(f"Timeout connecting to {connection_args.get('host')}: {e}")
        result['status'] = 'failed'
        result['error'] = f"Connection timeout: {str(e)}"

    except NetmikoAuthenticationException as e:
        log.error(f"Authentication failed for {connection_args.get('host')}: {e}")
        result['status'] = 'failed'
        result['error'] = f"Authentication failed: {str(e)}"

    except Exception as e:
        log.error(f"Error in set_config: {e}", exc_info=True)
        result['status'] = 'failed'
        result['error'] = str(e)

    return result


@celery_app.task(bind=True, name='tasks.run_commands')
def run_commands(self, connection_args: Dict, commands: List[str],
                 use_textfsm: bool = False) -> Dict:
    """
    Run multiple commands on a device

    Args:
        connection_args: Dict with device_type, host, username, password, etc.
        commands: List of CLI commands to execute
        use_textfsm: Parse output with TextFSM

    Returns:
        Dict with results for each command
    """
    result = {
        'status': 'started',
        'host': connection_args.get('host'),
        'commands': {},
    }

    try:
        log.info(f"Connecting to {connection_args.get('host')} for run_commands")

        with ConnectHandler(**connection_args) as conn:
            device_type = connection_args.get('device_type', 'cisco_ios')

            for command in commands:
                cmd_result = {'command': command}
                try:
                    output = conn.send_command(command)
                    cmd_result['output'] = output
                    cmd_result['status'] = 'success'

                    if use_textfsm:
                        template_path = get_textfsm_template_path(device_type, command)
                        if template_path:
                            cmd_result['parsed_output'] = parse_with_textfsm(output, template_path)

                except Exception as e:
                    cmd_result['status'] = 'failed'
                    cmd_result['error'] = str(e)

                result['commands'][command] = cmd_result

            result['status'] = 'success'

    except Exception as e:
        log.error(f"Error in run_commands: {e}", exc_info=True)
        result['status'] = 'failed'
        result['error'] = str(e)

    return result


@celery_app.task(bind=True, name='tasks.validate_config')
def validate_config(self, connection_args: Dict, expected_patterns: List[str],
                    validation_command: str = 'show running-config') -> Dict:
    """
    Validate that configuration patterns exist on device

    Args:
        connection_args: Dict with device_type, host, username, password, etc.
        expected_patterns: List of regex patterns to search for
        validation_command: Command to run for validation

    Returns:
        Dict with validation results
    """
    import re

    result = {
        'status': 'started',
        'host': connection_args.get('host'),
        'validations': [],
        'all_passed': True,
    }

    try:
        log.info(f"Connecting to {connection_args.get('host')} for validate_config")

        with ConnectHandler(**connection_args) as conn:
            output = conn.send_command(validation_command)

            for pattern in expected_patterns:
                validation = {
                    'pattern': pattern,
                    'found': bool(re.search(pattern, output, re.MULTILINE)),
                }
                result['validations'].append(validation)

                if not validation['found']:
                    result['all_passed'] = False

            result['status'] = 'success'
            result['validation_status'] = 'passed' if result['all_passed'] else 'failed'

    except Exception as e:
        log.error(f"Error in validate_config: {e}", exc_info=True)
        result['status'] = 'failed'
        result['error'] = str(e)
        result['all_passed'] = False

    return result


@celery_app.task(bind=True, name='tasks.render_template_only')
def render_template_only(self, template_content: str, variables: Dict) -> Dict:
    """
    Render a Jinja2 template without sending to device (dry run)

    Args:
        template_content: Jinja2 template string
        variables: Dict of variables

    Returns:
        Dict with rendered template
    """
    result = {
        'status': 'started',
    }

    try:
        rendered = render_jinja2_template(template_content, variables)
        result['rendered_config'] = rendered
        result['status'] = 'success'
    except Exception as e:
        log.error(f"Error rendering template: {e}", exc_info=True)
        result['status'] = 'failed'
        result['error'] = str(e)

    return result


@celery_app.task(bind=True, name='tasks.sync_netbox_devices')
def sync_netbox_devices(self, netbox_url: str, netbox_token: str,
                        filters: List[Dict] = None, verify_ssl: bool = False) -> Dict:
    """
    Sync device inventory from Netbox

    This task is scheduled to run periodically to keep device cache fresh.

    Args:
        netbox_url: Netbox API URL
        netbox_token: API token
        filters: Optional filter list
        verify_ssl: Whether to verify SSL

    Returns:
        Dict with sync results
    """
    result = {
        'status': 'started',
    }

    try:
        from netbox_client import NetboxClient

        client = NetboxClient(netbox_url, netbox_token, verify_ssl)
        devices = client.get_devices_with_details(filters=filters)

        result['status'] = 'success'
        result['device_count'] = len(devices)
        result['devices'] = devices

    except Exception as e:
        log.error(f"Error syncing Netbox devices: {e}", exc_info=True)
        result['status'] = 'failed'
        result['error'] = str(e)

    return result


@celery_app.task(bind=True, name='tasks.backup_device_config')
def backup_device_config(self, connection_args: Dict, device_name: str,
                         device_platform: str = None, juniper_set_format: bool = True,
                         snapshot_id: str = None, created_by: str = None) -> Dict:
    """
    Backup device running configuration and save to database.

    For Juniper devices, can optionally convert to set format for template matching.

    Args:
        connection_args: Dict with device_type, host, username, password, etc.
        device_name: Name of the device (for metadata)
        device_platform: Platform name (for identifying Juniper)
        juniper_set_format: If True, get Juniper config in set format
        snapshot_id: Optional snapshot ID to link backup to a snapshot
        created_by: Username who initiated the backup

    Returns:
        Dict with config content and metadata
    """
    result = {
        'status': 'started',
        'host': connection_args.get('host'),
        'device_name': device_name,
        'config_format': 'native',
    }

    try:
        log.info(f"Starting config backup for {device_name} ({connection_args.get('host')})")

        device_type = connection_args.get('device_type', '').lower()
        is_juniper = 'juniper' in device_type or (device_platform and 'junos' in device_platform.lower())

        with ConnectHandler(**connection_args) as conn:
            if is_juniper and juniper_set_format:
                # Get Juniper config in set format for template matching
                config_output = conn.send_command('show configuration | display set')
                result['config_format'] = 'set'
            elif is_juniper:
                # Get standard Juniper hierarchical config
                config_output = conn.send_command('show configuration')
            elif 'cisco' in device_type or 'ios' in device_type:
                config_output = conn.send_command('show running-config')
            elif 'arista' in device_type or 'eos' in device_type:
                config_output = conn.send_command('show running-config')
            elif 'nokia' in device_type or 'sros' in device_type:
                config_output = conn.send_command('admin display-config')
            else:
                # Default to Cisco-style command
                config_output = conn.send_command('show running-config')

            result['config_content'] = config_output
            result['config_size'] = len(config_output)
            result['status'] = 'success'

            # Save backup directly to database
            _save_backup_to_db(
                device_name=device_name,
                device_ip=connection_args.get('host'),
                platform=device_platform,
                config_content=config_output,
                config_format=result['config_format'],
                snapshot_id=snapshot_id,
                created_by=created_by,
                status='success'
            )
            result['saved'] = True

    except NetmikoTimeoutException as e:
        log.error(f"Timeout backing up {device_name}: {e}")
        result['status'] = 'failed'
        result['error'] = f"Connection timeout: {str(e)}"
        # Save failed backup record if part of snapshot
        if snapshot_id:
            _save_backup_to_db(
                device_name=device_name,
                device_ip=connection_args.get('host'),
                platform=device_platform,
                config_content='',
                config_format='native',
                snapshot_id=snapshot_id,
                created_by=created_by,
                status='failed',
                error_message=result['error']
            )

    except NetmikoAuthenticationException as e:
        log.error(f"Authentication failed backing up {device_name}: {e}")
        result['status'] = 'failed'
        result['error'] = f"Authentication failed: {str(e)}"
        # Save failed backup record if part of snapshot
        if snapshot_id:
            _save_backup_to_db(
                device_name=device_name,
                device_ip=connection_args.get('host'),
                platform=device_platform,
                config_content='',
                config_format='native',
                snapshot_id=snapshot_id,
                created_by=created_by,
                status='failed',
                error_message=result['error']
            )

    except Exception as e:
        log.error(f"Error backing up {device_name}: {e}", exc_info=True)
        result['status'] = 'failed'
        result['error'] = str(e)
        # Save failed backup record if part of snapshot
        if snapshot_id:
            _save_backup_to_db(
                device_name=device_name,
                device_ip=connection_args.get('host'),
                platform=device_platform,
                config_content='',
                config_format='native',
                snapshot_id=snapshot_id,
                created_by=created_by,
                status='failed',
                error_message=result['error']
            )

    return result


def _save_backup_to_db(device_name: str, device_ip: str, platform: str,
                       config_content: str, config_format: str,
                       snapshot_id: str = None, created_by: str = None,
                       status: str = 'success', error_message: str = None):
    """
    Save backup to database and update snapshot counts.
    Called from within Celery task.

    IMPORTANT: This function MUST update snapshot counts even if backup save fails.
    Otherwise snapshots will get stuck in 'in_progress' state forever.
    """
    # Ensure /app is in path for forked workers
    import sys
    if '/app' not in sys.path:
        sys.path.insert(0, '/app')
    # Import here to avoid circular imports
    import database_postgres as db

    backup_saved = False
    backup_id = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S%f')}_{device_name}"

    try:
        # Calculate config hash for change detection
        config_hash = hashlib.sha256(config_content.encode()).hexdigest() if config_content else None

        backup_data = {
            'backup_id': backup_id,
            'device_name': device_name,
            'device_ip': device_ip,
            'platform': platform,
            'config_content': config_content,
            'config_format': config_format,
            'config_hash': config_hash,
            'backup_type': 'snapshot' if snapshot_id else 'manual',
            'status': status,
            'error_message': error_message,
            'file_size': len(config_content) if config_content else 0,
            'snapshot_id': snapshot_id,
            'created_by': created_by
        }

        db.save_config_backup(backup_data)
        backup_saved = True
        log.info(f"Saved backup {backup_id} for device {device_name}" +
                 (f" (snapshot: {snapshot_id})" if snapshot_id else ""))

    except Exception as e:
        log.error(f"Failed to save backup for {device_name}: {e}", exc_info=True)
        # Mark as failed if we couldn't save the backup
        status = 'failed'

    # ALWAYS update snapshot counts if this is part of a snapshot
    # This must happen even if backup save failed to prevent stuck snapshots
    if snapshot_id:
        try:
            # If backup save failed but we were trying to save success, mark as failed
            final_status = status if backup_saved else 'failed'
            db.increment_snapshot_counts(snapshot_id, success=(final_status == 'success'))
            log.info(f"Updated snapshot {snapshot_id} counts for {device_name} (status: {final_status})")
        except Exception as e:
            log.error(f"CRITICAL: Failed to update snapshot counts for {snapshot_id}/{device_name}: {e}")
            # Last resort: try again with a fresh connection
            try:
                import database_postgres as db2
                db2.increment_snapshot_counts(snapshot_id, success=False)
                log.info(f"Retry: Updated snapshot {snapshot_id} counts for {device_name}")
            except Exception as e2:
                log.error(f"CRITICAL: Retry also failed for {snapshot_id}/{device_name}: {e2}")


@celery_app.task(bind=True, name='tasks.validate_config_from_backup')
def validate_config_from_backup(self, config_content: str, expected_patterns: List[str]) -> Dict:
    """
    Validate configuration patterns against a backed-up config (no device connection)

    Args:
        config_content: The backed-up configuration text
        expected_patterns: List of regex patterns to search for

    Returns:
        Dict with validation results
    """
    import re

    result = {
        'status': 'started',
        'validations': [],
        'all_passed': True,
        'source': 'backup',
    }

    try:
        for pattern in expected_patterns:
            validation = {
                'pattern': pattern,
                'found': bool(re.search(pattern, config_content, re.MULTILINE)),
            }
            result['validations'].append(validation)

            if not validation['found']:
                result['all_passed'] = False

        result['status'] = 'success'
        result['validation_status'] = 'passed' if result['all_passed'] else 'failed'

    except Exception as e:
        log.error(f"Error validating backup config: {e}", exc_info=True)
        result['status'] = 'failed'
        result['error'] = str(e)
        result['all_passed'] = False

    return result


# Helper to get device-specific queue name
def get_device_queue(device_ip: str) -> str:
    """
    Get queue name for a specific device (for serial execution)

    Args:
        device_ip: Device IP or hostname

    Returns:
        Queue name for routing
    """
    # Sanitize IP for queue name
    return f"device_{device_ip.replace('.', '_').replace(':', '_')}"
