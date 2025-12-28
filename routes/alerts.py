"""
Alerts and Incidents Routes

HTTP routes for alert management, webhooks, and incidents.
"""

import logging
import uuid
from flask import Blueprint, render_template, request, jsonify, session
from functools import wraps
from datetime import datetime

import database as db

log = logging.getLogger(__name__)

alerts_bp = Blueprint('alerts', __name__, url_prefix='/alerts')


def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# Alert UI Routes
# ============================================================================

@alerts_bp.route('/')
@login_required
def alerts_page():
    """Alerts dashboard"""
    return render_template('alerts.html')


@alerts_bp.route('/incidents')
@login_required
def incidents_page():
    """Incidents management page"""
    return render_template('incidents.html')


# ============================================================================
# Webhook Endpoints (No Auth - External Systems)
# ============================================================================

@alerts_bp.route('/api/webhooks/generic', methods=['POST'])
def webhook_generic():
    """
    Generic webhook for incoming alerts.

    Expects JSON with at least:
    {
        "title": "Alert title",
        "severity": "warning",  # info, warning, error, critical
        "description": "Alert description",
        "source": "source-system"
    }
    """
    try:
        data = request.get_json() or {}

        alert = _create_alert(
            title=data.get('title', 'Unknown Alert'),
            description=data.get('description', ''),
            severity=data.get('severity', 'warning'),
            source=data.get('source', 'generic'),
            source_id=data.get('source_id', str(uuid.uuid4())),
            device=data.get('device'),
            alert_data=data
        )

        # Optionally trigger triage agent
        if data.get('auto_triage', False):
            _trigger_triage_agent(alert)

        return jsonify({
            'status': 'received',
            'alert_id': alert['alert_id']
        }), 201

    except Exception as e:
        log.error(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 500


@alerts_bp.route('/api/webhooks/prometheus', methods=['POST'])
def webhook_prometheus():
    """
    Prometheus AlertManager webhook.

    Expects Prometheus AlertManager webhook format.
    """
    try:
        data = request.get_json() or {}
        alerts_data = data.get('alerts', [])
        created_alerts = []

        for alert_data in alerts_data:
            labels = alert_data.get('labels', {})
            annotations = alert_data.get('annotations', {})

            # Map Prometheus severity to our format
            severity_map = {
                'critical': 'critical',
                'warning': 'warning',
                'info': 'info',
            }
            severity = severity_map.get(
                labels.get('severity', 'warning'),
                'warning'
            )

            alert = _create_alert(
                title=labels.get('alertname', 'Prometheus Alert'),
                description=annotations.get('description', annotations.get('summary', '')),
                severity=severity,
                source='prometheus',
                source_id=alert_data.get('fingerprint', str(uuid.uuid4())),
                device=labels.get('instance', labels.get('device')),
                alert_data={
                    'labels': labels,
                    'annotations': annotations,
                    'status': alert_data.get('status'),
                    'startsAt': alert_data.get('startsAt'),
                    'endsAt': alert_data.get('endsAt'),
                }
            )
            created_alerts.append(alert['alert_id'])

        return jsonify({
            'status': 'received',
            'alerts': created_alerts
        }), 201

    except Exception as e:
        log.error(f"Prometheus webhook error: {e}")
        return jsonify({'error': str(e)}), 500


@alerts_bp.route('/api/webhooks/solarwinds', methods=['POST'])
def webhook_solarwinds():
    """
    SolarWinds webhook.

    Expects SolarWinds alert format.
    """
    try:
        data = request.get_json() or {}

        # Map SolarWinds severity
        severity_map = {
            'Critical': 'critical',
            'Warning': 'warning',
            'Informational': 'info',
            'Normal': 'info',
        }

        alert = _create_alert(
            title=data.get('AlertName', 'SolarWinds Alert'),
            description=data.get('AlertMessage', ''),
            severity=severity_map.get(data.get('Severity', 'Warning'), 'warning'),
            source='solarwinds',
            source_id=data.get('AlertObjectID', str(uuid.uuid4())),
            device=data.get('NodeName', data.get('Node')),
            alert_data=data
        )

        return jsonify({
            'status': 'received',
            'alert_id': alert['alert_id']
        }), 201

    except Exception as e:
        log.error(f"SolarWinds webhook error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Alert API Routes
# ============================================================================

@alerts_bp.route('/api/alerts', methods=['GET'])
@login_required
def list_alerts():
    """List alerts with optional filtering"""
    try:
        from models import Alert

        # Filters
        severity = request.args.get('severity')
        status = request.args.get('status')
        source = request.args.get('source')
        limit = request.args.get('limit', 100, type=int)

        with db.get_db() as db_session:
            query = db_session.query(Alert)

            if severity:
                query = query.filter(Alert.severity == severity)
            if status:
                query = query.filter(Alert.status == status)
            if source:
                query = query.filter(Alert.source == source)

            alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()

            return jsonify({
                'alerts': [
                    {
                        'alert_id': a.alert_id,
                        'title': a.title,
                        'description': a.description,
                        'severity': a.severity,
                        'status': a.status,
                        'source': a.source,
                        'device': a.device,
                        'incident_id': a.incident_id,
                        'created_at': a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in alerts
                ]
            })

    except Exception as e:
        log.error(f"Error listing alerts: {e}")
        return jsonify({'error': str(e)}), 500


@alerts_bp.route('/api/alerts/<alert_id>', methods=['GET'])
@login_required
def get_alert(alert_id):
    """Get alert details"""
    try:
        from models import Alert

        with db.get_db() as db_session:
            alert = db_session.query(Alert).filter(
                Alert.alert_id == alert_id
            ).first()

            if not alert:
                return jsonify({'error': 'Alert not found'}), 404

            return jsonify({
                'alert_id': alert.alert_id,
                'title': alert.title,
                'description': alert.description,
                'severity': alert.severity,
                'status': alert.status,
                'source': alert.source,
                'source_id': alert.source_id,
                'device': alert.device,
                'incident_id': alert.incident_id,
                'alert_data': alert.alert_data,
                'created_at': alert.created_at.isoformat() if alert.created_at else None,
                'acknowledged_at': alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                'acknowledged_by': alert.acknowledged_by,
            })

    except Exception as e:
        log.error(f"Error getting alert: {e}")
        return jsonify({'error': str(e)}), 500


@alerts_bp.route('/api/alerts/<alert_id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_alert(alert_id):
    """Acknowledge an alert"""
    try:
        from models import Alert

        username = session.get('username', 'unknown')

        with db.get_db() as db_session:
            alert = db_session.query(Alert).filter(
                Alert.alert_id == alert_id
            ).first()

            if not alert:
                return jsonify({'error': 'Alert not found'}), 404

            alert.status = 'acknowledged'
            alert.acknowledged_at = datetime.utcnow()
            alert.acknowledged_by = username
            db_session.commit()

            return jsonify({'message': 'Alert acknowledged'})

    except Exception as e:
        log.error(f"Error acknowledging alert: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Incident API Routes
# ============================================================================

@alerts_bp.route('/api/incidents', methods=['GET'])
@login_required
def list_incidents():
    """List incidents"""
    try:
        from models import Incident

        status = request.args.get('status')
        limit = request.args.get('limit', 50, type=int)

        with db.get_db() as db_session:
            query = db_session.query(Incident)

            if status:
                query = query.filter(Incident.status == status)

            incidents = query.order_by(Incident.created_at.desc()).limit(limit).all()

            return jsonify({
                'incidents': [
                    {
                        'incident_id': i.incident_id,
                        'title': i.title,
                        'description': i.description,
                        'severity': i.severity,
                        'status': i.status,
                        'source': i.source,
                        'created_at': i.created_at.isoformat() if i.created_at else None,
                        'resolved_at': i.resolved_at.isoformat() if i.resolved_at else None,
                    }
                    for i in incidents
                ]
            })

    except Exception as e:
        log.error(f"Error listing incidents: {e}")
        return jsonify({'error': str(e)}), 500


@alerts_bp.route('/api/incidents/<incident_id>', methods=['GET'])
@login_required
def get_incident(incident_id):
    """Get incident details with associated alerts"""
    try:
        from models import Incident, Alert

        with db.get_db() as db_session:
            incident = db_session.query(Incident).filter(
                Incident.incident_id == incident_id
            ).first()

            if not incident:
                return jsonify({'error': 'Incident not found'}), 404

            # Get associated alerts
            alerts = db_session.query(Alert).filter(
                Alert.incident_id == incident_id
            ).all()

            return jsonify({
                'incident_id': incident.incident_id,
                'title': incident.title,
                'description': incident.description,
                'severity': incident.severity,
                'status': incident.status,
                'source': incident.source,
                'resolution': incident.resolution,
                'incident_data': incident.incident_data,
                'created_at': incident.created_at.isoformat() if incident.created_at else None,
                'resolved_at': incident.resolved_at.isoformat() if incident.resolved_at else None,
                'alerts': [
                    {
                        'alert_id': a.alert_id,
                        'title': a.title,
                        'severity': a.severity,
                    }
                    for a in alerts
                ]
            })

    except Exception as e:
        log.error(f"Error getting incident: {e}")
        return jsonify({'error': str(e)}), 500


@alerts_bp.route('/api/incidents/<incident_id>', methods=['PATCH'])
@login_required
def update_incident(incident_id):
    """Update incident status or details"""
    try:
        from models import Incident

        data = request.get_json()

        with db.get_db() as db_session:
            incident = db_session.query(Incident).filter(
                Incident.incident_id == incident_id
            ).first()

            if not incident:
                return jsonify({'error': 'Incident not found'}), 404

            if 'status' in data:
                incident.status = data['status']
                if data['status'] == 'resolved':
                    incident.resolved_at = datetime.utcnow()
            if 'resolution' in data:
                incident.resolution = data['resolution']
            if 'severity' in data:
                incident.severity = data['severity']

            incident.updated_at = datetime.utcnow()
            db_session.commit()

            return jsonify({'message': 'Incident updated'})

    except Exception as e:
        log.error(f"Error updating incident: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Helper Functions
# ============================================================================

def _create_alert(title, description, severity, source, source_id, device=None, alert_data=None):
    """Create alert in database"""
    try:
        from models import Alert

        alert_id = str(uuid.uuid4())

        with db.get_db() as db_session:
            alert = Alert(
                alert_id=alert_id,
                title=title,
                description=description,
                severity=severity,
                status='new',
                source=source,
                source_id=source_id,
                device=device,
                alert_data=alert_data or {},
            )
            db_session.add(alert)
            db_session.commit()

            log.info(f"Created alert {alert_id}: {title}")

            return {
                'alert_id': alert_id,
                'title': title,
                'severity': severity,
            }

    except Exception as e:
        log.error(f"Error creating alert: {e}")
        raise


def _trigger_triage_agent(alert_data):
    """Trigger triage agent for an alert"""
    try:
        from ai.agents import create_agent

        agent = create_agent('triage')
        context = {
            'alert': alert_data,
            'trigger_type': 'alert',
        }

        # Run agent asynchronously (would use Celery in production)
        # For now, just log the intent
        log.info(f"Would trigger triage agent for alert {alert_data['alert_id']}")

    except Exception as e:
        log.error(f"Error triggering triage agent: {e}")
