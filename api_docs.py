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
            {"name": "deploy", "description": "Configuration deployment"}
        ]
    }
    return jsonify(spec)
