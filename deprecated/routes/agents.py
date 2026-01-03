"""
Agent Routes

HTTP routes for agent management and chat.
WebSocket handlers are in agent_websocket.py
"""

import logging
import uuid
from flask import Blueprint, render_template, request, jsonify
from datetime import datetime, timedelta
from sqlalchemy import func

import database as db
from shared.netstacks_core.db.models import Agent, AgentSession
from routes.auth import login_required, get_current_user

log = logging.getLogger(__name__)

agents_bp = Blueprint('agents', __name__, url_prefix='/agents')


# ============================================================================
# Agent Management UI Routes
# ============================================================================

@agents_bp.route('/')
@login_required
def agents_page():
    """Agent management page"""
    return render_template('agents.html')


@agents_bp.route('/chat')
@login_required
def chat_page():
    """Standalone agent chat interface"""
    return render_template('agent_chat.html', agent_id=None)


@agents_bp.route('/<agent_id>/chat')
@login_required
def agent_chat_page(agent_id):
    """Agent chat interface with pre-selected agent"""
    return render_template('agent_chat.html', agent_id=agent_id)


# ============================================================================
# Agent Management API Routes
# ============================================================================

@agents_bp.route('/api/agents', methods=['GET'])
@login_required
def list_agents():
    """List all configured agents"""
    try:
        with db.get_db() as db_session:
            agents = db_session.query(Agent).all()

            # Get session counts per agent
            session_counts = dict(
                db_session.query(
                    AgentSession.agent_id,
                    func.count(AgentSession.session_id)
                ).group_by(AgentSession.agent_id).all()
            )

            return jsonify({
                'agents': [
                    {
                        'agent_id': a.agent_id,
                        'agent_name': a.name,
                        'agent_type': a.agent_type,
                        'description': a.description,
                        'is_active': a.is_enabled,
                        'is_persistent': a.is_persistent,
                        'status': a.status,
                        'llm_provider': a.llm_provider,
                        'llm_model': a.llm_model,
                        'created_at': a.created_at.isoformat() if a.created_at else None,
                        'session_count': session_counts.get(a.agent_id, 0),
                    }
                    for a in agents
                ]
            })
    except Exception as e:
        log.error(f"Error listing agents: {e}")
        return jsonify({'error': str(e)}), 500


@agents_bp.route('/api/agents', methods=['POST'])
@login_required
def create_agent():
    """Create a new agent"""
    try:
        data = request.get_json()

        with db.get_db() as db_session:
            agent = Agent(
                agent_id=str(uuid.uuid4()),
                name=data.get('agent_name') or data.get('name'),
                agent_type=data.get('agent_type', 'custom'),
                description=data.get('description', ''),
                system_prompt=data.get('system_prompt', ''),
                is_enabled=data.get('is_enabled', True),
                is_persistent=data.get('is_persistent', False),
                llm_provider=data.get('llm_provider'),
                llm_model=data.get('llm_model'),
                temperature=data.get('temperature', 0.1),
                max_tokens=data.get('max_tokens', 4096),
                tools=data.get('tools', []),
                config=data.get('config', {}),
            )
            db_session.add(agent)
            db_session.commit()

            return jsonify({
                'agent_id': agent.agent_id,
                'message': 'Agent created successfully'
            }), 201

    except Exception as e:
        log.error(f"Error creating agent: {e}")
        return jsonify({'error': str(e)}), 500


@agents_bp.route('/api/agents/<agent_id>', methods=['GET'])
@login_required
def get_agent(agent_id):
    """Get agent details"""
    try:
        with db.get_db() as db_session:
            agent = db_session.query(Agent).filter(
                Agent.agent_id == agent_id
            ).first()

            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            return jsonify({
                'agent_id': agent.agent_id,
                'agent_name': agent.name,
                'agent_type': agent.agent_type,
                'description': agent.description,
                'system_prompt': agent.system_prompt,
                'is_active': agent.is_enabled,
                'is_persistent': agent.is_persistent,
                'status': agent.status,
                'llm_provider': agent.llm_provider,
                'llm_model': agent.llm_model,
                'temperature': agent.temperature,
                'max_tokens': agent.max_tokens,
                'tools': agent.tools,
                'config': agent.config,
                'created_at': agent.created_at.isoformat() if agent.created_at else None,
            })

    except Exception as e:
        log.error(f"Error getting agent: {e}")
        return jsonify({'error': str(e)}), 500


