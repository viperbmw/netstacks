# services/ai/app/routes/alerts.py
import asyncio
import logging
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from netstacks_core.db import get_session, Alert as AlertModel
from netstacks_core.auth import get_current_user

from app.services.alert_processor import process_alert_async, TriageResult

log = logging.getLogger(__name__)

router = APIRouter()


class AlertCreate(BaseModel):
    title: str
    severity: str = "warning"
    description: Optional[str] = None
    source: Optional[str] = None
    device_name: Optional[str] = None
    alert_type: Optional[str] = None
    raw_data: Optional[dict] = None
    skip_ai: bool = False


class AlertResponse(BaseModel):
    alert_id: str
    title: str
    severity: str
    status: str
    source: Optional[str] = None
    device_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/", response_model=dict)
async def list_alerts(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    user=Depends(get_current_user)
):
    """List alerts with optional filters."""
    session = get_session()
    try:
        query = session.query(AlertModel)
        if status:
            query = query.filter(AlertModel.status == status)
        if severity:
            query = query.filter(AlertModel.severity == severity)
        if source:
            query = query.filter(AlertModel.source == source)

        alerts = query.order_by(AlertModel.created_at.desc()).limit(limit).all()
        return {
            "success": True,
            "alerts": [
                {
                    "alert_id": a.alert_id,
                    "title": a.title,
                    "severity": a.severity,
                    "status": a.status,
                    "source": a.source,
                    "device_name": a.device_name,
                    "alert_type": a.alert_type,
                    "description": a.description,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in alerts
            ]
        }
    finally:
        session.close()


async def _trigger_ai_processing(alert_id: str, skip_ai: bool):
    """Background task to trigger AI processing for an alert."""
    if skip_ai:
        log.info(f"Skipping AI processing for alert {alert_id} per request")
        return

    try:
        log.info(f"Starting AI triage for alert {alert_id}")
        result = await process_alert_async(alert_id, skip_ai=False)
        log.info(f"AI triage completed for alert {alert_id}: status={result.status}")
    except Exception as e:
        log.error(f"AI processing failed for alert {alert_id}: {e}", exc_info=True)


@router.post("/", response_model=dict)
async def create_alert(alert: AlertCreate, background_tasks: BackgroundTasks):
    """Create alert (webhook endpoint - no auth required).

    Automatically triggers AI triage in the background unless skip_ai=True.
    """
    session = get_session()
    try:
        import uuid
        alert_id = str(uuid.uuid4())
        new_alert = AlertModel(
            alert_id=alert_id,
            title=alert.title,
            severity=alert.severity,
            description=alert.description,
            source=alert.source or "manual",
            device_name=alert.device_name,
            alert_type=alert.alert_type,
            raw_data=alert.raw_data or {},
            status="new",
        )
        session.add(new_alert)
        session.commit()

        # Trigger AI processing in background
        if not alert.skip_ai:
            background_tasks.add_task(_trigger_ai_processing, alert_id, alert.skip_ai)

        return {
            "status": "received",
            "alert_id": alert_id,
            "ai_processing": not alert.skip_ai
        }
    finally:
        session.close()


@router.get("/{alert_id}", response_model=dict)
async def get_alert(alert_id: str, user=Depends(get_current_user)):
    """Get alert by ID."""
    session = get_session()
    try:
        alert = session.query(AlertModel).filter(AlertModel.alert_id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {
            "success": True,
            "alert": {
                "alert_id": alert.alert_id,
                "title": alert.title,
                "severity": alert.severity,
                "status": alert.status,
                "description": alert.description,
                "source": alert.source,
                "device_name": alert.device_name,
                "alert_type": alert.alert_type,
                "raw_data": alert.raw_data,
                "incident_id": alert.incident_id,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
                "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            }
        }
    finally:
        session.close()


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, user=Depends(get_current_user)):
    """Acknowledge an alert."""
    session = get_session()
    try:
        alert = session.query(AlertModel).filter(AlertModel.alert_id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        alert.status = "acknowledged"
        session.commit()
        return {"success": True, "message": "Alert acknowledged"}
    finally:
        session.close()


@router.post("/{alert_id}/process")
async def process_alert(alert_id: str, background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    """Trigger AI processing for alert."""
    session = get_session()
    try:
        alert = session.query(AlertModel).filter(AlertModel.alert_id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        # Trigger AI processing in background
        background_tasks.add_task(_trigger_ai_processing, alert_id, False)

        return {
            "success": True,
            "message": "AI processing triggered",
            "alert_id": alert_id
        }
    finally:
        session.close()


@router.get("/{alert_id}/sessions")
async def get_alert_sessions(alert_id: str, user=Depends(get_current_user)):
    """Get AI sessions for alert."""
    from netstacks_core.db import AgentSession

    session = get_session()
    try:
        # Get sessions triggered by this alert
        sessions = session.query(AgentSession).filter(
            AgentSession.trigger_type == "alert",
            AgentSession.trigger_id == alert_id,
        ).order_by(AgentSession.created_at.desc()).all()

        return {
            "success": True,
            "alert_id": alert_id,
            "sessions": [
                {
                    "session_id": s.session_id,
                    "agent_id": s.agent_id,
                    "status": s.status,
                    "initial_prompt": s.initial_prompt,
                    "summary": s.summary,
                    "resolution_status": s.resolution_status,
                    "started_by": s.started_by,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
                for s in sessions
            ]
        }
    finally:
        session.close()


# Webhook endpoints
@router.post("/webhooks/generic", response_model=dict)
async def generic_webhook(data: dict, background_tasks: BackgroundTasks):
    """Generic alert webhook.

    Automatically triggers AI triage for each alert unless skip_ai=true in data.
    """
    session = get_session()
    try:
        import uuid
        alert_id = str(uuid.uuid4())
        skip_ai = data.get("skip_ai", False)

        alert = AlertModel(
            alert_id=alert_id,
            title=data.get("title", "Untitled Alert"),
            severity=data.get("severity", "warning"),
            description=data.get("description"),
            source=data.get("source", "generic"),
            device_name=data.get("device_name") or data.get("device"),
            alert_type=data.get("alert_type"),
            raw_data=data,
            status="new",
        )
        session.add(alert)
        session.commit()

        # Trigger AI processing
        if not skip_ai:
            background_tasks.add_task(_trigger_ai_processing, alert_id, skip_ai)

        return {
            "status": "received",
            "alert_id": alert_id,
            "ai_processing": not skip_ai
        }
    finally:
        session.close()


@router.post("/webhooks/prometheus", response_model=dict)
async def prometheus_webhook(data: dict, background_tasks: BackgroundTasks):
    """Prometheus AlertManager webhook.

    Automatically triggers AI triage for each alert.
    """
    session = get_session()
    try:
        import uuid
        alerts_data = data.get("alerts", [])
        created_ids = []

        for alert_data in alerts_data:
            labels = alert_data.get("labels", {})
            annotations = alert_data.get("annotations", {})
            alert_id = str(uuid.uuid4())

            alert = AlertModel(
                alert_id=alert_id,
                title=labels.get("alertname", "Prometheus Alert"),
                severity=labels.get("severity", "warning"),
                description=annotations.get("summary") or annotations.get("description"),
                source="prometheus",
                device_name=labels.get("instance"),
                alert_type=labels.get("alertname"),
                raw_data=alert_data,
                status="new",
            )
            session.add(alert)
            created_ids.append(alert_id)

        session.commit()

        # Trigger AI processing for each alert
        for alert_id in created_ids:
            background_tasks.add_task(_trigger_ai_processing, alert_id, False)

        return {
            "status": "received",
            "count": len(created_ids),
            "alert_ids": created_ids,
            "ai_processing": True
        }
    finally:
        session.close()
