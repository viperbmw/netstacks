"""
Workflow Tools

Tools for agent orchestration, handoffs, escalation, and MOP execution.
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

from .base import BaseTool, ToolResult

log = logging.getLogger(__name__)


class HandoffTool(BaseTool):
    """
    Hand off conversation to a specialist agent.

    Used by triage agent to route issues to BGP, OSPF, ISIS, or other specialists.
    """

    name = "handoff"
    description = """Hand off the current conversation to a specialist agent.
Use this when you've identified the issue type and a specialist agent can handle it better.
Include a summary of findings so far so the specialist doesn't repeat diagnostic steps."""
    category = "workflow"
    risk_level = "low"
    requires_approval = False

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target_agent": {
                    "type": "string",
                    "description": "Type of agent to hand off to (e.g., 'bgp', 'ospf', 'isis', 'layer2')",
                    "enum": ["bgp", "ospf", "isis", "layer2", "security", "custom"]
                },
                "summary": {
                    "type": "string",
                    "description": "Summary of the issue and diagnostic steps already taken"
                },
                "context": {
                    "type": "object",
                    "description": "Additional context data to pass to the specialist (device names, gathered info, etc.)"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Priority level for the handoff",
                    "default": "medium"
                }
            },
            "required": ["target_agent", "summary"]
        }

    def execute(
        self,
        target_agent: str,
        summary: str,
        context: Optional[Dict] = None,
        priority: str = "medium"
    ) -> ToolResult:
        """Execute handoff to specialist agent"""
        try:
            session_id = self.context.get('session_id')
            if not session_id:
                return ToolResult(
                    success=False,
                    error="No session context for handoff"
                )

            # Create handoff record
            handoff_data = {
                'handoff_id': str(uuid.uuid4()),
                'source_session': session_id,
                'target_agent': target_agent,
                'summary': summary,
                'context': context or {},
                'priority': priority,
                'timestamp': datetime.utcnow().isoformat()
            }

            # The actual handoff will be processed by the agent engine
            # This just signals the intent and provides the data
            return ToolResult(
                success=True,
                data={
                    'handoff': handoff_data,
                    'message': f'Handing off to {target_agent} specialist agent'
                }
            )

        except Exception as e:
            log.error(f"Handoff error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )


class EscalateTool(BaseTool):
    """
    Escalate issue to human operators.

    Used when the agent cannot resolve the issue or needs human decision.
    """

    name = "escalate"
    description = """Escalate the current issue to human operators.
Use this when:
- The issue requires human judgment or approval beyond your capabilities
- You've exhausted automated troubleshooting options
- The issue is too complex or risky for automated resolution
- A critical system is affected and human oversight is required"""
    category = "workflow"
    risk_level = "low"
    requires_approval = False

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Reason for escalation"
                },
                "summary": {
                    "type": "string",
                    "description": "Summary of the issue and troubleshooting steps taken"
                },
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "error", "critical"],
                    "description": "Severity level of the escalation",
                    "default": "warning"
                },
                "recommended_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of recommended actions for the human operator"
                },
                "affected_devices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of affected device names"
                }
            },
            "required": ["reason", "summary"]
        }

    def execute(
        self,
        reason: str,
        summary: str,
        severity: str = "warning",
        recommended_actions: Optional[List[str]] = None,
        affected_devices: Optional[List[str]] = None
    ) -> ToolResult:
        """Escalate to human operators"""
        try:
            session_id = self.context.get('session_id')

            escalation_data = {
                'escalation_id': str(uuid.uuid4()),
                'session_id': session_id,
                'reason': reason,
                'summary': summary,
                'severity': severity,
                'recommended_actions': recommended_actions or [],
                'affected_devices': affected_devices or [],
                'timestamp': datetime.utcnow().isoformat()
            }

            # Store escalation in database
            self._create_escalation_record(escalation_data)

            return ToolResult(
                success=True,
                data={
                    'escalation': escalation_data,
                    'message': 'Issue escalated to human operators'
                }
            )

        except Exception as e:
            log.error(f"Escalation error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )

    def _create_escalation_record(self, data: Dict) -> None:
        """Create escalation record in database"""
        try:
            import database as db
            from models import Incident

            with db.get_db() as session:
                incident = Incident(
                    incident_id=data['escalation_id'],
                    title=f"Escalation: {data['reason'][:100]}",
                    description=data['summary'],
                    severity=data['severity'],
                    status='escalated',
                    source='agent_escalation',
                    metadata={
                        'recommended_actions': data['recommended_actions'],
                        'affected_devices': data['affected_devices'],
                        'session_id': data['session_id']
                    }
                )
                session.add(incident)

        except Exception as e:
            log.error(f"Error creating escalation record: {e}")


class CreateIncidentTool(BaseTool):
    """
    Create a new incident for tracking.

    Creates a formal incident record for significant issues.
    """

    name = "create_incident"
    description = """Create a new incident for tracking a network issue.
Use this when you've identified a significant problem that needs formal tracking and resolution."""
    category = "workflow"
    risk_level = "low"
    requires_approval = False

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Brief title describing the incident"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the incident"
                },
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "error", "critical"],
                    "description": "Severity level",
                    "default": "warning"
                },
                "affected_devices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of affected device names"
                },
                "category": {
                    "type": "string",
                    "description": "Category of incident (e.g., 'bgp', 'ospf', 'connectivity')"
                }
            },
            "required": ["title", "description"]
        }

    def execute(
        self,
        title: str,
        description: str,
        severity: str = "warning",
        affected_devices: Optional[List[str]] = None,
        category: Optional[str] = None
    ) -> ToolResult:
        """Create incident record"""
        try:
            import database as db
            from models import Incident

            incident_id = str(uuid.uuid4())

            with db.get_db() as session:
                incident = Incident(
                    incident_id=incident_id,
                    title=title,
                    description=description,
                    severity=severity,
                    status='open',
                    source='agent',
                    metadata={
                        'affected_devices': affected_devices or [],
                        'category': category,
                        'session_id': self.context.get('session_id')
                    }
                )
                session.add(incident)

            return ToolResult(
                success=True,
                data={
                    'incident_id': incident_id,
                    'title': title,
                    'severity': severity,
                    'message': 'Incident created successfully'
                }
            )

        except Exception as e:
            log.error(f"Create incident error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )


class ExecuteMOPTool(BaseTool):
    """
    Execute a Method of Procedure (MOP).

    HIGH RISK - Requires approval before execution.
    Runs predefined procedures for network changes.
    """

    name = "execute_mop"
    description = """Execute a predefined Method of Procedure (MOP).
MOPs are step-by-step procedures for network changes with pre/post checks.
WARNING: This executes changes on network devices - requires approval."""
    category = "workflow"
    risk_level = "high"
    requires_approval = True

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mop_name": {
                    "type": "string",
                    "description": "Name of the MOP to execute"
                },
                "target_devices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of device names to execute the MOP on"
                },
                "variables": {
                    "type": "object",
                    "description": "Variables to pass to the MOP"
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, show what would be done without executing",
                    "default": False
                }
            },
            "required": ["mop_name", "target_devices"]
        }

    def execute(
        self,
        mop_name: str,
        target_devices: List[str],
        variables: Optional[Dict] = None,
        dry_run: bool = False
    ) -> ToolResult:
        """Execute MOP on target devices"""
        try:
            import database as db
            from models import MOP

            # Get MOP from database
            with db.get_db() as session:
                mop = session.query(MOP).filter(MOP.name == mop_name).first()
                if not mop:
                    return ToolResult(
                        success=False,
                        error=f"MOP not found: {mop_name}"
                    )

                mop_data = {
                    'id': mop.id,
                    'name': mop.name,
                    'description': mop.description,
                    'steps': mop.steps,
                    'pre_checks': mop.pre_checks,
                    'post_checks': mop.post_checks
                }

            # For dry run, just return what would be done
            if dry_run:
                return ToolResult(
                    success=True,
                    data={
                        'mop': mop_data,
                        'target_devices': target_devices,
                        'variables': variables,
                        'dry_run': True,
                        'message': 'Dry run - showing MOP details without execution'
                    }
                )

            # Check if we have approval
            approval_id = self.context.get('approval_id')
            if not approval_id:
                approval_id = str(uuid.uuid4())
                return ToolResult(
                    success=True,
                    requires_approval=True,
                    approval_id=approval_id,
                    risk_level="high",
                    data={
                        'mop': mop_data,
                        'target_devices': target_devices,
                        'variables': variables,
                        'message': 'MOP execution requires approval'
                    }
                )

            # Execute MOP via Celery task
            # This would call the actual MOP execution engine
            from workers.tasks.device_tasks import run_commands

            execution_results = []
            for device in target_devices:
                # This is a simplified example - real MOP execution is more complex
                device_results = {
                    'device': device,
                    'steps': [],
                    'status': 'pending'
                }
                execution_results.append(device_results)

            return ToolResult(
                success=True,
                data={
                    'mop': mop_name,
                    'execution_id': str(uuid.uuid4()),
                    'target_devices': target_devices,
                    'results': execution_results,
                    'message': 'MOP execution initiated'
                }
            )

        except Exception as e:
            log.error(f"Execute MOP error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )


class UpdateIncidentTool(BaseTool):
    """
    Update an existing incident.

    Used to add notes, change status, or update incident details.
    """

    name = "update_incident"
    description = """Update an existing incident with new information.
Use this to add resolution notes, change status, or update severity."""
    category = "workflow"
    risk_level = "low"
    requires_approval = False

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "incident_id": {
                    "type": "string",
                    "description": "ID of the incident to update"
                },
                "status": {
                    "type": "string",
                    "enum": ["open", "investigating", "identified", "resolved", "closed"],
                    "description": "New status for the incident"
                },
                "note": {
                    "type": "string",
                    "description": "Note to add to the incident timeline"
                },
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "error", "critical"],
                    "description": "Updated severity level"
                },
                "resolution": {
                    "type": "string",
                    "description": "Resolution notes (typically when closing)"
                }
            },
            "required": ["incident_id"]
        }

    def execute(
        self,
        incident_id: str,
        status: Optional[str] = None,
        note: Optional[str] = None,
        severity: Optional[str] = None,
        resolution: Optional[str] = None
    ) -> ToolResult:
        """Update incident"""
        try:
            import database as db
            from models import Incident

            with db.get_db() as session:
                incident = session.query(Incident).filter(
                    Incident.incident_id == incident_id
                ).first()

                if not incident:
                    return ToolResult(
                        success=False,
                        error=f"Incident not found: {incident_id}"
                    )

                updates = {}
                if status:
                    incident.status = status
                    updates['status'] = status
                if severity:
                    incident.severity = severity
                    updates['severity'] = severity
                if resolution:
                    incident.resolution = resolution
                    updates['resolution'] = resolution

                # Add note to timeline in metadata
                if note:
                    metadata = incident.metadata or {}
                    timeline = metadata.get('timeline', [])
                    timeline.append({
                        'timestamp': datetime.utcnow().isoformat(),
                        'note': note,
                        'agent_session': self.context.get('session_id')
                    })
                    metadata['timeline'] = timeline
                    incident.metadata = metadata
                    updates['note_added'] = True

                incident.updated_at = datetime.utcnow()

                return ToolResult(
                    success=True,
                    data={
                        'incident_id': incident_id,
                        'updates': updates,
                        'message': 'Incident updated successfully'
                    }
                )

        except Exception as e:
            log.error(f"Update incident error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )
