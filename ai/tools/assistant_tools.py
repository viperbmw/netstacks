"""
Assistant Tools

Tools for the NetStacks Assistant agent to help users navigate,
create MOPs, and create templates.
"""

import logging
import yaml
import uuid
from typing import Dict, Any, Optional
from jinja2 import Environment, BaseLoader, TemplateSyntaxError

from .base import BaseTool, ToolResult

log = logging.getLogger(__name__)


# Page definitions for navigation
NETSTACKS_PAGES = {
    'dashboard': {
        'url': '/',
        'name': 'Dashboard',
        'description': 'Overview of your network automation platform with stats, recent activity, and workflow visualization.',
        'keywords': ['home', 'overview', 'stats', 'activity', 'main']
    },
    'devices': {
        'url': '/devices',
        'name': 'Devices',
        'description': 'Manage network devices. Add, edit, delete devices. Test SSH connectivity. Sync from NetBox.',
        'keywords': ['device', 'router', 'switch', 'firewall', 'network', 'inventory', 'netbox']
    },
    'templates': {
        'url': '/templates',
        'name': 'Templates',
        'description': 'Create and manage Jinja2 configuration templates. Templates generate device configs with variables.',
        'keywords': ['template', 'jinja', 'config', 'configuration', 'j2']
    },
    'deploy': {
        'url': '/deploy',
        'name': 'Deploy',
        'description': 'Deploy configurations to devices using templates and service stacks.',
        'keywords': ['deploy', 'push', 'apply', 'configuration', 'stack']
    },
    'mops': {
        'url': '/mops',
        'name': 'MOPs',
        'description': 'Method of Procedures - create and execute multi-step automation workflows with approval gates.',
        'keywords': ['mop', 'procedure', 'workflow', 'automation', 'runbook', 'playbook']
    },
    'backups': {
        'url': '/backups',
        'name': 'Backups',
        'description': 'View device configuration backups. Compare versions, create snapshots, restore configs.',
        'keywords': ['backup', 'snapshot', 'restore', 'config', 'history', 'diff', 'compare']
    },
    'incidents': {
        'url': '/incidents',
        'name': 'Incidents',
        'description': 'Manage alerts and incidents. Track issues, update status, correlate related alerts.',
        'keywords': ['incident', 'alert', 'issue', 'problem', 'ticket', 'monitoring']
    },
    'agents': {
        'url': '/agents',
        'name': 'Agents',
        'description': 'Configure AI agents for automated operations. Start/stop agents, view stats, configure LLM.',
        'keywords': ['agent', 'ai', 'automation', 'bot', 'assistant']
    },
    'tools': {
        'url': '/tools',
        'name': 'Tools',
        'description': 'Manage tools available to AI agents. Built-in tools, custom tools, and MCP servers.',
        'keywords': ['tool', 'plugin', 'mcp', 'extension']
    },
    'knowledge': {
        'url': '/knowledge',
        'name': 'Knowledge',
        'description': 'Upload documentation for AI agents. Runbooks, procedures, and reference materials.',
        'keywords': ['knowledge', 'document', 'doc', 'runbook', 'wiki', 'reference']
    },
    'system': {
        'url': '/system',
        'name': 'System',
        'description': 'Monitor system health. Check service status, database, Redis, Celery workers.',
        'keywords': ['system', 'health', 'status', 'monitor', 'service']
    },
    'settings': {
        'url': '/settings',
        'name': 'Settings',
        'description': 'Configure AI assistant LLM provider, system settings, and user preferences.',
        'keywords': ['settings', 'config', 'preferences', 'llm', 'api']
    },
}

# MOP Step Types
MOP_STEP_TYPES = {
    'check_bgp': {
        'name': 'Check BGP',
        'description': 'Verify BGP neighbor status. Can check expected neighbor count.',
        'params': ['expect_neighbor_count']
    },
    'check_interfaces': {
        'name': 'Check Interfaces',
        'description': 'Verify interface status (up/down).',
        'params': ['interfaces', 'expected_state']
    },
    'check_routing': {
        'name': 'Check Routing',
        'description': 'Verify routing table entries.',
        'params': ['routes']
    },
    'get_config': {
        'name': 'Get Config',
        'description': 'Run show commands on devices. Optional TextFSM parsing.',
        'params': ['command', 'parse_with']
    },
    'set_config': {
        'name': 'Set Config',
        'description': 'Push configuration commands to devices.',
        'params': ['commands', 'template']
    },
    'validate_config': {
        'name': 'Validate Config',
        'description': 'Run command and validate output against expected patterns.',
        'params': ['command', 'expect_pattern', 'fail_pattern']
    },
    'api_call': {
        'name': 'API Call',
        'description': 'Make HTTP request to external API.',
        'params': ['url', 'method', 'headers', 'body']
    },
    'wait': {
        'name': 'Wait',
        'description': 'Pause execution for specified duration.',
        'params': ['seconds']
    },
    'manual_approval': {
        'name': 'Manual Approval',
        'description': 'Pause for human review and approval.',
        'params': ['message', 'approvers']
    },
    'webhook': {
        'name': 'Webhook',
        'description': 'Send webhook notification (Slack, Teams, etc.).',
        'params': ['url', 'message', 'channel']
    },
    'deploy_stack': {
        'name': 'Deploy Stack',
        'description': 'Deploy a service stack to devices.',
        'params': ['stack_id', 'variables']
    },
}


