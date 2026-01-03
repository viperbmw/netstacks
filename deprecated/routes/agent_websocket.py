"""
Agent WebSocket Handlers

Real-time WebSocket communication for agent chat using Flask-SocketIO.
Uses JWT authentication passed via query parameter or handshake.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Optional
from functools import wraps

import jwt

log = logging.getLogger(__name__)


def get_jwt_user_from_request(request):
    """
    Extract username from JWT token in WebSocket request.
    Token can be in query params (?token=xxx) or Authorization header.
    """
    token = None

    # Check query params first (common for WebSocket)
    token = request.args.get('token')

    # Fall back to Authorization header
    if not token:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]

    if not token:
        return None

    try:
        secret = os.environ.get('JWT_SECRET_KEY', 'netstacks-dev-secret-change-in-production')
        payload = jwt.decode(token, secret, algorithms=['HS256'])
        return payload.get('sub')
    except jwt.ExpiredSignatureError:
        log.warning("WebSocket JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        log.warning(f"Invalid WebSocket JWT token: {e}")
        return None

# Active agent sessions (in-memory for now)
# In production, this should be stored in Redis
active_sessions: Dict[str, dict] = {}


def init_socketio(socketio):
    """
    Initialize SocketIO event handlers.

    Call this from app.py after creating the SocketIO instance:

        from flask_socketio import SocketIO
        socketio = SocketIO(app)

        from routes.agent_websocket import init_socketio
        init_socketio(socketio)
    """

    @socketio.on('connect', namespace='/agents')
    def handle_connect():
        """Handle client connection"""
        from flask import request
        log.info(f"Agent WebSocket connected: {request.sid}")

        # Check JWT authentication
        username = get_jwt_user_from_request(request)
        if not username:
            log.warning("Unauthenticated WebSocket connection attempt")
            return False  # Reject connection

        # Store username in the connection for later use
        request.jwt_user = username

        socketio.emit('connected', {
            'message': 'Connected to agent service',
            'sid': request.sid,
            'user': username
        }, namespace='/agents')

    @socketio.on('disconnect', namespace='/agents')
    def handle_disconnect():
        """Handle client disconnection"""
        from flask import request
        log.info(f"Agent WebSocket disconnected: {request.sid}")

        # Clean up any active sessions for this client
        sid = request.sid
        for session_id, session_data in list(active_sessions.items()):
            if session_data.get('socket_id') == sid:
                session_data['status'] = 'disconnected'

    @socketio.on('start_session', namespace='/agents')
    def handle_start_session(data):
        """
        Start a new agent chat session.

        Expected data:
        {
            "agent_id": "uuid",  # ID of configured agent
            "agent_type": "triage",  # OR type for ad-hoc session
            "context": {}  # Optional context data
        }
        """
        from flask import request

        try:
            username = get_jwt_user_from_request(request) or 'unknown'
            agent_id = data.get('agent_id')
            agent_type = data.get('agent_type', 'triage')
            context = data.get('context', {})

            # Create session
            session_id = str(uuid.uuid4())

            # Get or create agent
            if agent_id:
                agent_instance = _get_agent_from_db(agent_id)
            else:
                from ai.agents import create_agent
                agent_instance = create_agent(agent_type, session_id=session_id)

            if not agent_instance:
                socketio.emit('error', {
                    'message': f'Could not create agent: {agent_type}'
                }, room=request.sid, namespace='/agents')
                return

            # Store session
            active_sessions[session_id] = {
                'agent': agent_instance,
                'socket_id': request.sid,
                'username': username,
                'status': 'active',
                'created_at': datetime.utcnow(),
            }

            # Persist session to database
            _save_session_to_db(session_id, agent_instance, username, context)

            socketio.emit('session_started', {
                'session_id': session_id,
                'agent_type': agent_instance.agent_type,
                'agent_name': agent_instance.agent_name,
            }, room=request.sid, namespace='/agents')

            log.info(f"Started agent session {session_id} for user {username}")

        except Exception as e:
            log.error(f"Error starting session: {e}", exc_info=True)
            socketio.emit('error', {
                'message': str(e)
            }, room=request.sid, namespace='/agents')

    @socketio.on('send_message', namespace='/agents')
    def handle_send_message(data):
        """
        Send a message to the agent.

        Expected data:
        {
            "session_id": "uuid",
            "message": "user message",
            "context": {}  # Optional additional context
        }
        """
        from flask import request

        try:
            session_id = data.get('session_id')
            message = data.get('message', '')
            context = data.get('context', {})

            if not session_id or session_id not in active_sessions:
                socketio.emit('error', {
                    'message': 'Invalid or expired session'
                }, room=request.sid, namespace='/agents')
                return

            session_data = active_sessions[session_id]
            agent = session_data['agent']

            # Save user message to database
            _save_message_to_db(session_id, 'user', message)

            # Run agent and stream events
            socketio.emit('agent_event', {
                'type': 'processing',
                'content': 'Processing your request...'
            }, room=request.sid, namespace='/agents')

            response_content = ""

            for event in agent.run(message, context):
                event_dict = event.to_dict()

                # Emit event to client
                socketio.emit('agent_event', event_dict, room=request.sid, namespace='/agents')

                # Save action to database
                _save_action_to_db(session_id, event)

                # Accumulate response content
                if event.type.value == 'final_response':
                    response_content = event.content

                # Handle special events
                if event.type.value == 'handoff':
                    _handle_handoff(socketio, request.sid, session_id, event)

                if event.type.value == 'approval_required':
                    _handle_approval_request(socketio, request.sid, session_id, event)

            # Save assistant response to database
            if response_content:
                _save_message_to_db(session_id, 'assistant', response_content)

        except Exception as e:
            log.error(f"Error processing message: {e}", exc_info=True)
            socketio.emit('error', {
                'message': str(e)
            }, room=request.sid, namespace='/agents')

    @socketio.on('approve_action', namespace='/agents')
    def handle_approve_action(data):
        """
        Handle approval/rejection of a pending action.

        Expected data:
        {
            "session_id": "uuid",
            "approval_id": "uuid",
            "approved": true/false,
            "reason": "optional reason"
        }
        """
        from flask import session, request

        try:
            session_id = data.get('session_id')
            approval_id = data.get('approval_id')
            approved = data.get('approved', False)
            reason = data.get('reason', '')

            if not session_id or session_id not in active_sessions:
                socketio.emit('error', {
                    'message': 'Invalid or expired session'
                }, room=request.sid, namespace='/agents')
                return

            session_data = active_sessions[session_id]
            agent = session_data['agent']
            username = get_jwt_user_from_request(request) or 'unknown'

            # Update approval in database
            _update_approval_in_db(approval_id, approved, username, reason)

            # Resume agent execution
            for event in agent.resume_with_approval(approval_id, approved, username):
                event_dict = event.to_dict()
                socketio.emit('agent_event', event_dict, room=request.sid, namespace='/agents')
                _save_action_to_db(session_id, event)

        except Exception as e:
            log.error(f"Error handling approval: {e}", exc_info=True)
            socketio.emit('error', {
                'message': str(e)
            }, room=request.sid, namespace='/agents')

    @socketio.on('resume_session', namespace='/agents')
    def handle_resume_session(data):
        """
        Resume an existing agent session.

        Expected data:
        {
            "session_id": "uuid"
        }
        """
        from flask import request

        try:
            session_id = data.get('session_id')
            username = get_jwt_user_from_request(request) or 'unknown'

            if not session_id:
                socketio.emit('error', {
                    'message': 'Session ID required'
                }, room=request.sid, namespace='/agents')
                return

            # Check if session exists in memory
            if session_id in active_sessions:
                session_data = active_sessions[session_id]
                # Update socket ID for this session
                session_data['socket_id'] = request.sid
                session_data['status'] = 'active'
                agent = session_data['agent']

                socketio.emit('session_resumed', {
                    'session_id': session_id,
                    'agent_type': agent.agent_type,
                    'agent_name': agent.agent_name,
                }, room=request.sid, namespace='/agents')

                log.info(f"Resumed in-memory session {session_id} for user {username}")
                return

            # Try to restore from database
            agent_type, context = _get_session_from_db(session_id, username)

            if agent_type:
                from ai.agents import create_agent
                agent_instance = create_agent(agent_type, session_id=session_id)

                if agent_instance:
                    # Restore conversation context
                    messages = _get_messages_from_db(session_id)
                    agent_instance.conversation_history = messages

                    # Store session
                    active_sessions[session_id] = {
                        'agent': agent_instance,
                        'socket_id': request.sid,
                        'username': username,
                        'status': 'active',
                        'created_at': datetime.utcnow(),
                    }

                    socketio.emit('session_resumed', {
                        'session_id': session_id,
                        'agent_type': agent_instance.agent_type,
                        'agent_name': agent_instance.agent_name,
                    }, room=request.sid, namespace='/agents')

                    log.info(f"Restored session {session_id} from database for user {username}")
                    return

            # Session not found - client should start a new one
            socketio.emit('session_expired', {
                'session_id': session_id,
                'message': 'Session not found or expired'
            }, room=request.sid, namespace='/agents')

        except Exception as e:
            log.error(f"Error resuming session: {e}", exc_info=True)
            socketio.emit('error', {
                'message': str(e)
            }, room=request.sid, namespace='/agents')

    @socketio.on('end_session', namespace='/agents')
    def handle_end_session(data):
        """End an agent session"""
        from flask import request

        try:
            session_id = data.get('session_id')

            if session_id in active_sessions:
                session_data = active_sessions.pop(session_id)
                _end_session_in_db(session_id)

                socketio.emit('session_ended', {
                    'session_id': session_id
                }, room=request.sid, namespace='/agents')

                log.info(f"Ended agent session {session_id}")

        except Exception as e:
            log.error(f"Error ending session: {e}", exc_info=True)

    return socketio


# ============================================================================
# Helper Functions
# ============================================================================

def _get_agent_from_db(agent_id: str):
    """Get agent instance from database configuration"""
    try:
        import database as db
        from shared.netstacks_core.db.models import Agent
        from ai.agents import create_agent

        with db.get_db() as db_session:
            agent_config = db_session.query(Agent).filter(
                Agent.agent_id == agent_id
            ).first()

            if not agent_config:
                return None

            return create_agent(
                agent_type=agent_config.agent_type,
                llm_provider=agent_config.llm_provider,
                llm_model=agent_config.llm_model,
                config={
                    'temperature': agent_config.temperature,
                    'max_tokens': agent_config.max_tokens,
                    'system_prompt': agent_config.system_prompt,
                }
            )

    except Exception as e:
        log.error(f"Error getting agent from DB: {e}")
        return None


def _save_session_to_db(session_id: str, agent, username: str, context: dict):
    """Save session to database"""
    try:
        import database as db
        from shared.netstacks_core.db.models import AgentSession

        with db.get_db() as db_session:
            session_obj = AgentSession(
                session_id=session_id,
                agent_id=agent.context.get('agent_id'),
                status='active',
                trigger_type='user',
                trigger_data=context,
                user_id=username,
            )
            db_session.add(session_obj)
            db_session.commit()

    except Exception as e:
        log.error(f"Error saving session to DB: {e}")


def _save_message_to_db(session_id: str, role: str, content: str):
    """Save message to database"""
    try:
        import database as db
        from shared.netstacks_core.db.models import AgentMessage

        with db.get_db() as db_session:
            message = AgentMessage(
                session_id=session_id,
                role=role,
                content=content,
            )
            db_session.add(message)
            db_session.commit()

    except Exception as e:
        log.error(f"Error saving message to DB: {e}")


def _save_action_to_db(session_id: str, event):
    """Save agent action to database"""
    try:
        import uuid
        import database as db
        from shared.netstacks_core.db.models import AgentAction

        with db.get_db() as db_session:
            # Get next sequence number for this session
            max_seq = db_session.query(AgentAction).filter_by(
                session_id=session_id
            ).count()

            action = AgentAction(
                action_id=str(uuid.uuid4()),
                session_id=session_id,
                sequence=max_seq + 1,
                action_type=event.type.value,
                tool_name=event.tool_name,
                tool_input=event.tool_args or {},
                tool_output=event.tool_result or {},
                content=event.content,
            )
            db_session.add(action)
            db_session.commit()

    except Exception as e:
        log.error(f"Error saving action to DB: {e}")


def _end_session_in_db(session_id: str):
    """Mark session as ended in database"""
    try:
        import database as db
        from shared.netstacks_core.db.models import AgentSession

        with db.get_db() as db_session:
            session_obj = db_session.query(AgentSession).filter(
                AgentSession.session_id == session_id
            ).first()

            if session_obj:
                session_obj.status = 'completed'
                session_obj.completed_at = datetime.utcnow()
                db_session.commit()

    except Exception as e:
        log.error(f"Error ending session in DB: {e}")


def _handle_handoff(socketio, socket_id: str, session_id: str, event):
    """Handle agent handoff"""
    handoff_data = event.data.get('handoff', {})
    target_agent = handoff_data.get('target_agent')

    socketio.emit('agent_handoff', {
        'session_id': session_id,
        'target_agent': target_agent,
        'summary': handoff_data.get('summary', ''),
        'context': handoff_data.get('context', {}),
    }, room=socket_id, namespace='/agents')


def _handle_approval_request(socketio, socket_id: str, session_id: str, event):
    """Handle approval request"""
    socketio.emit('approval_required', {
        'session_id': session_id,
        'approval_id': event.data.get('approval_id'),
        'tool_name': event.data.get('tool_name'),
        'tool_args': event.data.get('tool_args'),
        'risk_level': event.data.get('risk_level'),
        'message': event.content,
    }, room=socket_id, namespace='/agents')


def _update_approval_in_db(approval_id: str, approved: bool, username: str, reason: str):
    """Update approval status in database"""
    try:
        import database as db
        from shared.netstacks_core.db.models import PendingApproval

        with db.get_db() as db_session:
            approval = db_session.query(PendingApproval).filter(
                PendingApproval.approval_id == approval_id
            ).first()

            if approval:
                approval.status = 'approved' if approved else 'rejected'
                approval.reviewed_by = username
                approval.reviewed_at = datetime.utcnow()
                approval.review_notes = reason
                db_session.commit()

    except Exception as e:
        log.error(f"Error updating approval in DB: {e}")


def _get_session_from_db(session_id: str, username: str) -> tuple:
    """Get session info from database for resumption"""
    try:
        import database as db
        from shared.netstacks_core.db.models import AgentSession

        with db.get_db() as db_session:
            session_obj = db_session.query(AgentSession).filter(
                AgentSession.session_id == session_id,
                AgentSession.started_by == username,
                AgentSession.status == 'active'
            ).first()

            if session_obj:
                # Determine agent type from session
                agent_type = 'assistant'  # Default for assistant sessions
                if session_obj.agent_id:
                    from shared.netstacks_core.db.models import Agent
                    agent = db_session.query(Agent).filter(
                        Agent.agent_id == session_obj.agent_id
                    ).first()
                    if agent:
                        agent_type = agent.agent_type

                return agent_type, session_obj.context or {}

        return None, None

    except Exception as e:
        log.error(f"Error getting session from DB: {e}")
        return None, None


def _get_messages_from_db(session_id: str) -> list:
    """Get conversation messages from database for session resumption"""
    try:
        import database as db
        from shared.netstacks_core.db.models import AgentMessage

        with db.get_db() as db_session:
            messages = db_session.query(AgentMessage).filter(
                AgentMessage.session_id == session_id
            ).order_by(AgentMessage.created_at.asc()).all()

            return [
                {'role': msg.role, 'content': msg.content}
                for msg in messages
            ]

    except Exception as e:
        log.error(f"Error getting messages from DB: {e}")
        return []
