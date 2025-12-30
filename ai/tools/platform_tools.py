# /home/cwdavis/netstacks/ai/tools/platform_tools.py
"""
Internal Platform Tools for Agent Self-Awareness
These tools allow agents to query NetStacks platform state.
"""
import logging
from typing import Dict, Any, Optional

from .base import BaseTool, ToolResult

log = logging.getLogger(__name__)


class PlatformStatusTool(BaseTool):
    """Get current platform status and statistics."""

    name = "platform_status"
    description = "Get NetStacks platform status including device counts, incident counts, and system health."
    category = "platform"
    is_internal = True

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    def execute(self, **kwargs) -> ToolResult:
        from services.platform_stats_service import get_platform_stats
        stats = get_platform_stats()
        return ToolResult(success=True, data=stats)


class StackInfoTool(BaseTool):
    """Get information about service stacks."""

    name = "stack_info"
    description = "Get details about service stacks - deployed services, their states, and associated templates."
    category = "platform"
    is_internal = True

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "stack_name": {
                    "type": "string",
                    "description": "Optional name of specific stack to query"
                }
            },
            "required": []
        }

    def execute(self, stack_name: Optional[str] = None, **kwargs) -> ToolResult:
        import database as db

        if stack_name:
            stack = db.get_service_stack_by_name(stack_name)
            if not stack:
                return ToolResult(success=False, error=f'Stack {stack_name} not found')
            return ToolResult(success=True, data={'stack': stack})

        stacks = db.get_all_service_stacks() or []
        return ToolResult(success=True, data={
            'total': len(stacks),
            'stacks': [
                {
                    'name': s.get('stack_name'),
                    'state': s.get('state'),
                    'service_count': len(s.get('services', [])),
                }
                for s in stacks
            ]
        })


class TemplateInfoTool(BaseTool):
    """Get information about configuration templates."""

    name = "template_info"
    description = "Get details about configuration templates - types, variables, and usage."
    category = "platform"
    is_internal = True

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "template_name": {
                    "type": "string",
                    "description": "Optional name of specific template to query"
                }
            },
            "required": []
        }

    def execute(self, template_name: Optional[str] = None, **kwargs) -> ToolResult:
        import database as db

        if template_name:
            template = db.get_template_by_name(template_name)
            if not template:
                return ToolResult(success=False, error=f'Template {template_name} not found')
            return ToolResult(success=True, data={'template': template})

        templates = db.get_all_templates() or []
        return ToolResult(success=True, data={
            'total': len(templates),
            'templates': [
                {
                    'name': t.get('template_name'),
                    'type': t.get('template_type'),
                    'description': t.get('description', '')[:100],
                }
                for t in templates
            ]
        })


class IncidentStatusTool(BaseTool):
    """Get current incident status."""

    name = "incident_status"
    description = "Get current open incidents, their severity, and status."
    category = "platform"
    is_internal = True

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by incident status (default: open)",
                    "enum": ["open", "acknowledged", "resolved", "closed"]
                }
            },
            "required": []
        }

    def execute(self, status: str = 'open', **kwargs) -> ToolResult:
        import database as db

        incidents = db.get_incidents_by_status(status) or []
        return ToolResult(success=True, data={
            'status_filter': status,
            'count': len(incidents),
            'incidents': [
                {
                    'id': i.get('incident_id'),
                    'title': i.get('title'),
                    'severity': i.get('severity'),
                    'status': i.get('status'),
                    'created_at': i.get('created_at'),
                }
                for i in incidents[:20]  # Limit to 20
            ]
        })


class SystemHealthTool(BaseTool):
    """Check system component health."""

    name = "system_health"
    description = "Check health of system components: database, Redis, Celery workers."
    category = "platform"
    is_internal = True

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    def execute(self, **kwargs) -> ToolResult:
        import os
        results = {'components': {}}

        # Check Redis
        try:
            import redis
            redis_url = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
            r = redis.from_url(redis_url)
            results['components']['redis'] = {'status': 'ok' if r.ping() else 'error'}
        except Exception as e:
            results['components']['redis'] = {'status': 'error', 'error': str(e)}

        # Check database
        try:
            import database as db
            db.get_all_devices()  # Simple query test
            results['components']['database'] = {'status': 'ok'}
        except Exception as e:
            results['components']['database'] = {'status': 'error', 'error': str(e)}

        # Check Celery workers
        try:
            from tasks import celery_app
            inspector = celery_app.control.inspect()
            active = inspector.active() or {}
            results['components']['celery'] = {
                'status': 'ok' if active else 'warning',
                'worker_count': len(active),
            }
        except Exception as e:
            results['components']['celery'] = {'status': 'error', 'error': str(e)}

        # Overall status
        statuses = [c.get('status') for c in results['components'].values()]
        if all(s == 'ok' for s in statuses):
            results['overall'] = 'healthy'
        elif 'error' in statuses:
            results['overall'] = 'degraded'
        else:
            results['overall'] = 'warning'

        return ToolResult(success=True, data=results)


class PlatformConceptsTool(BaseTool):
    """Explain NetStacks platform concepts."""

    name = "platform_concepts"
    description = "Get explanations of NetStacks concepts: templates, stacks, MOPs, agents, etc."
    category = "platform"
    is_internal = True

    CONCEPTS = {
        'template': 'A Jinja2-based configuration template for network devices. Templates have variables that get filled in during rendering.',
        'stack': 'A Service Stack groups multiple templates together for coordinated deployment. Stacks define the order of template application.',
        'stack_template': 'Links a template to a stack with specific variable values and deployment order.',
        'mop': 'Method of Procedure - a multi-step automation workflow with approval gates and rollback capabilities.',
        'agent': 'An AI agent that can perform automated tasks, handle alerts, or assist with operations.',
        'incident': 'A tracked issue that may have correlated alerts and require remediation.',
        'backup': 'A stored copy of a device configuration, used for compliance and rollback.',
        'snapshot': 'A point-in-time backup of multiple devices, often scheduled.',
    }

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "concept": {
                    "type": "string",
                    "description": "Specific concept to explain",
                    "enum": list(self.CONCEPTS.keys())
                }
            },
            "required": []
        }

    def execute(self, concept: Optional[str] = None, **kwargs) -> ToolResult:
        if concept:
            concept_lower = concept.lower()
            if concept_lower in self.CONCEPTS:
                return ToolResult(success=True, data={
                    'concept': concept,
                    'explanation': self.CONCEPTS[concept_lower]
                })
            return ToolResult(success=False, error=f'Unknown concept: {concept}', data={
                'available': list(self.CONCEPTS.keys())
            })

        return ToolResult(success=True, data={'concepts': self.CONCEPTS})


# Export all platform tools
PLATFORM_TOOLS = [
    PlatformStatusTool,
    StackInfoTool,
    TemplateInfoTool,
    IncidentStatusTool,
    SystemHealthTool,
    PlatformConceptsTool,
]
