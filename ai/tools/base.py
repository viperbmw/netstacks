"""
Base Tool Classes

Defines the abstract interface for all agent tools.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import logging

log = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result from tool execution"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    requires_approval: bool = False
    approval_id: Optional[str] = None
    risk_level: str = "low"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "requires_approval": self.requires_approval,
            "approval_id": self.approval_id,
            "risk_level": self.risk_level,
        }


class BaseTool(ABC):
    """
    Base class for agent tools.

    All tools must implement:
    - name: Unique tool identifier
    - description: Human-readable description for LLM
    - input_schema: JSON Schema for tool inputs
    - execute(): Main execution method
    """

    name: str = ""
    description: str = ""
    category: str = "general"
    risk_level: str = "low"  # 'low', 'medium', 'high', 'critical'
    requires_approval: bool = False
    is_internal: bool = False  # Internal tools are hidden from UI but available to agents

    def __init__(self, session_context: Optional[Dict] = None):
        """
        Initialize tool with session context.

        Args:
            session_context: Context from the agent session (session_id, devices, etc.)
        """
        self.context = session_context or {}

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """
        JSON Schema defining the tool's input parameters.

        Returns:
            Dict with JSON Schema format defining properties and required fields.
        """
        pass

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with given arguments.

        Args:
            **kwargs: Tool-specific arguments matching input_schema

        Returns:
            ToolResult with success status and data or error
        """
        pass

    def to_llm_format(self) -> Dict[str, Any]:
        """
        Convert tool definition to LLM function format.

        Returns:
            Dict suitable for passing to LLM as a tool/function definition.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema
        }

    def to_openai_format(self) -> Dict[str, Any]:
        """
        Convert to OpenAI function calling format.

        Returns:
            Dict in OpenAI's tool format.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema
            }
        }

    def validate_inputs(self, **kwargs) -> Optional[str]:
        """
        Validate inputs against schema.

        Args:
            **kwargs: Input arguments to validate

        Returns:
            Error message if validation fails, None if valid.
        """
        schema = self.input_schema
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        # Check required fields
        for field in required:
            if field not in kwargs or kwargs[field] is None:
                return f"Missing required field: {field}"

        # Type validation (basic)
        for field, value in kwargs.items():
            if field in properties:
                expected_type = properties[field].get("type")
                if expected_type:
                    if not self._check_type(value, expected_type):
                        return f"Invalid type for {field}: expected {expected_type}"

        return None

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected JSON Schema type"""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected = type_map.get(expected_type)
        if expected is None:
            return True  # Unknown type, allow
        return isinstance(value, expected)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}' risk='{self.risk_level}'>"
