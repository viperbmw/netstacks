# /home/cwdavis/netstacks/tasks/utils.py
"""
Task Utilities for NetStacks
Parsing helpers (TextFSM, TTP, Jinja2)
"""
import os
import logging
from typing import Dict, List, Any, Optional

log = logging.getLogger(__name__)


def get_textfsm_template_path(device_type: str, command: str) -> Optional[str]:
    """
    Find TextFSM template for a given device type and command.
    """
    try:
        from ntc_templates.parse import _get_template_dir
        template_dir = _get_template_dir()

        # Normalize command for template lookup
        command_normalized = command.strip().lower().replace(' ', '_')
        template_name = f"{device_type}_{command_normalized}.textfsm"
        template_path = os.path.join(template_dir, template_name)

        if os.path.exists(template_path):
            return template_path
    except ImportError:
        log.debug("ntc_templates not installed")
    except Exception as e:
        log.debug(f"Error finding TextFSM template: {e}")

    return None


def parse_with_textfsm(output: str, device_type: str, command: str) -> Optional[List[Dict]]:
    """
    Parse command output using TextFSM templates.
    """
    try:
        from ntc_templates.parse import parse_output
        return parse_output(platform=device_type, command=command, data=output)
    except ImportError:
        log.debug("ntc_templates not installed")
    except Exception as e:
        log.debug(f"TextFSM parsing failed: {e}")
    return None


def parse_with_ttp(output: str, template: str) -> Optional[List[Dict]]:
    """
    Parse command output using TTP template.
    """
    try:
        from ttp import ttp
        parser = ttp(data=output, template=template)
        parser.parse()
        return parser.result()
    except ImportError:
        log.debug("TTP not installed")
    except Exception as e:
        log.debug(f"TTP parsing failed: {e}")
    return None


def render_jinja2_template(template_str: str, variables: Dict) -> str:
    """
    Render a Jinja2 template string with variables.
    """
    from jinja2 import Template, Environment, BaseLoader
    env = Environment(loader=BaseLoader())
    template = env.from_string(template_str)
    return template.render(**variables)


def get_device_queue(device_name: str) -> str:
    """
    Get the queue name for a specific device.
    Used for device-level serial execution.
    """
    return f"device:{device_name}"
