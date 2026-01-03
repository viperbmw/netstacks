# services/ai/app/routes/workflows.py
"""
Workflow API endpoints for retrieving AI processing workflow logs.

Provides detailed visibility into AI agent processing, including:
- Complete workflow timelines
- Individual step details with tool calls
- Token usage and cost tracking
- Drill-down capability for step analysis
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime, timedelta

from netstacks_core.db import get_session, WorkflowLog, WorkflowStep
from netstacks_core.auth import get_current_user

router = APIRouter()


@router.get("/", response_model=dict)
async def list_workflows(
    alert_id: Optional[str] = Query(None, description="Filter by alert ID"),
    incident_id: Optional[str] = Query(None, description="Filter by incident ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    outcome: Optional[str] = Query(None, description="Filter by outcome"),
    workflow_type: Optional[str] = Query(None, description="Filter by workflow type"),
    since_hours: Optional[int] = Query(None, description="Only show workflows from last N hours"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    user=Depends(get_current_user)
):
    """
    List workflow logs with optional filtering.

    Returns a summary of each workflow suitable for display in a table or list.
    """
    session = get_session()
    try:
        query = session.query(WorkflowLog)

        # Apply filters
        if alert_id:
            query = query.filter(WorkflowLog.alert_id == alert_id)
        if incident_id:
            query = query.filter(WorkflowLog.incident_id == incident_id)
        if status:
            query = query.filter(WorkflowLog.status == status)
        if outcome:
            query = query.filter(WorkflowLog.outcome == outcome)
        if workflow_type:
            query = query.filter(WorkflowLog.workflow_type == workflow_type)
        if since_hours:
            cutoff = datetime.utcnow() - timedelta(hours=since_hours)
            query = query.filter(WorkflowLog.started_at >= cutoff)

        # Get total count for pagination
        total = query.count()

        # Apply pagination and ordering
        workflows = query.order_by(WorkflowLog.started_at.desc()).offset(offset).limit(limit).all()

        return {
            "success": True,
            "total": total,
            "offset": offset,
            "limit": limit,
            "workflows": [
                {
                    "workflow_id": w.workflow_id,
                    "alert_id": w.alert_id,
                    "incident_id": w.incident_id,
                    "workflow_type": w.workflow_type,
                    "status": w.status,
                    "title": w.title,
                    "summary": w.summary,
                    "outcome": w.outcome,
                    "started_at": w.started_at.isoformat() if w.started_at else None,
                    "completed_at": w.completed_at.isoformat() if w.completed_at else None,
                    "duration_ms": w.duration_ms,
                    "total_tokens": w.total_tokens,
                    "total_input_tokens": w.total_input_tokens,
                    "total_output_tokens": w.total_output_tokens,
                    "estimated_cost_usd": round(w.estimated_cost_usd, 6) if w.estimated_cost_usd else 0,
                    "trigger_source": w.trigger_source,
                    "initiated_by": w.initiated_by,
                    "step_count": len(w.steps) if w.steps else 0,
                }
                for w in workflows
            ]
        }
    finally:
        session.close()


@router.get("/{workflow_id}", response_model=dict)
async def get_workflow(workflow_id: str, user=Depends(get_current_user)):
    """
    Get detailed workflow information including all steps.

    Returns the complete workflow with all steps, suitable for
    rendering a workflow timeline/diagram.
    """
    session = get_session()
    try:
        workflow = session.query(WorkflowLog).filter(
            WorkflowLog.workflow_id == workflow_id
        ).first()

        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        # Get all steps ordered by sequence
        steps = session.query(WorkflowStep).filter(
            WorkflowStep.workflow_id == workflow_id
        ).order_by(WorkflowStep.sequence).all()

        return {
            "success": True,
            "workflow": {
                "workflow_id": workflow.workflow_id,
                "alert_id": workflow.alert_id,
                "incident_id": workflow.incident_id,
                "workflow_type": workflow.workflow_type,
                "status": workflow.status,
                "title": workflow.title,
                "summary": workflow.summary,
                "outcome": workflow.outcome,
                "started_at": workflow.started_at.isoformat() if workflow.started_at else None,
                "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
                "duration_ms": workflow.duration_ms,
                "total_tokens": workflow.total_tokens,
                "total_input_tokens": workflow.total_input_tokens,
                "total_output_tokens": workflow.total_output_tokens,
                "estimated_cost_usd": round(workflow.estimated_cost_usd, 6) if workflow.estimated_cost_usd else 0,
                "trigger_source": workflow.trigger_source,
                "initiated_by": workflow.initiated_by,
                "primary_session_id": workflow.primary_session_id,
                "session_ids": workflow.session_ids or [],
                "context_data": workflow.context_data or {},
                "steps": [
                    {
                        "step_id": s.step_id,
                        "sequence": s.sequence,
                        "step_type": s.step_type,
                        "step_name": s.step_name,
                        "description": s.description,
                        "agent_type": s.agent_type,
                        "agent_name": s.agent_name,
                        "session_id": s.session_id,
                        "status": s.status,
                        "started_at": s.started_at.isoformat() if s.started_at else None,
                        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                        "duration_ms": s.duration_ms,
                        "input_tokens": s.input_tokens,
                        "output_tokens": s.output_tokens,
                        "total_tokens": s.total_tokens,
                        "model_used": s.model_used,
                        "tool_name": s.tool_name,
                        "risk_level": s.risk_level,
                        "error": s.error,
                        # Include input/output data for timeline preview
                        "has_input_data": bool(s.input_data),
                        "has_output_data": bool(s.output_data),
                        "has_tool_data": bool(s.tool_input or s.tool_output),
                        "has_reasoning": bool(s.reasoning),
                    }
                    for s in steps
                ]
            }
        }
    finally:
        session.close()


@router.get("/{workflow_id}/steps/{step_id}", response_model=dict)
async def get_workflow_step(
    workflow_id: str,
    step_id: str,
    user=Depends(get_current_user)
):
    """
    Get detailed information for a specific workflow step.

    Returns the complete step data including tool inputs/outputs,
    AI reasoning, and error details. This is for drill-down views.
    """
    session = get_session()
    try:
        step = session.query(WorkflowStep).filter(
            WorkflowStep.workflow_id == workflow_id,
            WorkflowStep.step_id == step_id
        ).first()

        if not step:
            raise HTTPException(status_code=404, detail="Step not found")

        return {
            "success": True,
            "step": {
                "step_id": step.step_id,
                "workflow_id": step.workflow_id,
                "sequence": step.sequence,
                "step_type": step.step_type,
                "step_name": step.step_name,
                "description": step.description,
                "agent_type": step.agent_type,
                "agent_name": step.agent_name,
                "session_id": step.session_id,
                "status": step.status,
                "started_at": step.started_at.isoformat() if step.started_at else None,
                "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                "duration_ms": step.duration_ms,
                "input_tokens": step.input_tokens,
                "output_tokens": step.output_tokens,
                "total_tokens": step.total_tokens,
                "model_used": step.model_used,
                # Full data for drill-down
                "input_data": step.input_data or {},
                "output_data": step.output_data or {},
                "tool_name": step.tool_name,
                "tool_input": step.tool_input or {},
                "tool_output": step.tool_output or {},
                "reasoning": step.reasoning,
                "error": step.error,
                "error_details": step.error_details or {},
                "risk_level": step.risk_level,
                "requires_approval": step.requires_approval,
                "approval_status": step.approval_status,
            }
        }
    finally:
        session.close()


@router.get("/by-alert/{alert_id}", response_model=dict)
async def get_workflows_by_alert(
    alert_id: str,
    user=Depends(get_current_user)
):
    """
    Get all workflows associated with a specific alert.

    Returns workflows in reverse chronological order, useful for
    showing the complete AI processing history for an alert.
    """
    session = get_session()
    try:
        workflows = session.query(WorkflowLog).filter(
            WorkflowLog.alert_id == alert_id
        ).order_by(WorkflowLog.started_at.desc()).all()

        result = []
        for w in workflows:
            # Get step count and summary
            step_count = session.query(WorkflowStep).filter(
                WorkflowStep.workflow_id == w.workflow_id
            ).count()

            result.append({
                "workflow_id": w.workflow_id,
                "workflow_type": w.workflow_type,
                "status": w.status,
                "title": w.title,
                "summary": w.summary,
                "outcome": w.outcome,
                "started_at": w.started_at.isoformat() if w.started_at else None,
                "completed_at": w.completed_at.isoformat() if w.completed_at else None,
                "duration_ms": w.duration_ms,
                "total_tokens": w.total_tokens,
                "estimated_cost_usd": round(w.estimated_cost_usd, 6) if w.estimated_cost_usd else 0,
                "step_count": step_count,
            })

        return {
            "success": True,
            "alert_id": alert_id,
            "workflows": result
        }
    finally:
        session.close()


@router.get("/stats/summary", response_model=dict)
async def get_workflow_stats(
    since_hours: int = Query(24, description="Stats for last N hours"),
    user=Depends(get_current_user)
):
    """
    Get summary statistics for AI workflow processing.

    Returns aggregated metrics including total workflows, token usage,
    cost, and outcome distributions.
    """
    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=since_hours)

        # Get all workflows in the time range
        workflows = session.query(WorkflowLog).filter(
            WorkflowLog.started_at >= cutoff
        ).all()

        # Calculate stats
        total_workflows = len(workflows)
        completed = sum(1 for w in workflows if w.status == "completed")
        failed = sum(1 for w in workflows if w.status == "failed")
        escalated = sum(1 for w in workflows if w.status == "escalated")
        in_progress = sum(1 for w in workflows if w.status in ("started", "in_progress"))

        # Token usage
        total_input_tokens = sum(w.total_input_tokens or 0 for w in workflows)
        total_output_tokens = sum(w.total_output_tokens or 0 for w in workflows)
        total_tokens = sum(w.total_tokens or 0 for w in workflows)
        total_cost = sum(w.estimated_cost_usd or 0 for w in workflows)

        # Outcome distribution
        outcomes = {}
        for w in workflows:
            outcome = w.outcome or "unknown"
            outcomes[outcome] = outcomes.get(outcome, 0) + 1

        # Average duration for completed workflows
        completed_workflows = [w for w in workflows if w.duration_ms]
        avg_duration_ms = (
            sum(w.duration_ms for w in completed_workflows) / len(completed_workflows)
            if completed_workflows else 0
        )

        return {
            "success": True,
            "period_hours": since_hours,
            "stats": {
                "total_workflows": total_workflows,
                "by_status": {
                    "completed": completed,
                    "failed": failed,
                    "escalated": escalated,
                    "in_progress": in_progress,
                },
                "by_outcome": outcomes,
                "tokens": {
                    "total_input": total_input_tokens,
                    "total_output": total_output_tokens,
                    "total": total_tokens,
                },
                "estimated_cost_usd": round(total_cost, 4),
                "avg_duration_ms": round(avg_duration_ms, 0) if avg_duration_ms else 0,
            }
        }
    finally:
        session.close()
