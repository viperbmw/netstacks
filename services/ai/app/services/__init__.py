# services/ai/app/services/__init__.py
"""
AI Services Module

Production-ready services for AI agent operations.
"""

from .llm_client import (
    LLMClient,
    LLMError,
    ProviderNotFoundError,
    APIKeyMissingError,
    RateLimitError,
    Message,
    AgentEvent,
    EventType,
)

from .agent_tools import (
    get_tool_definitions,
    get_tool_info,
    execute_tool,
    RiskLevel,
    TOOL_DEFINITIONS,
)

from .agent_executor import (
    AgentExecutor,
    ExecutorConfig,
    ExecutorContext,
    create_agent_session,
    end_agent_session,
    get_session_messages,
)

__all__ = [
    # LLM Client
    "LLMClient",
    "LLMError",
    "ProviderNotFoundError",
    "APIKeyMissingError",
    "RateLimitError",
    "Message",
    "AgentEvent",
    "EventType",
    # Agent Tools
    "get_tool_definitions",
    "get_tool_info",
    "execute_tool",
    "RiskLevel",
    "TOOL_DEFINITIONS",
    # Agent Executor
    "AgentExecutor",
    "ExecutorConfig",
    "ExecutorContext",
    "create_agent_session",
    "end_agent_session",
    "get_session_messages",
]