class NavigateTool(BaseTool):
    """Help users find the right page or feature."""

    name = "navigate"
    description = "Get information about NetStacks pages and features. Returns page URL, name, and description."
    category = "assistant"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What the user wants to do or find (e.g., 'manage devices', 'create template')"
                }
            },
            "required": ["query"]
        }

    def execute(self, query: str, **kwargs) -> ToolResult:
        query_lower = query.lower()
        matches = []

        for page_key, page_info in NETSTACKS_PAGES.items():
            score = 0
            # Check keywords
            for keyword in page_info['keywords']:
                if keyword in query_lower:
                    score += 10
            # Check name
            if page_info['name'].lower() in query_lower:
                score += 20
            # Check description
            desc_lower = page_info['description'].lower()
            for word in query_lower.split():
                if len(word) > 3 and word in desc_lower:
                    score += 5

            if score > 0:
                matches.append({
                    'score': score,
                    'page': page_key,
                    **page_info
                })

        # Sort by score
        matches.sort(key=lambda x: x['score'], reverse=True)

        if matches:
            best = matches[0]
            return ToolResult(success=True, data={
                'recommended': {
                    'name': best['name'],
                    'url': best['url'],
                    'description': best['description']
                },
                'alternatives': [
                    {'name': m['name'], 'url': m['url']}
                    for m in matches[1:3]  # Top 2 alternatives
                ]
            })

        # No match - return all pages
        return ToolResult(success=True, data={
            'message': 'No specific match found. Here are all available pages:',
            'pages': [
                {'name': p['name'], 'url': p['url'], 'description': p['description']}
                for p in NETSTACKS_PAGES.values()
            ]
        })


class ListStepTypesTool(BaseTool):
    """List available MOP step types."""

    name = "list_step_types"
    description = "Get list of available step types for MOPs with descriptions and parameters."
    category = "assistant"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={
            'step_types': MOP_STEP_TYPES
        })


class ListTemplatesTool(BaseTool):
    """List existing templates for reference."""

    name = "list_templates"
    description = "Get list of existing Jinja2 templates in the system."
    category = "assistant"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "template_type": {
                    "type": "string",
                    "description": "Filter by type: deploy, delete, or validation",
                    "enum": ["deploy", "delete", "validation"]
                }
            },
            "required": []
        }

    def execute(self, template_type: Optional[str] = None, **kwargs) -> ToolResult:
        try:
            import database as db
            templates = db.get_all_templates() or []

            if template_type:
                templates = [t for t in templates if t.get('type') == template_type]

            return ToolResult(success=True, data={
                'count': len(templates),
                'templates': [
                    {
                        'name': t.get('name'),
                        'type': t.get('type', 'deploy'),
                        'description': t.get('description', '')[:100] if t.get('description') else '',
                    }
                    for t in templates[:20]  # Limit to 20
                ]
            })
        except Exception as e:
            log.error(f"Error listing templates: {e}")
            return ToolResult(success=False, error=str(e))


class ValidateMOPTool(BaseTool):
    """Validate MOP YAML syntax before saving."""

    name = "validate_mop"
    description = "Validate MOP YAML syntax. Checks structure, step types, and control flow."
    category = "assistant"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "yaml_content": {
                    "type": "string",
                    "description": "The MOP YAML content to validate"
                }
            },
            "required": ["yaml_content"]
        }

    def execute(self, yaml_content: str, **kwargs) -> ToolResult:
        errors = []
        warnings = []

        # Parse YAML
        try:
            mop_data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            return ToolResult(success=False, error=f"Invalid YAML syntax: {e}")

        if not isinstance(mop_data, dict):
            return ToolResult(success=False, error="MOP must be a YAML object/dictionary")

        # Check required fields
        if 'name' not in mop_data:
            errors.append("Missing required field: 'name'")

        if 'steps' not in mop_data:
            errors.append("Missing required field: 'steps'")
        elif not isinstance(mop_data.get('steps'), list):
            errors.append("'steps' must be a list")
        else:
            steps = mop_data['steps']
            step_ids = set()

            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    errors.append(f"Step {i+1} must be an object")
                    continue

                if 'name' not in step:
                    errors.append(f"Step {i+1} missing 'name' field")

                if 'type' not in step:
                    errors.append(f"Step {i+1} missing 'type' field")
                elif step['type'] not in MOP_STEP_TYPES:
                    warnings.append(f"Step {i+1} has unknown type '{step['type']}' - may be a custom step type")

                # Collect step IDs for control flow validation
                if 'id' in step:
                    step_ids.add(step['id'])

            # Validate control flow references
            for i, step in enumerate(steps):
                if isinstance(step, dict):
                    for flow_key in ['on_success', 'on_failure']:
                        target = step.get(flow_key)
                        if target and target not in step_ids:
                            warnings.append(f"Step {i+1} references unknown step ID '{target}' in {flow_key}")

        # Check devices
        if 'devices' in mop_data:
            if not isinstance(mop_data['devices'], list):
                errors.append("'devices' must be a list")
            elif len(mop_data['devices']) == 0:
                warnings.append("No devices specified - MOP will need devices at execution time")

        if errors:
            return ToolResult(success=False, error="Validation failed", data={
                'errors': errors,
                'warnings': warnings
            })

        return ToolResult(success=True, data={
            'message': 'MOP YAML is valid',
            'warnings': warnings,
            'summary': {
                'name': mop_data.get('name'),
                'step_count': len(mop_data.get('steps', [])),
                'device_count': len(mop_data.get('devices', []))
            }
        })


