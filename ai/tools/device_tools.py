"""
Device Tools

Tools for network device operations using existing Celery tasks.
"""

import logging
import uuid
from typing import Dict, Any, Optional, List

from .base import BaseTool, ToolResult

log = logging.getLogger(__name__)


class DeviceListTool(BaseTool):
    """
    List devices from the inventory.

    Returns device count and basic info about devices in the system.
    """

    name = "device_list"
    description = """List devices from the network inventory.
Use this to get a count of devices, see what devices are available, or filter by device type/platform.
This is the first tool to use when asked about device inventory or how many devices exist."""
    category = "device"
    risk_level = "low"
    requires_approval = False

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "device_type": {
                    "type": "string",
                    "description": "Optional: Filter by device type (e.g., 'cisco_ios', 'juniper_junos')"
                },
                "platform": {
                    "type": "string",
                    "description": "Optional: Filter by platform (e.g., 'cisco', 'juniper', 'arista')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of devices to return (default 50)",
                    "default": 50
                }
            },
            "required": []
        }

    def execute(
        self,
        device_type: Optional[str] = None,
        platform: Optional[str] = None,
        limit: int = 50
    ) -> ToolResult:
        """List devices from inventory"""
        try:
            import database as db
            from models import Device

            with db.get_db() as session:
                query = session.query(Device)

                if device_type:
                    query = query.filter(Device.device_type == device_type)
                if platform:
                    query = query.filter(Device.platform.ilike(f"%{platform}%"))

                # Get total count
                total_count = query.count()

                # Get devices with limit
                devices = query.limit(limit).all()

                device_list = [
                    {
                        'name': d.name,
                        'host': d.host,
                        'device_type': d.device_type,
                        'platform': d.platform,
                        'site': d.site,
                        'manufacturer': d.manufacturer,
                        'model': d.model
                    }
                    for d in devices
                ]

                return ToolResult(
                    success=True,
                    data={
                        'total_count': total_count,
                        'returned_count': len(device_list),
                        'devices': device_list,
                        'filters_applied': {
                            'device_type': device_type,
                            'platform': platform
                        }
                    }
                )

        except ImportError:
            log.warning("Database not available")
            return ToolResult(
                success=False,
                error="Database not available"
            )
        except Exception as e:
            log.error(f"Device list error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )


class DeviceShowTool(BaseTool):
    """
    Execute show commands on network devices.

    Uses existing Celery tasks for device operations via Netmiko.
    Supports TextFSM and TTP parsing for structured output.
    """

    name = "device_show"
    description = """Execute show commands on a network device and return the output.
Can optionally parse output using TextFSM for structured data.
Use this to gather information about device state, configuration, routing tables, neighbors, etc."""
    category = "device"
    risk_level = "low"
    requires_approval = False

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "device_name": {
                    "type": "string",
                    "description": "Name or hostname of the device to connect to"
                },
                "command": {
                    "type": "string",
                    "description": "Show command to execute (e.g., 'show ip bgp summary', 'show interfaces')"
                },
                "parse": {
                    "type": "boolean",
                    "description": "Whether to parse output with TextFSM for structured data",
                    "default": True
                }
            },
            "required": ["device_name", "command"]
        }

    def execute(self, device_name: str, command: str, parse: bool = True) -> ToolResult:
        """Execute show command on device"""
        try:
            # Get device info from database
            device_info = self._get_device_info(device_name)
            if not device_info:
                return ToolResult(
                    success=False,
                    error=f"Device not found: {device_name}"
                )

            # Build connection arguments
            connection_args = self._build_connection_args(device_info)
            if not connection_args:
                return ToolResult(
                    success=False,
                    error=f"Could not build connection args for: {device_name}"
                )

            # Execute via Celery task
            from workers.tasks.device_tasks import get_config
            result = get_config.apply_async(
                args=[connection_args, command],
                kwargs={'use_textfsm': parse},
                expires=300  # 5 minute expiry
            ).get(timeout=120)

            if result.get('status') == 'success':
                return ToolResult(
                    success=True,
                    data={
                        'device': device_name,
                        'command': command,
                        'output': result.get('output'),
                        'parsed_output': result.get('parsed_output'),
                        'parser': result.get('parser')
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    error=result.get('error', 'Unknown error')
                )

        except ImportError as e:
            log.error(f"Celery tasks not available: {e}")
            return ToolResult(
                success=False,
                error="Device task system not available"
            )
        except Exception as e:
            log.error(f"Device show error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )

    def _get_device_info(self, device_name: str) -> Optional[Dict]:
        """Get device info from database"""
        try:
            import database as db
            from models import Device

            with db.get_db() as session:
                device = session.query(Device).filter(
                    Device.name == device_name
                ).first()

                if device:
                    return {
                        'id': device.id,
                        'name': device.name,
                        'host': device.host,
                        'device_type': device.device_type,
                        'platform': device.platform,
                        'username': device.username,
                        'password': device.password,
                    }
        except ImportError:
            log.warning("Database not available")
        except Exception as e:
            log.error(f"Error getting device info: {e}")

        return None

    def _build_connection_args(self, device_info: Dict) -> Optional[Dict]:
        """Build Netmiko connection arguments from device info"""
        try:
            import database as db
            from models import DefaultCredential

            # Use device-specific credentials if available
            username = device_info.get('username')
            password = device_info.get('password')

            # Fall back to default credentials if not on device
            if not username or not password:
                with db.get_db() as session:
                    credential = session.query(DefaultCredential).filter(
                        DefaultCredential.is_default == True
                    ).first()

                    if credential:
                        username = credential.username
                        password = credential.password

            if not username or not password:
                log.error("No credentials available")
                return None

            return {
                'device_type': device_info.get('device_type', 'cisco_ios'),
                'host': device_info.get('host'),
                'username': username,
                'password': password,
                'timeout': 30,
            }

        except ImportError:
            log.warning("Required modules not available")
        except Exception as e:
            log.error(f"Error building connection args: {e}")

        return None


class DeviceConfigTool(BaseTool):
    """
    Push configuration changes to network devices.

    This is a HIGH RISK tool that requires approval before execution.
    Can push raw config lines or render Jinja2 templates.
    """

    name = "device_config"
    description = """Push configuration changes to a network device.
Can send raw configuration commands or render a Jinja2 template.
WARNING: This modifies device configuration - use with caution."""
    category = "device"
    risk_level = "high"
    requires_approval = True

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "device_name": {
                    "type": "string",
                    "description": "Name or hostname of the device to configure"
                },
                "config_lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of configuration commands to push"
                },
                "template_name": {
                    "type": "string",
                    "description": "Name of Jinja2 template to render (alternative to config_lines)"
                },
                "variables": {
                    "type": "object",
                    "description": "Variables for template rendering"
                },
                "save_config": {
                    "type": "boolean",
                    "description": "Whether to save config after changes",
                    "default": True
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, only shows what would be configured without making changes",
                    "default": False
                }
            },
            "required": ["device_name"]
        }

    def execute(
        self,
        device_name: str,
        config_lines: Optional[List[str]] = None,
        template_name: Optional[str] = None,
        variables: Optional[Dict] = None,
        save_config: bool = True,
        dry_run: bool = False
    ) -> ToolResult:
        """Push configuration to device"""

        # Must have either config_lines or template_name
        if not config_lines and not template_name:
            return ToolResult(
                success=False,
                error="Must provide either config_lines or template_name"
            )

        try:
            # Get device info
            device_info = self._get_device_info(device_name)
            if not device_info:
                return ToolResult(
                    success=False,
                    error=f"Device not found: {device_name}"
                )

            # If template_name, fetch and render
            template_content = None
            if template_name:
                template_content = self._get_template(template_name)
                if not template_content:
                    return ToolResult(
                        success=False,
                        error=f"Template not found: {template_name}"
                    )

            # For dry run, just return what would be done
            if dry_run:
                if template_content and variables:
                    from jinja2 import Environment, BaseLoader
                    env = Environment(loader=BaseLoader())
                    template = env.from_string(template_content)
                    rendered = template.render(**(variables or {}))
                    config_lines = rendered.strip().split('\n')

                return ToolResult(
                    success=True,
                    data={
                        'device': device_name,
                        'dry_run': True,
                        'config_lines': config_lines,
                        'message': 'Dry run - no changes made'
                    }
                )

            # This requires approval - check approval status
            approval_id = self.context.get('approval_id')
            if not approval_id:
                # Create approval request
                approval_id = str(uuid.uuid4())
                return ToolResult(
                    success=True,
                    requires_approval=True,
                    approval_id=approval_id,
                    risk_level="high",
                    data={
                        'device': device_name,
                        'config_lines': config_lines,
                        'template_name': template_name,
                        'variables': variables,
                        'message': 'Configuration change requires approval'
                    }
                )

            # If we have approval, proceed
            connection_args = self._build_connection_args(device_info)
            if not connection_args:
                return ToolResult(
                    success=False,
                    error=f"Could not build connection args for: {device_name}"
                )

            # Execute via Celery task
            from workers.tasks.device_tasks import set_config
            result = set_config.apply_async(
                args=[connection_args],
                kwargs={
                    'config_lines': config_lines,
                    'template_content': template_content,
                    'variables': variables or {},
                    'save_config': save_config
                },
                expires=600
            ).get(timeout=300)

            if result.get('status') == 'success':
                return ToolResult(
                    success=True,
                    data={
                        'device': device_name,
                        'output': result.get('output'),
                        'config_lines': result.get('config_lines'),
                        'saved': save_config,
                        'message': 'Configuration applied successfully'
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    error=result.get('error', 'Unknown error')
                )

        except Exception as e:
            log.error(f"Device config error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )

    def _get_device_info(self, device_name: str) -> Optional[Dict]:
        """Get device info from database (same as DeviceShowTool)"""
        try:
            import database as db
            from models import Device

            with db.get_db() as session:
                device = session.query(Device).filter(
                    Device.name == device_name
                ).first()

                if device:
                    return {
                        'id': device.id,
                        'name': device.name,
                        'host': device.host,
                        'device_type': device.device_type,
                        'platform': device.platform,
                        'username': device.username,
                        'password': device.password,
                    }
        except ImportError:
            log.warning("Database not available")
        except Exception as e:
            log.error(f"Error getting device info: {e}")

        return None

    def _build_connection_args(self, device_info: Dict) -> Optional[Dict]:
        """Build Netmiko connection arguments"""
        try:
            import database as db
            from models import DefaultCredential

            # Use device-specific credentials if available
            username = device_info.get('username')
            password = device_info.get('password')

            # Fall back to default credentials if not on device
            if not username or not password:
                with db.get_db() as session:
                    credential = session.query(DefaultCredential).filter(
                        DefaultCredential.is_default == True
                    ).first()

                    if credential:
                        username = credential.username
                        password = credential.password

            if not username or not password:
                log.error("No credentials available")
                return None

            return {
                'device_type': device_info.get('device_type', 'cisco_ios'),
                'host': device_info.get('host'),
                'username': username,
                'password': password,
                'timeout': 60,
            }

        except ImportError:
            log.warning("Required modules not available")
        except Exception as e:
            log.error(f"Error building connection args: {e}")

        return None

    def _get_template(self, template_name: str) -> Optional[str]:
        """Get template content from database"""
        try:
            import database as db
            from models import Template

            with db.get_db() as session:
                template = session.query(Template).filter(
                    Template.name == template_name
                ).first()

                if template:
                    return template.content
        except ImportError:
            log.warning("Database not available")
        except Exception as e:
            log.error(f"Error getting template: {e}")

        return None


class DeviceMultiCommandTool(BaseTool):
    """
    Execute multiple show commands on a device.

    Useful for gathering comprehensive diagnostics in one call.
    """

    name = "device_multi_command"
    description = """Execute multiple show commands on a device and return all outputs.
Use this when you need to gather multiple pieces of information from a device efficiently."""
    category = "device"
    risk_level = "low"
    requires_approval = False

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "device_name": {
                    "type": "string",
                    "description": "Name or hostname of the device"
                },
                "commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of show commands to execute"
                },
                "parse": {
                    "type": "boolean",
                    "description": "Whether to parse outputs with TextFSM",
                    "default": True
                }
            },
            "required": ["device_name", "commands"]
        }

    def execute(
        self,
        device_name: str,
        commands: List[str],
        parse: bool = True
    ) -> ToolResult:
        """Execute multiple commands on device"""
        try:
            # Get device info
            device_info = self._get_device_info(device_name)
            if not device_info:
                return ToolResult(
                    success=False,
                    error=f"Device not found: {device_name}"
                )

            connection_args = self._build_connection_args(device_info)
            if not connection_args:
                return ToolResult(
                    success=False,
                    error=f"Could not build connection args for: {device_name}"
                )

            # Execute via Celery task
            from workers.tasks.device_tasks import run_commands
            result = run_commands.apply_async(
                args=[connection_args, commands],
                kwargs={'use_textfsm': parse},
                expires=600
            ).get(timeout=300)

            if result.get('status') == 'success':
                return ToolResult(
                    success=True,
                    data={
                        'device': device_name,
                        'commands': result.get('commands', {})
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    error=result.get('error', 'Unknown error')
                )

        except Exception as e:
            log.error(f"Multi-command error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )

    def _get_device_info(self, device_name: str) -> Optional[Dict]:
        """Get device info from database"""
        try:
            import database as db
            from models import Device

            with db.get_db() as session:
                device = session.query(Device).filter(
                    Device.name == device_name
                ).first()

                if device:
                    return {
                        'id': device.id,
                        'name': device.name,
                        'host': device.host,
                        'device_type': device.device_type,
                        'platform': device.platform,
                        'username': device.username,
                        'password': device.password,
                    }
        except ImportError:
            log.warning("Database not available")
        except Exception as e:
            log.error(f"Error getting device info: {e}")

        return None

    def _build_connection_args(self, device_info: Dict) -> Optional[Dict]:
        """Build connection arguments"""
        try:
            import database as db
            from models import DefaultCredential

            # Use device-specific credentials if available
            username = device_info.get('username')
            password = device_info.get('password')

            # Fall back to default credentials if not on device
            if not username or not password:
                with db.get_db() as session:
                    credential = session.query(DefaultCredential).filter(
                        DefaultCredential.is_default == True
                    ).first()

                    if credential:
                        username = credential.username
                        password = credential.password

            if not username or not password:
                log.error("No credentials available")
                return None

            return {
                'device_type': device_info.get('device_type', 'cisco_ios'),
                'host': device_info.get('host'),
                'username': username,
                'password': password,
                'timeout': 60,
            }

        except ImportError:
            log.warning("Required modules not available")
        except Exception as e:
            log.error(f"Error building connection args: {e}")

        return None
