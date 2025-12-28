"""
Anthropic Claude LLM Client

Native integration with Anthropic's Claude API.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Generator

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from .base import LLMClient, LLMResponse, ToolCall, StreamEvent

log = logging.getLogger(__name__)


class AnthropicClient(LLMClient):
    """Anthropic Claude API client"""

    provider_name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514", **kwargs):
        super().__init__(api_key, model, **kwargs)

        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

        self.client = anthropic.Anthropic(api_key=api_key)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        **kwargs
    ) -> LLMResponse:
        """Send chat completion to Claude"""

        # Extract system message if present
        system_content = None
        api_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            elif msg.get("role") == "tool":
                # Convert tool result to Anthropic format
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id"),
                        "content": msg.get("content", "")
                    }]
                })
            elif msg.get("role") == "assistant" and msg.get("tool_calls"):
                # Convert assistant message with tool calls
                content_blocks = []
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                for tc in msg["tool_calls"]:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id") or tc.get("tool_call_id"),
                        "name": tc.get("function", {}).get("name") or tc.get("name"),
                        "input": self._parse_arguments(tc)
                    })
                api_messages.append({"role": "assistant", "content": content_blocks})
            else:
                api_messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })

        # Build request parameters
        params = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": api_messages,
            "temperature": temperature,
        }

        if system_content:
            params["system"] = system_content

        if tools:
            params["tools"] = self._convert_tools(tools)

        try:
            response = self.client.messages.create(**params)
            return self._parse_response(response)
        except anthropic.APIError as e:
            log.error(f"Anthropic API error: {e}")
            raise

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        **kwargs
    ) -> Generator[StreamEvent, None, None]:
        """Stream chat completion from Claude"""

        # Extract system message if present
        system_content = None
        api_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            elif msg.get("role") == "tool":
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id"),
                        "content": msg.get("content", "")
                    }]
                })
            elif msg.get("role") == "assistant" and msg.get("tool_calls"):
                content_blocks = []
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                for tc in msg["tool_calls"]:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id") or tc.get("tool_call_id"),
                        "name": tc.get("function", {}).get("name") or tc.get("name"),
                        "input": self._parse_arguments(tc)
                    })
                api_messages.append({"role": "assistant", "content": content_blocks})
            else:
                api_messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })

        params = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": api_messages,
            "temperature": temperature,
        }

        if system_content:
            params["system"] = system_content

        if tools:
            params["tools"] = self._convert_tools(tools)

        try:
            with self.client.messages.stream(**params) as stream:
                current_tool_call = None

                for event in stream:
                    if hasattr(event, 'type'):
                        if event.type == 'content_block_start':
                            block = event.content_block
                            if hasattr(block, 'type'):
                                if block.type == 'tool_use':
                                    current_tool_call = ToolCall(
                                        id=block.id,
                                        name=block.name,
                                        arguments={}
                                    )
                                    yield StreamEvent(type='tool_call_start', tool_call=current_tool_call)

                        elif event.type == 'content_block_delta':
                            delta = event.delta
                            if hasattr(delta, 'type'):
                                if delta.type == 'text_delta':
                                    yield StreamEvent(type='content', content=delta.text)
                                elif delta.type == 'input_json_delta' and current_tool_call:
                                    # Accumulate JSON for tool call
                                    pass  # Will parse at end

                        elif event.type == 'content_block_stop':
                            if current_tool_call:
                                yield StreamEvent(type='tool_call_end', tool_call=current_tool_call)
                                current_tool_call = None

                        elif event.type == 'message_stop':
                            yield StreamEvent(type='done')

                # Get final message for usage stats
                final_message = stream.get_final_message()
                if final_message:
                    yield StreamEvent(
                        type='done',
                        usage={
                            'input_tokens': final_message.usage.input_tokens,
                            'output_tokens': final_message.usage.output_tokens
                        }
                    )

        except anthropic.APIError as e:
            log.error(f"Anthropic streaming error: {e}")
            raise

    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI-style tools to Anthropic format"""
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}})
                })
            else:
                # Already in simplified format
                anthropic_tools.append({
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("parameters", {"type": "object", "properties": {}})
                })
        return anthropic_tools

    def _parse_response(self, response) -> LLMResponse:
        """Parse Anthropic response to standard format"""
        content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {}
                ))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            usage={
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens
            },
            raw_response=response
        )

    def _parse_arguments(self, tool_call: Dict) -> Dict:
        """Parse tool call arguments from various formats"""
        if "function" in tool_call:
            args = tool_call["function"].get("arguments", {})
        else:
            args = tool_call.get("arguments", {})

        if isinstance(args, str):
            try:
                return json.loads(args)
            except json.JSONDecodeError:
                return {"raw": args}
        return args

    def format_tool_result(self, tool_call_id: str, result: Any) -> Dict[str, Any]:
        """Format tool result for Anthropic (user message with tool_result block)"""
        content = json.dumps(result) if not isinstance(result, str) else result
        return {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": content
            }]
        }

    def format_assistant_with_tool_calls(
        self,
        content: Optional[str],
        tool_calls: List[ToolCall]
    ) -> Dict[str, Any]:
        """Format assistant message with tool calls for Anthropic"""
        content_blocks = []
        if content:
            content_blocks.append({"type": "text", "text": content})
        for tc in tool_calls:
            content_blocks.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.name,
                "input": tc.arguments
            })
        return {"role": "assistant", "content": content_blocks}
