"""
Tool Registry

Manages registration, discovery, and retrieval of agent tools.
"""

import logging
from typing import Dict, List, Optional, Any, Type

from .base import BaseTool, ToolResult

log = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all agent tools.

    Manages tool registration, categorization, and retrieval.
    Tools can be registered programmatically or loaded from database.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._categories: Dict[str, List[str]] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool instance.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If tool with same name already registered
        """
        if tool.name in self._tools:
            log.warning(f"Tool '{tool.name}' already registered, replacing")

        self._tools[tool.name] = tool

        # Add to category index
        if tool.category not in self._categories:
            self._categories[tool.category] = []
        if tool.name not in self._categories[tool.category]:
            self._categories[tool.category].append(tool.name)

        log.debug(f"Registered tool: {tool.name} (category: {tool.category})")

    def unregister(self, name: str) -> bool:
        """
        Remove a tool from the registry.

        Args:
            name: Tool name to remove

        Returns:
            True if tool was removed, False if not found
        """
        if name not in self._tools:
            return False

        tool = self._tools.pop(name)

        # Remove from category index
        if tool.category in self._categories:
            if name in self._categories[tool.category]:
                self._categories[tool.category].remove(name)

        log.debug(f"Unregistered tool: {name}")
        return True

    def get(self, name: str) -> Optional[BaseTool]:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def get_all(self) -> List[BaseTool]:
        """Get all registered tools"""
        return list(self._tools.values())

    def get_ui_tools(self) -> List[BaseTool]:
        """Get tools visible in UI (excludes internal tools)"""
        return [
            tool for tool in self._tools.values()
            if not getattr(tool, 'is_internal', False)
        ]

    def get_by_category(self, category: str) -> List[BaseTool]:
        """
        Get all tools in a category.

        Args:
            category: Category name

        Returns:
            List of tools in the category
        """
        tool_names = self._categories.get(category, [])
        return [self._tools[name] for name in tool_names if name in self._tools]

    def get_categories(self) -> List[str]:
        """Get list of all categories"""
        return list(self._categories.keys())

    def get_by_risk_level(self, risk_level: str) -> List[BaseTool]:
        """
        Get all tools with a specific risk level.

        Args:
            risk_level: 'low', 'medium', 'high', or 'critical'

        Returns:
            List of tools matching the risk level
        """
        return [t for t in self._tools.values() if t.risk_level == risk_level]

    def get_for_agent(
        self,
        agent_type: str,
        include_categories: Optional[List[str]] = None,
        exclude_high_risk: bool = False
    ) -> List[BaseTool]:
        """
        Get tools appropriate for a specific agent type.

        Args:
            agent_type: Type of agent (triage, bgp, ospf, isis, etc.)
            include_categories: Only include tools from these categories
            exclude_high_risk: Exclude high and critical risk tools

        Returns:
            List of appropriate tools for the agent
        """
        tools = []

        for tool in self._tools.values():
            # Filter by category
            if include_categories and tool.category not in include_categories:
                continue

            # Filter high risk if requested
            if exclude_high_risk and tool.risk_level in ('high', 'critical'):
                continue

            tools.append(tool)

        return tools

    def to_llm_format(
        self,
        tool_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Convert tools to LLM function calling format.

        Args:
            tool_names: Specific tools to include (None = all)

        Returns:
            List of tool definitions in LLM format
        """
        tools = []

        if tool_names:
            for name in tool_names:
                if name in self._tools:
                    tools.append(self._tools[name].to_llm_format())
        else:
            for tool in self._tools.values():
                tools.append(tool.to_llm_format())

        return tools

    def to_openai_format(
        self,
        tool_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Convert tools to OpenAI function calling format.

        Args:
            tool_names: Specific tools to include (None = all)

        Returns:
            List of tool definitions in OpenAI format
        """
        tools = []

        if tool_names:
            for name in tool_names:
                if name in self._tools:
                    tools.append(self._tools[name].to_openai_format())
        else:
            for tool in self._tools.values():
                tools.append(tool.to_openai_format())

        return tools

    def execute(
        self,
        tool_name: str,
        session_context: Optional[Dict] = None,
        **kwargs
    ) -> ToolResult:
        """
        Execute a tool by name.

        Args:
            tool_name: Name of tool to execute
            session_context: Context from agent session
            **kwargs: Tool-specific arguments

        Returns:
            ToolResult from tool execution
        """
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool not found: {tool_name}"
            )

        # Update tool context if provided
        if session_context:
            tool.context = session_context

        # Validate inputs
        validation_error = tool.validate_inputs(**kwargs)
        if validation_error:
            return ToolResult(
                success=False,
                error=validation_error
            )

        try:
            return tool.execute(**kwargs)
        except Exception as e:
            log.error(f"Tool execution error ({tool_name}): {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __repr__(self) -> str:
        return f"<ToolRegistry tools={len(self._tools)} categories={len(self._categories)}>"


# Global registry instance
_global_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry instance"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def register_tool(tool: BaseTool) -> None:
    """Register a tool to the global registry"""
    get_registry().register(tool)


def get_tool(name: str) -> Optional[BaseTool]:
    """Get a tool from the global registry"""
    return get_registry().get(name)
