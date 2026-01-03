"""
Device Tasks

Celery tasks for network device operations using Netmiko.
Includes configuration retrieval, pushing, and validation.
"""

import os
import logging
from typing import Dict, List, Optional

from celery import shared_task
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException
from jinja2 import Environment, BaseLoader

log = logging.getLogger(__name__)


def parse_with_ntc_templates(output: str, device_type: str, command: str) -> List[Dict]:
    """Parse CLI output using ntc-templates.

    Args:
        output: Raw CLI output to parse
        device_type: Netmiko device type (e.g., 'arista_eos', 'cisco_ios')
        command: The CLI command that was executed

    Returns:
        List of parsed dictionaries, or empty list if parsing fails
    """
    try:
        from ntc_templates.parse import parse_output

        # ntc-templates uses platform names that match netmiko device types
        parsed = parse_output(platform=device_type, command=command, data=output)
        log.info(f"TextFSM parsed {len(parsed)} records for {device_type} '{command}'")
        return parsed
    except Exception as e:
        log.warning(f"TextFSM parsing not available for {device_type} '{command}': {e}")
        return []


def render_jinja2_template(template_content: str, variables: Dict) -> str:
    """Render a Jinja2 template with variables."""
    env = Environment(loader=BaseLoader())
    template = env.from_string(template_content)
    return template.render(**variables)


@shared_task(bind=True, name='tasks.device_tasks.get_config')
def get_config(self, connection_args: Dict, command: str,
               use_textfsm: bool = False, use_ttp: bool = False,
               ttp_template: str = None) -> Dict:
    """
    Get configuration or command output from a device.

    Args:
        connection_args: Dict with device_type, host, username, password, etc.
        command: CLI command to execute
        use_textfsm: Parse output with TextFSM
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

            # Parse with TTP if requested
            if use_ttp and ttp_template:
                try:
                    from ttp import ttp
                    parser = ttp(data=output, template=ttp_template)
                    parser.parse()
                    parsed = parser.result()
                    if parsed and len(parsed) > 0 and len(parsed[0]) > 0:
                        result['parsed_output'] = parsed[0]
                        result['parser'] = 'ttp'
                except ImportError:
                    log.warning("TTP not available")

            # Parse with TextFSM/ntc-templates if requested
            if use_textfsm and not result.get('parsed_output'):
                device_type = connection_args.get('device_type', 'cisco_ios')
                parsed = parse_with_ntc_templates(output, device_type, command)
                if parsed:
                    result['parsed_output'] = parsed
                    result['parser'] = 'textfsm'

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


@shared_task(bind=True, name='tasks.device_tasks.set_config')
def set_config(self, connection_args: Dict, config_lines: List[str] = None,
               template_content: str = None, variables: Dict = None,
               save_config: bool = True) -> Dict:
    """
    Push configuration to a device.

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

        # For Arista EOS devices, disable fast_cli to avoid timeout issues
        device_type = connection_args.get('device_type', '')
        if 'arista' in device_type.lower():
            connection_args['fast_cli'] = False
            log.debug(f"Disabled fast_cli for Arista device {connection_args.get('host')}")

        with ConnectHandler(**connection_args) as conn:
            # Enter enable mode if not already there (some devices need this)
            if not conn.check_enable_mode():
                conn.enable()
            
            output = conn.send_config_set(config_lines, read_timeout=60)
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


@shared_task(bind=True, name='tasks.device_tasks.run_commands')
def run_commands(self, connection_args: Dict, commands: List[str],
                 use_textfsm: bool = False) -> Dict:
    """
    Run multiple commands on a device.

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
                        parsed = parse_with_ntc_templates(output, device_type, command)
                        if parsed:
                            cmd_result['parsed_output'] = parsed

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


@shared_task(bind=True, name='tasks.device_tasks.validate_config')
def validate_config(self, connection_args: Dict, expected_patterns: List[str],
                    validation_command: str = 'show running-config') -> Dict:
    """
    Validate that configuration patterns exist on device.

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


@shared_task(bind=True, name='tasks.device_tasks.test_connectivity')
def test_connectivity(self, connection_args: Dict) -> Dict:
    """
    Test connectivity to a device.

    Args:
        connection_args: Dict with device_type, host, username, password, etc.

    Returns:
        Dict with connection test results
    """
    result = {
        'status': 'started',
        'host': connection_args.get('host'),
        'device_type': connection_args.get('device_type'),
    }

    try:
        log.info(f"Testing connectivity to {connection_args.get('host')}")

        with ConnectHandler(**connection_args) as conn:
            # Try to get prompt to verify connection
            prompt = conn.find_prompt()
            result['status'] = 'success'
            result['prompt'] = prompt
            result['message'] = 'Connection successful'

    except NetmikoTimeoutException as e:
        log.error(f"Timeout connecting to {connection_args.get('host')}: {e}")
        result['status'] = 'failed'
        result['error'] = f"Connection timeout: {str(e)}"

    except NetmikoAuthenticationException as e:
        log.error(f"Authentication failed for {connection_args.get('host')}: {e}")
        result['status'] = 'failed'
        result['error'] = f"Authentication failed: {str(e)}"

    except Exception as e:
        log.error(f"Error testing connectivity: {e}", exc_info=True)
        result['status'] = 'failed'
        result['error'] = str(e)

    return result
