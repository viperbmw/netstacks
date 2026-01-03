# services/ai/app/services/agent_tools.py
"""
Agent Tools Module

Defines tools available to AI agents for network operations.
Each tool has a schema for the LLM and an execute function.
"""

import logging
import httpx
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)

# Internal service URLs (within Docker network)
DEVICES_SERVICE_URL = "http://devices:8004"
CONFIG_SERVICE_URL = "http://config:8002"
TASKS_SERVICE_URL = "http://tasks:8006"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ToolDefinition:
    """Definition of an agent tool."""
    name: str
    description: str
    category: str
    risk_level: RiskLevel
    requires_approval: bool
    input_schema: Dict[str, Any]


# ============================================================================
# Tool Definitions
# ============================================================================

TOOL_DEFINITIONS: Dict[str, ToolDefinition] = {
    "get_devices": ToolDefinition(
        name="get_devices",
        description="Get a list of network devices. Can filter by platform, site, or search query.",
        category="device",
        risk_level=RiskLevel.LOW,
        requires_approval=False,
        input_schema={
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Optional search query to filter devices by name"
                },
                "platform": {
                    "type": "string",
                    "description": "Filter by platform (e.g., cisco_ios, juniper_junos)"
                },
                "site": {
                    "type": "string",
                    "description": "Filter by site location"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of devices to return",
                    "default": 50
                }
            },
            "required": []
        }
    ),

    "get_device_details": ToolDefinition(
        name="get_device_details",
        description="Get detailed information about a specific device including its configuration, credentials status, and recent backups.",
        category="device",
        risk_level=RiskLevel.LOW,
        requires_approval=False,
        input_schema={
            "type": "object",
            "properties": {
                "device_name": {
                    "type": "string",
                    "description": "The name of the device to get details for"
                }
            },
            "required": ["device_name"]
        }
    ),

    "run_show_command": ToolDefinition(
        name="run_show_command",
        description="Run a show command on a network device to gather diagnostic information. Only 'show' commands are allowed for safety.",
        category="device",
        risk_level=RiskLevel.LOW,
        requires_approval=False,
        input_schema={
            "type": "object",
            "properties": {
                "device_name": {
                    "type": "string",
                    "description": "The name of the device to run the command on"
                },
                "command": {
                    "type": "string",
                    "description": "The show command to run (must start with 'show')"
                }
            },
            "required": ["device_name", "command"]
        }
    ),

    "get_device_config": ToolDefinition(
        name="get_device_config",
        description="Get the running configuration backup for a device.",
        category="device",
        risk_level=RiskLevel.LOW,
        requires_approval=False,
        input_schema={
            "type": "object",
            "properties": {
                "device_name": {
                    "type": "string",
                    "description": "The name of the device"
                }
            },
            "required": ["device_name"]
        }
    ),

    "search_knowledge": ToolDefinition(
        name="search_knowledge",
        description="Search the knowledge base for relevant documentation, runbooks, and troubleshooting guides.",
        category="knowledge",
        risk_level=RiskLevel.LOW,
        requires_approval=False,
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "collection": {
                    "type": "string",
                    "description": "Optional collection to search in (e.g., 'runbook', 'vendor', 'protocol')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    ),

    "get_alerts": ToolDefinition(
        name="get_alerts",
        description="Get recent alerts from the monitoring system.",
        category="incident",
        risk_level=RiskLevel.LOW,
        requires_approval=False,
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status (open, acknowledged, resolved)",
                    "enum": ["open", "acknowledged", "resolved"]
                },
                "severity": {
                    "type": "string",
                    "description": "Filter by severity (critical, high, medium, low)",
                    "enum": ["critical", "high", "medium", "low"]
                },
                "device": {
                    "type": "string",
                    "description": "Filter by device name"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of alerts to return",
                    "default": 20
                }
            },
            "required": []
        }
    ),

    "create_incident": ToolDefinition(
        name="create_incident",
        description="Create a new incident ticket for tracking and escalation.",
        category="incident",
        risk_level=RiskLevel.MEDIUM,
        requires_approval=False,
        input_schema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short title for the incident"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the incident"
                },
                "severity": {
                    "type": "string",
                    "description": "Incident severity",
                    "enum": ["critical", "high", "medium", "low"]
                },
                "affected_devices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of affected device names"
                }
            },
            "required": ["title", "description", "severity"]
        }
    ),

    "update_incident": ToolDefinition(
        name="update_incident",
        description="Update an existing incident with new information or status.",
        category="incident",
        risk_level=RiskLevel.MEDIUM,
        requires_approval=False,
        input_schema={
            "type": "object",
            "properties": {
                "incident_id": {
                    "type": "string",
                    "description": "The incident ID to update"
                },
                "status": {
                    "type": "string",
                    "description": "New status",
                    "enum": ["open", "investigating", "resolved", "closed"]
                },
                "notes": {
                    "type": "string",
                    "description": "Notes to add to the incident"
                },
                "resolution": {
                    "type": "string",
                    "description": "Resolution description if resolving"
                }
            },
            "required": ["incident_id"]
        }
    ),

    "deploy_config": ToolDefinition(
        name="deploy_config",
        description="Deploy a configuration template to one or more devices. This is a HIGH RISK operation that modifies device configuration.",
        category="config",
        risk_level=RiskLevel.HIGH,
        requires_approval=True,
        input_schema={
            "type": "object",
            "properties": {
                "template_name": {
                    "type": "string",
                    "description": "Name of the configuration template to deploy"
                },
                "devices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of device names to deploy to"
                },
                "variables": {
                    "type": "object",
                    "description": "Template variables"
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, only preview changes without applying",
                    "default": True
                }
            },
            "required": ["template_name", "devices"]
        }
    ),

    "handoff_to_specialist": ToolDefinition(
        name="handoff_to_specialist",
        description="Hand off the conversation to a specialist agent (BGP, OSPF, IS-IS, or General). Use this when you identify a specific protocol issue.",
        category="workflow",
        risk_level=RiskLevel.LOW,
        requires_approval=False,
        input_schema={
            "type": "object",
            "properties": {
                "target_agent": {
                    "type": "string",
                    "description": "The specialist agent type to hand off to",
                    "enum": ["bgp", "ospf", "isis", "general"]
                },
                "summary": {
                    "type": "string",
                    "description": "Summary of the issue and findings so far"
                },
                "context": {
                    "type": "object",
                    "description": "Relevant context data to pass to the specialist"
                }
            },
            "required": ["target_agent", "summary"]
        }
    ),

    "escalate_to_human": ToolDefinition(
        name="escalate_to_human",
        description="Escalate the issue to a human NOC operator when the problem is beyond agent capabilities or requires human judgment.",
        category="workflow",
        risk_level=RiskLevel.LOW,
        requires_approval=False,
        input_schema={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Reason for escalation"
                },
                "summary": {
                    "type": "string",
                    "description": "Summary of investigation and findings"
                },
                "recommended_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recommended actions for the human operator"
                },
                "urgency": {
                    "type": "string",
                    "description": "Urgency level",
                    "enum": ["low", "medium", "high", "critical"]
                }
            },
            "required": ["reason", "summary"]
        }
    ),
}


