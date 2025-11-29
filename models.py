"""
SQLAlchemy Models for NetStacks
Phase 1: Define models matching current SQLite schema
These models will be used for PostgreSQL migration
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB
import os

Base = declarative_base()

# Database URL - defaults to PostgreSQL, can be overridden
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://netstacks:netstacks_secret_change_me@postgres:5432/netstacks'
)


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
    content = Column(Text, nullable=True)  # Jinja2 template content
    type = Column(String(50), default='deploy')  # 'deploy', 'delete', 'validation'
    validation_template = Column(String(255), nullable=True)
    delete_template = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ServiceStack(Base):
    """Service stacks - groups of related services"""
    __tablename__ = 'service_stacks'

    stack_id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    services = Column(JSONB, default=list)  # JSON array of service definitions
    shared_variables = Column(JSONB, default=dict)  # JSON object
    state = Column(String(50), default='pending')
    has_pending_changes = Column(Boolean, default=False)
    pending_since = Column(DateTime, nullable=True)
    deployed_services = Column(JSONB, default=list)  # JSON array of service IDs
    deployment_errors = Column(JSONB, default=list)  # JSON array
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deploy_started_at = Column(DateTime, nullable=True)
    deploy_completed_at = Column(DateTime, nullable=True)
    last_validated = Column(DateTime, nullable=True)
    validation_status = Column(String(50), nullable=True)

    # Relationships
    service_instances = relationship("ServiceInstance", back_populates="stack", cascade="all, delete-orphan")
    scheduled_operations = relationship("ScheduledStackOperation", back_populates="stack", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_service_stacks_state', 'state'),
    )


class ServiceInstance(Base):
    """Individual service deployments"""
    __tablename__ = 'service_instances'

    service_id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(255), nullable=False)
    template = Column(String(255), nullable=False)
    validation_template = Column(String(255), nullable=True)
    delete_template = Column(String(255), nullable=True)
    device = Column(String(255), nullable=False)
    variables = Column(JSONB, default=dict)  # JSON object
    rendered_config = Column(Text, nullable=True)
    state = Column(String(50), default='pending')
    error = Column(Text, nullable=True)
    task_id = Column(String(255), nullable=True)
    stack_id = Column(String(36), ForeignKey('service_stacks.stack_id', ondelete='CASCADE'), nullable=True)
    stack_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    deployed_at = Column(DateTime, nullable=True)
    last_validated = Column(DateTime, nullable=True)
    validation_status = Column(String(50), nullable=True)
    validation_errors = Column(JSONB, default=list)  # JSON array

    # Relationships
    stack = relationship("ServiceStack", back_populates="service_instances")

    __table_args__ = (
        Index('idx_service_instances_stack', 'stack_id'),
        Index('idx_service_instances_device', 'device'),
    )


class Device(Base):
    """
    Unified device table - replaces manual_devices
    Stores both Netbox-synced and manually added devices
    """
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    host = Column(String(255), nullable=False)  # IP or hostname
    device_type = Column(String(100), nullable=False)  # Netmiko device type
    port = Column(Integer, default=22)

    # Credentials (NULL = use default credentials)
    username = Column(String(255), nullable=True)
    password = Column(String(255), nullable=True)  # Should be encrypted in production
    enable_password = Column(String(255), nullable=True)

    # Metadata
    description = Column(Text, nullable=True)
    manufacturer = Column(String(255), nullable=True)
    model = Column(String(255), nullable=True)
    platform = Column(String(100), nullable=True)
    site = Column(String(255), nullable=True)
    tags = Column(JSONB, default=list)

    # Source tracking
    source = Column(String(20), default='manual')  # 'netbox' or 'manual'
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
    name = Column(String(100), nullable=False)  # e.g., "production", "lab"
    username = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)  # Should be encrypted
    enable_password = Column(String(255), nullable=True)
    is_default = Column(Boolean, default=False)  # One can be marked as default
    created_at = Column(DateTime, default=datetime.utcnow)


class StackTemplate(Base):
    """Reusable stack configurations"""
    __tablename__ = 'stack_templates'

    template_id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    services = Column(JSONB, nullable=False)  # JSON array of service definitions
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

    resource_id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    base_url = Column(String(500), nullable=False)
    auth_type = Column(String(50), nullable=True)  # 'none', 'bearer', 'basic', 'header', 'api_key'
    auth_token = Column(String(500), nullable=True)
    auth_username = Column(String(255), nullable=True)
    auth_password = Column(String(255), nullable=True)
    custom_headers = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)


class ScheduledStackOperation(Base):
    """Scheduled operations on stacks"""
    __tablename__ = 'scheduled_stack_operations'

    schedule_id = Column(String(36), primary_key=True)  # UUID
    stack_id = Column(String(36), ForeignKey('service_stacks.stack_id', ondelete='CASCADE'), nullable=True)
    operation_type = Column(String(50), nullable=False)  # 'deploy', 'validate', 'delete', 'config_deploy'
    schedule_type = Column(String(50), nullable=False)  # 'once', 'daily', 'weekly', 'monthly'
    scheduled_time = Column(String(50), nullable=False)  # ISO datetime or HH:MM
    day_of_week = Column(Integer, nullable=True)  # 0-6 for weekly
    day_of_month = Column(Integer, nullable=True)  # 1-31 for monthly
    config_data = Column(JSONB, nullable=True)  # For config_deploy operations
    enabled = Column(Boolean, default=True)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    run_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    # Relationships
    stack = relationship("ServiceStack", back_populates="scheduled_operations")


class AuthConfig(Base):
    """Authentication method configurations"""
    __tablename__ = 'auth_config'

    config_id = Column(Integer, primary_key=True, autoincrement=True)
    auth_type = Column(String(50), nullable=False)  # 'local', 'ldap', 'oidc'
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

    mop_id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    yaml_content = Column(Text, nullable=True)
    devices = Column(JSONB, default=list)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    # Relationships
    executions = relationship("MOPExecution", back_populates="mop", cascade="all, delete-orphan")


class MOPExecution(Base):
    """MOP execution history"""
    __tablename__ = 'mop_executions'

    execution_id = Column(String(36), primary_key=True)  # UUID
    mop_id = Column(String(36), ForeignKey('mops.mop_id', ondelete='CASCADE'), nullable=False)
    status = Column(String(50), default='pending')
    current_step = Column(Integer, default=0)
    execution_log = Column(JSONB, default=list)
    context = Column(JSONB, default=dict)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    started_by = Column(String(255), nullable=True)

    # Relationships
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
    parameters_schema = Column(JSONB, default=dict)
    handler_function = Column(String(100), nullable=False)
    icon = Column(String(50), nullable=True)
    enabled = Column(Boolean, default=True)
    is_custom = Column(Boolean, default=False)
    custom_type = Column(String(50), nullable=True)
    custom_code = Column(Text, nullable=True)
    custom_webhook_url = Column(String(500), nullable=True)
    custom_webhook_method = Column(String(10), default='POST')
    custom_webhook_headers = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskHistory(Base):
    """
    Task history - replaces the JSON file storage
    Stores Celery task IDs for monitoring
    """
    __tablename__ = 'task_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(255), nullable=False)
    device_name = Column(String(500), nullable=True)  # Descriptive job name
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_task_history_created', 'created_at'),
    )


# Database initialization functions
def get_engine(url: str = None):
    """Create database engine"""
    return create_engine(url or DATABASE_URL, echo=False)


def get_session(engine=None):
    """Create a new database session"""
    if engine is None:
        engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def init_postgres_db(engine=None):
    """Initialize PostgreSQL database with all tables"""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


# Default step types for seeding
DEFAULT_STEP_TYPES = [
    {
        'step_type_id': 'check_bgp',
        'name': 'Check BGP',
        'description': 'Verify BGP neighbor status',
        'category': 'Network Checks',
        'parameters_schema': {'neighbor_count': {'type': 'integer', 'description': 'Expected number of BGP neighbors'}},
        'handler_function': 'execute_check_bgp',
        'icon': 'network-wired'
    },
    {
        'step_type_id': 'check_ping',
        'name': 'Check Ping',
        'description': 'Verify device reachability',
        'category': 'Network Checks',
        'parameters_schema': {'timeout': {'type': 'integer', 'default': 5}},
        'handler_function': 'execute_check_ping',
        'icon': 'wifi'
    },
    {
        'step_type_id': 'check_interfaces',
        'name': 'Check Interfaces',
        'description': 'Verify interface status',
        'category': 'Network Checks',
        'parameters_schema': {},
        'handler_function': 'execute_check_interfaces',
        'icon': 'ethernet'
    },
    {
        'step_type_id': 'run_command',
        'name': 'Run Command',
        'description': 'Execute CLI command on devices',
        'category': 'Commands',
        'parameters_schema': {'command': {'type': 'string', 'required': True}, 'use_textfsm': {'type': 'boolean', 'default': False}},
        'handler_function': 'execute_run_command',
        'icon': 'terminal'
    },
    {
        'step_type_id': 'deploy_stack',
        'name': 'Deploy Stack',
        'description': 'Deploy configuration stack',
        'category': 'Configuration',
        'parameters_schema': {'stack_name': {'type': 'string', 'required': True}},
        'handler_function': 'execute_deploy_stack',
        'icon': 'upload'
    },
    {
        'step_type_id': 'email',
        'name': 'Send Email',
        'description': 'Send email notification',
        'category': 'Notifications',
        'parameters_schema': {'to': {'type': 'string', 'required': True}, 'subject': {'type': 'string'}, 'body': {'type': 'string'}},
        'handler_function': 'execute_email',
        'icon': 'envelope'
    },
    {
        'step_type_id': 'webhook',
        'name': 'Webhook',
        'description': 'Send HTTP webhook',
        'category': 'Notifications',
        'parameters_schema': {'url': {'type': 'string', 'required': True}, 'method': {'type': 'string', 'default': 'POST'}},
        'handler_function': 'execute_webhook',
        'icon': 'globe'
    },
    {
        'step_type_id': 'custom_python',
        'name': 'Custom Python',
        'description': 'Execute custom Python code',
        'category': 'Advanced',
        'parameters_schema': {'code': {'type': 'string', 'required': True}},
        'handler_function': 'execute_custom_python',
        'icon': 'code'
    },
    {
        'step_type_id': 'wait',
        'name': 'Wait',
        'description': 'Wait for specified duration',
        'category': 'Utility',
        'parameters_schema': {'seconds': {'type': 'integer', 'required': True}},
        'handler_function': 'execute_wait',
        'icon': 'clock'
    },
]

DEFAULT_MENU_ITEMS = [
    {'item_id': 'dashboard', 'label': 'Dashboard', 'icon': 'home', 'url': '/', 'order_index': 0, 'visible': True},
    {'item_id': 'deploy', 'label': 'Deploy Config', 'icon': 'rocket', 'url': '/deploy', 'order_index': 1, 'visible': True},
    {'item_id': 'monitor', 'label': 'Monitor Jobs', 'icon': 'chart-line', 'url': '/monitor', 'order_index': 2, 'visible': True},
    {'item_id': 'templates', 'label': 'Config Templates', 'icon': 'file-code', 'url': '/templates', 'order_index': 3, 'visible': True},
    {'item_id': 'service-stacks', 'label': 'Service Stacks', 'icon': 'layer-group', 'url': '/service-stacks', 'order_index': 4, 'visible': True},
    {'item_id': 'devices', 'label': 'Devices', 'icon': 'server', 'url': '/devices', 'order_index': 5, 'visible': True},
    {'item_id': 'mop', 'label': 'Procedures (MOP)', 'icon': 'list-check', 'url': '/mop', 'order_index': 7, 'visible': True},
]


def seed_defaults(session):
    """Seed default data into the database"""
    # Seed step types
    existing_step_types = session.query(StepType).count()
    if existing_step_types == 0:
        for st in DEFAULT_STEP_TYPES:
            session.add(StepType(**st, enabled=True, is_custom=False))
        session.commit()

    # Seed menu items
    existing_menu_items = session.query(MenuItem).count()
    if existing_menu_items == 0:
        for mi in DEFAULT_MENU_ITEMS:
            session.add(MenuItem(**mi))
        session.commit()


if __name__ == '__main__':
    # Test database connection and create tables
    print(f"Connecting to: {DATABASE_URL}")
    engine = get_engine()
    init_postgres_db(engine)
    print("Tables created successfully!")

    session = get_session(engine)
    seed_defaults(session)
    print("Default data seeded!")
    session.close()
