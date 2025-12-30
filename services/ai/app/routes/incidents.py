# services/ai/app/routes/incidents.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from netstacks_core.db import get_session, Incident as IncidentModel
from netstacks_core.auth import get_current_user

router = APIRouter()


class IncidentCreate(BaseModel):
    title: str
    severity: str = "warning"
    description: Optional[str] = None
    source: str = "manual"


class IncidentUpdate(BaseModel):
    status: Optional[str] = None
    resolution: Optional[str] = None
    severity: Optional[str] = None


@router.get("/", response_model=dict)
async def list_incidents(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    user=Depends(get_current_user)
):
    """List incidents."""
    session = get_session()
    try:
        query = session.query(IncidentModel)
        if status:
            query = query.filter(IncidentModel.status == status)
        if severity:
            query = query.filter(IncidentModel.severity == severity)

        incidents = query.order_by(IncidentModel.created_at.desc()).limit(limit).all()
        return {
            "success": True,
            "incidents": [
                {
                    "incident_id": i.incident_id,
                    "title": i.title,
                    "severity": i.severity,
                    "status": i.status,
                    "source": i.source,
                    "resolution": i.resolution,
                    "created_at": i.created_at.isoformat() if i.created_at else None,
                    "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
                }
                for i in incidents
            ]
        }
    finally:
        session.close()


@router.post("/", response_model=dict)
async def create_incident(incident: IncidentCreate, user=Depends(get_current_user)):
    """Create a new incident."""
    session = get_session()
    try:
        import uuid
        new_incident = IncidentModel(
            incident_id=str(uuid.uuid4()),
            title=incident.title,
            severity=incident.severity,
            description=incident.description,
            source=incident.source,
            status="open",
        )
        session.add(new_incident)
        session.commit()
        return {"success": True, "incident_id": new_incident.incident_id}
    finally:
        session.close()


@router.get("/{incident_id}", response_model=dict)
async def get_incident(incident_id: str, user=Depends(get_current_user)):
    """Get incident by ID."""
    session = get_session()
    try:
        incident = session.query(IncidentModel).filter(
            IncidentModel.incident_id == incident_id
        ).first()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {
            "success": True,
            "incident": {
                "incident_id": incident.incident_id,
                "title": incident.title,
                "severity": incident.severity,
                "status": incident.status,
                "description": incident.description,
                "source": incident.source,
                "resolution": incident.resolution,
                "created_at": incident.created_at.isoformat() if incident.created_at else None,
                "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
            }
        }
    finally:
        session.close()


@router.patch("/{incident_id}", response_model=dict)
async def update_incident(
    incident_id: str,
    updates: IncidentUpdate,
    user=Depends(get_current_user)
):
    """Update an incident."""
    session = get_session()
    try:
        incident = session.query(IncidentModel).filter(
            IncidentModel.incident_id == incident_id
        ).first()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        if updates.status:
            incident.status = updates.status
            if updates.status == "resolved":
                incident.resolved_at = datetime.utcnow()
        if updates.resolution:
            incident.resolution = updates.resolution
        if updates.severity:
            incident.severity = updates.severity

        session.commit()
        return {"success": True, "message": "Incident updated"}
    finally:
        session.close()


@router.delete("/{incident_id}")
async def delete_incident(incident_id: str, user=Depends(get_current_user)):
    """Delete an incident."""
    session = get_session()
    try:
        incident = session.query(IncidentModel).filter(
            IncidentModel.incident_id == incident_id
        ).first()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        session.delete(incident)
        session.commit()
        return {"success": True, "message": "Incident deleted"}
    finally:
        session.close()
