"""
Base Agent Class

Implements the ReAct (Reason → Act → Observe) pattern for agent execution.
All specialized agents inherit from this base class.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Generator

from ai.llm import get_llm_client, LLMResponse
from ai.tools import ToolRegistry, get_registry, register_all_tools, ToolResult

log = logging.getLogger(__name__)


def get_platform_context_summary() -> str:
    """
    Generate a brief platform context summary for agent system prompts.
    Injected automatically so agents understand current platform state.
    """
    try:
        from services.platform_stats_service import get_platform_stats
        stats = get_platform_stats()

        summary = f"""
## Current NetStacks Platform State

- **Devices:** {stats.get('devices', {}).get('total', 0)} total
- **Templates:** {stats.get('templates', {}).get('total', 0)} available
- **Service Stacks:** {stats.get('stacks', {}).get('deployed', 0)} deployed / {stats.get('stacks', {}).get('total', 0)} total
- **Open Incidents:** {stats.get('incidents', {}).get('open', 0)}
- **Active Agents:** {stats.get('agents', {}).get('active', 0)}

You have access to internal platform tools: platform_status, stack_info, template_info, incident_status, system_health, platform_concepts.
"""
        return summary.strip()
    except Exception as e:
        log.warning(f"Platform context unavailable: {e}")
        return ""


class AgentEventType(Enum):
    """Types of events emitted during agent execution"""
    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    OBSERVATION = "observation"
    FINAL_RESPONSE = "final_response"
    HANDOFF = "handoff"
    ESCALATION = "escalation"
    APPROVAL_REQUIRED = "approval_required"
    ERROR = "error"
    DONE = "done"


@dataclass
class AgentEvent:
    """Event emitted during agent execution"""
    type: AgentEventType
    content: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tool_name: Optional[str] = None
    tool_args: Optional[Dict] = None
    tool_result: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'type': self.type.value,
            'content': self.content,
            'data': self.data,
            'timestamp': self.timestamp.isoformat(),
            'tool_name': self.tool_name,
            'tool_args': self.tool_args,
            'tool_result': self.tool_result,
        }


class BaseAgent(ABC):
    """
    Base class for all AI agents.

    Implements the ReAct pattern:
    1. Reason: Analyze the situation and decide on next action
    2. Act: Execute a tool or respond
    3. Observe: Process tool results
    4. Repeat until done or handoff

    Subclasses must implement:
    - agent_type: Unique identifier for the agent type
    - system_prompt: Prompt defining agent behavior
    - get_tools(): Return list of tools available to this agent
    """

    agent_type: str = "base"
    agent_name: str = "Base Agent"
    description: str = "Base agent class"

    # Configuration
    max_iterations: int = 10
    temperature: float = 0.1
    max_tokens: int = 4096

    def __init__(
        self,
        session_id: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        config: Optional[Dict] = None
    ):
        """
        Initialize agent.

        Args:
            session_id: Session ID for this agent instance
            llm_provider: LLM provider to use (None = default)
            llm_model: Model to use (None = provider default)
            config: Additional configuration
        """
        self.session_id = session_id or str(uuid.uuid4())
        self.config = config or {}
        self.messages: List[Dict[str, Any]] = []
        self.actions: List[AgentEvent] = []

        # Initialize LLM client
        self.llm = get_llm_client(provider=llm_provider, model=llm_model)

        # Initialize tool registry with agent-specific tools
        self.tool_registry = ToolRegistry()
        self._register_tools()

        # Context passed to tools
        self.context = {
            'session_id': self.session_id,
            'agent_type': self.agent_type,
        }

        log.info(f"Initialized {self.agent_type} agent with session {self.session_id}")

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """
        System prompt defining agent behavior.

        Should include:
        - Role and capabilities description
        - Available tools and when to use them
        - Reasoning guidelines
        - Output format expectations
        """
        pass

    def _register_tools(self) -> None:
        """
        Register tools available to this agent.

        Override in subclasses to customize available tools.
        Default implementation registers all tools.
        """
        register_all_tools(self.tool_registry)

    def get_tools(self) -> List[Dict[str, Any]]:
        """
        Get tools in LLM format for this agent.

        Override to filter or customize tools per agent type.
        """
        return self.tool_registry.to_openai_format()

    def run(
        self,
        user_message: str,
        context: Optional[Dict] = None
    ) -> Generator[AgentEvent, None, None]:
        """
        Execute the ReAct loop.

        Args:
            user_message: User's input message
            context: Additional context (alert data, device info, etc.)

        Yields:
            AgentEvent objects as the agent reasons and acts
        """
        # Update context
        if context:
            self.context.update(context)

        # Add system message if first interaction
        if not self.messages:
            # Build system prompt with platform context
            platform_context = get_platform_context_summary()
            full_system_prompt = self.system_prompt
            if platform_context:
                full_system_prompt = f"{self.system_prompt}\n\n{platform_context}"

            self.messages.append({
                "role": "system",
                "content": full_system_prompt
            })

        # Add context as system reminder if provided
        if context:
            context_prompt = self._format_context(context)
            if context_prompt:
                self.messages.append({
                    "role": "system",
                    "content": f"Context for this request:\n{context_prompt}"
                })

        # Add user message
        self.messages.append({
            "role": "user",
            "content": user_message
        })

        # Get available tools
        tools = self.get_tools()

        # ReAct loop
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            log.debug(f"ReAct iteration {iteration}/{self.max_iterations}")

            try:
                # Get LLM response
                response = self.llm.chat(
                    messages=self.messages,
                    tools=tools,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )

                # Emit thought if present
                if response.content:
                    thought_event = AgentEvent(
                        type=AgentEventType.THOUGHT,
                        content=response.content
                    )
                    self.actions.append(thought_event)
                    yield thought_event

                # If no tool calls, we're done - emit final response
                if not response.has_tool_calls:
                    final_event = AgentEvent(
                        type=AgentEventType.FINAL_RESPONSE,
                        content=response.content
                    )
                    self.actions.append(final_event)
                    yield final_event

                    # Add to messages
                    self.messages.append({
                        "role": "assistant",
                        "content": response.content
                    })

                    yield AgentEvent(type=AgentEventType.DONE)
                    return

                # Process tool calls
                for tool_call in response.tool_calls:
                    # Emit tool call event
                    tool_call_event = AgentEvent(
                        type=AgentEventType.TOOL_CALL,
                        tool_name=tool_call.name,
                        tool_args=tool_call.arguments
                    )
                    self.actions.append(tool_call_event)
                    yield tool_call_event

                    # Execute tool
                    result = self._execute_tool(tool_call.name, tool_call.arguments)

                    # Check for special results
                    if result.requires_approval:
                        approval_event = AgentEvent(
                            type=AgentEventType.APPROVAL_REQUIRED,
                            content=f"Action requires approval: {tool_call.name}",
                            data={
                                'approval_id': result.approval_id,
                                'tool_name': tool_call.name,
                                'tool_args': tool_call.arguments,
                                'risk_level': result.risk_level,
                                'result_data': result.data
                            }
                        )
                        self.actions.append(approval_event)
                        yield approval_event

                        # Pause execution - approval needed
                        yield AgentEvent(type=AgentEventType.DONE)
                        return

                    # Check for handoff
                    if tool_call.name == "handoff" and result.success:
                        handoff_event = AgentEvent(
                            type=AgentEventType.HANDOFF,
                            content=f"Handing off to {result.data.get('handoff', {}).get('target_agent')}",
                            data=result.data
                        )
                        self.actions.append(handoff_event)
                        yield handoff_event

                        yield AgentEvent(type=AgentEventType.DONE)
                        return

                    # Check for escalation
                    if tool_call.name == "escalate" and result.success:
                        escalation_event = AgentEvent(
                            type=AgentEventType.ESCALATION,
                            content="Issue escalated to human operators",
                            data=result.data
                        )
                        self.actions.append(escalation_event)
                        yield escalation_event

                    # Emit tool result event
                    tool_result_event = AgentEvent(
                        type=AgentEventType.TOOL_RESULT,
                        tool_name=tool_call.name,
                        tool_result=result.to_dict()
                    )
                    self.actions.append(tool_result_event)
                    yield tool_result_event

                    # Add tool call and result to messages
                    self.messages.append(
                        self.llm.format_assistant_with_tool_calls(
                            response.content,
                            [tool_call]
                        )
                    )
                    self.messages.append(
                        self.llm.format_tool_result(
                            tool_call.id,
                            result.to_dict()
                        )
                    )

            except Exception as e:
                log.error(f"Agent error in iteration {iteration}: {e}", exc_info=True)
                error_event = AgentEvent(
                    type=AgentEventType.ERROR,
                    content=str(e)
                )
                self.actions.append(error_event)
                yield error_event
                yield AgentEvent(type=AgentEventType.DONE)
                return

        # Max iterations reached
        log.warning(f"Agent {self.session_id} reached max iterations")
        yield AgentEvent(
            type=AgentEventType.ERROR,
            content="Maximum iterations reached without resolution"
        )
        yield AgentEvent(type=AgentEventType.DONE)

    def _execute_tool(self, tool_name: str, arguments: Dict) -> ToolResult:
        """Execute a tool and return result"""
        return self.tool_registry.execute(
            tool_name,
            session_context=self.context,
            **arguments
        )

    def _format_context(self, context: Dict) -> str:
        """Format context data for the system prompt"""
        parts = []

        if 'alert' in context:
            alert = context['alert']
            parts.append(f"Alert: {alert.get('title', 'Unknown')}")
            parts.append(f"Severity: {alert.get('severity', 'unknown')}")
            if alert.get('device'):
                parts.append(f"Device: {alert.get('device')}")
            if alert.get('description'):
                parts.append(f"Description: {alert.get('description')}")

        if 'devices' in context:
            parts.append(f"Available devices: {', '.join(context['devices'])}")

        if 'handoff' in context:
            handoff = context['handoff']
            parts.append(f"Handoff from: {handoff.get('source_agent', 'unknown')}")
            parts.append(f"Summary: {handoff.get('summary', '')}")

        return "\n".join(parts)

    def resume_with_approval(
        self,
        approval_id: str,
        approved: bool,
        approver: Optional[str] = None
    ) -> Generator[AgentEvent, None, None]:
        """
        Resume execution after approval decision.

        Args:
            approval_id: ID of the approval request
            approved: Whether the action was approved
            approver: Who approved/rejected (optional)

        Yields:
            AgentEvent objects as execution continues
        """
        if approved:
            # Update context with approval
            self.context['approval_id'] = approval_id
            self.context['approved_by'] = approver

            # Find the pending action
            # Re-execute the tool that required approval
            for action in reversed(self.actions):
                if action.type == AgentEventType.APPROVAL_REQUIRED:
                    if action.data.get('approval_id') == approval_id:
                        tool_name = action.data.get('tool_name')
                        tool_args = action.data.get('tool_args')

                        # Execute with approval context
                        result = self._execute_tool(tool_name, tool_args)

                        yield AgentEvent(
                            type=AgentEventType.TOOL_RESULT,
                            tool_name=tool_name,
                            tool_result=result.to_dict()
                        )

                        # Continue ReAct loop
                        yield from self.run("Continue with the approved action.", {})
                        return

            yield AgentEvent(
                type=AgentEventType.ERROR,
                content=f"Approval ID not found: {approval_id}"
            )
        else:
            # Rejection - inform the agent
            self.messages.append({
                "role": "system",
                "content": f"The requested action was rejected by {approver or 'an operator'}. Please suggest an alternative approach."
            })
            yield from self.run("The action was rejected. What alternatives can you suggest?", {})

    def get_history(self) -> List[Dict]:
        """Get conversation history"""
        return self.messages.copy()

    def get_actions(self) -> List[Dict]:
        """Get action history"""
        return [a.to_dict() for a in self.actions]

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} session='{self.session_id}' type='{self.agent_type}'>"
