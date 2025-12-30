# services/ai/app/routes/alerts.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from netstacks_core.db import get_session, Alert as AlertModel
from netstacks_core.auth import get_current_user

router = APIRouter()


class AlertCreate(BaseModel):
    title: str
    severity: str = "warning"
    description: Optional[str] = None
    source: Optional[str] = None
    device: Optional[str] = None
    skip_ai: bool = False


class AlertResponse(BaseModel):
    alert_id: str
    title: str
    severity: str
    status: str
    source: Optional[str] = None
    device: Optional[str] = None
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
                    "device": a.device,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in alerts
            ]
        }
    finally:
        session.close()


@router.post("/", response_model=dict)
async def create_alert(alert: AlertCreate):
    """Create alert (webhook endpoint - no auth required)."""
    session = get_session()
    try:
        import uuid
        new_alert = AlertModel(
            alert_id=str(uuid.uuid4()),
            title=alert.title,
            severity=alert.severity,
            description=alert.description,
            source=alert.source,
            device=alert.device,
            status="new",
        )
        session.add(new_alert)
        session.commit()
        return {
            "status": "received",
            "alert_id": new_alert.alert_id,
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
                "device": alert.device,
                "incident_id": alert.incident_id,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
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
async def process_alert(alert_id: str, user=Depends(get_current_user)):
    """Trigger AI processing for alert."""
    # TODO: Implement AI processing trigger
    return {"success": True, "message": "AI processing triggered", "alert_id": alert_id}


@router.get("/{alert_id}/sessions")
async def get_alert_sessions(alert_id: str, user=Depends(get_current_user)):
    """Get AI sessions for alert."""
    # TODO: Implement session lookup
    return {"alert_id": alert_id, "sessions": []}


# Webhook endpoints
@router.post("/webhooks/generic", response_model=dict)
async def generic_webhook(data: dict):
    """Generic alert webhook."""
    session = get_session()
    try:
        import uuid
        alert = AlertModel(
            alert_id=str(uuid.uuid4()),
            title=data.get("title", "Untitled Alert"),
            severity=data.get("severity", "warning"),
            description=data.get("description"),
            source=data.get("source", "generic"),
            device=data.get("device"),
            status="new",
        )
        session.add(alert)
        session.commit()
        return {"status": "received", "alert_id": alert.alert_id}
    finally:
        session.close()


@router.post("/webhooks/prometheus", response_model=dict)
async def prometheus_webhook(data: dict):
    """Prometheus AlertManager webhook."""
    session = get_session()
    try:
        import uuid
        alerts_data = data.get("alerts", [])
        created_ids = []

        for alert_data in alerts_data:
            labels = alert_data.get("labels", {})
            annotations = alert_data.get("annotations", {})

            alert = AlertModel(
                alert_id=str(uuid.uuid4()),
                title=labels.get("alertname", "Prometheus Alert"),
                severity=labels.get("severity", "warning"),
                description=annotations.get("summary") or annotations.get("description"),
                source="prometheus",
                device=labels.get("instance"),
                status="new",
            )
            session.add(alert)
            created_ids.append(alert.alert_id)

        session.commit()
        return {"status": "received", "count": len(created_ids), "alert_ids": created_ids}
    finally:
        session.close()
