"""
Approval Workflow Routes

HTTP routes for managing pending approvals for high-risk agent actions.
"""

import logging
import uuid
from flask import Blueprint, render_template, request, jsonify
from datetime import datetime

import database as db
from routes.auth import login_required, get_current_user

log = logging.getLogger(__name__)

approvals_bp = Blueprint('approvals', __name__, url_prefix='/approvals')


# ============================================================================
# Approval UI Routes
# ============================================================================

@approvals_bp.route('/')
@login_required
def approvals_page():
    """Pending approvals page"""
    return render_template('approvals.html')


# ============================================================================
# Approval API Routes
# ============================================================================

@approvals_bp.route('/api/approvals', methods=['GET'])
@login_required
def list_pending_approvals():
    """List pending approvals"""
    try:
        from shared.netstacks_core.db.models import PendingApproval

        status = request.args.get('status', 'pending')
        limit = request.args.get('limit', 50, type=int)

        with db.get_db() as db_session:
            query = db_session.query(PendingApproval)

            if status != 'all':
                query = query.filter(PendingApproval.status == status)

            approvals = query.order_by(
                PendingApproval.created_at.desc()
            ).limit(limit).all()

            return jsonify({
                'approvals': [
                    {
                        'approval_id': a.approval_id,
                        'session_id': a.session_id,
                        'agent_id': a.agent_id,
                        'action_type': a.action_type,
                        'action_summary': a.action_summary,
                        'action_details': a.action_details,
                        'risk_level': a.risk_level,
                        'status': a.status,
                        'expires_at': a.expires_at.isoformat() if a.expires_at else None,
                        'created_at': a.created_at.isoformat() if a.created_at else None,
                        'reviewed_by': a.reviewed_by,
                        'reviewed_at': a.reviewed_at.isoformat() if a.reviewed_at else None,
                    }
                    for a in approvals
                ]
            })

    except Exception as e:
        log.error(f"Error listing approvals: {e}")
        return jsonify({'error': str(e)}), 500


@approvals_bp.route('/api/approvals/<approval_id>', methods=['GET'])
@login_required
def get_approval(approval_id):
    """Get approval details"""
    try:
        from shared.netstacks_core.db.models import PendingApproval

        with db.get_db() as db_session:
            approval = db_session.query(PendingApproval).filter(
                PendingApproval.approval_id == approval_id
            ).first()

            if not approval:
                return jsonify({'error': 'Approval not found'}), 404

            return jsonify({
                'approval_id': approval.approval_id,
                'session_id': approval.session_id,
                'agent_id': approval.agent_id,
                'action_type': approval.action_type,
                'action_summary': approval.action_summary,
                'action_details': approval.action_details,
                'risk_level': approval.risk_level,
                'status': approval.status,
                'expires_at': approval.expires_at.isoformat() if approval.expires_at else None,
                'created_at': approval.created_at.isoformat() if approval.created_at else None,
                'reviewed_by': approval.reviewed_by,
                'reviewed_at': approval.reviewed_at.isoformat() if approval.reviewed_at else None,
                'review_notes': approval.review_notes,
            })

    except Exception as e:
        log.error(f"Error getting approval: {e}")
        return jsonify({'error': str(e)}), 500


@approvals_bp.route('/api/approvals/<approval_id>/approve', methods=['POST'])
@login_required
def approve_action(approval_id):
    """Approve a pending action"""
    try:
        from shared.netstacks_core.db.models import PendingApproval

        data = request.get_json() or {}
        username = get_current_user()

        with db.get_db() as db_session:
            approval = db_session.query(PendingApproval).filter(
                PendingApproval.approval_id == approval_id
            ).first()

            if not approval:
                return jsonify({'error': 'Approval not found'}), 404

            if approval.status != 'pending':
                return jsonify({
                    'error': f'Approval already {approval.status}'
                }), 400

            # Check expiration
            if approval.expires_at and approval.expires_at < datetime.utcnow():
                approval.status = 'expired'
                db_session.commit()
                return jsonify({'error': 'Approval has expired'}), 400

            approval.status = 'approved'
            approval.reviewed_by = username
            approval.reviewed_at = datetime.utcnow()
            approval.review_notes = data.get('notes', '')
            db_session.commit()

            # Notify agent via WebSocket (if session is active)
            _notify_agent_approval(approval.session_id, approval_id, True, username)

            return jsonify({
                'message': 'Action approved',
                'approval_id': approval_id
            })

    except Exception as e:
        log.error(f"Error approving action: {e}")
        return jsonify({'error': str(e)}), 500


