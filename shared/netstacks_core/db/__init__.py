"""
Database module for NetStacks Core

Provides:
- SQLAlchemy models for all entities
- Session factory for database connections
- Base class for all models
"""

from .models import (
    Base,
    Setting,
    User,
    Template,
    ServiceStack,
    ServiceInstance,
    Device,
    DefaultCredential,
    StackTemplate,
    APIResource,
    ScheduledStackOperation,
    AuthConfig,
    MenuItem,
    MOP,
    MOPExecution,
    StepType,
    TaskHistory,
    ConfigSnapshot,
    ConfigBackup,
    BackupSchedule,
    DeviceOverride,
    LLMProvider,
    Agent,
    AgentSession,
    AgentMessage,
    AgentAction,
    AgentTool,
    WorkflowLog,
    WorkflowStep,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeEmbedding,
    AlertSource,
    Alert,
    Incident,
    PendingApproval,
    DEFAULT_STEP_TYPES,
    DEFAULT_MENU_ITEMS,
)

from .session import (
    get_engine,
    get_session,
    get_db,
    get_session_factory,
    init_db,
    seed_defaults,
)

__all__ = [
    # Base
    "Base",
    # Models
    "Setting",
    "User",
    "Template",
    "ServiceStack",
    "ServiceInstance",
    "Device",
    "DefaultCredential",
    "StackTemplate",
    "APIResource",
    "ScheduledStackOperation",
    "AuthConfig",
    "MenuItem",
    "MOP",
    "MOPExecution",
    "StepType",
    "TaskHistory",
    "ConfigSnapshot",
    "ConfigBackup",
    "BackupSchedule",
    "DeviceOverride",
    # AI Models
    "LLMProvider",
    "Agent",
    "AgentSession",
    "AgentMessage",
    "AgentAction",
    "AgentTool",
    "WorkflowLog",
    "WorkflowStep",
    "KnowledgeCollection",
    "KnowledgeDocument",
    "KnowledgeEmbedding",
    "AlertSource",
    "Alert",
    "Incident",
    "PendingApproval",
    # Defaults
    "DEFAULT_STEP_TYPES",
    "DEFAULT_MENU_ITEMS",
    # Session
    "get_engine",
    "get_session",
    "get_db",
    "get_session_factory",
    "init_db",
    "seed_defaults",
]
