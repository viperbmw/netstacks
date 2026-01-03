# services/ai/app/routes/chat.py
"""
Agent Chat Routes

Provides HTTP endpoints for agent chat with Server-Sent Events (SSE) streaming.
"""

import logging
import json
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from netstacks_core.db import get_session, Agent as AgentModel, AgentSession
from netstacks_core.auth import get_current_user

from app.services import (
    AgentExecutor,
    ExecutorContext,
    create_agent_session,
    end_agent_session,
    get_session_messages,
    EventType,
)

log = logging.getLogger(__name__)

router = APIRouter()


class StartSessionRequest(BaseModel):
    """Request to start a new chat session."""
    agent_id: str = Field(..., description="ID of the agent to chat with")


class StartSessionResponse(BaseModel):
    """Response when starting a session."""
    success: bool
    session_id: str
    agent_name: str
    agent_type: str


class SendMessageRequest(BaseModel):
    """Request to send a message in a session."""
    message: str = Field(..., description="User message to send")


class EndSessionRequest(BaseModel):
    """Request to end a session."""
    summary: Optional[str] = None
    resolution_status: Optional[str] = None


@router.post("/start", response_model=StartSessionResponse)
async def start_chat_session(
    request: StartSessionRequest,
    user=Depends(get_current_user)
):
    """
    Start a new chat session with an agent.

    Returns a session_id to use for subsequent messages.
    """
    db_session = get_session()
    try:
        # Get the agent
        agent = db_session.query(AgentModel).filter(
            AgentModel.agent_id == request.agent_id
        ).first()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        if not agent.is_enabled:
            raise HTTPException(status_code=400, detail="Agent is not active")

        # Create session
        username = user.get("sub", "unknown") if isinstance(user, dict) else getattr(user, "sub", "unknown")
        session_id = create_agent_session(
            agent_id=request.agent_id,
            username=username,
            trigger_type="user",
        )

        log.info(f"Started chat session {session_id} with agent {agent.name}")

        return StartSessionResponse(
            success=True,
            session_id=session_id,
            agent_name=agent.name,
            agent_type=agent.agent_type,
        )
    finally:
        db_session.close()


@router.post("/{session_id}/message")
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    http_request: Request,
    user=Depends(get_current_user)
):
    """
    Send a message to the agent and get a streaming response.

    Returns a Server-Sent Events stream with agent events.
    """
    db_session = get_session()
    try:
        # Verify session exists and is active
        session = db_session.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.status != "active":
            raise HTTPException(status_code=400, detail="Session is not active")

        # Get the agent
        agent = db_session.query(AgentModel).filter(
            AgentModel.agent_id == session.agent_id
        ).first()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        username = user.get("sub", "unknown") if isinstance(user, dict) else getattr(user, "sub", "unknown")

        # Get auth token from request
        auth_header = http_request.headers.get("Authorization", "")
        auth_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

    finally:
        db_session.close()

    # Create executor from agent config
    try:
        executor = AgentExecutor.from_agent_config(session.agent_id)
    except Exception as e:
        log.error(f"Failed to create executor: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize agent: {e}")

    # Load existing conversation history
    existing_messages = get_session_messages(session_id)
    for msg in existing_messages:
        from app.services.llm_client import Message
        executor.messages.append(Message(
            role=msg["role"],
            content=msg["content"],
        ))

    # Create execution context
    context = ExecutorContext(
        session_id=session_id,
        agent_id=session.agent_id,
        username=username,
        auth_token=auth_token,
        trigger_type="user",
    )

    async def event_generator():
        """Generate SSE events from agent execution."""
        try:
            async for event in executor.run(request.message, context):
                # Format as SSE
                event_data = json.dumps(event.to_dict())
                yield f"data: {event_data}\n\n"

        except Exception as e:
            log.error(f"Error during agent execution: {e}", exc_info=True)
            error_event = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.post("/{session_id}/message/sync")
async def send_message_sync(
    session_id: str,
    request: SendMessageRequest,
    http_request: Request,
    user=Depends(get_current_user)
):
    """
    Send a message and wait for the complete response (non-streaming).

    Use this for simpler integrations that don't need streaming.
    """
    db_session = get_session()
    try:
        # Verify session
        session = db_session.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.status != "active":
            raise HTTPException(status_code=400, detail="Session is not active")

        agent = db_session.query(AgentModel).filter(
            AgentModel.agent_id == session.agent_id
        ).first()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        username = user.get("sub", "unknown") if isinstance(user, dict) else getattr(user, "sub", "unknown")
        auth_header = http_request.headers.get("Authorization", "")
        auth_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

    finally:
        db_session.close()

    # Create executor
    try:
        executor = AgentExecutor.from_agent_config(session.agent_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize agent: {e}")

    # Load history
    existing_messages = get_session_messages(session_id)
    for msg in existing_messages:
        from app.services.llm_client import Message
        executor.messages.append(Message(
            role=msg["role"],
            content=msg["content"],
        ))

    context = ExecutorContext(
        session_id=session_id,
        agent_id=session.agent_id,
        username=username,
        auth_token=auth_token,
        trigger_type="user",
    )

    # Collect all events
    events = []
    final_response = ""
    tool_calls = []

    try:
        async for event in executor.run(request.message, context):
            events.append(event.to_dict())

            if event.type == EventType.FINAL_RESPONSE:
                final_response = event.content
            elif event.type == EventType.TOOL_CALL:
                tool_calls.append({
                    "name": event.tool_name,
                    "input": event.tool_input,
                })
            elif event.type == EventType.ERROR:
                return {
                    "success": False,
                    "error": event.content,
                    "events": events,
                }

    except Exception as e:
        log.error(f"Error during agent execution: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "events": events,
        }

    return {
        "success": True,
        "response": final_response,
        "tool_calls": tool_calls,
        "events": events,
    }


@router.get("/{session_id}/messages")
async def get_chat_messages(
    session_id: str,
    user=Depends(get_current_user)
):
    """Get all messages in a chat session."""
    db_session = get_session()
    try:
        session = db_session.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        messages = get_session_messages(session_id)

        return {
            "success": True,
            "session_id": session_id,
            "messages": messages,
        }
    finally:
        db_session.close()


@router.post("/{session_id}/end")
async def end_chat_session(
    session_id: str,
    request: Optional[EndSessionRequest] = None,
    user=Depends(get_current_user)
):
    """End a chat session."""
    db_session = get_session()
    try:
        session = db_session.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        end_agent_session(
            session_id=session_id,
            status="completed",
            summary=request.summary if request else None,
            resolution_status=request.resolution_status if request else None,
        )

        log.info(f"Ended chat session {session_id}")

        return {"success": True, "message": "Session ended"}
    finally:
        db_session.close()


@router.get("/{session_id}")
async def get_session_info(
    session_id: str,
    user=Depends(get_current_user)
):
    """Get information about a chat session."""
    db_session = get_session()
    try:
        session = db_session.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        agent = db_session.query(AgentModel).filter(
            AgentModel.agent_id == session.agent_id
        ).first()

        return {
            "success": True,
            "session": {
                "session_id": session.session_id,
                "agent_id": session.agent_id,
                "agent_name": agent.name if agent else None,
                "agent_type": agent.agent_type if agent else None,
                "status": session.status,
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                "started_by": session.started_by,
            }
        }
    finally:
        db_session.close()
