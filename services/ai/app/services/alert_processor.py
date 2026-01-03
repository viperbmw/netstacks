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

All processing is logged to WorkflowLog and WorkflowStep for full transparency.
"""

import logging
import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from netstacks_core.db import (
    get_session,
    Alert as AlertModel,
    Incident as IncidentModel,
    Agent as AgentModel,
    AgentSession,
    AgentMessage,
    WorkflowLog,
    WorkflowStep,
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

# Token cost estimates per model (per 1M tokens)
TOKEN_COSTS = {
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "default": {"input": 3.00, "output": 15.00},
}


@dataclass
class TokenUsage:
    """Token usage tracking for LLM calls."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    estimated_cost_usd: float = 0.0

    def add(self, input_tokens: int, output_tokens: int, model: str = ""):
        """Add token usage from an LLM call."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens
        if model:
            self.model = model
        self._update_cost()

    def _update_cost(self):
        """Calculate estimated cost based on token usage."""
        costs = TOKEN_COSTS.get(self.model, TOKEN_COSTS["default"])
        self.estimated_cost_usd = (
            (self.input_tokens / 1_000_000) * costs["input"] +
            (self.output_tokens / 1_000_000) * costs["output"]
        )


@dataclass
class TriageResult:
    """Result of alert triage."""
    alert_id: str
    status: str  # 'noise', 'resolved', 'incident_created', 'escalated', 'handoff', 'error'
    specialist_type: Optional[str] = None
    incident_id: Optional[str] = None
    workflow_id: Optional[str] = None
    summary: Optional[str] = None
    actions_taken: List[str] = field(default_factory=list)
    token_usage: Optional[TokenUsage] = None

    def __post_init__(self):
        if self.token_usage is None:
            self.token_usage = TokenUsage()


class WorkflowLogger:
    """
    Manages workflow logging for AI processing.
    Creates and updates WorkflowLog and WorkflowStep records.
    """

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.current_sequence = 0
        self.token_usage = TokenUsage()

    def create_workflow(
        self,
        alert_id: str,
        workflow_type: str = "alert_triage",
        title: str = "",
        trigger_source: str = "webhook",
    ) -> str:
        """Create a new workflow log entry."""
        session = get_session()
        try:
            workflow = WorkflowLog(
                workflow_id=self.workflow_id,
                alert_id=alert_id,
                workflow_type=workflow_type,
                status="started",
                title=title or f"Alert Triage: {alert_id[:8]}",
                trigger_source=trigger_source,
                initiated_by="system",
                started_at=datetime.utcnow(),
            )
            session.add(workflow)
            session.commit()
            log.debug(f"Created workflow {self.workflow_id} for alert {alert_id}")
            return self.workflow_id
        except Exception as e:
            log.error(f"Failed to create workflow: {e}")
            session.rollback()
            return ""
        finally:
            session.close()

    def add_step(
        self,
        step_type: str,
        step_name: str,
        description: str = "",
        agent_type: str = None,
        agent_name: str = None,
        session_id: str = None,
        input_data: dict = None,
        status: str = "running",
    ) -> str:
        """Add a new step to the workflow."""
        self.current_sequence += 1
        step_id = str(uuid.uuid4())

        session = get_session()
        try:
            step = WorkflowStep(
                step_id=step_id,
                workflow_id=self.workflow_id,
                sequence=self.current_sequence,
                step_type=step_type,
                step_name=step_name,
                description=description,
                agent_type=agent_type,
                agent_name=agent_name,
                session_id=session_id,
                status=status,
                started_at=datetime.utcnow(),
                input_data=input_data or {},
            )
            session.add(step)
            session.commit()
            log.debug(f"Added workflow step {step_id}: {step_name}")
            return step_id
        except Exception as e:
            log.error(f"Failed to add workflow step: {e}")
            session.rollback()
            return ""
        finally:
            session.close()

    def update_step(
        self,
        step_id: str,
        status: str = None,
        output_data: dict = None,
        tool_name: str = None,
        tool_input: dict = None,
        tool_output: dict = None,
        reasoning: str = None,
        error: str = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model_used: str = None,
        risk_level: str = None,
        session_id: str = None,
    ):
        """Update an existing workflow step."""
        db_session = get_session()
        try:
            step = db_session.query(WorkflowStep).filter(
                WorkflowStep.step_id == step_id
            ).first()
            if not step:
                log.warning(f"Step {step_id} not found")
                return

            if status:
                step.status = status
                if status in ("completed", "failed", "skipped"):
                    step.completed_at = datetime.utcnow()
                    if step.started_at:
                        step.duration_ms = int(
                            (step.completed_at - step.started_at).total_seconds() * 1000
                        )

            if output_data is not None:
                step.output_data = output_data
            if tool_name:
                step.tool_name = tool_name
            if tool_input is not None:
                step.tool_input = tool_input
            if tool_output is not None:
                step.tool_output = tool_output
            if reasoning:
                step.reasoning = reasoning
            if error:
                step.error = error
                step.status = "failed"
            if input_tokens or output_tokens:
                step.input_tokens = input_tokens
                step.output_tokens = output_tokens
                step.total_tokens = input_tokens + output_tokens
                # Track totals
                self.token_usage.add(input_tokens, output_tokens, model_used or "")
            if model_used:
                step.model_used = model_used
            if risk_level:
                step.risk_level = risk_level
            if session_id:
                step.session_id = session_id

            db_session.commit()
        except Exception as e:
            log.error(f"Failed to update workflow step: {e}")
            db_session.rollback()
        finally:
            db_session.close()

    def add_tool_call_step(
        self,
        tool_name: str,
        tool_input: dict,
        agent_type: str = None,
        session_id: str = None,
    ) -> str:
        """Add a tool call step."""
        step_id = self.add_step(
            step_type="tool_call",
            step_name=f"Tool: {tool_name}",
            description=f"Executing tool {tool_name}",
            agent_type=agent_type,
            session_id=session_id,
            input_data={"tool_name": tool_name},
            status="running",
        )
        self.update_step(step_id, tool_name=tool_name, tool_input=tool_input)
        return step_id

    def complete_tool_call_step(
        self,
        step_id: str,
        tool_output: dict,
        duration_ms: int = None,
        error: str = None,
    ):
        """Complete a tool call step with results."""
        status = "failed" if error else "completed"
        self.update_step(
            step_id,
            status=status,
            tool_output=tool_output,
            error=error,
        )

    def update_workflow(
        self,
        status: str = None,
        summary: str = None,
        outcome: str = None,
        incident_id: str = None,
        session_ids: list = None,
        primary_session_id: str = None,
    ):
        """Update the main workflow record."""
        session = get_session()
        try:
            workflow = session.query(WorkflowLog).filter(
                WorkflowLog.workflow_id == self.workflow_id
            ).first()
            if not workflow:
                log.warning(f"Workflow {self.workflow_id} not found")
                return

            if status:
                workflow.status = status
                if status in ("completed", "failed", "escalated"):
                    workflow.completed_at = datetime.utcnow()
                    if workflow.started_at:
                        workflow.duration_ms = int(
                            (workflow.completed_at - workflow.started_at).total_seconds() * 1000
                        )

            if summary:
                workflow.summary = summary
            if outcome:
                workflow.outcome = outcome
            if incident_id:
                workflow.incident_id = incident_id
            if session_ids:
                workflow.session_ids = session_ids
            if primary_session_id:
                workflow.primary_session_id = primary_session_id

            # Update token totals
            workflow.total_input_tokens = self.token_usage.input_tokens
            workflow.total_output_tokens = self.token_usage.output_tokens
            workflow.total_tokens = self.token_usage.total_tokens
            workflow.estimated_cost_usd = self.token_usage.estimated_cost_usd

            session.commit()
        except Exception as e:
            log.error(f"Failed to update workflow: {e}")
            session.rollback()
        finally:
            session.close()


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

    All processing is logged to WorkflowLog for full transparency and audit trail.
    """

    def __init__(self):
        self._processing_lock = asyncio.Lock()
        self._active_sessions: Dict[str, str] = {}  # alert_id -> session_id
        self._active_workflows: Dict[str, WorkflowLogger] = {}  # alert_id -> workflow logger

    async def process_alert(
        self,
        alert_id: str,
        skip_ai: bool = False,
        trigger_source: str = "webhook",
    ) -> TriageResult:
        """
        Process an alert through AI triage.

        Args:
            alert_id: The alert ID to process
            skip_ai: If True, skip AI processing entirely
            trigger_source: Source of the alert trigger

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

        # Create workflow logger
        workflow_id = str(uuid.uuid4())
        workflow_logger = WorkflowLogger(workflow_id)
        self._active_workflows[alert_id] = workflow_logger

        # Initialize workflow
        workflow_logger.create_workflow(
            alert_id=alert_id,
            workflow_type="alert_triage",
            title=f"AI Triage: {alert.title[:100]}",
            trigger_source=trigger_source,
        )

        # Log intake step
        intake_step = workflow_logger.add_step(
            step_type="intake",
            step_name="Alert Received",
            description=f"Alert '{alert.title}' received from {alert.source}",
            input_data={
                "alert_id": alert_id,
                "title": alert.title,
                "severity": alert.severity,
                "device": alert.device_name,
                "source": alert.source,
            },
            status="completed",
        )
        workflow_logger.update_step(intake_step, status="completed")

        # Mark alert as being processed
        self._update_alert_status(alert_id, "processing")
        workflow_logger.update_workflow(status="in_progress")

        try:
            # Run triage agent with workflow logger
            triage_result = await self._run_triage(alert, workflow_logger)

            # If handoff requested, run specialist
            if triage_result.status == "handoff" and triage_result.specialist_type:
                # Log handoff step
                handoff_step = workflow_logger.add_step(
                    step_type="handoff",
                    step_name=f"Handoff to {triage_result.specialist_type.upper()} Specialist",
                    description=f"Triage agent handing off to {triage_result.specialist_type} specialist",
                    input_data={"target_specialist": triage_result.specialist_type},
                )
                workflow_logger.update_step(handoff_step, status="completed")

                specialist_result = await self._run_specialist(
                    alert,
                    triage_result.specialist_type,
                    triage_result.summary,
                    workflow_logger,
                )
                specialist_result.workflow_id = workflow_id
                specialist_result.token_usage = workflow_logger.token_usage
                return specialist_result

            triage_result.workflow_id = workflow_id
            triage_result.token_usage = workflow_logger.token_usage

            # Finalize workflow
            workflow_logger.update_workflow(
                status="completed",
                summary=triage_result.summary[:500] if triage_result.summary else "Triage completed",
                outcome=triage_result.status,
            )

            return triage_result

        except Exception as e:
            log.error(f"Alert processing error for {alert_id}: {e}", exc_info=True)
            self._update_alert_status(alert_id, "error")

            # Log error to workflow
            workflow_logger.add_step(
                step_type="error",
                step_name="Processing Error",
                description=str(e),
                status="failed",
            )
            workflow_logger.update_workflow(
                status="failed",
                summary=f"Processing failed: {str(e)}",
                outcome="failed",
            )

            return TriageResult(
                alert_id=alert_id,
                status="error",
                workflow_id=workflow_id,
                summary=f"Processing error: {str(e)}",
                token_usage=workflow_logger.token_usage,
            )
        finally:
            # Clean up
            if alert_id in self._active_workflows:
                del self._active_workflows[alert_id]

    async def _run_triage(
        self,
        alert: AlertModel,
        workflow_logger: WorkflowLogger,
    ) -> TriageResult:
        """Run the triage agent on an alert with full workflow logging."""
        # Get triage agent from database
        triage_agent = self._get_agent_by_type("triage")
        if not triage_agent:
            log.error("Triage agent not found in database")
            workflow_logger.add_step(
                step_type="error",
                step_name="Agent Not Found",
                description="Triage agent not configured in database",
                status="failed",
            )
            return TriageResult(
                alert_id=alert.alert_id,
                status="error",
                summary="Triage agent not configured"
            )

        # Log triage start step
        triage_step = workflow_logger.add_step(
            step_type="triage",
            step_name="Triage Agent Analysis",
            description=f"Triage agent analyzing alert: {alert.title}",
            agent_type="triage",
            agent_name=triage_agent.name,
            input_data={
                "alert_title": alert.title,
                "severity": alert.severity,
                "device": alert.device_name,
            },
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
        workflow_logger.update_step(triage_step, session_id=session_id)
        workflow_logger.update_workflow(
            primary_session_id=session_id,
            session_ids=[session_id],
        )

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
        current_tool_step = None
        model_used = triage_agent.llm_model or "claude-sonnet-4-20250514"

        try:
            async for event in executor.run(prompt, context):
                if event.type == EventType.TOOL_CALL:
                    actions_taken.append(f"Called tool: {event.tool_name}")
                    # Log tool call step
                    current_tool_step = workflow_logger.add_tool_call_step(
                        tool_name=event.tool_name,
                        tool_input=event.tool_input or {},
                        agent_type="triage",
                        session_id=session_id,
                    )

                elif event.type == EventType.TOOL_RESULT:
                    # Complete tool call step
                    if current_tool_step:
                        workflow_logger.complete_tool_call_step(
                            current_tool_step,
                            tool_output=event.tool_result or {},
                        )
                        current_tool_step = None

                    if event.tool_name == "handoff_to_specialist":
                        result = event.tool_result or {}
                        if result.get("success"):
                            handoff_info = result.get("handoff", {})

                    elif event.tool_name == "escalate_to_human":
                        result = event.tool_result or {}
                        if result.get("success"):
                            escalation_info = result.get("escalation", {})

                elif event.type == EventType.THINKING:
                    # Log AI reasoning
                    workflow_logger.add_step(
                        step_type="analysis",
                        step_name="AI Reasoning",
                        description=event.content[:200] if event.content else "Analyzing...",
                        agent_type="triage",
                        session_id=session_id,
                        status="completed",
                    )

                elif event.type == EventType.TOKEN_USAGE:
                    # Track token usage
                    if event.data:
                        input_tokens = event.data.get("input_tokens", 0)
                        output_tokens = event.data.get("output_tokens", 0)
                        workflow_logger.update_step(
                            triage_step,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            model_used=model_used,
                        )

                elif event.type == EventType.FINAL_RESPONSE:
                    final_response = event.content or ""

                elif event.type == EventType.ERROR:
                    log.error(f"Triage agent error: {event.content}")
                    workflow_logger.add_step(
                        step_type="error",
                        step_name="Agent Error",
                        description=event.content or "Unknown error",
                        agent_type="triage",
                        session_id=session_id,
                        status="failed",
                    )

                elif event.type == EventType.DONE:
                    if event.data and event.data.get("handoff"):
                        handoff_info = event.data["handoff"]
                    elif event.data and event.data.get("escalation"):
                        escalation_info = event.data["escalation"]

        except Exception as e:
            log.error(f"Error running triage agent: {e}", exc_info=True)
            workflow_logger.update_step(triage_step, status="failed", error=str(e))
            end_agent_session(session_id, status="error")
            return TriageResult(
                alert_id=alert.alert_id,
                status="error",
                summary=f"Triage agent error: {str(e)}",
                actions_taken=actions_taken,
            )

        # Complete triage step
        workflow_logger.update_step(
            triage_step,
            status="completed",
            output_data={
                "response": final_response[:1000] if final_response else "",
                "actions_taken": actions_taken,
                "handoff": handoff_info,
                "escalation": escalation_info,
            },
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
            # Log escalation decision
            workflow_logger.add_step(
                step_type="escalation",
                step_name="Escalated to Human",
                description=escalation_info.get("reason", "Requires human review"),
                agent_type="triage",
                session_id=session_id,
                status="completed",
            )

            # Create incident for escalation
            incident_id = self._create_incident_from_alert(
                alert,
                f"Escalated: {escalation_info.get('reason', 'Requires human review')}",
                escalation_info.get("summary", final_response),
            )
            self._update_alert_status(alert.alert_id, "escalated", incident_id)
            workflow_logger.update_workflow(incident_id=incident_id)

            end_agent_session(
                session_id,
                status="completed",
                summary="Escalated to human operator",
                resolution_status="escalated",
            )

            workflow_logger.update_workflow(
                status="escalated",
                summary=f"Escalated: {escalation_info.get('reason', 'Human review required')}",
                outcome="escalated",
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
            # Log decision
            workflow_logger.add_step(
                step_type="decision",
                step_name="Classified as Noise",
                description="Alert determined to be noise or false positive",
                agent_type="triage",
                session_id=session_id,
                status="completed",
            )

            self._update_alert_status(alert.alert_id, "noise")
            end_agent_session(
                session_id,
                status="completed",
                summary="Determined to be noise/false positive",
                resolution_status="noise",
            )

            workflow_logger.update_workflow(
                status="completed",
                summary="Alert classified as noise - no action required",
                outcome="noise",
            )

            return TriageResult(
                alert_id=alert.alert_id,
                status="noise",
                summary=final_response,
                actions_taken=actions_taken,
            )

        # Default: mark as triaged but needs review
        workflow_logger.add_step(
            step_type="decision",
            step_name="Triage Complete",
            description="Alert triaged, may require human review",
            agent_type="triage",
            session_id=session_id,
            status="completed",
        )

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
        workflow_logger: WorkflowLogger,
    ) -> TriageResult:
        """Run a specialist agent after triage handoff with full workflow logging."""
        # Get specialist agent
        specialist_agent = self._get_agent_by_type(specialist_type)
        if not specialist_agent:
            log.warning(f"Specialist agent '{specialist_type}' not found, using general")
            specialist_agent = self._get_agent_by_type("general")
            if not specialist_agent:
                workflow_logger.add_step(
                    step_type="error",
                    step_name="Specialist Not Found",
                    description=f"No specialist agent available for {specialist_type}",
                    status="failed",
                )
                return TriageResult(
                    alert_id=alert.alert_id,
                    status="error",
                    summary=f"No specialist agent available for {specialist_type}",
                )

        # Log specialist investigation step
        specialist_step = workflow_logger.add_step(
            step_type="investigation",
            step_name=f"{specialist_type.upper()} Specialist Investigation",
            description=f"{specialist_type.upper()} specialist investigating: {alert.title}",
            agent_type=specialist_type,
            agent_name=specialist_agent.name,
            input_data={
                "alert_title": alert.title,
                "triage_summary": triage_summary[:500],
            },
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
        workflow_logger.update_step(specialist_step, session_id=session_id)

        # Update workflow with new session
        current_sessions = workflow_logger.token_usage  # Get existing session list
        workflow_logger.update_workflow(
            session_ids=[session_id],  # Will be appended
        )

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
        current_tool_step = None
        model_used = specialist_agent.llm_model or "claude-sonnet-4-20250514"

        try:
            async for event in executor.run(prompt, context):
                if event.type == EventType.TOOL_CALL:
                    actions_taken.append(f"Called tool: {event.tool_name}")
                    # Log tool call step
                    current_tool_step = workflow_logger.add_tool_call_step(
                        tool_name=event.tool_name,
                        tool_input=event.tool_input or {},
                        agent_type=specialist_type,
                        session_id=session_id,
                    )

                elif event.type == EventType.TOOL_RESULT:
                    # Complete tool call step
                    if current_tool_step:
                        workflow_logger.complete_tool_call_step(
                            current_tool_step,
                            tool_output=event.tool_result or {},
                        )
                        current_tool_step = None

                    if event.tool_name == "create_incident":
                        result = event.tool_result or {}
                        if result.get("success"):
                            incident_created = True
                            incident_id = result.get("incident_id")

                    elif event.tool_name == "escalate_to_human":
                        result = event.tool_result or {}
                        if result.get("success"):
                            escalation_info = result.get("escalation", {})

                elif event.type == EventType.THINKING:
                    # Log AI reasoning
                    workflow_logger.add_step(
                        step_type="analysis",
                        step_name="Specialist Reasoning",
                        description=event.content[:200] if event.content else "Analyzing...",
                        agent_type=specialist_type,
                        session_id=session_id,
                        status="completed",
                    )

                elif event.type == EventType.TOKEN_USAGE:
                    # Track token usage
                    if event.data:
                        input_tokens = event.data.get("input_tokens", 0)
                        output_tokens = event.data.get("output_tokens", 0)
                        workflow_logger.update_step(
                            specialist_step,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            model_used=model_used,
                        )

                elif event.type == EventType.FINAL_RESPONSE:
                    final_response = event.content or ""

                elif event.type == EventType.ERROR:
                    log.error(f"Specialist agent error: {event.content}")
                    workflow_logger.add_step(
                        step_type="error",
                        step_name="Specialist Error",
                        description=event.content or "Unknown error",
                        agent_type=specialist_type,
                        session_id=session_id,
                        status="failed",
                    )

                elif event.type == EventType.DONE:
                    if event.data and event.data.get("escalation"):
                        escalation_info = event.data["escalation"]

        except Exception as e:
            log.error(f"Error running specialist agent: {e}", exc_info=True)
            workflow_logger.update_step(specialist_step, status="failed", error=str(e))
            end_agent_session(session_id, status="error")
            return TriageResult(
                alert_id=alert.alert_id,
                status="error",
                specialist_type=specialist_type,
                summary=f"Specialist agent error: {str(e)}",
                actions_taken=actions_taken,
            )

        # Complete specialist step
        workflow_logger.update_step(
            specialist_step,
            status="completed",
            output_data={
                "response": final_response[:1000] if final_response else "",
                "actions_taken": actions_taken,
                "incident_created": incident_created,
                "escalation": escalation_info,
            },
        )

        # Determine outcome
        if escalation_info:
            # Log escalation
            workflow_logger.add_step(
                step_type="escalation",
                step_name="Escalated by Specialist",
                description=escalation_info.get("reason", "Requires human review"),
                agent_type=specialist_type,
                session_id=session_id,
                status="completed",
            )

            if not incident_id:
                incident_id = self._create_incident_from_alert(
                    alert,
                    f"Escalated by {specialist_type} specialist",
                    escalation_info.get("summary", final_response),
                )
            self._update_alert_status(alert.alert_id, "escalated", incident_id)
            workflow_logger.update_workflow(incident_id=incident_id)

            end_agent_session(
                session_id,
                status="completed",
                summary="Escalated to human operator",
                resolution_status="escalated",
            )

            workflow_logger.update_workflow(
                status="escalated",
                summary=f"Escalated by {specialist_type}: {escalation_info.get('reason', 'Human review required')}",
                outcome="escalated",
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
            # Log incident creation
            workflow_logger.add_step(
                step_type="decision",
                step_name="Incident Created",
                description=f"Created incident {incident_id}",
                agent_type=specialist_type,
                session_id=session_id,
                status="completed",
            )

            self._update_alert_status(alert.alert_id, "incident_created", incident_id)
            workflow_logger.update_workflow(incident_id=incident_id)

            end_agent_session(
                session_id,
                status="completed",
                summary=f"Created incident {incident_id}",
                resolution_status="incident_created",
            )

            workflow_logger.update_workflow(
                status="completed",
                summary=f"Incident created: {incident_id}",
                outcome="incident_created",
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
            # Log resolution
            workflow_logger.add_step(
                step_type="resolution",
                step_name="Issue Resolved",
                description="Issue resolved by AI specialist",
                agent_type=specialist_type,
                session_id=session_id,
                status="completed",
            )

            self._update_alert_status(alert.alert_id, "resolved")
            end_agent_session(
                session_id,
                status="completed",
                summary="Issue resolved by AI",
                resolution_status="resolved",
            )

            workflow_logger.update_workflow(
                status="completed",
                summary="Issue resolved by AI specialist",
                outcome="resolved",
            )

            return TriageResult(
                alert_id=alert.alert_id,
                status="resolved",
                specialist_type=specialist_type,
                summary=final_response,
                actions_taken=actions_taken,
            )

        # Default: investigated but needs review
        workflow_logger.add_step(
            step_type="decision",
            step_name="Investigation Complete",
            description="Investigation completed, may require human review",
            agent_type=specialist_type,
            session_id=session_id,
            status="completed",
        )

        end_agent_session(
            session_id,
            status="completed",
            summary=final_response[:500] if final_response else "Investigation completed",
        )
        self._update_alert_status(alert.alert_id, "investigated")

        workflow_logger.update_workflow(
            status="completed",
            summary=final_response[:500] if final_response else "Investigation completed",
            outcome="monitoring",
        )

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
