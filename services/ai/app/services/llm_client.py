# services/ai/app/services/llm_client.py
"""
LLM Client Service

Production-ready client for interacting with LLM providers (Anthropic, OpenRouter).
Supports tool use, streaming, and proper error handling.
"""

import json
import logging
from typing import Optional, List, Dict, Any, Generator, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum

import httpx

from netstacks_core.db import get_session, LLMProvider

log = logging.getLogger(__name__)

# API Endpoints
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMError(Exception):
    """Base exception for LLM errors."""
    pass


class ProviderNotFoundError(LLMError):
    """Provider not configured."""
    pass


class APIKeyMissingError(LLMError):
    """API key not configured."""
    pass


class RateLimitError(LLMError):
    """Rate limit exceeded."""
    pass


class ContentFilterError(LLMError):
    """Content was filtered."""
    pass


class EventType(str, Enum):
    """Agent event types for streaming."""
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TEXT = "text"
    FINAL_RESPONSE = "final_response"
    ERROR = "error"
    DONE = "done"


@dataclass
class AgentEvent:
    """Event emitted during agent execution."""
    type: EventType
    content: str = ""
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_result: Optional[Any] = None
    tool_call_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "content": self.content,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_result": self.tool_result,
            "tool_call_id": self.tool_call_id,
            "data": self.data,
        }


@dataclass
class Message:
    """Chat message."""
    role: str  # 'user', 'assistant', 'system'
    content: str
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None


def get_provider_config(provider_name: str) -> tuple[str, str, str]:
    """
    Get provider configuration from database.

    Returns: (api_key, api_base_url, default_model)
    """
    session = get_session()
    try:
        provider = session.query(LLMProvider).filter(
            LLMProvider.name == provider_name,
            LLMProvider.is_enabled == True
        ).first()

        if not provider:
            raise ProviderNotFoundError(f"Provider '{provider_name}' not found or disabled")

        if not provider.api_key:
            raise APIKeyMissingError(f"No API key configured for '{provider_name}'")

        return (
            provider.api_key,
            provider.api_base_url,
            provider.default_model
        )
    finally:
        session.close()


def get_default_provider() -> tuple[str, str, str, str]:
    """
    Get the default enabled provider.

    Returns: (provider_name, api_key, api_base_url, default_model)
    """
    session = get_session()
    try:
        # First try to get the default provider
        provider = session.query(LLMProvider).filter(
            LLMProvider.is_default == True,
            LLMProvider.is_enabled == True
        ).first()

        # Fall back to any enabled provider
        if not provider:
            provider = session.query(LLMProvider).filter(
                LLMProvider.is_enabled == True
            ).first()

        if not provider:
            raise ProviderNotFoundError("No LLM provider configured")

        if not provider.api_key:
            raise APIKeyMissingError(f"No API key configured for '{provider.name}'")

        return (
            provider.name,
            provider.api_key,
            provider.api_base_url,
            provider.default_model
        )
    finally:
        session.close()


