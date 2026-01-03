"""
NetStacks API Documentation
Swagger/OpenAPI documentation for all NetStacks REST APIs
Uses a custom Swagger UI with manually defined OpenAPI spec to avoid route conflicts
"""

from flask import Blueprint, jsonify, render_template_string

# Create blueprint for API docs with URL prefix to avoid root path conflicts
api_bp = Blueprint('api_docs', __name__, url_prefix='/docs')

@api_bp.route('/')
def swagger_ui():
    """Render Swagger UI with custom spec URL"""
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>NetStacks API</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
    <style>
        html { box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }
        *, *:before, *:after { box-sizing: inherit; }
        body { margin:0; padding:0; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
    <script>
    window.onload = function() {
        window.ui = SwaggerUIBundle({
            url: "/docs/swagger.json",
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIStandalonePreset
            ],
            plugins: [
                SwaggerUIBundle.plugins.DownloadUrl
            ],
            layout: "StandaloneLayout"
        });
    };
    </script>
</body>
</html>
    ''')

# Flask-RESTX imports no longer needed - we use custom Swagger spec
# All API documentation is defined in the swagger.json route below

# ============================================================================
# API Endpoint Documentation
# ============================================================================
# Since the actual endpoints are in app.py, we manually define the swagger spec
# This prevents route conflicts while still providing comprehensive documentation

@api_bp.route('/swagger.json')
def swagger_spec():
    """Return custom Swagger/OpenAPI specification"""
    spec = {
        "swagger": "2.0",
        "basePath": "/api",
        "info": {
            "title": "NetStacks API",
            "version": "1.0",
            "description": "Network Automation and Configuration Management REST API"
        },
        "paths": {
            "/devices": {
                "post": {
                    "tags": ["devices"],
                    "summary": "Get list of all devices",
                    "description": "Fetches devices from Netbox based on configured filters",
                    "parameters": [{
                        "in": "body",
                        "name": "body",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "filters": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "key": {"type": "string"},
                                            "value": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "success": {"type": "boolean"},
                                    "devices": {
                                        "type": "array",
                                        "items": {"$ref": "#/definitions/Device"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/tasks": {
                "get": {
                    "tags": ["tasks"],
                    "summary": "Get all task IDs",
                    "description": "Retrieves list of all task IDs from Celery",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "data": {
                                        "type": "object",
                                        "properties": {
                                            "task_id": {
                                                "type": "array",
                                                "items": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/tasks/{task_id}": {
                "get": {
                    "tags": ["tasks"],
                    "summary": "Get task details",
                    "description": "Fetch detailed information about a specific task",
                    "parameters": [{
                        "name": "task_id",
                        "in": "path",
                        "required": True,
                        "type": "string",
                        "description": "Task identifier"
                    }],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {"$ref": "#/definitions/Task"}
                        }
                    }
                }
            },
            "/tasks/metadata": {
                "get": {
                    "tags": ["tasks"],
                    "summary": "Get task metadata",
                    "description": "Retrieve metadata for all tasks (device names, timestamps, etc.)",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "metadata": {
                                        "type": "object",
                                        "additionalProperties": {
                                            "type": "object",
                                            "properties": {
                                                "device_name": {"type": "string"},
                                                "timestamp": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/workers": {
                "get": {
                    "tags": ["workers"],
                    "summary": "Get all workers",
                    "description": "Fetch list of active Celery workers",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "hostname": {"type": "string"},
                                        "pid": {"type": "string"},
                                        "last_heartbeat": {"type": "string"},
                                        "successful_job_count": {"type": "integer"},
                                        "failed_job_count": {"type": "integer"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/service-stacks": {
                "get": {
                    "tags": ["stacks"],
                    "summary": "List service stacks",
                    "description": "Get all service stack definitions",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "array",
                                "items": {"$ref": "#/definitions/ServiceStack"}
                            }
                        }
                    }
                },
                "post": {
                    "tags": ["stacks"],
                    "summary": "Create service stack",
                    "description": "Create a new service stack definition",
                    "parameters": [{
                        "in": "body",
                        "name": "body",
                        "schema": {"$ref": "#/definitions/ServiceStack"}
                    }],
                    "responses": {
                        "200": {"description": "Success"}
                    }
                }
            },
            "/service-stacks/{stack_id}": {
                "get": {
                    "tags": ["stacks"],
                    "summary": "Get service stack",
                    "parameters": [{
                        "name": "stack_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {"$ref": "#/definitions/ServiceStack"}
                        }
                    }
                },
                "put": {
                    "tags": ["stacks"],
                    "summary": "Update service stack",
                    "parameters": [
                        {
                            "name": "stack_id",
                            "in": "path",
                            "required": True,
                            "type": "string"
                        },
                        {
                            "in": "body",
                            "name": "body",
                            "schema": {"$ref": "#/definitions/ServiceStack"}
                        }
                    ],
                    "responses": {
                        "200": {"description": "Success"}
                    }
                },
                "delete": {
                    "tags": ["stacks"],
                    "summary": "Delete service stack",
                    "parameters": [{
                        "name": "stack_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {"description": "Success"}
                    }
                }
            },
            "/service-stacks/{stack_id}/deploy": {
                "post": {
                    "tags": ["stacks"],
                    "summary": "Deploy service stack",
                    "parameters": [{
                        "name": "stack_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {"description": "Deployment initiated"}
                    }
                }
            },
            "/service-stacks/{stack_id}/validate": {
                "post": {
                    "tags": ["stacks"],
                    "summary": "Validate service stack",
                    "parameters": [{
                        "name": "stack_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {"description": "Validation initiated"}
                    }
                }
            },
            "/scheduled-operations": {
                "get": {
                    "tags": ["schedules"],
                    "summary": "List scheduled operations",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "array",
                                "items": {"$ref": "#/definitions/Schedule"}
                            }
                        }
                    }
                },
                "post": {
                    "tags": ["schedules"],
                    "summary": "Create scheduled operation",
                    "parameters": [{
                        "in": "body",
                        "name": "body",
                        "schema": {"$ref": "#/definitions/Schedule"}
                    }],
                    "responses": {
                        "200": {"description": "Schedule created"}
                    }
                }
            },
            "/scheduled-operations/{schedule_id}": {
                "put": {
                    "tags": ["schedules"],
                    "summary": "Update schedule",
                    "parameters": [
                        {
                            "name": "schedule_id",
                            "in": "path",
                            "required": True,
                            "type": "string"
                        },
                        {
                            "in": "body",
                            "name": "body",
                            "schema": {"$ref": "#/definitions/Schedule"}
                        }
                    ],
                    "responses": {
                        "200": {"description": "Schedule updated"}
                    }
                },
                "delete": {
                    "tags": ["schedules"],
                    "summary": "Delete schedule",
                    "parameters": [{
                        "name": "schedule_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {"description": "Schedule deleted"}
                    }
                }
            },
            "/deploy/setconfig": {
                "post": {
                    "tags": ["deploy"],
                    "summary": "Deploy configuration",
                    "description": "Deploy configuration commands to device(s)",
                    "parameters": [{
                        "in": "body",
                        "name": "body",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "devices": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                },
                                "config": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                }
                            }
                        }
                    }],
                    "responses": {
                        "200": {"description": "Deployment initiated"}
                    }
                }
            },
            "/templates": {
                "get": {
                    "tags": ["templates"],
                    "summary": "List templates",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "array",
                                "items": {"$ref": "#/definitions/Template"}
                            }
                        }
                    }
                },
                "post": {
                    "tags": ["templates"],
                    "summary": "Create template",
                    "parameters": [{
                        "in": "body",
                        "name": "body",
                        "schema": {"$ref": "#/definitions/Template"}
                    }],
                    "responses": {
                        "200": {"description": "Template created"}
                    }
                }
            },
            "/stack-templates": {
                "get": {
                    "tags": ["stack-templates"],
                    "summary": "List stack templates",
                    "description": "Get all reusable service stack templates",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "success": {"type": "boolean"},
                                    "templates": {
                                        "type": "array",
                                        "items": {"$ref": "#/definitions/StackTemplate"}
                                    }
                                }
                            }
                        }
                    }
                },
                "post": {
                    "tags": ["stack-templates"],
                    "summary": "Create stack template",
                    "description": "Create a new reusable service stack template with API variables",
                    "parameters": [{
                        "in": "body",
                        "name": "body",
                        "schema": {"$ref": "#/definitions/StackTemplate"}
                    }],
                    "responses": {
                        "200": {
                            "description": "Template created",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "success": {"type": "boolean"},
                                    "template_id": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            },
            "/stack-templates/{template_id}": {
                "get": {
                    "tags": ["stack-templates"],
                    "summary": "Get stack template",
                    "description": "Get a specific stack template by ID",
                    "parameters": [{
                        "name": "template_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {"$ref": "#/definitions/StackTemplate"}
                        }
                    }
                },
                "put": {
                    "tags": ["stack-templates"],
                    "summary": "Update stack template",
                    "parameters": [
                        {
                            "name": "template_id",
                            "in": "path",
                            "required": True,
                            "type": "string"
                        },
                        {
                            "in": "body",
                            "name": "body",
                            "schema": {"$ref": "#/definitions/StackTemplate"}
                        }
                    ],
                    "responses": {
                        "200": {"description": "Template updated"}
                    }
                },
                "delete": {
                    "tags": ["stack-templates"],
                    "summary": "Delete stack template",
                    "parameters": [{
                        "name": "template_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {"description": "Template deleted"}
                    }
                }
            },
            # ============================================================================
            # Alerts API
            # ============================================================================
            "/alerts/api/webhooks/generic": {
                "post": {
                    "tags": ["alerts"],
                    "summary": "Generic alert webhook",
                    "description": "Receive alerts from any monitoring system. Alerts are automatically processed by AI triage unless skip_ai=true.",
                    "parameters": [{
                        "in": "body",
                        "name": "body",
                        "schema": {
                            "type": "object",
                            "required": ["title", "severity"],
                            "properties": {
                                "title": {"type": "string", "description": "Alert title"},
                                "severity": {"type": "string", "enum": ["info", "warning", "error", "critical"]},
                                "description": {"type": "string"},
                                "source": {"type": "string", "description": "Source system name"},
                                "device": {"type": "string", "description": "Affected device name"},
                                "skip_ai": {"type": "boolean", "description": "Skip AI processing", "default": False}
                            }
                        }
                    }],
                    "responses": {
                        "201": {
                            "description": "Alert received",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "status": {"type": "string"},
                                    "alert_id": {"type": "string"},
                                    "ai_processing": {"type": "boolean"}
                                }
                            }
                        }
                    }
                }
            },
            "/alerts/api/webhooks/prometheus": {
                "post": {
                    "tags": ["alerts"],
                    "summary": "Prometheus AlertManager webhook",
                    "description": "Receive alerts from Prometheus AlertManager. All alerts are automatically processed by AI triage.",
                    "parameters": [{
                        "in": "body",
                        "name": "body",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "alerts": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "labels": {"type": "object"},
                                            "annotations": {"type": "object"},
                                            "status": {"type": "string"},
                                            "startsAt": {"type": "string"},
                                            "endsAt": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }],
                    "responses": {
                        "201": {"description": "Alerts received"}
                    }
                }
            },
            "/alerts/api/webhooks/solarwinds": {
                "post": {
                    "tags": ["alerts"],
                    "summary": "SolarWinds webhook",
                    "description": "Receive alerts from SolarWinds. All alerts are automatically processed by AI triage.",
                    "parameters": [{
                        "in": "body",
                        "name": "body",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "AlertName": {"type": "string"},
                                "AlertMessage": {"type": "string"},
                                "Severity": {"type": "string"},
                                "NodeName": {"type": "string"},
                                "AlertObjectID": {"type": "string"}
                            }
                        }
                    }],
                    "responses": {
                        "201": {"description": "Alert received"}
                    }
                }
            },
            "/alerts/api/alerts": {
                "get": {
                    "tags": ["alerts"],
                    "summary": "List alerts",
                    "description": "Get all alerts with optional filtering",
                    "parameters": [
                        {"name": "severity", "in": "query", "type": "string", "description": "Filter by severity"},
                        {"name": "status", "in": "query", "type": "string", "description": "Filter by status"},
                        {"name": "source", "in": "query", "type": "string", "description": "Filter by source"},
                        {"name": "limit", "in": "query", "type": "integer", "default": 100}
                    ],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "alerts": {
                                        "type": "array",
                                        "items": {"$ref": "#/definitions/Alert"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/alerts/api/alerts/{alert_id}": {
                "get": {
                    "tags": ["alerts"],
                    "summary": "Get alert details",
                    "parameters": [{
                        "name": "alert_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {"$ref": "#/definitions/Alert"}
                        }
                    }
                }
            },
            "/alerts/api/alerts/{alert_id}/acknowledge": {
                "post": {
                    "tags": ["alerts"],
                    "summary": "Acknowledge an alert",
                    "parameters": [{
                        "name": "alert_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {"description": "Alert acknowledged"}
                    }
                }
            },
            "/alerts/api/alerts/{alert_id}/process": {
                "post": {
                    "tags": ["alerts"],
                    "summary": "Trigger AI processing for alert",
                    "description": "Manually trigger AI processing for an alert. Use to re-process or process skipped alerts.",
                    "parameters": [{
                        "name": "alert_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {
                            "description": "Processing triggered",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "message": {"type": "string"},
                                    "alert_id": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            },
            "/alerts/api/alerts/{alert_id}/sessions": {
                "get": {
                    "tags": ["alerts"],
                    "summary": "Get AI sessions for alert",
                    "description": "Get the history of AI agent sessions that processed this alert",
                    "parameters": [{
                        "name": "alert_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "alert_id": {"type": "string"},
                                    "sessions": {
                                        "type": "array",
                                        "items": {"$ref": "#/definitions/AgentSession"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            # ============================================================================
            # Incidents API
            # ============================================================================
            "/alerts/api/incidents": {
                "get": {
                    "tags": ["incidents"],
                    "summary": "List incidents",
                    "description": "Get all incidents with optional filtering",
                    "parameters": [
                        {"name": "status", "in": "query", "type": "string"},
                        {"name": "severity", "in": "query", "type": "string"},
                        {"name": "source", "in": "query", "type": "string"},
                        {"name": "limit", "in": "query", "type": "integer", "default": 100}
                    ],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "incidents": {
                                        "type": "array",
                                        "items": {"$ref": "#/definitions/Incident"}
                                    }
                                }
                            }
                        }
                    }
                },
                "post": {
                    "tags": ["incidents"],
                    "summary": "Create incident",
                    "parameters": [{
                        "in": "body",
                        "name": "body",
                        "schema": {"$ref": "#/definitions/Incident"}
                    }],
                    "responses": {
                        "201": {"description": "Incident created"}
                    }
                }
            },
            "/alerts/api/incidents/{incident_id}": {
                "get": {
                    "tags": ["incidents"],
                    "summary": "Get incident details",
                    "parameters": [{
                        "name": "incident_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {"$ref": "#/definitions/Incident"}
                        }
                    }
                },
                "patch": {
                    "tags": ["incidents"],
                    "summary": "Update incident",
                    "parameters": [
                        {
                            "name": "incident_id",
                            "in": "path",
                            "required": True,
                            "type": "string"
                        },
                        {
                            "in": "body",
                            "name": "body",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "status": {"type": "string"},
                                    "resolution": {"type": "string"}
                                }
                            }
                        }
                    ],
                    "responses": {
                        "200": {"description": "Incident updated"}
                    }
                }
            },
            # ============================================================================
            # Agents API
            # ============================================================================
            "/agents/api/agents": {
                "get": {
                    "tags": ["agents"],
                    "summary": "List agents",
                    "description": "Get all configured AI agents with session counts",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "agents": {
                                        "type": "array",
                                        "items": {"$ref": "#/definitions/Agent"}
                                    }
                                }
                            }
                        }
                    }
                },
                "post": {
                    "tags": ["agents"],
                    "summary": "Create agent",
                    "parameters": [{
                        "in": "body",
                        "name": "body",
                        "schema": {"$ref": "#/definitions/Agent"}
                    }],
                    "responses": {
                        "201": {"description": "Agent created"}
                    }
                }
            },
            "/agents/api/agents/{agent_id}": {
                "get": {
                    "tags": ["agents"],
                    "summary": "Get agent details",
                    "parameters": [{
                        "name": "agent_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {"$ref": "#/definitions/Agent"}
                        }
                    }
                },
                "patch": {
                    "tags": ["agents"],
                    "summary": "Update agent",
                    "parameters": [
                        {
                            "name": "agent_id",
                            "in": "path",
                            "required": True,
                            "type": "string"
                        },
                        {
                            "in": "body",
                            "name": "body",
                            "schema": {"$ref": "#/definitions/Agent"}
                        }
                    ],
                    "responses": {
                        "200": {"description": "Agent updated"}
                    }
                },
                "delete": {
                    "tags": ["agents"],
                    "summary": "Delete agent",
                    "parameters": [{
                        "name": "agent_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {"description": "Agent deleted"}
                    }
                }
            },
            "/agents/api/agents/{agent_id}/toggle": {
                "post": {
                    "tags": ["agents"],
                    "summary": "Toggle agent active status",
                    "parameters": [{
                        "name": "agent_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {"description": "Agent toggled"}
                    }
                }
            },
            "/agents/api/agents/tools": {
                "get": {
                    "tags": ["agents"],
                    "summary": "Get available tools",
                    "description": "Get list of tools available for agent configuration",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "tools": {
                                        "type": "array",
                                        "items": {"$ref": "#/definitions/Tool"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/agents/api/stats": {
                "get": {
                    "tags": ["agents"],
                    "summary": "Get agent statistics",
                    "description": "Get aggregate statistics including sessions today, total sessions, and active agents",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "sessions_today": {"type": "integer"},
                                    "total_sessions": {"type": "integer"},
                                    "active_agents": {"type": "integer"}
                                }
                            }
                        }
                    }
                }
            },
            "/agents/api/sessions": {
                "get": {
                    "tags": ["agents"],
                    "summary": "List agent sessions",
                    "parameters": [
                        {"name": "agent_id", "in": "query", "type": "string", "description": "Filter by agent ID"},
                        {"name": "status", "in": "query", "type": "string"},
                        {"name": "limit", "in": "query", "type": "integer", "default": 50}
                    ],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "sessions": {
                                        "type": "array",
                                        "items": {"$ref": "#/definitions/AgentSession"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/agents/api/sessions/{session_id}": {
                "get": {
                    "tags": ["agents"],
                    "summary": "Get session details",
                    "description": "Get session details including messages and actions",
                    "parameters": [{
                        "name": "session_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {"$ref": "#/definitions/AgentSession"}
                        }
                    }
                }
            },
            # ============================================================================
            # Approvals API
            # ============================================================================
            "/approvals/api/approvals": {
                "get": {
                    "tags": ["approvals"],
                    "summary": "List pending approvals",
                    "parameters": [
                        {"name": "status", "in": "query", "type": "string", "description": "Filter by status (pending, approved, rejected)"}
                    ],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "approvals": {
                                        "type": "array",
                                        "items": {"$ref": "#/definitions/Approval"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/approvals/api/approvals/{approval_id}/approve": {
                "post": {
                    "tags": ["approvals"],
                    "summary": "Approve a pending action",
                    "parameters": [{
                        "name": "approval_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {"description": "Action approved"}
                    }
                }
            },
            "/approvals/api/approvals/{approval_id}/reject": {
                "post": {
                    "tags": ["approvals"],
                    "summary": "Reject a pending action",
                    "parameters": [{
                        "name": "approval_id",
                        "in": "path",
                        "required": True,
                        "type": "string"
                    }],
                    "responses": {
                        "200": {"description": "Action rejected"}
                    }
                }
            },
            # ============================================================================
            # Platform API
            # ============================================================================
            "/platform/stats": {
                "get": {
                    "tags": ["platform"],
                    "summary": "Get platform statistics",
                    "description": "Returns aggregated platform metrics including device counts, template counts, incident counts, and system health. Cached for 60 seconds.",
                    "responses": {
                        "200": {
                            "description": "Platform statistics",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "timestamp": {"type": "string", "format": "date-time"},
                                    "devices": {
                                        "type": "object",
                                        "properties": {
                                            "total": {"type": "integer"},
                                            "by_type": {"type": "object"},
                                            "by_status": {"type": "object"}
                                        }
                                    },
                                    "templates": {
                                        "type": "object",
                                        "properties": {
                                            "total": {"type": "integer"},
                                            "by_type": {"type": "object"}
                                        }
                                    },
                                    "stacks": {
                                        "type": "object",
                                        "properties": {
                                            "total": {"type": "integer"},
                                            "deployed": {"type": "integer"},
                                            "by_state": {"type": "object"}
                                        }
                                    },
                                    "incidents": {
                                        "type": "object",
                                        "properties": {
                                            "total": {"type": "integer"},
                                            "open": {"type": "integer"}
                                        }
                                    },
                                    "agents": {
                                        "type": "object",
                                        "properties": {
                                            "total": {"type": "integer"},
                                            "active": {"type": "integer"}
                                        }
                                    },
                                    "backups": {
                                        "type": "object",
                                        "properties": {
                                            "schedule_enabled": {"type": "boolean"},
                                            "recent_count": {"type": "integer"}
                                        }
                                    },
                                    "system": {
                                        "type": "object",
                                        "properties": {
                                            "redis_connected": {"type": "boolean"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/platform/health": {
                "get": {
                    "tags": ["platform"],
                    "summary": "Get platform health status",
                    "description": "Returns health status of all platform services including microservices, Redis, PostgreSQL, and Celery workers.",
                    "responses": {
                        "200": {
                            "description": "Platform health status",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "success": {"type": "boolean"},
                                    "data": {
                                        "type": "object",
                                        "properties": {
                                            "overall_status": {"type": "string", "enum": ["healthy", "degraded"]},
                                            "services": {
                                                "type": "object",
                                                "additionalProperties": {
                                                    "type": "object",
                                                    "properties": {
                                                        "status": {"type": "string"},
                                                        "response_ms": {"type": "integer"},
                                                        "details": {"type": "object"}
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "definitions": {
            "Device": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "ip_address": {"type": "string"},
                    "device_type": {"type": "string"},
                    "manufacturer": {"type": "string"},
                    "platform": {"type": "string"},
                    "site": {"type": "string"},
                    "status": {"type": "string"}
                }
            },
            "Task": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "task_status": {"type": "string"},
                    "created_on": {"type": "string", "format": "date-time"},
                    "task_result": {"type": "object"},
                    "task_errors": {"type": "object"}
                }
            },
            "Template": {
                "type": "object",
                "properties": {
                    "template_id": {"type": "string"},
                    "template_name": {"type": "string"},
                    "template_type": {"type": "string"},
                    "template_content": {"type": "string"},
                    "variables": {"type": "object"},
                    "created_at": {"type": "string", "format": "date-time"}
                }
            },
            "Schedule": {
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "string"},
                    "operation_type": {"type": "string"},
                    "schedule_type": {"type": "string"},
                    "scheduled_time": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "next_run": {"type": "string", "format": "date-time"},
                    "last_run": {"type": "string", "format": "date-time"},
                    "run_count": {"type": "integer"}
                }
            },
            "ServiceStack": {
                "type": "object",
                "properties": {
                    "stack_id": {"type": "string"},
                    "stack_name": {"type": "string"},
                    "description": {"type": "string"},
                    "deploy_template_id": {"type": "string"},
                    "delete_template_id": {"type": "string"},
                    "validation_template_id": {"type": "string"},
                    "target_devices": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "service_variables": {"type": "object"},
                    "created_at": {"type": "string", "format": "date-time"}
                }
            },
            "StackTemplate": {
                "type": "object",
                "properties": {
                    "template_id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "services": {
                        "type": "array",
                        "description": "Array of service definitions",
                        "items": {
                            "type": "object",
                            "properties": {
                                "service_name": {"type": "string"},
                                "device_template": {"type": "string"},
                                "device_filters": {"type": "object"}
                            }
                        }
                    },
                    "required_variables": {
                        "type": "array",
                        "description": "List of required variable names",
                        "items": {"type": "string"}
                    },
                    "api_variables": {
                        "type": "object",
                        "description": "API variable configurations for browser-side fetching",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "description": "API endpoint URL"},
                                "method": {"type": "string", "description": "HTTP method (GET/POST/PUT)"},
                                "headers": {"type": "object", "description": "HTTP headers"},
                                "json_path": {"type": "string", "description": "JSONPath to extract value"},
                                "description": {"type": "string", "description": "Variable description"}
                            }
                        }
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "created_at": {"type": "string", "format": "date-time"},
                    "updated_at": {"type": "string", "format": "date-time"},
                    "created_by": {"type": "string"}
                }
            },
            "Alert": {
                "type": "object",
                "properties": {
                    "alert_id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "severity": {"type": "string", "enum": ["info", "warning", "error", "critical"]},
                    "status": {"type": "string", "enum": ["new", "acknowledged", "processing", "incident_created", "correlated", "escalated", "analyzed", "handed_off", "resolved"]},
                    "source": {"type": "string"},
                    "device": {"type": "string"},
                    "incident_id": {"type": "string", "description": "Linked incident ID if correlated"},
                    "alert_data": {"type": "object", "description": "Raw alert data from source"},
                    "created_at": {"type": "string", "format": "date-time"}
                }
            },
            "Incident": {
                "type": "object",
                "properties": {
                    "incident_id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "severity": {"type": "string", "enum": ["info", "warning", "error", "critical"]},
                    "status": {"type": "string", "enum": ["open", "investigating", "identified", "monitoring", "resolved", "escalated"]},
                    "source": {"type": "string", "enum": ["agent", "agent_escalation", "manual", "noc", "helpdesk", "security", "change-management"]},
                    "resolution": {"type": "string"},
                    "incident_data": {"type": "object", "description": "Additional incident metadata"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "resolved_at": {"type": "string", "format": "date-time"}
                }
            },
            "Agent": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "agent_name": {"type": "string"},
                    "agent_type": {"type": "string", "enum": ["triage", "bgp", "ospf", "isis", "general", "custom"]},
                    "description": {"type": "string"},
                    "is_active": {"type": "boolean"},
                    "is_persistent": {"type": "boolean"},
                    "status": {"type": "string", "enum": ["idle", "running", "error"]},
                    "llm_provider": {"type": "string", "enum": ["anthropic", "openai", "openrouter"]},
                    "llm_model": {"type": "string"},
                    "temperature": {"type": "number"},
                    "max_tokens": {"type": "integer"},
                    "system_prompt": {"type": "string"},
                    "tools": {"type": "array", "items": {"type": "string"}},
                    "session_count": {"type": "integer", "description": "Number of sessions for this agent"},
                    "created_at": {"type": "string", "format": "date-time"}
                }
            },
            "AgentSession": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "agent_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["active", "completed", "failed", "handoff"]},
                    "trigger_type": {"type": "string", "enum": ["user", "alert", "scheduled", "mop"]},
                    "trigger_data": {"type": "object"},
                    "parent_session_id": {"type": "string", "description": "If handed off from another session"},
                    "handoff_to": {"type": "string", "description": "If handed off to another session"},
                    "user_id": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "ended_at": {"type": "string", "format": "date-time"}
                }
            },
            "Tool": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                    "requires_approval": {"type": "boolean"},
                    "input_schema": {"type": "object"}
                }
            },
            "Approval": {
                "type": "object",
                "properties": {
                    "approval_id": {"type": "string"},
                    "session_id": {"type": "string"},
                    "action_type": {"type": "string"},
                    "action_data": {"type": "object"},
                    "status": {"type": "string", "enum": ["pending", "approved", "rejected", "expired"]},
                    "requested_at": {"type": "string", "format": "date-time"},
                    "responded_at": {"type": "string", "format": "date-time"},
                    "responded_by": {"type": "string"}
                }
            }
        },
        "tags": [
            {"name": "devices", "description": "Device management operations"},
            {"name": "tasks", "description": "Task and job monitoring"},
            {"name": "workers", "description": "Worker management"},
            {"name": "templates", "description": "Configuration templates"},
            {"name": "stacks", "description": "Service stack operations"},
            {"name": "stack-templates", "description": "Reusable stack templates with API variables"},
            {"name": "schedules", "description": "Scheduled operations"},
            {"name": "deploy", "description": "Configuration deployment"},
            {"name": "alerts", "description": "Alert management and webhooks - Alerts are automatically processed by AI triage"},
            {"name": "incidents", "description": "Incident management - AI-created and manual incidents"},
            {"name": "agents", "description": "AI agent configuration and management"},
            {"name": "approvals", "description": "Approval workflow for high-risk agent actions"},
            {"name": "platform", "description": "Platform health and statistics"}
        ]
    }
    return jsonify(spec)
