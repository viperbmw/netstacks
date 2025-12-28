"""
OpenRouter LLM Client

OpenAI-compatible API for accessing multiple LLM providers.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Generator

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from .base import LLMClient, LLMResponse, ToolCall, StreamEvent

log = logging.getLogger(__name__)


class OpenRouterClient(LLMClient):
    """OpenRouter API client (OpenAI-compatible)"""

    provider_name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-3.5-sonnet",
        base_url: str = "https://openrouter.ai/api/v1",
        **kwargs
    ):
        super().__init__(api_key, model, **kwargs)

        if not REQUESTS_AVAILABLE:
            raise ImportError("requests package not installed. Run: pip install requests")

        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": kwargs.get("referer", "https://netstacks.local"),
            "X-Title": kwargs.get("app_name", "NetStacks AI"),
            "Content-Type": "application/json"
        }

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        **kwargs
    ) -> LLMResponse:
        """Send chat completion to OpenRouter"""

        # Format messages (OpenAI format)
        api_messages = self._format_messages(messages)

        payload = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = self._format_tools(tools)
            payload["tool_choice"] = "auto"

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            return self._parse_response(response.json())

        except requests.exceptions.RequestException as e:
            log.error(f"OpenRouter API error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                log.error(f"Response: {e.response.text}")
            raise

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        **kwargs
    ) -> Generator[StreamEvent, None, None]:
        """Stream chat completion from OpenRouter"""

        api_messages = self._format_messages(messages)

        payload = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        if tools:
            payload["tools"] = self._format_tools(tools)
            payload["tool_choice"] = "auto"

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                stream=True,
                timeout=120
            )
            response.raise_for_status()

            current_tool_calls = {}

            for line in response.iter_lines():
                if not line:
                    continue

                line = line.decode('utf-8')
                if not line.startswith('data: '):
                    continue

                data = line[6:]  # Remove 'data: ' prefix
                if data == '[DONE]':
                    yield StreamEvent(type='done')
                    break

                try:
                    chunk = json.loads(data)
                    delta = chunk.get('choices', [{}])[0].get('delta', {})

                    # Handle content
                    if delta.get('content'):
                        yield StreamEvent(type='content', content=delta['content'])

                    # Handle tool calls
                    if delta.get('tool_calls'):
                        for tc in delta['tool_calls']:
                            idx = tc.get('index', 0)
                            if idx not in current_tool_calls:
                                current_tool_calls[idx] = {
                                    'id': tc.get('id', ''),
                                    'name': '',
                                    'arguments': ''
                                }
                                if tc.get('id'):
                                    current_tool_calls[idx]['id'] = tc['id']

                            if tc.get('function', {}).get('name'):
                                current_tool_calls[idx]['name'] = tc['function']['name']
                                yield StreamEvent(
                                    type='tool_call_start',
                                    tool_call=ToolCall(
                                        id=current_tool_calls[idx]['id'],
                                        name=tc['function']['name'],
                                        arguments={}
                                    )
                                )

                            if tc.get('function', {}).get('arguments'):
                                current_tool_calls[idx]['arguments'] += tc['function']['arguments']

                    # Check for finish reason
                    finish_reason = chunk.get('choices', [{}])[0].get('finish_reason')
                    if finish_reason:
                        # Finalize tool calls
                        for idx, tc_data in current_tool_calls.items():
                            try:
                                args = json.loads(tc_data['arguments']) if tc_data['arguments'] else {}
                            except json.JSONDecodeError:
                                args = {'raw': tc_data['arguments']}

                            yield StreamEvent(
                                type='tool_call_end',
                                tool_call=ToolCall(
                                    id=tc_data['id'],
                                    name=tc_data['name'],
                                    arguments=args
                                )
                            )

                        # Get usage if available
                        usage = chunk.get('usage')
                        if usage:
                            yield StreamEvent(
                                type='done',
                                usage={
                                    'input_tokens': usage.get('prompt_tokens', 0),
                                    'output_tokens': usage.get('completion_tokens', 0)
                                }
                            )

                except json.JSONDecodeError:
                    continue

        except requests.exceptions.RequestException as e:
            log.error(f"OpenRouter streaming error: {e}")
            raise

    def _format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format messages for OpenAI-compatible API"""
        formatted = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "tool":
                # Tool result message
                formatted.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "content": content if isinstance(content, str) else json.dumps(content)
                })
            elif role == "assistant" and msg.get("tool_calls"):
                # Assistant message with tool calls
                tc_formatted = []
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict):
                        tc_id = tc.get("id") or tc.get("tool_call_id", "")
                        if "function" in tc:
                            tc_formatted.append({
                                "id": tc_id,
                                "type": "function",
                                "function": {
                                    "name": tc["function"].get("name", ""),
                                    "arguments": tc["function"].get("arguments", "{}")
                                }
                            })
                        else:
                            args = tc.get("arguments", {})
                            tc_formatted.append({
                                "id": tc_id,
                                "type": "function",
                                "function": {
                                    "name": tc.get("name", ""),
                                    "arguments": json.dumps(args) if isinstance(args, dict) else str(args)
                                }
                            })

                formatted.append({
                    "role": "assistant",
                    "content": content if content else None,
                    "tool_calls": tc_formatted
                })
            else:
                formatted.append({
                    "role": role,
                    "content": content
                })

        return formatted

    def _format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format tools for OpenAI-compatible API"""
        formatted = []
        for tool in tools:
            if tool.get("type") == "function":
                formatted.append(tool)
            else:
                # Convert simplified format to OpenAI format
                formatted.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {"type": "object", "properties": {}})
                    }
                })
        return formatted

    def _parse_response(self, data: Dict[str, Any]) -> LLMResponse:
        """Parse OpenAI-compatible response to standard format"""
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        content = message.get("content", "") or ""
        tool_calls = []

        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                args = func.get("arguments", "{}")
                try:
                    parsed_args = json.loads(args) if isinstance(args, str) else args
                except json.JSONDecodeError:
                    parsed_args = {"raw": args}

                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=func.get("name", ""),
                    arguments=parsed_args
                ))

        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=choice.get("finish_reason"),
            usage={
                'input_tokens': usage.get('prompt_tokens', 0),
                'output_tokens': usage.get('completion_tokens', 0)
            },
            raw_response=data
        )
