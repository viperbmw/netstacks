"""
Alert Processor

Processes incoming alerts through AI agents for triage, correlation, and resolution.
This is the main entry point for the AI-powered alert workflow.

Workflow:
1. Alert ingested via webhook
2. Alert processor checks for correlation with existing alerts/incidents
3. If correlated: attach to existing incident (or update analysis)
4. If new: trigger triage agent for analysis
5. Triage agent decides whether to:
   - Resolve directly (transient/low-priority)
   - Create incident (significant issue)
   - Hand off to specialist (protocol-specific)
   - Escalate to humans (critical/complex)
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from threading import Thread

log = logging.getLogger(__name__)


class AlertProcessor:
    """
    Processes alerts through AI workflow.

    Responsibilities:
    - Alert correlation (group related alerts)
    - Trigger triage agent for new issues
    - Track AI analysis results
    - Manage incident creation decisions
    """

    # Correlation window - alerts within this time may be related
    CORRELATION_WINDOW_MINUTES = 15

    # Similarity threshold for alert correlation (0-1)
    SIMILARITY_THRESHOLD = 0.6

    def __init__(self):
        self.processing = {}  # Track alerts being processed

    def process_alert(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process an incoming alert through AI workflow.

        Args:
            alert_data: Alert data dict with alert_id, title, severity, etc.

        Returns:
            Processing result with status and any correlation/incident info
        """
        alert_id = alert_data.get('alert_id')
        log.info(f"Processing alert {alert_id}: {alert_data.get('title')}")

        try:
            # Step 1: Check for correlation with existing alerts/incidents
            correlation = self._find_correlation(alert_data)

            if correlation['correlated']:
                # Alert correlates with existing incident
                result = self._handle_correlated_alert(alert_data, correlation)
            else:
                # New issue - trigger AI triage
                result = self._trigger_ai_triage(alert_data)

            return result

        except Exception as e:
            log.error(f"Error processing alert {alert_id}: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e),
                'alert_id': alert_id
            }

    def process_alert_async(self, alert_data: Dict[str, Any]) -> None:
        """
        Process alert asynchronously (fire and forget).

        Use this for webhook handlers to not block the response.
        """
        thread = Thread(target=self.process_alert, args=(alert_data,))
        thread.daemon = True
        thread.start()

    def _find_correlation(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Find correlation with existing alerts or incidents.

        Correlation factors:
        - Same device within time window
        - Similar title/description
        - Same source alert type
        - Related to open incident
        """
        import database as db
        from models import Alert, Incident

        alert_id = alert_data.get('alert_id')
        device = alert_data.get('device')
        title = alert_data.get('title', '')
        source = alert_data.get('source', '')

        correlation_result = {
            'correlated': False,
            'incident_id': None,
            'related_alerts': [],
            'correlation_reason': None,
            'confidence': 0.0
        }

        with db.get_db() as session:
            # Time window for correlation
            window_start = datetime.utcnow() - timedelta(
                minutes=self.CORRELATION_WINDOW_MINUTES
            )

            # Check for recent alerts on same device that have incidents
            if device:
                log.info(f"Checking for device correlation: device={device}, window_start={window_start}")

                # Find alerts on same device linked to incidents
                device_alert = session.query(Alert).filter(
                    Alert.alert_id != alert_id,
                    Alert.device == device,
                    Alert.incident_id.isnot(None),
                    Alert.created_at >= window_start,
                ).order_by(Alert.created_at.desc()).first()

                if device_alert:
                    log.info(
                        f"Alert {alert_id} correlates with device alert {device_alert.alert_id} "
                        f"(incident: {device_alert.incident_id})"
                    )
                    correlation_result['correlated'] = True
                    correlation_result['incident_id'] = device_alert.incident_id
                    correlation_result['correlation_reason'] = 'same_device_incident'
                    correlation_result['confidence'] = 0.85
                    return correlation_result
                else:
                    # Debug: check if any alerts exist for this device
                    all_device_alerts = session.query(Alert).filter(
                        Alert.device == device,
                        Alert.incident_id.isnot(None),
                    ).all()
                    log.info(
                        f"No correlating alert in window for device {device}. "
                        f"Total alerts with incidents on device: {len(all_device_alerts)}"
                    )
                    for da in all_device_alerts:
                        log.info(f"  Found: {da.alert_id[:8]}... created_at={da.created_at}")

            # Check for open incidents with similar title
            if device or title:
                incidents = session.query(Incident).filter(
                    Incident.status.in_(['open', 'investigating', 'identified']),
                    Incident.created_at >= window_start,
                ).all()

                for incident in incidents:
                    # Check if incident relates to this device
                    incident_data = incident.incident_data or {}
                    affected_devices = incident_data.get('affected_devices', [])

                    if (device and device in affected_devices) or self._titles_similar(
                        title, incident.title
                    ):
                        correlation_result['correlated'] = True
                        correlation_result['incident_id'] = incident.incident_id
                        correlation_result['correlation_reason'] = 'incident_match'
                        correlation_result['confidence'] = 0.8
                        return correlation_result

            # Check for recent similar alerts
            recent_alerts = session.query(Alert).filter(
                Alert.alert_id != alert_id,
                Alert.created_at >= window_start,
                Alert.status.in_(['new', 'acknowledged', 'processing'])
            ).all()

            for existing_alert in recent_alerts:
                similarity = self._calculate_similarity(alert_data, {
                    'title': existing_alert.title,
                    'device': existing_alert.device,
                    'source': existing_alert.source,
                    'severity': existing_alert.severity
                })

                if similarity >= self.SIMILARITY_THRESHOLD:
                    correlation_result['related_alerts'].append({
                        'alert_id': existing_alert.alert_id,
                        'title': existing_alert.title,
                        'similarity': similarity
                    })

                    # If related alert has incident, correlate to that
                    if existing_alert.incident_id:
                        correlation_result['correlated'] = True
                        correlation_result['incident_id'] = existing_alert.incident_id
                        correlation_result['correlation_reason'] = 'similar_alert_with_incident'
                        correlation_result['confidence'] = similarity
                        return correlation_result

            # If we found related alerts but no incident, still flag for grouping
            if correlation_result['related_alerts']:
                correlation_result['correlation_reason'] = 'similar_alerts'
                correlation_result['confidence'] = max(
                    a['similarity'] for a in correlation_result['related_alerts']
                )

        return correlation_result

    def _calculate_similarity(
        self,
        alert1: Dict[str, Any],
        alert2: Dict[str, Any]
    ) -> float:
        """Calculate similarity score between two alerts."""
        score = 0.0
        weights = {
            'device': 0.4,
            'source': 0.2,
            'title': 0.3,
            'severity': 0.1
        }

        # Same device is a strong indicator
        if alert1.get('device') and alert1.get('device') == alert2.get('device'):
            score += weights['device']

        # Same source type
        if alert1.get('source') == alert2.get('source'):
            score += weights['source']

        # Title similarity
        if self._titles_similar(
            alert1.get('title', ''),
            alert2.get('title', '')
        ):
            score += weights['title']

        # Same severity
        if alert1.get('severity') == alert2.get('severity'):
            score += weights['severity']

        return score

    def _titles_similar(self, title1: str, title2: str) -> bool:
        """Check if two alert titles are similar."""
        if not title1 or not title2:
            return False

        # Simple word overlap check
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())

        # Remove common stopwords
        stopwords = {'the', 'a', 'an', 'is', 'on', 'for', 'at', 'in', 'to'}
        words1 = words1 - stopwords
        words2 = words2 - stopwords

        if not words1 or not words2:
            return False

        # Calculate Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return (intersection / union) >= 0.4

    def _handle_correlated_alert(
        self,
        alert_data: Dict[str, Any],
        correlation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle alert that correlates with existing incident."""
        import database as db
        from models import Alert, Incident

        alert_id = alert_data.get('alert_id')
        incident_id = correlation.get('incident_id')

        log.info(
            f"Alert {alert_id} correlates with incident {incident_id} "
            f"(reason: {correlation.get('correlation_reason')})"
        )

        with db.get_db() as session:
            # Link alert to incident
            alert = session.query(Alert).filter(
                Alert.alert_id == alert_id
            ).first()

            if alert:
                alert.incident_id = incident_id
                alert.status = 'correlated'

                # Update incident with new alert info
                incident = session.query(Incident).filter(
                    Incident.incident_id == incident_id
                ).first()

                if incident:
                    # Add to incident timeline
                    incident_data = incident.incident_data or {}
                    timeline = incident_data.get('timeline', [])
                    timeline.append({
                        'timestamp': datetime.utcnow().isoformat(),
                        'type': 'alert_correlated',
                        'alert_id': alert_id,
                        'alert_title': alert_data.get('title'),
                        'correlation_reason': correlation.get('correlation_reason')
                    })
                    incident_data['timeline'] = timeline
                    incident.incident_data = incident_data
                    incident.updated_at = datetime.utcnow()

                session.commit()

        return {
            'status': 'correlated',
            'alert_id': alert_id,
            'incident_id': incident_id,
            'correlation_reason': correlation.get('correlation_reason'),
            'confidence': correlation.get('confidence')
        }

    def _trigger_ai_triage(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger AI triage agent for a new alert.

        The triage agent will:
        1. Analyze the alert
        2. Gather diagnostic info if needed
        3. Decide whether to create incident, hand off, or resolve
        """
        from ai.agents import create_agent
        from ai.agents.base import AgentEventType
        from models import Alert, AgentSession, AgentMessage, AgentAction
        import database as db

        alert_id = alert_data.get('alert_id')

        log.info(f"Triggering triage agent for alert {alert_id}")

        # Update alert status
        with db.get_db() as session:
            alert = session.query(Alert).filter(
                Alert.alert_id == alert_id
            ).first()
            if alert:
                alert.status = 'processing'
                session.commit()

        try:
            # Create triage agent
            agent = create_agent('triage')

            # Create agent session record
            with db.get_db() as session:
                agent_session = AgentSession(
                    session_id=agent.session_id,
                    agent_id=None,  # System-triggered, not specific agent config
                    status='running',
                    trigger_type='alert',
                    trigger_data={
                        'alert_id': alert_id,
                        'alert_title': alert_data.get('title'),
                        'alert_severity': alert_data.get('severity')
                    }
                )
                session.add(agent_session)
                session.commit()

            # Build the triage message
            triage_message = self._build_triage_message(alert_data)

            # Run the agent
            result = {
                'status': 'processed',
                'alert_id': alert_id,
                'session_id': agent.session_id,
                'events': [],
                'incident_created': False,
                'incident_id': None,
                'handoff': None,
                'escalated': False
            }

            for event in agent.run(triage_message, context={'alert': alert_data}):
                event_dict = event.to_dict()
                result['events'].append(event_dict)

                # Track specific outcomes
                if event.type == AgentEventType.TOOL_RESULT:
                    if event.tool_name == 'create_incident':
                        tool_result = event.tool_result or {}
                        if tool_result.get('success'):
                            result['incident_created'] = True
                            result['incident_id'] = tool_result.get('data', {}).get('incident_id')

                            # Link alert to incident
                            self._link_alert_to_incident(
                                alert_id,
                                result['incident_id']
                            )

                elif event.type == AgentEventType.HANDOFF:
                    result['handoff'] = event.data

                elif event.type == AgentEventType.ESCALATION:
                    result['escalated'] = True

                # Store message/action in database
                self._record_agent_event(agent.session_id, event)

            # Update session status
            with db.get_db() as session:
                agent_session = session.query(AgentSession).filter(
                    AgentSession.session_id == agent.session_id
                ).first()
                if agent_session:
                    agent_session.status = 'completed'
                    agent_session.ended_at = datetime.utcnow()
                    session.commit()

            # Update alert status based on outcome
            self._update_alert_status(alert_id, result)

            log.info(
                f"Triage complete for alert {alert_id}: "
                f"incident_created={result['incident_created']}, "
                f"handoff={result['handoff'] is not None}, "
                f"escalated={result['escalated']}"
            )

            return result

        except Exception as e:
            log.error(f"Triage agent error for alert {alert_id}: {e}", exc_info=True)

            # Mark alert as needing manual review
            with db.get_db() as session:
                alert = session.query(Alert).filter(
                    Alert.alert_id == alert_id
                ).first()
                if alert:
                    alert.status = 'error'
                    session.commit()

            return {
                'status': 'error',
                'alert_id': alert_id,
                'error': str(e)
            }

    def _build_triage_message(self, alert_data: Dict[str, Any]) -> str:
        """Build the message to send to triage agent."""
        parts = [
            f"Analyze this incoming alert and determine the appropriate action:",
            f"",
            f"**Alert:** {alert_data.get('title', 'Unknown')}",
            f"**Severity:** {alert_data.get('severity', 'unknown')}",
            f"**Source:** {alert_data.get('source', 'unknown')}",
        ]

        if alert_data.get('device'):
            parts.append(f"**Device:** {alert_data.get('device')}")

        if alert_data.get('description'):
            parts.append(f"**Description:** {alert_data.get('description')}")

        # Add any additional alert data
        extra_data = alert_data.get('alert_data', {})
        if extra_data:
            parts.append("")
            parts.append("**Additional Data:**")
            for key, value in extra_data.items():
                if key not in ['title', 'severity', 'source', 'device', 'description']:
                    parts.append(f"- {key}: {value}")

        parts.extend([
            "",
            "Based on your analysis:",
            "1. If this is a significant issue requiring tracking, create an incident",
            "2. If it needs specialist analysis, hand off to the appropriate agent",
            "3. If it's critical and requires human attention, escalate",
            "4. If it's transient or self-resolving, explain your assessment",
            "",
            "Remember: Only create incidents for issues that warrant formal tracking. "
            "Not every alert needs an incident."
        ])

        return "\n".join(parts)

    def _link_alert_to_incident(self, alert_id: str, incident_id: str) -> None:
        """Link an alert to an incident."""
        import database as db
        from models import Alert

        with db.get_db() as session:
            alert = session.query(Alert).filter(
                Alert.alert_id == alert_id
            ).first()
            if alert:
                alert.incident_id = incident_id
                session.commit()

    def _update_alert_status(self, alert_id: str, result: Dict[str, Any]) -> None:
        """Update alert status based on triage result."""
        import database as db
        from models import Alert

        with db.get_db() as session:
            alert = session.query(Alert).filter(
                Alert.alert_id == alert_id
            ).first()
            if alert:
                if result.get('incident_created'):
                    alert.status = 'incident_created'
                elif result.get('escalated'):
                    alert.status = 'escalated'
                elif result.get('handoff'):
                    alert.status = 'handed_off'
                else:
                    alert.status = 'analyzed'
                session.commit()

    def _record_agent_event(self, session_id: str, event) -> None:
        """Record agent event to database."""
        import database as db
        from models import AgentMessage, AgentAction
        from ai.agents.base import AgentEventType

        try:
            with db.get_db() as session:
                if event.type in [
                    AgentEventType.THOUGHT,
                    AgentEventType.FINAL_RESPONSE
                ]:
                    message = AgentMessage(
                        session_id=session_id,
                        role='assistant',
                        content=event.content or ''
                    )
                    session.add(message)

                elif event.type in [
                    AgentEventType.TOOL_CALL,
                    AgentEventType.TOOL_RESULT
                ]:
                    action = AgentAction(
                        session_id=session_id,
                        action_type=event.type.value,
                        tool_name=event.tool_name,
                        tool_args=event.tool_args,
                        result=event.tool_result
                    )
                    session.add(action)

                session.commit()
        except Exception as e:
            log.error(f"Error recording agent event: {e}")


# Global processor instance
_processor = None


def get_processor() -> AlertProcessor:
    """Get the global alert processor instance."""
    global _processor
    if _processor is None:
        _processor = AlertProcessor()
    return _processor


def process_alert(alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process an alert through the AI workflow."""
    return get_processor().process_alert(alert_data)


def process_alert_async(alert_data: Dict[str, Any]) -> None:
    """Process an alert asynchronously."""
    get_processor().process_alert_async(alert_data)
