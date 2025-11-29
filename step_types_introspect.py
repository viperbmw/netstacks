"""
Step Types Introspection
Returns step types from database (built-in and custom)
"""
import db

def get_step_types():
    """
    Get all step types from database (built-in and custom)
    Returns them in the format expected by the visual builder
    """
    step_types = []

    # Get all step types from database
    db_step_types = db.get_all_step_types()

    for step_type in db_step_types:
        # Convert database format to visual builder format
        params = []
        if step_type.get('parameters_schema'):
            schema = step_type['parameters_schema']
            for param_name, param_def in schema.items():
                params.append({
                    'name': param_name,
                    'type': param_def.get('type', 'string'),
                    'required': param_def.get('required', False),
                    'description': param_def.get('description', param_name.replace('_', ' ').title()),
                    'default': param_def.get('default')
                })

        step_types.append({
            'id': step_type['step_type_id'],
            'name': step_type['name'],
            'description': step_type['description'] or '',
            'category': step_type.get('category', 'General'),
            'parameters': params,
            'icon': step_type.get('icon', 'cog'),
            'is_custom': step_type.get('is_custom', 0) == 1
        })

    return sorted(step_types, key=lambda x: (x.get('is_custom', False), x['name']))


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