class LLMClient:
    """
    Production LLM client with tool use support.

    Supports Anthropic and OpenRouter providers with streaming responses.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_base_url = None

        # Load from database if not provided
        if not self.api_key:
            self._load_provider_config()

    def _load_provider_config(self):
        """Load provider configuration from database."""
        try:
            if self.provider:
                api_key, api_base_url, default_model = get_provider_config(self.provider)
            else:
                self.provider, api_key, api_base_url, default_model = get_default_provider()

            self.api_key = api_key
            self.api_base_url = api_base_url
            if not self.model:
                self.model = default_model
        except LLMError:
            raise
        except Exception as e:
            log.error(f"Error loading provider config: {e}")
            raise LLMError(f"Failed to load provider configuration: {e}")

    def _get_default_model(self) -> str:
        """Get default model for provider."""
        defaults = {
            "anthropic": "claude-sonnet-4-20250514",
            "openrouter": "anthropic/claude-3.5-sonnet",
            "openai": "gpt-4o",
        }
        return defaults.get(self.provider, "claude-sonnet-4-20250514")

    def _format_tools_for_anthropic(self, tools: List[Dict]) -> List[Dict]:
        """Format tools for Anthropic API."""
        formatted = []
        for tool in tools:
            formatted.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("input_schema", tool.get("parameters", {"type": "object", "properties": {}}))
            })
        return formatted

    def _format_tools_for_openrouter(self, tools: List[Dict]) -> List[Dict]:
        """Format tools for OpenRouter API (OpenAI format)."""
        formatted = []
        for tool in tools:
            formatted.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", tool.get("parameters", {"type": "object", "properties": {}}))
                }
            })
        return formatted

    def _format_messages_for_anthropic(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None
    ) -> tuple[Optional[str], List[Dict]]:
        """Format messages for Anthropic API."""
        formatted = []

        for msg in messages:
            if msg.role == "system":
                # Anthropic uses a separate system parameter
                if system_prompt is None:
                    system_prompt = msg.content
                continue

            if msg.role == "tool":
                # Tool results in Anthropic format
                formatted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content
                    }]
                })
            elif msg.tool_calls:
                # Assistant message with tool calls
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc.get("input", tc.get("arguments", {}))
                    })
                formatted.append({"role": "assistant", "content": content})
            else:
                formatted.append({
                    "role": msg.role,
                    "content": msg.content
                })

        return system_prompt, formatted

    def _format_messages_for_openrouter(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None
    ) -> List[Dict]:
        """Format messages for OpenRouter API (OpenAI format)."""
        formatted = []

        if system_prompt:
            formatted.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if msg.role == "system" and not system_prompt:
                formatted.append({"role": "system", "content": msg.content})
            elif msg.role == "tool":
                formatted.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content
                })
            elif msg.tool_calls:
                tool_calls = []
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc.get("input", tc.get("arguments", {})))
                        }
                    })
                formatted.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": tool_calls
                })
            else:
                formatted.append({
                    "role": msg.role,
                    "content": msg.content
                })

        return formatted

    async def chat(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request.

        Returns the full response including any tool calls.
        """
        model = self.model or self._get_default_model()

        if self.provider == "anthropic":
            return await self._chat_anthropic(messages, system_prompt, tools, model)
        elif self.provider in ("openrouter", "openai"):
            return await self._chat_openrouter(messages, system_prompt, tools, model)
        else:
            raise LLMError(f"Unsupported provider: {self.provider}")

    async def _chat_anthropic(
        self,
        messages: List[Message],
        system_prompt: Optional[str],
        tools: Optional[List[Dict]],
        model: str
    ) -> Dict[str, Any]:
        """Chat using Anthropic API."""
        system, formatted_messages = self._format_messages_for_anthropic(messages, system_prompt)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = {
            "model": model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": formatted_messages,
        }

        if system:
            payload["system"] = system

        if tools:
            payload["tools"] = self._format_tools_for_anthropic(tools)

        url = self.api_base_url or ANTHROPIC_API_URL

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code == 429:
                    raise RateLimitError("Rate limit exceeded")

                response.raise_for_status()
                data = response.json()

                return self._parse_anthropic_response(data)

            except httpx.HTTPStatusError as e:
                log.error(f"Anthropic API error: {e.response.text}")
                raise LLMError(f"API error: {e.response.status_code}")

    async def _chat_openrouter(
        self,
        messages: List[Message],
        system_prompt: Optional[str],
        tools: Optional[List[Dict]],
        model: str
    ) -> Dict[str, Any]:
        """Chat using OpenRouter API."""
        formatted_messages = self._format_messages_for_openrouter(messages, system_prompt)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://netstacks.io",
            "X-Title": "NetStacks AI Agent",
        }

        payload = {
            "model": model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": formatted_messages,
        }

        if tools:
            payload["tools"] = self._format_tools_for_openrouter(tools)
            payload["tool_choice"] = "auto"

        url = self.api_base_url or OPENROUTER_API_URL

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code == 429:
                    raise RateLimitError("Rate limit exceeded")

                response.raise_for_status()
                data = response.json()

                return self._parse_openrouter_response(data)

            except httpx.HTTPStatusError as e:
                log.error(f"OpenRouter API error: {e.response.text}")
                raise LLMError(f"API error: {e.response.status_code}")

    def _parse_anthropic_response(self, data: Dict) -> Dict[str, Any]:
        """Parse Anthropic API response."""
        result = {
            "content": "",
            "tool_calls": [],
            "stop_reason": data.get("stop_reason"),
            "usage": data.get("usage", {}),
        }

        for block in data.get("content", []):
            if block["type"] == "text":
                result["content"] += block["text"]
            elif block["type"] == "tool_use":
                result["tool_calls"].append({
                    "id": block["id"],
                    "name": block["name"],
                    "input": block["input"],
                })

        return result

    def _parse_openrouter_response(self, data: Dict) -> Dict[str, Any]:
        """Parse OpenRouter API response."""
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        result = {
            "content": message.get("content", ""),
            "tool_calls": [],
            "stop_reason": choice.get("finish_reason"),
            "usage": data.get("usage", {}),
        }

        for tc in message.get("tool_calls", []):
            func = tc.get("function", {})
            args = func.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            result["tool_calls"].append({
                "id": tc["id"],
                "name": func.get("name"),
                "input": args,
            })

        return result

    async def stream_chat(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Stream a chat completion request.

        Yields AgentEvents as they arrive.
        """
        model = self.model or self._get_default_model()

        if self.provider == "anthropic":
            async for event in self._stream_anthropic(messages, system_prompt, tools, model):
                yield event
        elif self.provider in ("openrouter", "openai"):
            async for event in self._stream_openrouter(messages, system_prompt, tools, model):
                yield event
        else:
            raise LLMError(f"Unsupported provider: {self.provider}")

    async def _stream_anthropic(
        self,
        messages: List[Message],
        system_prompt: Optional[str],
        tools: Optional[List[Dict]],
        model: str
    ) -> AsyncGenerator[AgentEvent, None]:
        """Stream using Anthropic API."""
        system, formatted_messages = self._format_messages_for_anthropic(messages, system_prompt)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = {
            "model": model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": formatted_messages,
            "stream": True,
        }

        if system:
            payload["system"] = system

        if tools:
            payload["tools"] = self._format_tools_for_anthropic(tools)

        url = self.api_base_url or ANTHROPIC_API_URL

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code == 429:
                    yield AgentEvent(type=EventType.ERROR, content="Rate limit exceeded")
                    return

                if response.status_code >= 400:
                    yield AgentEvent(type=EventType.ERROR, content=f"API error: {response.status_code}")
                    return

                current_text = ""
                current_tool = None
                tool_input_json = ""

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

                    event_type = data.get("type")

                    if event_type == "content_block_start":
                        block = data.get("content_block", {})
                        if block.get("type") == "tool_use":
                            current_tool = {
                                "id": block.get("id"),
                                "name": block.get("name"),
                            }
                            tool_input_json = ""

                    elif event_type == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            current_text += text
                            yield AgentEvent(type=EventType.TEXT, content=text)
                        elif delta.get("type") == "input_json_delta":
                            tool_input_json += delta.get("partial_json", "")

                    elif event_type == "content_block_stop":
                        if current_tool:
                            try:
                                tool_input = json.loads(tool_input_json) if tool_input_json else {}
                            except json.JSONDecodeError:
                                tool_input = {}

                            yield AgentEvent(
                                type=EventType.TOOL_CALL,
                                tool_name=current_tool["name"],
                                tool_input=tool_input,
                                tool_call_id=current_tool["id"],
                            )
                            current_tool = None
                            tool_input_json = ""

                    elif event_type == "message_stop":
                        if current_text:
                            yield AgentEvent(type=EventType.FINAL_RESPONSE, content=current_text)
                        yield AgentEvent(type=EventType.DONE)

    async def _stream_openrouter(
        self,
        messages: List[Message],
        system_prompt: Optional[str],
        tools: Optional[List[Dict]],
        model: str
    ) -> AsyncGenerator[AgentEvent, None]:
        """Stream using OpenRouter API."""
        formatted_messages = self._format_messages_for_openrouter(messages, system_prompt)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://netstacks.io",
            "X-Title": "NetStacks AI Agent",
        }

        payload = {
            "model": model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": formatted_messages,
            "stream": True,
        }

        if tools:
            payload["tools"] = self._format_tools_for_openrouter(tools)
            payload["tool_choice"] = "auto"

        url = self.api_base_url or OPENROUTER_API_URL

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code == 429:
                    yield AgentEvent(type=EventType.ERROR, content="Rate limit exceeded")
                    return

                if response.status_code >= 400:
                    yield AgentEvent(type=EventType.ERROR, content=f"API error: {response.status_code}")
                    return

                current_text = ""
                tool_calls = {}  # id -> {name, arguments}

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    if line == "data: [DONE]":
                        if current_text:
                            yield AgentEvent(type=EventType.FINAL_RESPONSE, content=current_text)
                        yield AgentEvent(type=EventType.DONE)
                        break

                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

                    choice = data.get("choices", [{}])[0]
                    delta = choice.get("delta", {})

                    # Text content
                    if delta.get("content"):
                        text = delta["content"]
                        current_text += text
                        yield AgentEvent(type=EventType.TEXT, content=text)

                    # Tool calls
                    for tc in delta.get("tool_calls", []):
                        tc_id = tc.get("id")
                        if tc_id and tc_id not in tool_calls:
                            tool_calls[tc_id] = {"name": "", "arguments": ""}

                        func = tc.get("function", {})
                        if func.get("name"):
                            tool_calls[tc_id]["name"] = func["name"]
                        if func.get("arguments"):
                            tool_calls[tc_id]["arguments"] += func["arguments"]

                    # Check for finish
                    if choice.get("finish_reason") == "tool_calls":
                        for tc_id, tc_data in tool_calls.items():
                            try:
                                args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                            except json.JSONDecodeError:
                                args = {}

                            yield AgentEvent(
                                type=EventType.TOOL_CALL,
                                tool_name=tc_data["name"],
                                tool_input=args,
                                tool_call_id=tc_id,
                            )
