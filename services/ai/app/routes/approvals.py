# services/ai/app/routes/approvals.py
"""
Approval workflow routes.

Provides endpoints for managing pending approvals for high-risk agent actions.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func

from netstacks_core.db import get_session, PendingApproval
from netstacks_core.auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models
class ApprovalResponse(BaseModel):
    approval_id: str
    session_id: str
    action_id: str
    action_type: str
    description: str
    risk_level: str = "high"
    target_device: Optional[str] = None
    proposed_action: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    status: str = "pending"
    expires_at: Optional[datetime] = None
    requested_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decision_reason: Optional[str] = None

    class Config:
        from_attributes = True


class ApprovalCreate(BaseModel):
    session_id: str
    action_id: str
    action_type: str
    description: str
    risk_level: str = Field(default="high", pattern="^(medium|high|critical)$")
    target_device: Optional[str] = None
    proposed_action: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    expires_minutes: int = Field(default=30, ge=1, le=1440)


class ApprovalAction(BaseModel):
    reason: Optional[str] = None


class ApprovalStats(BaseModel):
    by_status: Dict[str, int] = {}
    by_risk_level: Dict[str, int] = {}


@router.get("/", response_model=dict)
async def list_approvals(
    status: str = Query("pending", description="Filter by status (pending, approved, rejected, expired, all)"),
    limit: int = Query(50, ge=1, le=500),
    user=Depends(get_current_user)
):
    """List pending approvals."""
    session = get_session()
    try:
        query = session.query(PendingApproval)

        if status != "all":
            query = query.filter(PendingApproval.status == status)

        approvals = query.order_by(
            PendingApproval.requested_at.desc()
        ).limit(limit).all()

        return {
            "success": True,
            "approvals": [
                {
                    "approval_id": a.approval_id,
                    "session_id": a.session_id,
                    "action_id": a.action_id,
                    "action_type": a.action_type,
                    "description": a.description,
                    "risk_level": a.risk_level,
                    "target_device": a.target_device,
                    "status": a.status,
                    "expires_at": a.expires_at.isoformat() if a.expires_at else None,
                    "requested_at": a.requested_at.isoformat() if a.requested_at else None,
                    "decided_by": a.decided_by,
                    "decided_at": a.decided_at.isoformat() if a.decided_at else None,
                }
                for a in approvals
            ]
        }
    finally:
        session.close()


@router.get("/stats", response_model=dict)
async def get_approval_stats(user=Depends(get_current_user)):
    """Get approval statistics."""
    session = get_session()
    try:
        # Count by status
        status_counts = session.query(
            PendingApproval.status,
            func.count(PendingApproval.approval_id)
        ).group_by(PendingApproval.status).all()

        # Count by risk level
        risk_counts = session.query(
            PendingApproval.risk_level,
            func.count(PendingApproval.approval_id)
        ).group_by(PendingApproval.risk_level).all()

        return {
            "success": True,
            "by_status": {s[0]: s[1] for s in status_counts if s[0]},
            "by_risk_level": {r[0]: r[1] for r in risk_counts if r[0]},
        }
    finally:
        session.close()


@router.get("/{approval_id}", response_model=dict)
async def get_approval(approval_id: str, user=Depends(get_current_user)):
    """Get approval details."""
    session = get_session()
    try:
        approval = session.query(PendingApproval).filter(
            PendingApproval.approval_id == approval_id
        ).first()

        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")

        return {
            "success": True,
            "approval": {
                "approval_id": approval.approval_id,
                "session_id": approval.session_id,
                "action_id": approval.action_id,
                "action_type": approval.action_type,
                "description": approval.description,
                "risk_level": approval.risk_level,
                "target_device": approval.target_device,
                "proposed_action": approval.proposed_action,
                "context": approval.context,
                "status": approval.status,
                "requires_count": approval.requires_count,
                "approved_count": approval.approved_count,
                "approvers": approval.approvers,
                "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
                "requested_at": approval.requested_at.isoformat() if approval.requested_at else None,
                "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
                "decided_by": approval.decided_by,
                "decision_reason": approval.decision_reason,
            }
        }
    finally:
        session.close()


@router.post("/", response_model=dict)
async def create_approval(request: ApprovalCreate, user=Depends(get_current_user)):
    """Create a new approval request (typically called by agent system)."""
    session = get_session()
    try:
        approval_id = str(uuid.uuid4())

        approval = PendingApproval(
            approval_id=approval_id,
            session_id=request.session_id,
            action_id=request.action_id,
            action_type=request.action_type,
            description=request.description,
            risk_level=request.risk_level,
            target_device=request.target_device,
            proposed_action=request.proposed_action or {},
            context=request.context or {},
            status="pending",
            expires_at=datetime.utcnow() + timedelta(minutes=request.expires_minutes),
        )
        session.add(approval)
        session.commit()

        log.info(f"Created approval request {approval_id} for {request.action_type}")

        return {
            "success": True,
            "approval_id": approval_id,
            "expires_at": approval.expires_at.isoformat()
        }
    finally:
        session.close()


@router.post("/{approval_id}/approve", response_model=dict)
async def approve_action(
    approval_id: str,
    action: ApprovalAction = None,
    user=Depends(get_current_user)
):
    """Approve a pending action."""
    session = get_session()
    try:
        approval = session.query(PendingApproval).filter(
            PendingApproval.approval_id == approval_id
        ).first()

        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")

        if approval.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Approval already {approval.status}"
            )

        # Check expiration
        if approval.expires_at and approval.expires_at < datetime.utcnow():
            approval.status = "expired"
            session.commit()
            raise HTTPException(status_code=400, detail="Approval has expired")

        username = user.get("username") if isinstance(user, dict) else user

        approval.status = "approved"
        approval.decided_by = username
        approval.decided_at = datetime.utcnow()
        if action and action.reason:
            approval.decision_reason = action.reason
        session.commit()

        log.info(f"Approval {approval_id} approved by {username}")

        return {
            "success": True,
            "message": "Action approved",
            "approval_id": approval_id
        }
    finally:
        session.close()


@router.post("/{approval_id}/reject", response_model=dict)
async def reject_action(
    approval_id: str,
    action: ApprovalAction = None,
    user=Depends(get_current_user)
):
    """Reject a pending action."""
    session = get_session()
    try:
        approval = session.query(PendingApproval).filter(
            PendingApproval.approval_id == approval_id
        ).first()

        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")

        if approval.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Approval already {approval.status}"
            )

        username = user.get("username") if isinstance(user, dict) else user

        approval.status = "rejected"
        approval.decided_by = username
        approval.decided_at = datetime.utcnow()
        approval.decision_reason = (action.reason if action and action.reason else "No reason provided")
        session.commit()

        log.info(f"Approval {approval_id} rejected by {username}")

        return {
            "success": True,
            "message": "Action rejected",
            "approval_id": approval_id
        }
    finally:
        session.close()


@router.post("/expire-old", response_model=dict)
async def expire_old_approvals(user=Depends(get_current_user)):
    """Expire old pending approvals (maintenance endpoint)."""
    session = get_session()
    try:
        expired = session.query(PendingApproval).filter(
            PendingApproval.status == "pending",
            PendingApproval.expires_at < datetime.utcnow()
        ).all()

        for approval in expired:
            approval.status = "expired"

        if expired:
            session.commit()
            log.info(f"Expired {len(expired)} approval requests")

        return {
            "success": True,
            "expired_count": len(expired)
        }
    finally:
        session.close()
