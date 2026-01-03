# services/ai/app/services/alert_processor.py
"""
Alert Processing Service

Automatically triggers AI triage when alerts are received.
Implements the full NOC automation workflow:
1. Alert received -> Triage agent investigates
2. Triage identifies issue type -> Handoff to specialist (BGP/OSPF/IS-IS/General)
3. Specialist investigates and either:
   - Resolves the issue (mark alert noise/resolved)
   - Creates incident for human review
   - Escalates to human operator
"""

import logging
import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from netstacks_core.db import (
    get_session,
    Alert as AlertModel,
    Incident as IncidentModel,
    Agent as AgentModel,
    AgentSession,
    AgentMessage,
)

from .agent_executor import (
    AgentExecutor,
    ExecutorContext,
    ExecutorConfig,
    create_agent_session,
    end_agent_session,
)
from .llm_client import EventType

log = logging.getLogger(__name__)


@dataclass
class TriageResult:
    """Result of alert triage."""
    alert_id: str
    status: str  # 'noise', 'resolved', 'incident_created', 'escalated', 'handoff', 'error'
    specialist_type: Optional[str] = None
    incident_id: Optional[str] = None
    summary: Optional[str] = None
    actions_taken: List[str] = None

    def __post_init__(self):
        if self.actions_taken is None:
            self.actions_taken = []


