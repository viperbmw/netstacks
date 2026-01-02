# services/ai/app/routes/sessions.py
"""
Agent session routes.

Provides endpoints for managing and viewing agent sessions.
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func

from netstacks_core.db import get_session, AgentSession, AgentMessage, AgentAction
from netstacks_core.auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter()


class SessionResponse(BaseModel):
    session_id: str
    agent_id: str
    status: str
    started_by: Optional[str] = None
    created_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    message_count: int = 0
    action_count: int = 0

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    message_id: str
    role: str
    content: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ActionResponse(BaseModel):
    action_id: str
    tool_name: str
    tool_input: Optional[str] = None
    tool_output: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.get("/", response_model=dict)
async def list_sessions(
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500),
    user=Depends(get_current_user)
):
    """List agent sessions."""
    session = get_session()
    try:
        query = session.query(AgentSession)

        if agent_id:
            query = query.filter(AgentSession.agent_id == agent_id)
        if status:
            query = query.filter(AgentSession.status == status)

        sessions = query.order_by(AgentSession.started_at.desc()).limit(limit).all()

        return {
            "success": True,
            "sessions": [
                {
                    "session_id": s.session_id,
                    "agent_id": s.agent_id,
                    "status": s.status,
                    "started_by": s.started_by,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "message_count": len(s.messages) if s.messages else 0,
                    "action_count": len(s.actions) if s.actions else 0,
                }
                for s in sessions
            ]
        }
    finally:
        session.close()


@router.get("/{session_id}", response_model=dict)
async def get_session_details(session_id: str, user=Depends(get_current_user)):
    """Get session details with messages and actions."""
    db_session = get_session()
    try:
        agent_session = db_session.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()

        if not agent_session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Get messages
        messages = db_session.query(AgentMessage).filter(
            AgentMessage.session_id == session_id
        ).order_by(AgentMessage.created_at).all()

        # Get actions
        actions = db_session.query(AgentAction).filter(
            AgentAction.session_id == session_id
        ).order_by(AgentAction.created_at).all()

        return {
            "success": True,
            "session": {
                "session_id": agent_session.session_id,
                "agent_id": agent_session.agent_id,
                "status": agent_session.status,
                "started_by": agent_session.started_by,
                "trigger_type": agent_session.trigger_type,
                "trigger_id": agent_session.trigger_id,
                "started_at": agent_session.started_at.isoformat() if agent_session.started_at else None,
                "completed_at": agent_session.completed_at.isoformat() if agent_session.completed_at else None,
            },
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
            "actions": [
                {
                    "action_id": a.action_id,
                    "action_type": a.action_type,
                    "tool_name": a.tool_name,
                    "tool_input": a.tool_input or {},
                    "tool_output": a.tool_output or {},
                    "status": a.status,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in actions
            ]
        }
    finally:
        db_session.close()


@router.get("/{session_id}/messages", response_model=dict)
async def get_session_messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=1000),
    user=Depends(get_current_user)
):
    """Get messages for a session."""
    db_session = get_session()
    try:
        # Verify session exists
        agent_session = db_session.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()

        if not agent_session:
            raise HTTPException(status_code=404, detail="Session not found")

        messages = db_session.query(AgentMessage).filter(
            AgentMessage.session_id == session_id
        ).order_by(AgentMessage.created_at).limit(limit).all()

        return {
            "success": True,
            "session_id": session_id,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ]
        }
    finally:
        db_session.close()


@router.get("/{session_id}/actions", response_model=dict)
async def get_session_actions(
    session_id: str,
    limit: int = Query(100, ge=1, le=1000),
    user=Depends(get_current_user)
):
    """Get actions for a session."""
    db_session = get_session()
    try:
        # Verify session exists
        agent_session = db_session.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()

        if not agent_session:
            raise HTTPException(status_code=404, detail="Session not found")

        actions = db_session.query(AgentAction).filter(
            AgentAction.session_id == session_id
        ).order_by(AgentAction.created_at).limit(limit).all()

        return {
            "success": True,
            "session_id": session_id,
            "actions": [
                {
                    "action_id": a.action_id,
                    "action_type": a.action_type,
                    "tool_name": a.tool_name,
                    "tool_input": a.tool_input or {},
                    "tool_output": a.tool_output or {},
                    "status": a.status,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in actions
            ]
        }
    finally:
        db_session.close()
