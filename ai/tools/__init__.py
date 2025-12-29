"""
Agent Tool Registry

Provides tools for AI agents to interact with:
- Network devices (show commands, configuration)
- Knowledge base (search)
- Workflows (MOPs, handoffs, escalation)
"""

from .base import BaseTool, ToolResult
from .registry import ToolRegistry, get_registry, register_tool, get_tool

# Device tools
from .device_tools import (
    DeviceListTool,
    DeviceShowTool,
    DeviceConfigTool,
    DeviceMultiCommandTool,
)

# Knowledge tools
from .knowledge_tools import (
    KnowledgeSearchTool,
    KnowledgeContextTool,
    KnowledgeListTool,
)

# Workflow tools
from .workflow_tools import (
    HandoffTool,
    EscalateTool,
    CreateIncidentTool,
    ExecuteMOPTool,
    UpdateIncidentTool,
)

__all__ = [
    # Base classes
    'BaseTool',
    'ToolResult',
    'ToolRegistry',
    'get_registry',
    'register_tool',
    'get_tool',
    # Device tools
    'DeviceListTool',
    'DeviceShowTool',
    'DeviceConfigTool',
    'DeviceMultiCommandTool',
    # Knowledge tools
    'KnowledgeSearchTool',
    'KnowledgeContextTool',
    'KnowledgeListTool',
    # Workflow tools
    'HandoffTool',
    'EscalateTool',
    'CreateIncidentTool',
    'ExecuteMOPTool',
    'UpdateIncidentTool',
    # Registration helper
    'register_all_tools',
]


def register_all_tools(registry: ToolRegistry = None) -> ToolRegistry:
    """
    Register all built-in tools to a registry.

    Args:
        registry: Registry to use (creates new one if None)

    Returns:
        Registry with all tools registered
    """
    if registry is None:
        registry = get_registry()

    # Device tools
    registry.register(DeviceListTool())
    registry.register(DeviceShowTool())
    registry.register(DeviceConfigTool())
    registry.register(DeviceMultiCommandTool())

    # Knowledge tools
    registry.register(KnowledgeSearchTool())
    registry.register(KnowledgeContextTool())
    registry.register(KnowledgeListTool())

    # Workflow tools
    registry.register(HandoffTool())
    registry.register(EscalateTool())
    registry.register(CreateIncidentTool())
    registry.register(ExecuteMOPTool())
    registry.register(UpdateIncidentTool())

    return registry