class AlertProcessor:
    """
    Processes alerts through AI triage workflow.

    Workflow:
    1. Alert received via webhook
    2. Triage agent analyzes the alert
    3. Based on findings:
       - If noise/duplicate -> Mark as noise, no incident
       - If simple fix -> Resolve and log
       - If protocol-specific -> Handoff to specialist
       - If complex -> Create incident and/or escalate
    """

    def __init__(self):
        self._processing_lock = asyncio.Lock()
        self._active_sessions: Dict[str, str] = {}  # alert_id -> session_id

    async def process_alert(
        self,
        alert_id: str,
        skip_ai: bool = False,
    ) -> TriageResult:
        """
        Process an alert through AI triage.

        Args:
            alert_id: The alert ID to process
            skip_ai: If True, skip AI processing entirely

        Returns:
            TriageResult with processing outcome
        """
        if skip_ai:
            return TriageResult(
                alert_id=alert_id,
                status="skipped",
                summary="AI processing skipped per request"
            )

        # Get alert details
        alert = self._get_alert(alert_id)
        if not alert:
            return TriageResult(
                alert_id=alert_id,
                status="error",
                summary=f"Alert {alert_id} not found"
            )

        # Mark alert as being processed
        self._update_alert_status(alert_id, "processing")

        try:
            # Run triage agent
            triage_result = await self._run_triage(alert)

            # If handoff requested, run specialist
            if triage_result.status == "handoff" and triage_result.specialist_type:
                specialist_result = await self._run_specialist(
                    alert,
                    triage_result.specialist_type,
                    triage_result.summary,
                )
                return specialist_result

            return triage_result

        except Exception as e:
            log.error(f"Alert processing error for {alert_id}: {e}", exc_info=True)
            self._update_alert_status(alert_id, "error")
            return TriageResult(
                alert_id=alert_id,
                status="error",
                summary=f"Processing error: {str(e)}"
            )

    async def _run_triage(self, alert: AlertModel) -> TriageResult:
        """Run the triage agent on an alert."""
        # Get triage agent from database
        triage_agent = self._get_agent_by_type("triage")
        if not triage_agent:
            log.error("Triage agent not found in database")
            return TriageResult(
                alert_id=alert.alert_id,
                status="error",
                summary="Triage agent not configured"
            )

        # Create agent session
        session_id = create_agent_session(
            agent_id=triage_agent.agent_id,
            username="system",
            trigger_type="alert",
            trigger_id=alert.alert_id,
            initial_prompt=f"Triage alert: {alert.title}",
        )

        self._active_sessions[alert.alert_id] = session_id

        # Build triage prompt
        prompt = self._build_triage_prompt(alert)

        # Create executor from agent config
        executor = AgentExecutor.from_agent_config(triage_agent.agent_id)
        context = ExecutorContext(
            session_id=session_id,
            agent_id=triage_agent.agent_id,
            username="system",
            trigger_type="alert",
            trigger_id=alert.alert_id,
        )

        # Run agent and collect results
        actions_taken = []
        handoff_info = None
        final_response = ""
        escalation_info = None

        try:
            async for event in executor.run(prompt, context):
                if event.type == EventType.TOOL_CALL:
                    actions_taken.append(f"Called tool: {event.tool_name}")

                elif event.type == EventType.TOOL_RESULT:
                    if event.tool_name == "handoff_to_specialist":
                        result = event.tool_result or {}
                        if result.get("success"):
                            handoff_info = result.get("handoff", {})

                    elif event.tool_name == "escalate_to_human":
                        result = event.tool_result or {}
                        if result.get("success"):
                            escalation_info = result.get("escalation", {})

                elif event.type == EventType.FINAL_RESPONSE:
                    final_response = event.content or ""

                elif event.type == EventType.ERROR:
                    log.error(f"Triage agent error: {event.content}")

                elif event.type == EventType.DONE:
                    if event.data and event.data.get("handoff"):
                        handoff_info = event.data["handoff"]
                    elif event.data and event.data.get("escalation"):
                        escalation_info = event.data["escalation"]

        except Exception as e:
            log.error(f"Error running triage agent: {e}", exc_info=True)
            end_agent_session(session_id, status="error")
            return TriageResult(
                alert_id=alert.alert_id,
                status="error",
                summary=f"Triage agent error: {str(e)}",
                actions_taken=actions_taken,
            )

        # Determine result based on agent actions
        if handoff_info:
            end_agent_session(
                session_id,
                status="completed",
                summary=f"Handed off to {handoff_info.get('target_agent')} specialist",
            )
            return TriageResult(
                alert_id=alert.alert_id,
                status="handoff",
                specialist_type=handoff_info.get("target_agent"),
                summary=handoff_info.get("summary", final_response),
                actions_taken=actions_taken,
            )

        if escalation_info:
            # Create incident for escalation
            incident_id = self._create_incident_from_alert(
                alert,
                f"Escalated: {escalation_info.get('reason', 'Requires human review')}",
                escalation_info.get("summary", final_response),
            )
            self._update_alert_status(alert.alert_id, "escalated", incident_id)
            end_agent_session(
                session_id,
                status="completed",
                summary="Escalated to human operator",
                resolution_status="escalated",
            )
            return TriageResult(
                alert_id=alert.alert_id,
                status="escalated",
                incident_id=incident_id,
                summary=escalation_info.get("summary", final_response),
                actions_taken=actions_taken,
            )

        # Check if triage determined this is noise
        if self._is_noise_determination(final_response):
            self._update_alert_status(alert.alert_id, "noise")
            end_agent_session(
                session_id,
                status="completed",
                summary="Determined to be noise/false positive",
                resolution_status="noise",
            )
            return TriageResult(
                alert_id=alert.alert_id,
                status="noise",
                summary=final_response,
                actions_taken=actions_taken,
            )

        # Default: mark as triaged but needs review
        end_agent_session(
            session_id,
            status="completed",
            summary=final_response[:500] if final_response else "Triage completed",
        )
        self._update_alert_status(alert.alert_id, "triaged")

        return TriageResult(
            alert_id=alert.alert_id,
            status="triaged",
            summary=final_response,
            actions_taken=actions_taken,
        )

    async def _run_specialist(
        self,
        alert: AlertModel,
        specialist_type: str,
        triage_summary: str,
    ) -> TriageResult:
        """Run a specialist agent after triage handoff."""
        # Get specialist agent
        specialist_agent = self._get_agent_by_type(specialist_type)
        if not specialist_agent:
            log.warning(f"Specialist agent '{specialist_type}' not found, using general")
            specialist_agent = self._get_agent_by_type("general")
            if not specialist_agent:
                return TriageResult(
                    alert_id=alert.alert_id,
                    status="error",
                    summary=f"No specialist agent available for {specialist_type}",
                )

        # Create specialist session
        session_id = create_agent_session(
            agent_id=specialist_agent.agent_id,
            username="system",
            trigger_type="alert",
            trigger_id=alert.alert_id,
            initial_prompt=f"Specialist investigation: {alert.title}",
        )

        self._active_sessions[alert.alert_id] = session_id

        # Build specialist prompt with triage context
        prompt = self._build_specialist_prompt(alert, triage_summary)

        # Create executor
        executor = AgentExecutor.from_agent_config(specialist_agent.agent_id)
        context = ExecutorContext(
            session_id=session_id,
            agent_id=specialist_agent.agent_id,
            username="system",
            trigger_type="alert",
            trigger_id=alert.alert_id,
        )

        # Run specialist
        actions_taken = []
        final_response = ""
        incident_created = False
        incident_id = None
        escalation_info = None

        try:
            async for event in executor.run(prompt, context):
                if event.type == EventType.TOOL_CALL:
                    actions_taken.append(f"Called tool: {event.tool_name}")

                elif event.type == EventType.TOOL_RESULT:
                    if event.tool_name == "create_incident":
                        result = event.tool_result or {}
                        if result.get("success"):
                            incident_created = True
                            incident_id = result.get("incident_id")

                    elif event.tool_name == "escalate_to_human":
                        result = event.tool_result or {}
                        if result.get("success"):
                            escalation_info = result.get("escalation", {})

                elif event.type == EventType.FINAL_RESPONSE:
                    final_response = event.content or ""

                elif event.type == EventType.ERROR:
                    log.error(f"Specialist agent error: {event.content}")

                elif event.type == EventType.DONE:
                    if event.data and event.data.get("escalation"):
                        escalation_info = event.data["escalation"]

        except Exception as e:
            log.error(f"Error running specialist agent: {e}", exc_info=True)
            end_agent_session(session_id, status="error")
            return TriageResult(
                alert_id=alert.alert_id,
                status="error",
                specialist_type=specialist_type,
                summary=f"Specialist agent error: {str(e)}",
                actions_taken=actions_taken,
            )

        # Determine outcome
        if escalation_info:
            if not incident_id:
                incident_id = self._create_incident_from_alert(
                    alert,
                    f"Escalated by {specialist_type} specialist",
                    escalation_info.get("summary", final_response),
                )
            self._update_alert_status(alert.alert_id, "escalated", incident_id)
            end_agent_session(
                session_id,
                status="completed",
                summary="Escalated to human operator",
                resolution_status="escalated",
            )
            return TriageResult(
                alert_id=alert.alert_id,
                status="escalated",
                specialist_type=specialist_type,
                incident_id=incident_id,
                summary=final_response,
                actions_taken=actions_taken,
            )

        if incident_created and incident_id:
            self._update_alert_status(alert.alert_id, "incident_created", incident_id)
            end_agent_session(
                session_id,
                status="completed",
                summary=f"Created incident {incident_id}",
                resolution_status="incident_created",
            )
            return TriageResult(
                alert_id=alert.alert_id,
                status="incident_created",
                specialist_type=specialist_type,
                incident_id=incident_id,
                summary=final_response,
                actions_taken=actions_taken,
            )

        # Check if resolved
        if self._is_resolved_determination(final_response):
            self._update_alert_status(alert.alert_id, "resolved")
            end_agent_session(
                session_id,
                status="completed",
                summary="Issue resolved by AI",
                resolution_status="resolved",
            )
            return TriageResult(
                alert_id=alert.alert_id,
                status="resolved",
                specialist_type=specialist_type,
                summary=final_response,
                actions_taken=actions_taken,
            )

        # Default: investigated but needs review
        end_agent_session(
            session_id,
            status="completed",
            summary=final_response[:500] if final_response else "Investigation completed",
        )
        self._update_alert_status(alert.alert_id, "investigated")

        return TriageResult(
            alert_id=alert.alert_id,
            status="investigated",
            specialist_type=specialist_type,
            summary=final_response,
            actions_taken=actions_taken,
        )

    def _build_triage_prompt(self, alert: AlertModel) -> str:
        """Build the initial prompt for triage agent."""
        prompt = f"""A new alert has been received and needs triage:

## Alert Details
- **Title**: {alert.title}
- **Severity**: {alert.severity}
- **Source**: {alert.source or 'unknown'}
- **Device**: {alert.device_name or 'N/A'}
- **Alert Type**: {alert.alert_type or 'N/A'}
- **Time**: {alert.created_at.isoformat() if alert.created_at else 'N/A'}

## Description
{alert.description or 'No description provided'}

"""
        if alert.raw_data:
            import json
            raw_str = json.dumps(alert.raw_data, indent=2, default=str)
            if len(raw_str) < 2000:
                prompt += f"""## Raw Alert Data
```json
{raw_str}
```

"""

        prompt += """## Your Task
1. Analyze this alert to understand what happened
2. If a device is specified, gather diagnostic information using show commands
3. Check for similar alerts or known issues in the knowledge base
4. Determine if this is:
   - **Noise/False Positive**: Alert can be dismissed, no action needed
   - **Simple Issue**: You can identify and explain the issue
   - **Protocol-Specific**: Hand off to specialist (BGP, OSPF, IS-IS, or General)
   - **Complex Issue**: Create an incident for human review
   - **Critical**: Escalate immediately to human operator

Based on your findings, take the appropriate action (dismiss, handoff, create incident, or escalate).
"""
        return prompt

    def _build_specialist_prompt(self, alert: AlertModel, triage_summary: str) -> str:
        """Build prompt for specialist agent after handoff."""
        prompt = f"""You've received a handoff from the Triage agent for a specialized investigation.

## Alert Details
- **Title**: {alert.title}
- **Severity**: {alert.severity}
- **Source**: {alert.source or 'unknown'}
- **Device**: {alert.device_name or 'N/A'}
- **Alert Type**: {alert.alert_type or 'N/A'}

## Triage Summary
{triage_summary}

## Description
{alert.description or 'No description provided'}

## Your Task
1. Perform deep investigation using your protocol expertise
2. Run relevant show commands to gather detailed diagnostics
3. Identify the root cause if possible
4. Take one of the following actions:
   - If the issue is noise or already resolved: Explain why and recommend dismissal
   - If you identify a fix: Explain the fix (note: config changes require approval)
   - If complex or requires human judgment: Create an incident
   - If critical and requires immediate human attention: Escalate

Provide a detailed analysis and recommendation.
"""
        return prompt

    def _is_noise_determination(self, response: str) -> bool:
        """Check if the agent determined the alert is noise."""
        response_lower = response.lower()
        noise_indicators = [
            "false positive",
            "no action needed",
            "no action required",
            "can be safely ignored",
            "this is noise",
            "not a real issue",
            "expected behavior",
            "normal operation",
            "duplicate alert",
        ]
        return any(indicator in response_lower for indicator in noise_indicators)

    def _is_resolved_determination(self, response: str) -> bool:
        """Check if the agent determined the issue is resolved."""
        response_lower = response.lower()
        resolved_indicators = [
            "issue has been resolved",
            "problem is resolved",
            "is now resolved",
            "has cleared",
            "has recovered",
            "back to normal",
            "operating normally",
            "no longer occurring",
        ]
        return any(indicator in response_lower for indicator in resolved_indicators)

    def _get_alert(self, alert_id: str) -> Optional[AlertModel]:
        """Get alert from database."""
        session = get_session()
        try:
            return session.query(AlertModel).filter(
                AlertModel.alert_id == alert_id
            ).first()
        finally:
            session.close()

    def _get_agent_by_type(self, agent_type: str) -> Optional[AgentModel]:
        """Get agent by type from database."""
        session = get_session()
        try:
            return session.query(AgentModel).filter(
                AgentModel.agent_type == agent_type,
                AgentModel.status.in_(["idle", "available"]),
            ).first()
        finally:
            session.close()

    def _update_alert_status(
        self,
        alert_id: str,
        status: str,
        incident_id: Optional[str] = None,
    ):
        """Update alert status in database."""
        session = get_session()
        try:
            alert = session.query(AlertModel).filter(
                AlertModel.alert_id == alert_id
            ).first()
            if alert:
                alert.status = status
                if incident_id:
                    alert.incident_id = incident_id
                if status in ("acknowledged", "resolved", "noise"):
                    alert.acknowledged_at = datetime.utcnow()
                if status == "resolved":
                    alert.resolved_at = datetime.utcnow()
                session.commit()
        except Exception as e:
            log.error(f"Failed to update alert status: {e}")
            session.rollback()
        finally:
            session.close()

    def _create_incident_from_alert(
        self,
        alert: AlertModel,
        title: str,
        description: str,
    ) -> str:
        """Create incident from alert and return incident_id."""
        incident_id = str(uuid.uuid4())
        session = get_session()
        try:
            incident = IncidentModel(
                incident_id=incident_id,
                title=title,
                description=description,
                severity=alert.severity,
                status="open",
                source="ai_triage",
                affected_devices=[alert.device_name] if alert.device_name else [],
            )
            session.add(incident)
            session.commit()
            log.info(f"Created incident {incident_id} from alert {alert.alert_id}")
            return incident_id
        except Exception as e:
            log.error(f"Failed to create incident: {e}")
            session.rollback()
            return ""
        finally:
            session.close()


# Singleton instance
_processor: Optional[AlertProcessor] = None


def get_alert_processor() -> AlertProcessor:
    """Get or create the alert processor singleton."""
    global _processor
    if _processor is None:
        _processor = AlertProcessor()
    return _processor


async def process_alert_async(alert_id: str, skip_ai: bool = False) -> TriageResult:
    """
    Convenience function to process an alert asynchronously.

    This is the main entry point for alert processing, called from webhook routes.
    """
    processor = get_alert_processor()
    return await processor.process_alert(alert_id, skip_ai=skip_ai)