@agents_bp.route('/api/agents/<agent_id>', methods=['PUT', 'PATCH'])
@login_required
def update_agent(agent_id):
    """Update agent configuration"""
    try:
        data = request.get_json()

        with db.get_db() as db_session:
            agent = db_session.query(Agent).filter(
                Agent.agent_id == agent_id
            ).first()

            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            # Update fields
            if 'agent_name' in data:
                agent.name = data['agent_name']
            if 'name' in data:
                agent.name = data['name']
            if 'description' in data:
                agent.description = data['description']
            if 'system_prompt' in data:
                agent.system_prompt = data['system_prompt']
            if 'is_enabled' in data:
                agent.is_enabled = data['is_enabled']
            if 'is_persistent' in data:
                agent.is_persistent = data['is_persistent']
            if 'llm_provider' in data:
                agent.llm_provider = data['llm_provider']
            if 'llm_model' in data:
                agent.llm_model = data['llm_model']
            if 'temperature' in data:
                agent.temperature = data['temperature']
            if 'max_tokens' in data:
                agent.max_tokens = data['max_tokens']
            if 'tools' in data:
                agent.tools = data['tools']
            if 'config' in data:
                agent.config = data['config']

            agent.updated_at = datetime.utcnow()
            db_session.commit()

            return jsonify({
                'agent_id': agent_id,
                'message': 'Agent updated successfully'
            })

    except Exception as e:
        log.error(f"Error updating agent: {e}")
        return jsonify({'error': str(e)}), 500


@agents_bp.route('/api/agents/<agent_id>', methods=['DELETE'])
@login_required
def delete_agent(agent_id):
    """Delete an agent"""
    try:
        with db.get_db() as db_session:
            agent = db_session.query(Agent).filter(
                Agent.agent_id == agent_id
            ).first()

            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            db_session.delete(agent)
            db_session.commit()

            return jsonify({
                'message': 'Agent deleted successfully'
            })

    except Exception as e:
        log.error(f"Error deleting agent: {e}")
        return jsonify({'error': str(e)}), 500


