"""
Base LLM Client Interface

Defines the abstract interface for all LLM providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Generator
import logging

log = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Represents a tool call from the LLM"""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """Standardized response from LLM providers"""
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    stop_reason: Optional[str] = None
    usage: Dict[str, int] = field(default_factory=dict)  # input_tokens, output_tokens
    raw_response: Optional[Any] = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass
class StreamEvent:
    """Event from streaming response"""
    type: str  # 'content', 'tool_call_start', 'tool_call_delta', 'tool_call_end', 'done'
    content: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    usage: Optional[Dict[str, int]] = None


class LLMClient(ABC):
    """Abstract base class for LLM providers"""

    provider_name: str = "base"

    def __init__(self, api_key: str, model: str, **kwargs):
        self.api_key = api_key
        self.model = model
        self.config = kwargs

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        **kwargs
    ) -> LLMResponse:
        """
        Send chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            LLMResponse with content and/or tool calls
        """
        pass

    @abstractmethod
    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        **kwargs
    ) -> Generator[StreamEvent, None, None]:
        """
        Stream chat completion response.

        Yields:
            StreamEvent objects as response is generated
        """
        pass

    def format_tool_result(self, tool_call_id: str, result: Any) -> Dict[str, Any]:
        """
        Format tool result for adding to messages.
        Override in subclasses for provider-specific formatting.
        """
        import json
        content = json.dumps(result) if not isinstance(result, str) else result
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content
        }

    def format_assistant_with_tool_calls(
        self,
        content: Optional[str],
        tool_calls: List[ToolCall]
    ) -> Dict[str, Any]:
        """
        Format assistant message with tool calls for adding to messages.
        Override in subclasses for provider-specific formatting.
        """
        return {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments if isinstance(tc.arguments, str) else str(tc.arguments)
                    }
                }
                for tc in tool_calls
            ]
        }