def get_tool_definitions(tool_names: Optional[List[str]] = None) -> List[Dict]:
    """
    Get tool definitions formatted for LLM APIs.

    Args:
        tool_names: Optional list of tool names to include. If None, returns all tools.

    Returns:
        List of tool definitions with name, description, and input_schema.
    """
    tools = []

    for name, tool in TOOL_DEFINITIONS.items():
        if tool_names and name not in tool_names:
            continue

        tools.append({
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        })

    return tools


def get_tool_info(tool_name: str) -> Optional[ToolDefinition]:
    """Get full tool information including risk level and approval requirements."""
    return TOOL_DEFINITIONS.get(tool_name)


# ============================================================================
# Tool Execution
# ============================================================================

async def execute_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Execute a tool and return the result.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        context: Optional context (session info, auth token, etc.)

    Returns:
        Tool execution result
    """
    context = context or {}

    executors = {
        "get_devices": _execute_get_devices,
        "get_device_details": _execute_get_device_details,
        "run_show_command": _execute_run_show_command,
        "get_device_config": _execute_get_device_config,
        "search_knowledge": _execute_search_knowledge,
        "get_alerts": _execute_get_alerts,
        "create_incident": _execute_create_incident,
        "update_incident": _execute_update_incident,
        "deploy_config": _execute_deploy_config,
        "handoff_to_specialist": _execute_handoff,
        "escalate_to_human": _execute_escalate,
    }

    executor = executors.get(tool_name)
    if not executor:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return await executor(tool_input, context)
    except Exception as e:
        log.error(f"Tool execution error ({tool_name}): {e}", exc_info=True)
        return {"error": str(e)}


async def _execute_get_devices(params: Dict, context: Dict) -> Dict:
    """Get list of devices from the devices service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            query_params = {}
            if params.get("search"):
                query_params["search"] = params["search"]
            if params.get("platform"):
                query_params["platform"] = params["platform"]
            if params.get("site"):
                query_params["site"] = params["site"]
            query_params["limit"] = params.get("limit", 50)

            headers = _get_auth_headers(context)
            response = await client.get(
                f"{DEVICES_SERVICE_URL}/api/devices",
                params=query_params,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            devices = data.get("devices", [])
            return {
                "success": True,
                "count": len(devices),
                "devices": [
                    {
                        "name": d.get("device_name") or d.get("name"),
                        "ip": d.get("host"),
                        "platform": d.get("platform"),
                        "site": d.get("site"),
                        "enabled": d.get("is_enabled", True),
                    }
                    for d in devices
                ]
            }
        except httpx.HTTPError as e:
            return {"error": f"Failed to get devices: {e}"}


async def _execute_get_device_details(params: Dict, context: Dict) -> Dict:
    """Get detailed device information."""
    device_name = params.get("device_name")
    if not device_name:
        return {"error": "device_name is required"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            headers = _get_auth_headers(context)
            response = await client.get(
                f"{DEVICES_SERVICE_URL}/api/devices/{device_name}",
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            device = data.get("device", data)
            return {
                "success": True,
                "device": {
                    "name": device.get("device_name") or device.get("name"),
                    "ip": device.get("host"),
                    "platform": device.get("platform"),
                    "site": device.get("site"),
                    "enabled": device.get("is_enabled", True),
                    "has_credentials": device.get("has_credentials", False),
                    "last_backup": device.get("last_backup"),
                    "variables": device.get("variables", {}),
                }
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": f"Device '{device_name}' not found"}
            return {"error": f"Failed to get device details: {e}"}
        except httpx.HTTPError as e:
            return {"error": f"Failed to get device details: {e}"}


async def _execute_run_show_command(params: Dict, context: Dict) -> Dict:
    """Run a show command on a device."""
    device_name = params.get("device_name")
    command = params.get("command", "").strip()

    if not device_name:
        return {"error": "device_name is required"}
    if not command:
        return {"error": "command is required"}

    # Security: Only allow show commands
    if not command.lower().startswith("show"):
        return {"error": "Only 'show' commands are allowed for safety. Use deploy_config for configuration changes."}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            headers = _get_auth_headers(context)
            response = await client.post(
                f"{TASKS_SERVICE_URL}/api/tasks/run-command",
                json={
                    "device_name": device_name,
                    "command": command
                },
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            return {
                "success": True,
                "device": device_name,
                "command": command,
                "output": data.get("output", data.get("result", "")),
            }
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_detail = e.response.json().get("detail", "")
            except Exception:
                pass
            return {"error": f"Failed to run command: {error_detail or str(e)}"}
        except httpx.HTTPError as e:
            return {"error": f"Failed to run command: {e}"}


async def _execute_get_device_config(params: Dict, context: Dict) -> Dict:
    """Get device configuration backup."""
    device_name = params.get("device_name")
    if not device_name:
        return {"error": "device_name is required"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            headers = _get_auth_headers(context)
            response = await client.get(
                f"{DEVICES_SERVICE_URL}/api/config-backups",
                params={"device": device_name, "limit": 1},
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            backups = data.get("backups", [])
            if not backups:
                return {"error": f"No configuration backup found for device '{device_name}'"}

            backup = backups[0]
            return {
                "success": True,
                "device": device_name,
                "backup_id": backup.get("backup_id"),
                "backup_date": backup.get("created_at"),
                "config": backup.get("config_content", "(config content available via backup_id)"),
            }
        except httpx.HTTPError as e:
            return {"error": f"Failed to get device config: {e}"}


async def _execute_search_knowledge(params: Dict, context: Dict) -> Dict:
    """Search the knowledge base."""
    query = params.get("query")
    if not query:
        return {"error": "query is required"}

    # For now, return a placeholder since knowledge base may not be populated
    # In production, this would query the knowledge service
    return {
        "success": True,
        "query": query,
        "results": [],
        "message": "Knowledge base search not yet populated. Add documents via Settings > Knowledge Base."
    }


async def _execute_get_alerts(params: Dict, context: Dict) -> Dict:
    """Get alerts from the AI service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            headers = _get_auth_headers(context)
            query_params = {}
            if params.get("status"):
                query_params["status"] = params["status"]
            if params.get("severity"):
                query_params["severity"] = params["severity"]
            if params.get("device"):
                query_params["device"] = params["device"]
            query_params["limit"] = params.get("limit", 20)

            # Alerts are in the AI service (this service)
            response = await client.get(
                "http://localhost:8003/api/alerts",
                params=query_params,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            return {
                "success": True,
                "count": len(data.get("alerts", [])),
                "alerts": data.get("alerts", [])
            }
        except httpx.HTTPError as e:
            return {"error": f"Failed to get alerts: {e}"}


async def _execute_create_incident(params: Dict, context: Dict) -> Dict:
    """Create a new incident."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            headers = _get_auth_headers(context)
            response = await client.post(
                "http://localhost:8003/api/incidents",
                json={
                    "title": params.get("title"),
                    "description": params.get("description"),
                    "severity": params.get("severity"),
                    "affected_devices": params.get("affected_devices", []),
                    "source": "agent",
                },
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            return {
                "success": True,
                "incident_id": data.get("incident_id"),
                "message": f"Incident created: {params.get('title')}"
            }
        except httpx.HTTPError as e:
            return {"error": f"Failed to create incident: {e}"}


async def _execute_update_incident(params: Dict, context: Dict) -> Dict:
    """Update an incident."""
    incident_id = params.get("incident_id")
    if not incident_id:
        return {"error": "incident_id is required"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            headers = _get_auth_headers(context)
            update_data = {}
            if params.get("status"):
                update_data["status"] = params["status"]
            if params.get("notes"):
                update_data["notes"] = params["notes"]
            if params.get("resolution"):
                update_data["resolution"] = params["resolution"]

            response = await client.patch(
                f"http://localhost:8003/api/incidents/{incident_id}",
                json=update_data,
                headers=headers
            )
            response.raise_for_status()

            return {
                "success": True,
                "incident_id": incident_id,
                "message": "Incident updated"
            }
        except httpx.HTTPError as e:
            return {"error": f"Failed to update incident: {e}"}


async def _execute_deploy_config(params: Dict, context: Dict) -> Dict:
    """Deploy configuration to devices."""
    # This requires approval - the executor should check approval status before calling
    return {
        "success": False,
        "error": "Configuration deployment requires approval. Please wait for approval before proceeding.",
        "requires_approval": True,
        "template": params.get("template_name"),
        "devices": params.get("devices", []),
    }


async def _execute_handoff(params: Dict, context: Dict) -> Dict:
    """Hand off to a specialist agent."""
    return {
        "success": True,
        "handoff": {
            "target_agent": params.get("target_agent"),
            "summary": params.get("summary"),
            "context": params.get("context", {}),
        },
        "message": f"Handing off to {params.get('target_agent')} specialist agent"
    }


async def _execute_escalate(params: Dict, context: Dict) -> Dict:
    """Escalate to human operator."""
    return {
        "success": True,
        "escalation": {
            "reason": params.get("reason"),
            "summary": params.get("summary"),
            "recommended_actions": params.get("recommended_actions", []),
            "urgency": params.get("urgency", "medium"),
        },
        "message": "Issue escalated to human operator"
    }


def _get_auth_headers(context: Dict) -> Dict[str, str]:
    """Get authentication headers from context."""
    headers = {"Content-Type": "application/json"}

    auth_token = context.get("auth_token")
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
        log.debug(f"Using auth token: {auth_token[:20]}...")
    else:
        log.warning("No auth token in context for internal service call")

    return headers
