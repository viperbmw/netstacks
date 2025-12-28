"""
SQLAlchemy Models for NetStacks
Phase 1: Define models matching current SQLite schema
These models will be used for PostgreSQL migration
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, Float
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
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
    vendor_types = Column(JSONB, nullable=True)  # List of platform/vendor types (e.g., ['cisco_ios', 'juniper_junos'])
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
    verify_ssl = Column(Boolean, default=True, nullable=False)  # TLS verification - default to secure
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
    """Available step types for MOPs - fully UI configurable"""
    __tablename__ = 'step_types'

    step_type_id = Column(String(50), primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)  # Display category (Network Checks, Configuration, etc)
    icon = Column(String(50), nullable=True)
    enabled = Column(Boolean, default=True)
    is_builtin = Column(Boolean, default=False)  # Built-in types cannot be deleted

    # Action type determines how the step executes
    # Options: get_config, set_config, api_call, validate, wait, manual
    action_type = Column(String(50), nullable=False)

    # Configuration for the action (all UI-configurable)
    # For get_config: {command, use_textfsm, use_ttp, ttp_template, use_genie}
    # For set_config: {config_lines, template_name, save_config}
    # For api_call: {url, method, headers, body_template, auth_type, expected_status}
    # For validate: {command, patterns: [{pattern, must_match, description}]}
    # For wait: {seconds}
    # For manual: {prompt, instructions}
    config = Column(JSONB, default=dict)

    # Parameters that MOP authors can override when using this step type
    # e.g., {command: {type: 'string', description: 'CLI command', required: true}}
    parameters_schema = Column(JSONB, default=dict)

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


class ConfigSnapshot(Base):
    """
    Configuration snapshots - groups backups taken at the same point in time
    A snapshot represents a "point in time" capture of all devices' configs
    """
    __tablename__ = 'config_snapshots'

    snapshot_id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(255), nullable=True)  # Optional user-friendly name
    description = Column(Text, nullable=True)
    snapshot_type = Column(String(20), default='manual')  # 'manual', 'scheduled', 'pre-change'
    status = Column(String(20), default='in_progress')  # 'in_progress', 'complete', 'partial', 'failed'
    total_devices = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    created_by = Column(String(255), nullable=True)

    # Relationships
    backups = relationship("ConfigBackup", back_populates="snapshot", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_config_snapshots_created', 'created_at'),
        Index('idx_config_snapshots_status', 'status'),
    )


class ConfigBackup(Base):
    """
    Device configuration backups
    Stores running configs for validation and comparison
    """
    __tablename__ = 'config_backups'

    backup_id = Column(String(255), primary_key=True)
    device_name = Column(String(255), nullable=False, index=True)
    device_ip = Column(String(50), nullable=True)
    platform = Column(String(50), nullable=True)  # cisco_ios, juniper_junos, etc.
    config_content = Column(Text, nullable=False)  # The actual config
    config_format = Column(String(20), default='native')  # 'native', 'set' (for Juniper)
    config_hash = Column(String(64), nullable=True)  # SHA256 hash for change detection
    backup_type = Column(String(20), default='scheduled')  # 'scheduled', 'manual', 'pre-change', 'post-change', 'snapshot'
    status = Column(String(20), default='success')  # 'success', 'failed'
    error_message = Column(Text, nullable=True)
    file_size = Column(Integer, nullable=True)  # Size in bytes
    snapshot_id = Column(String(36), ForeignKey('config_snapshots.snapshot_id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255), nullable=True)  # Username or 'scheduler'

    # Relationships
    snapshot = relationship("ConfigSnapshot", back_populates="backups")

    __table_args__ = (
        Index('idx_config_backup_device_created', 'device_name', 'created_at'),
        Index('idx_config_backup_snapshot', 'snapshot_id'),
    )


class BackupSchedule(Base):
    """
    Backup schedule configuration
    Controls when and how backups run
    """
    __tablename__ = 'backup_schedules'

    schedule_id = Column(String(50), primary_key=True, default='default')
    enabled = Column(Boolean, default=True)
    interval_hours = Column(Integer, default=24)  # How often to run backups
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    retention_days = Column(Integer, default=30)  # How long to keep backups
    include_filters = Column(JSONB, default=list)  # Netbox filters for devices to include
    exclude_patterns = Column(JSONB, default=list)  # Device name patterns to exclude
    juniper_set_format = Column(Boolean, default=True)  # Use 'set' format for Juniper devices
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeviceOverride(Base):
    """
    Device-specific overrides for connection settings.
    Allows customization of credentials, platform, timeouts etc. for any device
    (whether from NetBox or manual). These settings override the defaults.
    """
    __tablename__ = 'device_overrides'

    device_name = Column(String(255), primary_key=True)  # Device name as key

    # Connection overrides (null means use default)
    device_type = Column(String(50), nullable=True)  # Override platform/device_type
    host = Column(String(255), nullable=True)  # Override IP/hostname
    port = Column(Integer, nullable=True)  # Override SSH port

    # Credential overrides
    username = Column(String(255), nullable=True)
    password = Column(String(255), nullable=True)  # Encrypted or plaintext
    secret = Column(String(255), nullable=True)  # Enable password

    # Connection settings
    timeout = Column(Integer, nullable=True)  # Connection timeout in seconds
    conn_timeout = Column(Integer, nullable=True)  # Connection timeout
    auth_timeout = Column(Integer, nullable=True)  # Auth timeout
    banner_timeout = Column(Integer, nullable=True)  # Banner timeout

    # Additional settings
    notes = Column(Text, nullable=True)  # Admin notes about this device
    disabled = Column(Boolean, default=False)  # Exclude from bulk operations

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# AI Agent Models
# ============================================================================

class LLMProvider(Base):
    """LLM provider configuration (Anthropic, OpenRouter)"""
    __tablename__ = 'llm_providers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)  # 'anthropic', 'openrouter'
    display_name = Column(String(100), nullable=True)
    api_key = Column(String(500), nullable=False)  # Encrypted
    base_url = Column(String(500), nullable=True)  # For custom endpoints
    default_model = Column(String(100), nullable=True)
    available_models = Column(JSONB, default=list)  # List of available models
    is_enabled = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    config = Column(JSONB, default=dict)  # Additional provider config
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Agent(Base):
    """AI Agent configuration"""
    __tablename__ = 'agents'

    agent_id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(255), nullable=False)
    agent_type = Column(String(50), nullable=False)  # 'triage', 'bgp', 'ospf', 'isis', 'custom'
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)  # Custom system prompt override
    is_enabled = Column(Boolean, default=True)
    is_persistent = Column(Boolean, default=False)  # Runs continuously vs on-demand
    status = Column(String(50), default='idle')  # 'idle', 'running', 'stopped', 'error'

    # LLM Configuration
    llm_provider = Column(String(50), nullable=True)  # Provider name
    llm_model = Column(String(100), nullable=True)  # Model to use
    temperature = Column(Float, default=0.1)
    max_tokens = Column(Integer, default=4096)

    # Tool Configuration
    tools = Column(JSONB, default=list)  # List of enabled tool names
    config = Column(JSONB, default=dict)  # Additional agent config

    # Stats
    total_sessions = Column(Integer, default=0)
    total_messages = Column(Integer, default=0)
    last_active = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    # Relationships
    sessions = relationship("AgentSession", back_populates="agent", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_agents_type', 'agent_type'),
        Index('idx_agents_status', 'status'),
    )


class AgentSession(Base):
    """Agent conversation session"""
    __tablename__ = 'agent_sessions'

    session_id = Column(String(36), primary_key=True)  # UUID
    agent_id = Column(String(36), ForeignKey('agents.agent_id', ondelete='SET NULL'), nullable=True)
    status = Column(String(50), default='active')  # 'active', 'completed', 'failed', 'handoff'
    trigger_type = Column(String(50), default='user')  # 'user', 'alert', 'scheduled', 'mop'
    trigger_data = Column(JSONB, nullable=True)  # Context that triggered the session

    # Handoff tracking
    parent_session_id = Column(String(36), nullable=True)  # If handed off from another session
    handoff_to = Column(String(36), nullable=True)  # If handed off to another session

    # User/context
    user_id = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)

    # Relationships
    agent = relationship("Agent", back_populates="sessions")
    messages = relationship("AgentMessage", back_populates="session", cascade="all, delete-orphan")
    actions = relationship("AgentAction", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_agent_sessions_agent', 'agent_id'),
        Index('idx_agent_sessions_status', 'status'),
    )


class AgentMessage(Base):
    """Chat messages in agent session"""
    __tablename__ = 'agent_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey('agent_sessions.session_id', ondelete='CASCADE'), nullable=False)
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("AgentSession", back_populates="messages")

    __table_args__ = (
        Index('idx_agent_messages_session', 'session_id'),
    )


class AgentAction(Base):
    """Agent thought/action/observation audit log"""
    __tablename__ = 'agent_actions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey('agent_sessions.session_id', ondelete='CASCADE'), nullable=False)
    action_type = Column(String(50), nullable=False)  # 'thought', 'tool_call', 'tool_result', 'handoff', 'escalation'
    tool_name = Column(String(100), nullable=True)
    tool_args = Column(JSONB, nullable=True)
    result = Column(JSONB, nullable=True)
    content = Column(Text, nullable=True)  # For thoughts/observations
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("AgentSession", back_populates="actions")

    __table_args__ = (
        Index('idx_agent_actions_session', 'session_id'),
    )


class AgentTool(Base):
    """Tool definitions for agents"""
    __tablename__ = 'agent_tools'

    name = Column(String(100), primary_key=True)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String(50), default='general')
    risk_level = Column(String(20), default='low')  # 'low', 'medium', 'high', 'critical'
    requires_approval = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)
    is_builtin = Column(Boolean, default=True)
    input_schema = Column(JSONB, nullable=True)  # JSON Schema for tool parameters
    config = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================================
# Knowledge Base Models
# ============================================================================

class KnowledgeCollection(Base):
    """Logical groupings for knowledge documents"""
    __tablename__ = 'knowledge_collections'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    documents = relationship("KnowledgeDocument", back_populates="collection", cascade="all, delete-orphan")


class KnowledgeDocument(Base):
    """Knowledge base documents for RAG"""
    __tablename__ = 'knowledge_documents'

    doc_id = Column(String(36), primary_key=True)  # UUID
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)  # Original content
    doc_type = Column(String(50), default='text')  # 'text', 'markdown', 'pdf', 'html'
    source = Column(String(255), nullable=True)  # Where the doc came from
    collection_id = Column(Integer, ForeignKey('knowledge_collections.id', ondelete='SET NULL'), nullable=True)
    is_indexed = Column(Boolean, default=False)  # Has embeddings been generated
    doc_metadata = Column(JSONB, default=dict)  # Additional document metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    collection = relationship("KnowledgeCollection", back_populates="documents")
    embeddings = relationship("KnowledgeEmbedding", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_knowledge_docs_collection', 'collection_id'),
    )


class KnowledgeEmbedding(Base):
    """Vector embeddings for RAG search (uses pgvector)"""
    __tablename__ = 'knowledge_embeddings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String(36), ForeignKey('knowledge_documents.doc_id', ondelete='CASCADE'), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    # Note: embedding column is vector(1536) - handled via raw SQL for pgvector
    # embedding = Column(Vector(1536))  # Requires pgvector extension
    token_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    document = relationship("KnowledgeDocument", back_populates="embeddings")

    __table_args__ = (
        Index('idx_knowledge_embeddings_doc', 'doc_id'),
    )


# ============================================================================
# Alert and Incident Models
# ============================================================================

class AlertSource(Base):
    """Alert source configurations (webhooks, polling)"""
    __tablename__ = 'alert_sources'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    source_type = Column(String(50), nullable=False)  # 'webhook', 'poll', 'snmp'
    config = Column(JSONB, default=dict)  # Source-specific config
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    alerts = relationship("Alert", back_populates="source_ref")


class Alert(Base):
    """Incoming alerts from monitoring systems"""
    __tablename__ = 'alerts'

    alert_id = Column(String(36), primary_key=True)  # UUID
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String(20), default='warning')  # 'info', 'warning', 'error', 'critical'
    status = Column(String(50), default='new')  # 'new', 'acknowledged', 'processing', 'resolved'
    source = Column(String(100), nullable=True)  # Alert source name
    source_id = Column(String(255), nullable=True)  # ID from source system
    source_ref_id = Column(Integer, ForeignKey('alert_sources.id', ondelete='SET NULL'), nullable=True)
    device = Column(String(255), nullable=True)  # Affected device
    incident_id = Column(String(36), ForeignKey('incidents.incident_id', ondelete='SET NULL'), nullable=True)
    alert_data = Column(JSONB, default=dict)  # Raw alert data from source
    created_at = Column(DateTime, default=datetime.utcnow)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(255), nullable=True)

    # Relationships
    source_ref = relationship("AlertSource", back_populates="alerts")
    incident = relationship("Incident", back_populates="alerts")

    __table_args__ = (
        Index('idx_alerts_status', 'status'),
        Index('idx_alerts_severity', 'severity'),
        Index('idx_alerts_incident', 'incident_id'),
    )


class Incident(Base):
    """Correlated incidents grouping alerts"""
    __tablename__ = 'incidents'

    incident_id = Column(String(36), primary_key=True)  # UUID
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String(20), default='warning')
    status = Column(String(50), default='open')  # 'open', 'investigating', 'identified', 'resolved', 'closed'
    source = Column(String(100), nullable=True)  # What created the incident
    resolution = Column(Text, nullable=True)
    incident_data = Column(JSONB, default=dict)  # Additional incident data
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    alerts = relationship("Alert", back_populates="incident")

    __table_args__ = (
        Index('idx_incidents_status', 'status'),
    )


# ============================================================================
# Approval Workflow Models
# ============================================================================

class PendingApproval(Base):
    """Approval requests for high-risk agent actions"""
    __tablename__ = 'pending_approvals'

    approval_id = Column(String(36), primary_key=True)  # UUID
    session_id = Column(String(36), nullable=True)  # Agent session requesting approval
    agent_id = Column(String(36), nullable=True)
    action_type = Column(String(100), nullable=False)  # e.g., 'device_config', 'execute_mop'
    action_summary = Column(String(500), nullable=False)  # Brief description
    action_details = Column(JSONB, nullable=False)  # Full action details
    risk_level = Column(String(20), default='high')  # 'medium', 'high', 'critical'
    status = Column(String(50), default='pending')  # 'pending', 'approved', 'rejected', 'expired'
    expires_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(255), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_pending_approvals_status', 'status'),
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
    # Network Check Steps (get_config action type)
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
            'command': {'type': 'string', 'description': 'BGP command to run', 'default': 'show ip bgp summary'},
            'expected_neighbors': {'type': 'integer', 'description': 'Expected number of established neighbors'}
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
            'command': {'type': 'string', 'description': 'Interface command', 'default': 'show ip interface brief'}
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
            'command': {'type': 'string', 'description': 'Routing command', 'default': 'show ip route'},
            'expected_routes': {'type': 'array', 'description': 'List of expected route prefixes'}
        }
    },
    # Generic Get Config Step
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
            'command': {'type': 'string', 'description': 'CLI command to execute', 'required': True},
            'use_textfsm': {'type': 'boolean', 'description': 'Parse output with TextFSM', 'default': False},
            'use_ttp': {'type': 'boolean', 'description': 'Parse output with TTP', 'default': False},
            'ttp_template': {'type': 'string', 'description': 'TTP template (if use_ttp is true)'},
            'use_genie': {'type': 'boolean', 'description': 'Parse output with Genie', 'default': False}
        }
    },
    # Set Config Step
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
            'config_lines': {'type': 'array', 'description': 'Configuration commands to push', 'required': True},
            'template_name': {'type': 'string', 'description': 'Use saved config template by name'},
            'save_config': {'type': 'boolean', 'description': 'Save config after push', 'default': True}
        }
    },
    # Validation Step
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
            'command': {'type': 'string', 'description': 'Command to run for validation', 'default': 'show running-config'},
            'patterns': {
                'type': 'array',
                'description': 'Patterns to check',
                'items': {
                    'pattern': {'type': 'string', 'description': 'Regex pattern to match'},
                    'must_match': {'type': 'boolean', 'description': 'True if pattern must exist, False if must not exist', 'default': True},
                    'description': {'type': 'string', 'description': 'Description of what this validates'}
                }
            }
        }
    },
    # API Call Step
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
            'url': {'type': 'string', 'description': 'API endpoint URL', 'required': True},
            'method': {'type': 'string', 'description': 'HTTP method', 'default': 'GET', 'enum': ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']},
            'headers': {'type': 'object', 'description': 'HTTP headers'},
            'body': {'type': 'string', 'description': 'Request body (supports Jinja2 templating)'},
            'expected_status': {'type': 'array', 'description': 'Expected HTTP status codes', 'default': [200, 201, 204]}
        }
    },
    # Wait Step
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
            'seconds': {'type': 'integer', 'description': 'Seconds to wait', 'required': True, 'default': 30}
        }
    },
    # Manual Approval Step
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
            'prompt': {'type': 'string', 'description': 'Approval prompt message', 'default': 'Please review and approve to continue'},
            'instructions': {'type': 'string', 'description': 'Detailed instructions for reviewer'}
        }
    },
    # Webhook/Notification Step
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
            'url': {'type': 'string', 'description': 'Webhook URL', 'required': True},
            'message': {'type': 'string', 'description': 'Message to send'},
            'channel': {'type': 'string', 'description': 'Channel (if applicable)'}
        }
    },
    # Deploy Service Stack Step
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
            'stack_name': {'type': 'string', 'description': 'Name of the service stack to deploy', 'required': True},
            'stack_id': {'type': 'string', 'description': 'ID of the service stack (alternative to name)'},
            'validate_only': {'type': 'boolean', 'description': 'Only validate, do not deploy', 'default': False}
        }
    },
]

DEFAULT_MENU_ITEMS = [
    {'item_id': 'dashboard', 'label': 'Dashboard', 'icon': 'home', 'url': '/', 'order_index': 0, 'visible': True},
    {'item_id': 'deploy', 'label': 'Deploy Config', 'icon': 'rocket', 'url': '/deploy', 'order_index': 1, 'visible': True},
    {'item_id': 'monitor', 'label': 'Monitor Jobs', 'icon': 'chart-line', 'url': '/monitor', 'order_index': 2, 'visible': True},
    {'item_id': 'templates', 'label': 'Config Templates', 'icon': 'file-code', 'url': '/templates', 'order_index': 3, 'visible': True},
    {'item_id': 'service-stacks', 'label': 'Service Stacks', 'icon': 'layer-group', 'url': '/service-stacks', 'order_index': 4, 'visible': True},
    {'item_id': 'devices', 'label': 'Devices', 'icon': 'server', 'url': '/devices', 'order_index': 5, 'visible': True},
    {'item_id': 'snapshots', 'label': 'Snapshots', 'icon': 'camera', 'url': '/snapshots', 'order_index': 6, 'visible': True},
    {'item_id': 'mop', 'label': 'Procedures (MOP)', 'icon': 'list-check', 'url': '/mop', 'order_index': 7, 'visible': True},
    {'item_id': 'agents', 'label': 'AI Agents', 'icon': 'robot', 'url': '/agents', 'order_index': 8, 'visible': True},
    {'item_id': 'alerts', 'label': 'Alerts', 'icon': 'bell', 'url': '/alerts', 'order_index': 9, 'visible': True},
    {'item_id': 'knowledge', 'label': 'Knowledge Base', 'icon': 'book', 'url': '/knowledge', 'order_index': 10, 'visible': True},
]

# Default AI Agent Tools
DEFAULT_AGENT_TOOLS = [
    {'name': 'device_show', 'display_name': 'Device Show Command', 'description': 'Execute show commands on network devices', 'category': 'device', 'risk_level': 'low', 'requires_approval': False, 'is_builtin': True},
    {'name': 'device_config', 'display_name': 'Device Configuration', 'description': 'Push configuration changes to devices', 'category': 'device', 'risk_level': 'high', 'requires_approval': True, 'is_builtin': True},
    {'name': 'device_multi_command', 'display_name': 'Multi-Command', 'description': 'Execute multiple show commands on a device', 'category': 'device', 'risk_level': 'low', 'requires_approval': False, 'is_builtin': True},
    {'name': 'knowledge_search', 'display_name': 'Knowledge Search', 'description': 'Search the knowledge base for relevant documentation', 'category': 'knowledge', 'risk_level': 'low', 'requires_approval': False, 'is_builtin': True},
    {'name': 'knowledge_context', 'display_name': 'Knowledge Context', 'description': 'Get expanded context from knowledge documents', 'category': 'knowledge', 'risk_level': 'low', 'requires_approval': False, 'is_builtin': True},
    {'name': 'knowledge_list', 'display_name': 'Knowledge List', 'description': 'List available knowledge collections', 'category': 'knowledge', 'risk_level': 'low', 'requires_approval': False, 'is_builtin': True},
    {'name': 'handoff', 'display_name': 'Handoff to Specialist', 'description': 'Hand off conversation to a specialist agent', 'category': 'workflow', 'risk_level': 'low', 'requires_approval': False, 'is_builtin': True},
    {'name': 'escalate', 'display_name': 'Escalate to Human', 'description': 'Escalate issue to human operators', 'category': 'workflow', 'risk_level': 'low', 'requires_approval': False, 'is_builtin': True},
    {'name': 'create_incident', 'display_name': 'Create Incident', 'description': 'Create a new incident for tracking', 'category': 'workflow', 'risk_level': 'low', 'requires_approval': False, 'is_builtin': True},
    {'name': 'update_incident', 'display_name': 'Update Incident', 'description': 'Update an existing incident', 'category': 'workflow', 'risk_level': 'low', 'requires_approval': False, 'is_builtin': True},
    {'name': 'execute_mop', 'display_name': 'Execute MOP', 'description': 'Execute a Method of Procedure', 'category': 'workflow', 'risk_level': 'high', 'requires_approval': True, 'is_builtin': True},
]

# Default Knowledge Collections
DEFAULT_KNOWLEDGE_COLLECTIONS = [
    {'name': 'runbooks', 'description': 'Standard Operating Procedures and runbooks'},
    {'name': 'vendor-docs', 'description': 'Vendor documentation and guides'},
    {'name': 'troubleshooting', 'description': 'Troubleshooting guides and past incident resolutions'},
    {'name': 'network-topology', 'description': 'Network topology and architecture documentation'},
]


def seed_defaults(session):
    """Seed default data into the database"""
    # Seed step types
    existing_step_types = session.query(StepType).count()
    if existing_step_types == 0:
        for st in DEFAULT_STEP_TYPES:
            session.add(StepType(**st, enabled=True))
        session.commit()

    # Seed menu items
    existing_menu_items = session.query(MenuItem).count()
    if existing_menu_items == 0:
        for mi in DEFAULT_MENU_ITEMS:
            session.add(MenuItem(**mi))
        session.commit()

    # Seed agent tools
    existing_tools = session.query(AgentTool).count()
    if existing_tools == 0:
        for tool in DEFAULT_AGENT_TOOLS:
            session.add(AgentTool(**tool, is_enabled=True))
        session.commit()

    # Seed knowledge collections
    existing_collections = session.query(KnowledgeCollection).count()
    if existing_collections == 0:
        for coll in DEFAULT_KNOWLEDGE_COLLECTIONS:
            session.add(KnowledgeCollection(**coll))
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
