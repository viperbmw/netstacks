"""
Step Types Introspection
Automatically discovers step types from mop_engine.py
"""
import re
import ast
import inspect
from mop_engine import MOPEngine

def get_step_types():
    """
    Introspect MOPEngine to find all execute_* methods and their parameters
    """
    step_types = []

    # Get the MOPEngine class
    engine_class = MOPEngine

    # Find all execute_* methods
    for name, method in inspect.getmembers(engine_class, predicate=inspect.isfunction):
        if name.startswith('execute_') and name != 'execute_step':
            step_type_name = name.replace('execute_', '')

            # Get docstring to extract parameters
            docstring = inspect.getdoc(method) or ""

            # Parse parameters from YAML example in docstring
            params = extract_params_from_docstring(docstring)

            # Get description
            description = docstring.split('\n')[0] if docstring else f"Execute {step_type_name}"

            step_types.append({
                'id': step_type_name,
                'name': step_type_name.replace('_', ' ').title(),
                'description': description,
                'parameters': params,
                'icon': get_icon_for_type(step_type_name)
            })

    return sorted(step_types, key=lambda x: x['name'])


def extract_params_from_docstring(docstring):
    """Extract parameter definitions from YAML example in docstring"""
    params = []

    # Look for YAML example section
    yaml_match = re.search(r'YAML example:(.*?)(?=\n\s*"""|\Z)', docstring, re.DOTALL)
    if not yaml_match:
        return params

    yaml_section = yaml_match.group(1)

    # Extract parameter lines (lines with key: value that aren't common mop keys)
    skip_keys = {'name', 'type', 'id', 'on_success', 'on_failure', 'devices'}

    for line in yaml_section.split('\n'):
        # Match yaml key: value pairs
        match = re.match(r'\s+(\w+):\s*(.+)', line)
        if match:
            key, value = match.groups()
            if key not in skip_keys:
                # Determine parameter type from value
                param_type = infer_type_from_value(value.strip())

                params.append({
                    'name': key,
                    'type': param_type,
                    'required': False,  # Could be enhanced to detect required vs optional
                    'description': f"{key.replace('_', ' ').title()}"
                })

    return params


def infer_type_from_value(value):
    """Infer parameter type from example value"""
    value_lower = value.lower()

    if value_lower in ('true', 'false'):
        return 'boolean'
    elif value.isdigit():
        return 'number'
    elif value.startswith('"') or value.startswith("'"):
        return 'string'
    elif value.startswith('['):
        return 'array'
    elif value.startswith('{'):
        return 'object'
    else:
        return 'string'


def get_icon_for_type(step_type):
    """Get FontAwesome icon for step type"""
    icon_map = {
        'check_bgp': 'network-wired',
        'check_ping': 'wifi',
        'check_interfaces': 'ethernet',
        'run_command': 'terminal',
        'deploy_stack': 'upload',
        'email': 'envelope',
        'webhook': 'globe',
        'custom_python': 'code',
        'wait': 'clock'
    }
    return icon_map.get(step_type, 'cog')
