"""
Deploy Routes
Configuration deployment using Celery tasks
"""
from flask import Blueprint, jsonify, request
import logging

import database as db
from services.celery_device_service import celery_device_service
from services.device_service import get_device_connection_info, get_device_credentials

log = logging.getLogger(__name__)

deploy_bp = Blueprint('deploy', __name__)


@deploy_bp.route('/api/celery/getconfig', methods=['POST'])
def celery_getconfig():
    """
    Execute a show command using Celery

    Request body:
    {
        "device": "device-name",
        "command": "show version",
        "use_textfsm": true,
        "use_genie": false,
        "username": "optional-override",
        "password": "optional-override"
    }

    Returns:
        {"task_id": "..."}
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        device_name = data.get('device')
        command = data.get('command')

        if not device_name:
            return jsonify({'error': 'Device name is required'}), 400
        if not command:
            return jsonify({'error': 'Command is required'}), 400

        # Get credential override if provided
        credential_override = None
        if data.get('username'):
            credential_override = {
                'username': data.get('username'),
                'password': data.get('password', '')
            }

        # Get device connection info
        device_info = get_device_connection_info(device_name, credential_override)
        if not device_info:
            return jsonify({'error': f'Device {device_name} not found'}), 404

        connection_args = device_info['connection_args']

        # Add default credentials if not in connection_args
        if not connection_args.get('username'):
            creds = get_device_credentials(device_name)
            connection_args['username'] = creds.get('username')
            connection_args['password'] = creds.get('password')
            if creds.get('secret'):
                connection_args['secret'] = creds['secret']

        # Execute via Celery
        task_id = celery_device_service.execute_get_config(
            connection_args=connection_args,
            command=command,
            use_textfsm=data.get('use_textfsm', False),
            use_genie=data.get('use_genie', False)
        )

        return jsonify({
            'task_id': task_id,
            'device': device_name,
            'command': command,
            'message': 'Task submitted successfully'
        })

    except Exception as e:
        log.error(f"Error in celery_getconfig: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@deploy_bp.route('/api/celery/setconfig', methods=['POST'])
def celery_setconfig():
    """
    Push configuration using Celery

    Request body:
    {
        "device": "device-name",
        "config_lines": ["line1", "line2"],
        "template_content": "optional jinja2 template",
        "variables": {"var1": "value1"},
        "save_config": true
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        device_name = data.get('device')
        if not device_name:
            return jsonify({'error': 'Device name is required'}), 400

        config_lines = data.get('config_lines')
        template_content = data.get('template_content')
        variables = data.get('variables', {})

        if not config_lines and not template_content:
            return jsonify({'error': 'Either config_lines or template_content is required'}), 400

        # Get credential override if provided
        credential_override = None
        if data.get('username'):
            credential_override = {
                'username': data.get('username'),
                'password': data.get('password', '')
            }

        # Get device connection info
        device_info = get_device_connection_info(device_name, credential_override)
        if not device_info:
            return jsonify({'error': f'Device {device_name} not found'}), 404

        connection_args = device_info['connection_args']

        # Add default credentials if not in connection_args
        if not connection_args.get('username'):
            creds = get_device_credentials(device_name)
            connection_args['username'] = creds.get('username')
            connection_args['password'] = creds.get('password')
            if creds.get('secret'):
                connection_args['secret'] = creds['secret']

        # Execute via Celery
        task_id = celery_device_service.execute_set_config(
            connection_args=connection_args,
            config_lines=config_lines,
            template_content=template_content,
            variables=variables,
            save_config=data.get('save_config', True)
        )

        return jsonify({
            'task_id': task_id,
            'device': device_name,
            'message': 'Task submitted successfully'
        })

    except Exception as e:
        log.error(f"Error in celery_setconfig: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@deploy_bp.route('/api/celery/task/<task_id>', methods=['GET'])
def celery_task_status(task_id):
    """
    Get Celery task status and result

    Returns:
        {
            "task_id": "...",
            "status": "SUCCESS|PENDING|STARTED|FAILURE",
            "result": {...}  # if completed
        }
    """
    try:
        result = celery_device_service.get_task_result(task_id)
        return jsonify(result)

    except Exception as e:
        log.error(f"Error getting task status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@deploy_bp.route('/api/celery/validate', methods=['POST'])
def celery_validate():
    """
    Validate configuration patterns on a device

    Request body:
    {
        "device": "device-name",
        "patterns": ["pattern1", "pattern2"],
        "command": "show running-config"  # optional
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        device_name = data.get('device')
        patterns = data.get('patterns', [])

        if not device_name:
            return jsonify({'error': 'Device name is required'}), 400
        if not patterns:
            return jsonify({'error': 'Patterns list is required'}), 400

        # Get device connection info
        device_info = get_device_connection_info(device_name)
        if not device_info:
            return jsonify({'error': f'Device {device_name} not found'}), 404

        connection_args = device_info['connection_args']

        # Add default credentials if not in connection_args
        if not connection_args.get('username'):
            creds = get_device_credentials(device_name)
            connection_args['username'] = creds.get('username')
            connection_args['password'] = creds.get('password')
            if creds.get('secret'):
                connection_args['secret'] = creds['secret']

        # Execute via Celery
        task_id = celery_device_service.execute_validate(
            connection_args=connection_args,
            expected_patterns=patterns,
            validation_command=data.get('command', 'show running-config')
        )

        return jsonify({
            'task_id': task_id,
            'device': device_name,
            'message': 'Validation task submitted'
        })

    except Exception as e:
        log.error(f"Error in celery_validate: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