@approvals_bp.route('/api/approvals/<approval_id>/reject', methods=['POST'])
@login_required
def reject_action(approval_id):
    """Reject a pending action"""
    try:
        from shared.netstacks_core.db.models import PendingApproval

        data = request.get_json() or {}
        username = get_current_user()
        reason = data.get('reason', 'No reason provided')

        with db.get_db() as db_session:
            approval = db_session.query(PendingApproval).filter(
                PendingApproval.approval_id == approval_id
            ).first()

            if not approval:
                return jsonify({'error': 'Approval not found'}), 404

            if approval.status != 'pending':
                return jsonify({
                    'error': f'Approval already {approval.status}'
                }), 400

            approval.status = 'rejected'
            approval.reviewed_by = username
            approval.reviewed_at = datetime.utcnow()
            approval.review_notes = reason
            db_session.commit()

            # Notify agent via WebSocket
            _notify_agent_approval(approval.session_id, approval_id, False, username)

            return jsonify({
                'message': 'Action rejected',
                'approval_id': approval_id
            })

    except Exception as e:
        log.error(f"Error rejecting action: {e}")
        return jsonify({'error': str(e)}), 500


@approvals_bp.route('/api/approvals/stats', methods=['GET'])
@login_required
def get_approval_stats():
    """Get approval statistics"""
    try:
        from shared.netstacks_core.db.models import PendingApproval
        from sqlalchemy import func

        with db.get_db() as db_session:
            # Count by status
            status_counts = db_session.query(
                PendingApproval.status,
                func.count(PendingApproval.approval_id)
            ).group_by(PendingApproval.status).all()

            # Count by risk level
            risk_counts = db_session.query(
                PendingApproval.risk_level,
                func.count(PendingApproval.approval_id)
            ).group_by(PendingApproval.risk_level).all()

            return jsonify({
                'by_status': {s[0]: s[1] for s in status_counts},
                'by_risk_level': {r[0]: r[1] for r in risk_counts},
            })

    except Exception as e:
        log.error(f"Error getting approval stats: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Helper Functions
# ============================================================================

def create_approval_request(
    session_id: str,
    agent_id: str,
    action_type: str,
    action_summary: str,
    action_details: dict,
    risk_level: str = 'high',
    expires_minutes: int = 30
) -> str:
    """
    Create a pending approval request.

    Args:
        session_id: Agent session ID
        agent_id: Agent ID
        action_type: Type of action (e.g., 'device_config', 'execute_mop')
        action_summary: Brief description of the action
        action_details: Full details of the action
        risk_level: Risk level (medium, high, critical)
        expires_minutes: Minutes until approval expires

    Returns:
        Approval ID
    """
    try:
        from shared.netstacks_core.db.models import PendingApproval
        from datetime import timedelta

        approval_id = str(uuid.uuid4())

        with db.get_db() as db_session:
            approval = PendingApproval(
                approval_id=approval_id,
                session_id=session_id,
                agent_id=agent_id,
                action_type=action_type,
                action_summary=action_summary,
                action_details=action_details,
                risk_level=risk_level,
                status='pending',
                expires_at=datetime.utcnow() + timedelta(minutes=expires_minutes),
            )
            db_session.add(approval)
            db_session.commit()

            log.info(f"Created approval request {approval_id} for {action_type}")

        return approval_id

    except Exception as e:
        log.error(f"Error creating approval request: {e}")
        raise


def _notify_agent_approval(session_id: str, approval_id: str, approved: bool, username: str):
    """Notify agent of approval decision via WebSocket"""
    try:
        from routes.agent_websocket import active_sessions

        if session_id in active_sessions:
            session_data = active_sessions[session_id]
            socket_id = session_data.get('socket_id')

            if socket_id:
                # This would emit via SocketIO
                # In practice, this needs access to the socketio instance
                log.info(
                    f"Would notify session {session_id} of "
                    f"{'approval' if approved else 'rejection'} "
                    f"by {username}"
                )

    except Exception as e:
        log.error(f"Error notifying agent: {e}")


def check_expired_approvals():
    """Check and expire old approval requests"""
    try:
        from shared.netstacks_core.db.models import PendingApproval

        with db.get_db() as db_session:
            expired = db_session.query(PendingApproval).filter(
                PendingApproval.status == 'pending',
                PendingApproval.expires_at < datetime.utcnow()
            ).all()

            for approval in expired:
                approval.status = 'expired'

            if expired:
                db_session.commit()
                log.info(f"Expired {len(expired)} approval requests")

    except Exception as e:
        log.error(f"Error checking expired approvals: {e}")