class ValidateTemplateTool(BaseTool):
    """Validate Jinja2 template syntax before saving."""

    name = "validate_template"
    description = "Validate Jinja2 template syntax. Checks for syntax errors."
    category = "assistant"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The Jinja2 template content to validate"
                }
            },
            "required": ["content"]
        }

    def execute(self, content: str, **kwargs) -> ToolResult:
        try:
            env = Environment(loader=BaseLoader())
            env.parse(content)

            # Extract variables
            from jinja2 import meta
            ast = env.parse(content)
            variables = meta.find_undeclared_variables(ast)

            return ToolResult(success=True, data={
                'message': 'Template syntax is valid',
                'variables': list(variables)
            })
        except TemplateSyntaxError as e:
            return ToolResult(success=False, error=f"Jinja2 syntax error at line {e.lineno}: {e.message}")
        except Exception as e:
            return ToolResult(success=False, error=f"Validation error: {str(e)}")


class CreateMOPTool(BaseTool):
    """Create a new MOP in the database."""

    name = "create_mop"
    description = "Create and save a new MOP to the database. Validates YAML first."
    category = "assistant"
    risk_level = "medium"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name for the MOP"
                },
                "description": {
                    "type": "string",
                    "description": "Description of what this MOP does"
                },
                "yaml_content": {
                    "type": "string",
                    "description": "The complete MOP YAML content"
                }
            },
            "required": ["name", "yaml_content"]
        }

    def execute(self, name: str, yaml_content: str, description: str = "", **kwargs) -> ToolResult:
        # Validate first
        validate_tool = ValidateMOPTool()
        validation = validate_tool.execute(yaml_content=yaml_content)
        if not validation.success:
            return ToolResult(success=False, error=f"Validation failed: {validation.error}", data=validation.data)

        try:
            import database as db

            # Parse to extract devices
            mop_data = yaml.safe_load(yaml_content)
            devices = mop_data.get('devices', [])

            # Create MOP
            mop_id = str(uuid.uuid4())
            mop = db.create_mop(
                mop_id=mop_id,
                name=name,
                description=description or mop_data.get('description', ''),
                yaml_content=yaml_content,
                devices=devices
            )

            return ToolResult(success=True, data={
                'message': f'MOP "{name}" created successfully',
                'mop_id': mop_id,
                'url': f'/mops/{mop_id}'
            })
        except Exception as e:
            log.error(f"Error creating MOP: {e}")
            return ToolResult(success=False, error=f"Failed to create MOP: {str(e)}")


class CreateTemplateTool(BaseTool):
    """Create a new Jinja2 template in the database."""

    name = "create_template"
    description = "Create and save a new Jinja2 template to the database. Validates syntax first."
    category = "assistant"
    risk_level = "medium"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name for the template (without .j2 extension)"
                },
                "content": {
                    "type": "string",
                    "description": "The Jinja2 template content"
                },
                "template_type": {
                    "type": "string",
                    "description": "Template type: deploy, delete, or validation",
                    "enum": ["deploy", "delete", "validation"],
                    "default": "deploy"
                },
                "description": {
                    "type": "string",
                    "description": "Description of what this template does"
                }
            },
            "required": ["name", "content"]
        }

    def execute(self, name: str, content: str, template_type: str = "deploy", description: str = "", **kwargs) -> ToolResult:
        # Validate first
        validate_tool = ValidateTemplateTool()
        validation = validate_tool.execute(content=content)
        if not validation.success:
            return ToolResult(success=False, error=f"Validation failed: {validation.error}")

        try:
            import database as db

            # Remove .j2 extension if present
            if name.endswith('.j2'):
                name = name[:-3]

            # Create template
            template = db.create_template(
                name=name,
                content=content,
                template_type=template_type,
                description=description
            )

            return ToolResult(success=True, data={
                'message': f'Template "{name}" created successfully',
                'name': name,
                'type': template_type,
                'variables': validation.data.get('variables', []),
                'url': f'/templates/{name}'
            })
        except Exception as e:
            log.error(f"Error creating template: {e}")
            return ToolResult(success=False, error=f"Failed to create template: {str(e)}")


# Export all assistant tools
ASSISTANT_TOOLS = [
    NavigateTool,
    ListStepTypesTool,
    ListTemplatesTool,
    ValidateMOPTool,
    ValidateTemplateTool,
    CreateMOPTool,
    CreateTemplateTool,
]
