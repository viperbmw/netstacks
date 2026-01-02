# services/ai/app/routes/webhooks.py
"""
Alert webhook routes.

Provides endpoints for receiving alerts from external systems.
These endpoints do not require authentication.
"""

import logging
import uuid
from typing import Optional, Dict, Any, List

from fastapi import APIRouter
from pydantic import BaseModel

from netstacks_core.db import get_session, Alert as AlertModel

log = logging.getLogger(__name__)

router = APIRouter()


class GenericWebhookData(BaseModel):
    title: str = "Untitled Alert"
    severity: str = "warning"
    description: Optional[str] = None
    source: str = "generic"
    device: Optional[str] = None
    skip_ai: bool = False


class PrometheusAlert(BaseModel):
    status: str
    labels: Dict[str, str] = {}
    annotations: Dict[str, str] = {}
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None
    generatorURL: Optional[str] = None
    fingerprint: Optional[str] = None


class PrometheusWebhookData(BaseModel):
    version: str = "4"
    groupKey: str = ""
    status: str = "firing"
    receiver: str = ""
    groupLabels: Dict[str, str] = {}
    commonLabels: Dict[str, str] = {}
    commonAnnotations: Dict[str, str] = {}
    externalURL: str = ""
    alerts: List[PrometheusAlert] = []


class SolarWindsWebhookData(BaseModel):
    AlertID: Optional[str] = None
    AlertName: Optional[str] = None
    AlertMessage: Optional[str] = None
    Severity: Optional[str] = None
    NodeName: Optional[str] = None
    IP: Optional[str] = None
    AlertStatus: Optional[str] = None


@router.post("/generic", response_model=dict)
async def generic_webhook(data: GenericWebhookData):
    """
    Generic alert webhook - no authentication required.

    Use this for custom integrations or testing.
    """
    session = get_session()
    try:
        alert = AlertModel(
            alert_id=str(uuid.uuid4()),
            title=data.title,
            severity=data.severity,
            description=data.description,
            source=data.source,
            device=data.device,
            status="new",
        )
        session.add(alert)
        session.commit()

        log.info(f"Received generic webhook alert: {alert.alert_id}")

        return {
            "status": "received",
            "alert_id": alert.alert_id,
            "ai_processing": not data.skip_ai
        }
    finally:
        session.close()


@router.post("/prometheus", response_model=dict)
async def prometheus_webhook(data: PrometheusWebhookData):
    """
    Prometheus AlertManager webhook - no authentication required.

    Receives alerts in Prometheus AlertManager format.
    """
    session = get_session()
    try:
        created_ids = []

        for alert_data in data.alerts:
            labels = alert_data.labels
            annotations = alert_data.annotations

            # Map Prometheus severity to our severity
            severity = labels.get("severity", "warning")
            if severity not in ["critical", "high", "medium", "warning", "low", "info"]:
                severity = "warning"

            alert = AlertModel(
                alert_id=str(uuid.uuid4()),
                title=labels.get("alertname", "Prometheus Alert"),
                severity=severity,
                description=annotations.get("summary") or annotations.get("description"),
                source="prometheus",
                device=labels.get("instance"),
                status="new",
            )
            session.add(alert)
            created_ids.append(alert.alert_id)

        session.commit()

        log.info(f"Received Prometheus webhook with {len(created_ids)} alerts")

        return {
            "status": "received",
            "count": len(created_ids),
            "alert_ids": created_ids
        }
    finally:
        session.close()


@router.post("/solarwinds", response_model=dict)
async def solarwinds_webhook(data: SolarWindsWebhookData):
    """
    SolarWinds webhook - no authentication required.

    Receives alerts from SolarWinds Orion.
    """
    session = get_session()
    try:
        # Map SolarWinds severity
        severity_map = {
            "Critical": "critical",
            "Warning": "warning",
            "Informational": "info",
            "Info": "info",
        }
        severity = severity_map.get(data.Severity, "warning")

        alert = AlertModel(
            alert_id=str(uuid.uuid4()),
            title=data.AlertName or "SolarWinds Alert",
            severity=severity,
            description=data.AlertMessage,
            source="solarwinds",
            device=data.NodeName or data.IP,
            status="new",
        )
        session.add(alert)
        session.commit()

        log.info(f"Received SolarWinds webhook alert: {alert.alert_id}")

        return {
            "status": "received",
            "alert_id": alert.alert_id
        }
    finally:
        session.close()


@router.post("/zabbix", response_model=dict)
async def zabbix_webhook(data: dict):
    """
    Zabbix webhook - no authentication required.

    Receives alerts from Zabbix.
    """
    session = get_session()
    try:
        # Map Zabbix severity
        severity_map = {
            "Disaster": "critical",
            "High": "high",
            "Average": "warning",
            "Warning": "warning",
            "Information": "info",
            "Not classified": "low",
        }
        zabbix_severity = data.get("severity", "Warning")
        severity = severity_map.get(zabbix_severity, "warning")

        alert = AlertModel(
            alert_id=str(uuid.uuid4()),
            title=data.get("subject", data.get("name", "Zabbix Alert")),
            severity=severity,
            description=data.get("message", data.get("description")),
            source="zabbix",
            device=data.get("host", data.get("hostname")),
            status="new",
        )
        session.add(alert)
        session.commit()

        log.info(f"Received Zabbix webhook alert: {alert.alert_id}")

        return {
            "status": "received",
            "alert_id": alert.alert_id
        }
    finally:
        session.close()
