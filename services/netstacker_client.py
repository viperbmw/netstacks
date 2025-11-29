"""
Netstacker API Client
Handles all communication with the Netstacker backend API
This will be replaced by Celery tasks in Phase 3
"""
import requests
import logging
from config import config

log = logging.getLogger(__name__)


class NetstackerClient:
    """Client for Netstacker API operations"""

    def __init__(self, base_url=None, api_key=None):
        self.base_url = base_url or config.NETSTACKER_API_URL
        self.api_key = api_key or config.NETSTACKER_API_KEY
        self.timeout = 30

    @property
    def headers(self):
        return {
            'x-api-key': self.api_key,
            'Content-Type': 'application/json'
        }

    def _request(self, method, endpoint, **kwargs):
        """Make a request to Netstacker API"""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault('headers', self.headers)
        kwargs.setdefault('timeout', self.timeout)

        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            log.error(f"Netstacker API error: {e}")
            raise

    def get_config(self, connection_args, command, use_textfsm=False):
        """
        Get configuration/output from a device

        Args:
            connection_args: Dict with device_type, host, username, password, etc.
            command: CLI command to execute
            use_textfsm: Whether to parse output with TextFSM

        Returns:
            Task ID for polling results
        """
        payload = {
            'library': 'netmiko',
            'connection_args': connection_args,
            'command': command,
            'args': {
                'use_textfsm': use_textfsm
            }
        }

        response = self._request('POST', '/getconfig', json=payload)
        return response.get('task_id')

    def set_config(self, connection_args, config_lines=None, j2config=None, dry_run=False):
        """
        Push configuration to a device

        Args:
            connection_args: Dict with device_type, host, username, password, etc.
            config_lines: List of config commands to send
            j2config: Dict with template name and args for Jinja2 rendering
            dry_run: If True, only render template without pushing

        Returns:
            Task ID for polling results
        """
        payload = {
            'library': 'netmiko',
            'connection_args': connection_args,
        }

        if config_lines:
            payload['config'] = config_lines
        if j2config:
            payload['j2config'] = j2config

        endpoint = '/setconfig/dry-run' if dry_run else '/setconfig'
        response = self._request('POST', endpoint, json=payload)
        return response.get('task_id')

    def get_task_result(self, task_id):
        """
        Get the result of a task

        Args:
            task_id: Task ID to query

        Returns:
            Dict with task status and result
        """
        return self._request('GET', f'/task/{task_id}')

    def get_workers(self):
        """Get list of active workers"""
        return self._request('GET', '/workers')

    def get_template(self, template_name):
        """Get a Jinja2 template from Netstacker"""
        return self._request('GET', f'/j2template/config/{template_name}')

    def list_templates(self):
        """List all available Jinja2 templates"""
        return self._request('GET', '/j2template/config/')

    def save_template(self, template_name, template_content):
        """Save a Jinja2 template to Netstacker"""
        payload = {
            'key': template_name,
            'driver': 'b64',
            'value': template_content
        }
        return self._request('POST', '/j2template/config/', json=payload)

    def delete_template(self, template_name):
        """Delete a Jinja2 template from Netstacker"""
        return self._request('DELETE', f'/j2template/config/{template_name}')

    def render_template(self, template_name, variables):
        """
        Render a Jinja2 template with variables

        Args:
            template_name: Name of template in Netstacker
            variables: Dict of variables to render with

        Returns:
            Rendered template content
        """
        payload = {
            'j2config': {
                'template': template_name,
                'args': variables
            }
        }
        # Use dry-run to just render without sending to device
        response = self._request('POST', '/setconfig/dry-run', json=payload)
        return response.get('rendered_config')


# Global client instance
netstacker = NetstackerClient()