@agents_bp.route('/api/agents/<agent_id>/toggle', methods=['POST'])
@login_required
def toggle_agent(agent_id):
    """Toggle agent enabled status"""
    try:
        with db.get_db() as db_session:
            agent = db_session.query(Agent).filter(
                Agent.agent_id == agent_id
            ).first()

            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            agent.is_enabled = not agent.is_enabled
            agent.updated_at = datetime.utcnow()
            db_session.commit()

            return jsonify({
                'agent_id': agent_id,
                'is_active': agent.is_enabled
            })

    except Exception as e:
        log.error(f"Error toggling agent: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Agent Type and Tool Discovery Routes
# ============================================================================

@agents_bp.route('/api/agents/types', methods=['GET'])
@login_required
def get_agent_types():
    """Get available agent types"""
    try:
        from ai.agents import get_agent_types
        types = get_agent_types()
        return jsonify({'types': types})

    except Exception as e:
        log.error(f"Error getting agent types: {e}")
        return jsonify({'error': str(e)}), 500


@agents_bp.route('/api/agents/tools', methods=['GET'])
@login_required
def get_available_tools():
    """Get available tools for agents"""
    try:
        from ai.tools import get_registry, register_all_tools

        registry = register_all_tools()
        tools = []

        for tool in registry.get_all():
            tools.append({
                'name': tool.name,
                'description': tool.description,
                'category': tool.category,
                'risk_level': tool.risk_level,
                'requires_approval': tool.requires_approval,
                'input_schema': tool.input_schema,
            })

        return jsonify({'tools': tools})

    except Exception as e:
        log.error(f"Error getting tools: {e}")
        return jsonify({'error': str(e)}), 500


@agents_bp.route('/api/stats', methods=['GET'])
@login_required
def get_agent_stats():
    """Get agent statistics including sessions today"""
    try:
        with db.get_db() as db_session:
            # Get sessions created today
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            sessions_today = db_session.query(func.count(AgentSession.session_id)).filter(
                AgentSession.created_at >= today_start
            ).scalar() or 0

            # Get total sessions
            total_sessions = db_session.query(func.count(AgentSession.session_id)).scalar() or 0

            # Get active agents count
            active_agents = db_session.query(func.count(Agent.agent_id)).filter(
                Agent.is_enabled == True
            ).scalar() or 0

            return jsonify({
                'sessions_today': sessions_today,
                'total_sessions': total_sessions,
                'active_agents': active_agents,
            })

    except Exception as e:
        log.error(f"Error getting agent stats: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Agent Session Routes
# ============================================================================

@agents_bp.route('/api/agents/<agent_id>/sessions', methods=['GET'])
@login_required
def list_agent_sessions(agent_id):
    """List sessions for an agent"""
    try:
        from shared.netstacks_core.db.models import AgentSession

        limit = request.args.get('limit', 50, type=int)

        with db.get_db() as db_session:
            sessions = db_session.query(AgentSession).filter(
                AgentSession.agent_id == agent_id
            ).order_by(
                AgentSession.created_at.desc()
            ).limit(limit).all()

            return jsonify({
                'sessions': [
                    {
                        'session_id': s.session_id,
                        'status': s.status,
                        'trigger_type': s.trigger_type,
                        'started_at': s.started_at.isoformat() if s.started_at else None,
                        'completed_at': s.completed_at.isoformat() if s.completed_at else None,
                    }
                    for s in sessions
                ]
            })

    except Exception as e:
        log.error(f"Error listing sessions: {e}")
        return jsonify({'error': str(e)}), 500


@agents_bp.route('/api/sessions/<session_id>', methods=['GET'])
@login_required
def get_session_detail(session_id):
    """Get session details with messages and actions"""
    try:
        from shared.netstacks_core.db.models import AgentSession, AgentMessage, AgentAction

        with db.get_db() as db_session:
            session_obj = db_session.query(AgentSession).filter(
                AgentSession.session_id == session_id
            ).first()

            if not session_obj:
                return jsonify({'error': 'Session not found'}), 404

            messages = db_session.query(AgentMessage).filter(
                AgentMessage.session_id == session_id
            ).order_by(AgentMessage.created_at).all()

            actions = db_session.query(AgentAction).filter(
                AgentAction.session_id == session_id
            ).order_by(AgentAction.created_at).all()

            return jsonify({
                'session': {
                    'session_id': session_obj.session_id,
                    'agent_id': session_obj.agent_id,
                    'status': session_obj.status,
                    'trigger_type': session_obj.trigger_type,
                    'context': session_obj.context,
                    'started_at': session_obj.started_at.isoformat() if session_obj.started_at else None,
                    'completed_at': session_obj.completed_at.isoformat() if session_obj.completed_at else None,
                },
                'messages': [
                    {
                        'id': m.id,
                        'role': m.role,
                        'content': m.content,
                        'created_at': m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in messages
                ],
                'actions': [
                    {
                        'action_id': a.action_id,
                        'action_type': a.action_type,
                        'tool_name': a.tool_name,
                        'tool_input': a.tool_input,
                        'tool_output': a.tool_output,
                        'sequence': a.sequence,
                        'created_at': a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in actions
                ]
            })

    except Exception as e:
        log.error(f"Error getting session: {e}")
        return jsonify({'error': str(e)}), 500


@agents_bp.route('/api/sessions/<session_id>/messages', methods=['GET'])
@login_required
def get_session_messages(session_id):
    """Get messages for a session - used by assistant sidebar for history restoration"""
    try:
        from shared.netstacks_core.db.models import AgentSession, AgentMessage

        username = get_current_user()

        with db.get_db() as db_session:
            # Verify session belongs to current user
            session_obj = db_session.query(AgentSession).filter(
                AgentSession.session_id == session_id,
                AgentSession.started_by == username
            ).first()

            if not session_obj:
                return jsonify({'error': 'Session not found'}), 404

            messages = db_session.query(AgentMessage).filter(
                AgentMessage.session_id == session_id
            ).order_by(AgentMessage.created_at).all()

            return jsonify({
                'session_id': session_id,
                'status': session_obj.status,
                'messages': [
                    {
                        'role': m.role,
                        'content': m.content,
                    }
                    for m in messages
                ]
            })

    except Exception as e:
        log.error(f"Error getting session messages: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# LLM Provider Routes
# ============================================================================

@agents_bp.route('/api/llm/providers', methods=['GET'])
@login_required
def list_llm_providers():
    """List configured LLM providers"""
    try:
        from ai.llm import get_available_providers
        providers = get_available_providers()
        return jsonify({'providers': providers})

    except Exception as e:
        log.error(f"Error listing LLM providers: {e}")
        return jsonify({'error': str(e)}), 500


@agents_bp.route('/api/llm/providers', methods=['POST'])
@login_required
def configure_llm_provider():
    """Configure an LLM provider"""
    try:
        from shared.netstacks_core.db.models import LLMProvider
        from credential_encryption import encrypt_value

        data = request.get_json()

        with db.get_db() as db_session:
            # Check if provider exists
            provider = db_session.query(LLMProvider).filter(
                LLMProvider.name == data.get('name')
            ).first()

            if provider:
                # Update existing
                if data.get('api_key'):
                    provider.api_key = encrypt_value(data['api_key'])
                if 'default_model' in data:
                    provider.default_model = data['default_model']
                if 'is_enabled' in data:
                    provider.is_enabled = data['is_enabled']
                if 'is_default' in data:
                    # Unset other defaults first
                    if data['is_default']:
                        db_session.query(LLMProvider).update({'is_default': False})
                    provider.is_default = data['is_default']
            else:
                # Create new
                provider = LLMProvider(
                    name=data.get('name'),
                    display_name=data.get('display_name', data.get('name')),
                    api_key=encrypt_value(data.get('api_key', '')),
                    default_model=data.get('default_model'),
                    available_models=data.get('available_models', []),
                    is_enabled=data.get('is_enabled', True),
                    is_default=data.get('is_default', False),
                )
                db_session.add(provider)

            db_session.commit()

            return jsonify({
                'message': 'Provider configured successfully'
            })

    except ImportError:
        # Encryption not available
        return jsonify({'error': 'Credential encryption not configured'}), 500
    except Exception as e:
        log.error(f"Error configuring LLM provider: {e}")
        return jsonify({'error': str(e)}), 500
