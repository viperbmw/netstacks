"""
SQLAlchemy Models for NetStacks

Defines all database models used across NetStacks microservices.
These models use PostgreSQL with JSONB for structured data.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()


class Setting(Base):
    """Application settings key-value store"""
    __tablename__ = 'settings'

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base):
    """User accounts"""
    __tablename__ = 'users'

    username = Column(String(255), primary_key=True)
    password_hash = Column(String(255), nullable=False)
    theme = Column(String(50), default='dark')
    auth_source = Column(String(50), default='local')  # 'local', 'ldap', 'oidc'
    created_at = Column(DateTime, default=datetime.utcnow)


class Template(Base):
    """Jinja2 configuration templates"""
    __tablename__ = 'templates'

    name = Column(String(255), primary_key=True)
    content = Column(Text, nullable=True)
    type = Column(String(50), default='deploy')  # 'deploy', 'delete', 'validation'
    validation_template = Column(String(255), nullable=True)
    delete_template = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ServiceStack(Base):
    """Service stacks - groups of related services"""
    __tablename__ = 'service_stacks'

    stack_id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    services = Column(JSONB, default=list)
    shared_variables = Column(JSONB, default=dict)
    state = Column(String(50), default='pending')
    has_pending_changes = Column(Boolean, default=False)
    pending_since = Column(DateTime, nullable=True)
    deployed_services = Column(JSONB, default=list)
    deployment_errors = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deploy_started_at = Column(DateTime, nullable=True)
    deploy_completed_at = Column(DateTime, nullable=True)
    last_validated = Column(DateTime, nullable=True)
    validation_status = Column(String(50), nullable=True)

    service_instances = relationship(
        "ServiceInstance",
        back_populates="stack",
        cascade="all, delete-orphan"
    )
    scheduled_operations = relationship(
        "ScheduledStackOperation",
        back_populates="stack",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('idx_service_stacks_state', 'state'),
    )


class ServiceInstance(Base):
    """Individual service deployments"""
    __tablename__ = 'service_instances'

    service_id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    template = Column(String(255), nullable=False)
    validation_template = Column(String(255), nullable=True)
    delete_template = Column(String(255), nullable=True)
    device = Column(String(255), nullable=False)
    variables = Column(JSONB, default=dict)
    rendered_config = Column(Text, nullable=True)
    state = Column(String(50), default='pending')
    error = Column(Text, nullable=True)
    task_id = Column(String(255), nullable=True)
    stack_id = Column(
        String(36),
        ForeignKey('service_stacks.stack_id', ondelete='CASCADE'),
        nullable=True
    )
    stack_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    deployed_at = Column(DateTime, nullable=True)
    last_validated = Column(DateTime, nullable=True)
    validation_status = Column(String(50), nullable=True)
    validation_errors = Column(JSONB, default=list)

    stack = relationship("ServiceStack", back_populates="service_instances")

    __table_args__ = (
        Index('idx_service_instances_stack', 'stack_id'),
        Index('idx_service_instances_device', 'device'),
    )


class Device(Base):
    """
    Unified device table
    Stores both Netbox-synced and manually added devices
    """
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    host = Column(String(255), nullable=False)
    device_type = Column(String(100), nullable=False)
    port = Column(Integer, default=22)
    username = Column(String(255), nullable=True)
    password = Column(String(255), nullable=True)
    enable_password = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    manufacturer = Column(String(255), nullable=True)
    model = Column(String(255), nullable=True)
    platform = Column(String(100), nullable=True)
    site = Column(String(255), nullable=True)
    tags = Column(JSONB, default=list)
    source = Column(String(20), default='manual')
    netbox_id = Column(Integer, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_devices_type', 'device_type'),
        Index('idx_devices_source', 'source'),
    )


class DefaultCredential(Base):
    """Default credentials for device connections"""
    __tablename__ = 'default_credentials'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    username = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)
    enable_password = Column(String(255), nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class StackTemplate(Base):
    """Reusable stack configurations"""
    __tablename__ = 'stack_templates'

    template_id = Column(String(36), primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    services = Column(JSONB, nullable=False)
    required_variables = Column(JSONB, default=list)
    api_variables = Column(JSONB, default=dict)
    per_device_variables = Column(JSONB, default=list)
    tags = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)


class APIResource(Base):
    """Reusable API configurations for fetching variables"""
    __tablename__ = 'api_resources'

    resource_id = Column(String(36), primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    base_url = Column(String(500), nullable=False)
    auth_type = Column(String(50), nullable=True)
    auth_token = Column(String(500), nullable=True)
    auth_username = Column(String(255), nullable=True)
    auth_password = Column(String(255), nullable=True)
    custom_headers = Column(JSONB, nullable=True)
    verify_ssl = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)


class ScheduledStackOperation(Base):
    """Scheduled operations on stacks"""
    __tablename__ = 'scheduled_stack_operations'

    schedule_id = Column(String(36), primary_key=True)
    stack_id = Column(
        String(36),
        ForeignKey('service_stacks.stack_id', ondelete='CASCADE'),
        nullable=True
    )
    operation_type = Column(String(50), nullable=False)
    schedule_type = Column(String(50), nullable=False)
    scheduled_time = Column(String(50), nullable=False)
    day_of_week = Column(Integer, nullable=True)
    day_of_month = Column(Integer, nullable=True)
    config_data = Column(JSONB, nullable=True)
    enabled = Column(Boolean, default=True)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    run_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    stack = relationship("ServiceStack", back_populates="scheduled_operations")


class AuthConfig(Base):
    """Authentication method configurations"""
    __tablename__ = 'auth_config'

    config_id = Column(Integer, primary_key=True, autoincrement=True)
    auth_type = Column(String(50), nullable=False)
    is_enabled = Column(Boolean, default=False)
    priority = Column(Integer, default=0)
    config_data = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MenuItem(Base):
    """Custom menu ordering"""
    __tablename__ = 'menu_items'

    item_id = Column(String(50), primary_key=True)
    label = Column(String(100), nullable=False)
    icon = Column(String(50), nullable=False)
    url = Column(String(255), nullable=False)
    order_index = Column(Integer, nullable=False)
    visible = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MOP(Base):
    """Method of Procedures - YAML-based workflows"""
    __tablename__ = 'mops'

    mop_id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    yaml_content = Column(Text, nullable=True)
    devices = Column(JSONB, default=list)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    executions = relationship(
        "MOPExecution",
        back_populates="mop",
        cascade="all, delete-orphan"
    )


class MOPExecution(Base):
    """MOP execution history"""
    __tablename__ = 'mop_executions'

    execution_id = Column(String(36), primary_key=True)
    mop_id = Column(
        String(36),
        ForeignKey('mops.mop_id', ondelete='CASCADE'),
        nullable=False
    )
    status = Column(String(50), default='pending')
    current_step = Column(Integer, default=0)
    execution_log = Column(JSONB, default=list)
    context = Column(JSONB, default=dict)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    started_by = Column(String(255), nullable=True)

    mop = relationship("MOP", back_populates="executions")

    __table_args__ = (
        Index('idx_mop_executions_mop', 'mop_id'),
        Index('idx_mop_executions_status', 'status'),
    )


class StepType(Base):
    """Available step types for MOPs"""
    __tablename__ = 'step_types'

    step_type_id = Column(String(50), primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    icon = Column(String(50), nullable=True)
    enabled = Column(Boolean, default=True)
    is_builtin = Column(Boolean, default=False)
    action_type = Column(String(50), nullable=False)
    config = Column(JSONB, default=dict)
    parameters_schema = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskHistory(Base):
    """Task history for Celery task monitoring"""
    __tablename__ = 'task_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(255), nullable=False)
    device_name = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_task_history_created', 'created_at'),
    )


class ConfigSnapshot(Base):
    """Configuration snapshots - groups backups at a point in time"""
    __tablename__ = 'config_snapshots'

    snapshot_id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    snapshot_type = Column(String(20), default='manual')
    status = Column(String(20), default='in_progress')
    total_devices = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    created_by = Column(String(255), nullable=True)

    backups = relationship(
        "ConfigBackup",
        back_populates="snapshot",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('idx_config_snapshots_created', 'created_at'),
        Index('idx_config_snapshots_status', 'status'),
    )


class ConfigBackup(Base):
    """Device configuration backups"""
    __tablename__ = 'config_backups'

    backup_id = Column(String(255), primary_key=True)
    device_name = Column(String(255), nullable=False, index=True)
    device_ip = Column(String(50), nullable=True)
    platform = Column(String(50), nullable=True)
    config_content = Column(Text, nullable=False)
    config_format = Column(String(20), default='native')
    config_hash = Column(String(64), nullable=True)
    backup_type = Column(String(20), default='scheduled')
    status = Column(String(20), default='success')
    error_message = Column(Text, nullable=True)
    file_size = Column(Integer, nullable=True)
    snapshot_id = Column(
        String(36),
        ForeignKey('config_snapshots.snapshot_id', ondelete='SET NULL'),
        nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    snapshot = relationship("ConfigSnapshot", back_populates="backups")

    __table_args__ = (
        Index('idx_config_backup_device_created', 'device_name', 'created_at'),
        Index('idx_config_backup_snapshot', 'snapshot_id'),
    )


class BackupSchedule(Base):
    """Backup schedule configuration"""
    __tablename__ = 'backup_schedules'

    schedule_id = Column(String(50), primary_key=True, default='default')
    enabled = Column(Boolean, default=True)
    interval_hours = Column(Integer, default=24)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    retention_days = Column(Integer, default=30)
    include_filters = Column(JSONB, default=list)
    exclude_patterns = Column(JSONB, default=list)
    juniper_set_format = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeviceOverride(Base):
    """Device-specific overrides for connection settings"""
    __tablename__ = 'device_overrides'

    device_name = Column(String(255), primary_key=True)
    device_type = Column(String(50), nullable=True)
    host = Column(String(255), nullable=True)
    port = Column(Integer, nullable=True)
    username = Column(String(255), nullable=True)
    password = Column(String(255), nullable=True)
    secret = Column(String(255), nullable=True)
    timeout = Column(Integer, nullable=True)
    conn_timeout = Column(Integer, nullable=True)
    auth_timeout = Column(Integer, nullable=True)
    banner_timeout = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    disabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Default step types for seeding
DEFAULT_STEP_TYPES = [
    {
        'step_type_id': 'check_bgp',
        'name': 'Check BGP Neighbors',
        'description': 'Verify BGP neighbor status and count',
        'category': 'Network Checks',
        'icon': 'network-wired',
        'is_builtin': True,
        'action_type': 'get_config',
        'config': {
            'command': 'show ip bgp summary',
            'use_textfsm': True
        },
        'parameters_schema': {
            'command': {
                'type': 'string',
                'description': 'BGP command to run',
                'default': 'show ip bgp summary'
            },
            'expected_neighbors': {
                'type': 'integer',
                'description': 'Expected number of established neighbors'
            }
        }
    },
    {
        'step_type_id': 'check_interfaces',
        'name': 'Check Interfaces',
        'description': 'Verify interface status (up/down)',
        'category': 'Network Checks',
        'icon': 'ethernet',
        'is_builtin': True,
        'action_type': 'get_config',
        'config': {
            'command': 'show ip interface brief',
            'use_textfsm': True
        },
        'parameters_schema': {
            'command': {
                'type': 'string',
                'description': 'Interface command',
                'default': 'show ip interface brief'
            }
        }
    },
    {
        'step_type_id': 'check_routing',
        'name': 'Check Routing Table',
        'description': 'Verify routes exist in routing table',
        'category': 'Network Checks',
        'icon': 'route',
        'is_builtin': True,
        'action_type': 'get_config',
        'config': {
            'command': 'show ip route',
            'use_textfsm': True
        },
        'parameters_schema': {
            'command': {
                'type': 'string',
                'description': 'Routing command',
                'default': 'show ip route'
            },
            'expected_routes': {
                'type': 'array',
                'description': 'List of expected route prefixes'
            }
        }
    },
    {
        'step_type_id': 'get_config',
        'name': 'Get Config / Run Command',
        'description': 'Execute any show command on devices',
        'category': 'Commands',
        'icon': 'terminal',
        'is_builtin': True,
        'action_type': 'get_config',
        'config': {
            'command': '',
            'use_textfsm': False,
            'use_ttp': False,
            'use_genie': False
        },
        'parameters_schema': {
            'command': {
                'type': 'string',
                'description': 'CLI command to execute',
                'required': True
            },
            'use_textfsm': {
                'type': 'boolean',
                'description': 'Parse output with TextFSM',
                'default': False
            },
            'use_ttp': {
                'type': 'boolean',
                'description': 'Parse output with TTP',
                'default': False
            },
            'ttp_template': {
                'type': 'string',
                'description': 'TTP template (if use_ttp is true)'
            },
            'use_genie': {
                'type': 'boolean',
                'description': 'Parse output with Genie',
                'default': False
            }
        }
    },
    {
        'step_type_id': 'set_config',
        'name': 'Push Configuration',
        'description': 'Push configuration commands to devices',
        'category': 'Configuration',
        'icon': 'upload',
        'is_builtin': True,
        'action_type': 'set_config',
        'config': {
            'config_lines': [],
            'save_config': True
        },
        'parameters_schema': {
            'config_lines': {
                'type': 'array',
                'description': 'Configuration commands to push',
                'required': True
            },
            'template_name': {
                'type': 'string',
                'description': 'Use saved config template by name'
            },
            'save_config': {
                'type': 'boolean',
                'description': 'Save config after push',
                'default': True
            }
        }
    },
    {
        'step_type_id': 'validate_config',
        'name': 'Validate Configuration',
        'description': 'Run command and validate output against patterns',
        'category': 'Validation',
        'icon': 'check-circle',
        'is_builtin': True,
        'action_type': 'validate',
        'config': {
            'command': 'show running-config',
            'patterns': []
        },
        'parameters_schema': {
            'command': {
                'type': 'string',
                'description': 'Command to run for validation',
                'default': 'show running-config'
            },
            'patterns': {
                'type': 'array',
                'description': 'Patterns to check',
                'items': {
                    'pattern': {
                        'type': 'string',
                        'description': 'Regex pattern to match'
                    },
                    'must_match': {
                        'type': 'boolean',
                        'description': 'True if pattern must exist',
                        'default': True
                    },
                    'description': {
                        'type': 'string',
                        'description': 'Description of what this validates'
                    }
                }
            }
        }
    },
    {
        'step_type_id': 'api_call',
        'name': 'API Call',
        'description': 'Make HTTP request to external API',
        'category': 'Integration',
        'icon': 'globe',
        'is_builtin': True,
        'action_type': 'api_call',
        'config': {
            'url': '',
            'method': 'GET',
            'headers': {},
            'body_template': '',
            'expected_status': [200, 201, 204]
        },
        'parameters_schema': {
            'url': {
                'type': 'string',
                'description': 'API endpoint URL',
                'required': True
            },
            'method': {
                'type': 'string',
                'description': 'HTTP method',
                'default': 'GET',
                'enum': ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
            },
            'headers': {
                'type': 'object',
                'description': 'HTTP headers'
            },
            'body': {
                'type': 'string',
                'description': 'Request body (supports Jinja2 templating)'
            },
            'expected_status': {
                'type': 'array',
                'description': 'Expected HTTP status codes',
                'default': [200, 201, 204]
            }
        }
    },
    {
        'step_type_id': 'wait',
        'name': 'Wait / Delay',
        'description': 'Pause execution for specified duration',
        'category': 'Utility',
        'icon': 'clock',
        'is_builtin': True,
        'action_type': 'wait',
        'config': {
            'seconds': 30
        },
        'parameters_schema': {
            'seconds': {
                'type': 'integer',
                'description': 'Seconds to wait',
                'required': True,
                'default': 30
            }
        }
    },
    {
        'step_type_id': 'manual_approval',
        'name': 'Manual Approval',
        'description': 'Pause for human review and approval',
        'category': 'Utility',
        'icon': 'hand-paper',
        'is_builtin': True,
        'action_type': 'manual',
        'config': {
            'prompt': 'Please review and approve to continue',
            'instructions': ''
        },
        'parameters_schema': {
            'prompt': {
                'type': 'string',
                'description': 'Approval prompt message',
                'default': 'Please review and approve to continue'
            },
            'instructions': {
                'type': 'string',
                'description': 'Detailed instructions for reviewer'
            }
        }
    },
    {
        'step_type_id': 'webhook',
        'name': 'Webhook Notification',
        'description': 'Send webhook notification (Slack, Teams, etc)',
        'category': 'Notifications',
        'icon': 'bell',
        'is_builtin': True,
        'action_type': 'api_call',
        'config': {
            'url': '',
            'method': 'POST',
            'headers': {'Content-Type': 'application/json'},
            'body_template': '{"text": "MOP step completed: {{ step_name }}"}',
            'expected_status': [200, 201, 204]
        },
        'parameters_schema': {
            'url': {
                'type': 'string',
                'description': 'Webhook URL',
                'required': True
            },
            'message': {
                'type': 'string',
                'description': 'Message to send'
            },
            'channel': {
                'type': 'string',
                'description': 'Channel (if applicable)'
            }
        }
    },
    {
        'step_type_id': 'deploy_stack',
        'name': 'Deploy Service Stack',
        'description': 'Deploy a service stack to devices',
        'category': 'Configuration',
        'icon': 'layer-group',
        'is_builtin': True,
        'action_type': 'deploy_stack',
        'config': {
            'stack_name': '',
            'validate_only': False
        },
        'parameters_schema': {
            'stack_name': {
                'type': 'string',
                'description': 'Name of the service stack to deploy',
                'required': True
            },
            'stack_id': {
                'type': 'string',
                'description': 'ID of the service stack (alternative to name)'
            },
            'validate_only': {
                'type': 'boolean',
                'description': 'Only validate, do not deploy',
                'default': False
            }
        }
    },
]

DEFAULT_MENU_ITEMS = [
    {
        'item_id': 'dashboard',
        'label': 'Dashboard',
        'icon': 'home',
        'url': '/',
        'order_index': 0,
        'visible': True
    },
    {
        'item_id': 'deploy',
        'label': 'Deploy Config',
        'icon': 'rocket',
        'url': '/deploy',
        'order_index': 1,
        'visible': True
    },
    {
        'item_id': 'monitor',
        'label': 'Monitor Jobs',
        'icon': 'chart-line',
        'url': '/monitor',
        'order_index': 2,
        'visible': True
    },
    {
        'item_id': 'templates',
        'label': 'Config Templates',
        'icon': 'file-code',
        'url': '/templates',
        'order_index': 3,
        'visible': True
    },
    {
        'item_id': 'service-stacks',
        'label': 'Service Stacks',
        'icon': 'layer-group',
        'url': '/service-stacks',
        'order_index': 4,
        'visible': True
    },
    {
        'item_id': 'devices',
        'label': 'Devices',
        'icon': 'server',
        'url': '/devices',
        'order_index': 5,
        'visible': True
    },
    {
        'item_id': 'snapshots',
        'label': 'Snapshots',
        'icon': 'camera',
        'url': '/snapshots',
        'order_index': 6,
        'visible': True
    },
    {
        'item_id': 'mop',
        'label': 'Procedures (MOP)',
        'icon': 'list-check',
        'url': '/mop',
        'order_index': 7,
        'visible': True
    },
]
