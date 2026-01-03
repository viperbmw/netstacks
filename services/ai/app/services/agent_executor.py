# services/ai/app/services/agent_executor.py
"""
Agent Executor

Production-ready ReAct agent executor with tool use, streaming, and persistence.
Implements the classic ReAct (Reason + Act) loop for network operations.
"""

import logging
import uuid
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field

from netstacks_core.db import (
    get_session,
    Agent as AgentModel,
    AgentSession,
    AgentMessage,
    AgentAction,
)

from .llm_client import LLMClient, Message, AgentEvent, EventType, LLMError
from .agent_tools import (
    get_tool_definitions,
    get_tool_info,
    execute_tool,
    RiskLevel,
)

log = logging.getLogger(__name__)


# ============================================================================
# System Prompts
# ============================================================================

TRIAGE_SYSTEM_PROMPT = """You are a Triage Agent for network operations at a NOC (Network Operations Center).

Your primary role is to:
1. Assess incoming issues and alerts
2. Gather initial diagnostic information
3. Classify the problem type (BGP, OSPF, IS-IS, Layer 2, general)
4. Either resolve simple issues or hand off to appropriate specialist agents

When investigating:
- Start by understanding what devices and symptoms are involved
- Use show commands to gather diagnostic data
- Look for patterns that indicate the root cause
- Check the knowledge base for relevant runbooks

For handoffs:
- If you identify a BGP issue, hand off to the bgp specialist
- If you identify an OSPF issue, hand off to the ospf specialist
- If you identify an IS-IS issue, hand off to the isis specialist
- For other issues, hand off to the general specialist

Always explain your reasoning and what you've found before making decisions."""

BGP_SYSTEM_PROMPT = """You are a BGP (Border Gateway Protocol) Specialist Agent for network operations.

You are an expert in:
- BGP neighbor state troubleshooting
- AS-PATH analysis and manipulation
- Route filtering and prefix lists
- BGP communities and extended communities
- Route propagation issues
- BGP convergence and flapping

When troubleshooting BGP issues:
1. Check BGP neighbor states (show ip bgp summary, show bgp neighbors)
2. Verify route advertisements and received routes
3. Analyze AS-PATH for routing anomalies
4. Check for route filtering issues
5. Look for interface or connectivity problems

Provide clear explanations of your findings and recommended actions."""

OSPF_SYSTEM_PROMPT = """You are an OSPF (Open Shortest Path First) Specialist Agent for network operations.

You are an expert in:
- OSPF neighbor adjacency troubleshooting
- Area configuration and design
- DR/BDR election issues
- LSA types and LSDB problems
- SPF calculation and convergence
- Route redistribution

When troubleshooting OSPF issues:
1. Check OSPF neighbor states (show ip ospf neighbor)
2. Verify area configurations
3. Analyze the LSDB for inconsistencies
4. Check for MTU mismatches or authentication issues
5. Look for network type mismatches

Provide clear explanations of your findings and recommended actions."""

ISIS_SYSTEM_PROMPT = """You are an IS-IS (Intermediate System to Intermediate System) Specialist Agent for network operations.

You are an expert in:
- IS-IS adjacency troubleshooting
- Level 1/Level 2 routing
- NET (Network Entity Title) addressing
- LSP (Link State PDU) analysis
- CSNP/PSNP issues
- Metric and cost configuration

When troubleshooting IS-IS issues:
1. Check IS-IS adjacency states
2. Verify NET addresses and area configuration
3. Analyze LSP database
4. Check for authentication or hello timer mismatches
5. Look for interface or level configuration issues

Provide clear explanations of your findings and recommended actions."""

GENERAL_SYSTEM_PROMPT = """You are a General Network Operations Agent.

You handle:
- Layer 2 switching issues (VLANs, STP, port-channels)
- General connectivity problems
- Configuration issues
- Interface troubleshooting
- Multi-protocol environments
- Issues that don't fall into specific protocol categories

When troubleshooting:
1. Gather information about the symptoms
2. Check interface states and configurations
3. Verify connectivity at each layer
4. Look for configuration inconsistencies
5. Check logs for error messages

Provide clear explanations of your findings and recommended actions."""

SYSTEM_PROMPTS = {
    "triage": TRIAGE_SYSTEM_PROMPT,
    "bgp": BGP_SYSTEM_PROMPT,
    "ospf": OSPF_SYSTEM_PROMPT,
    "isis": ISIS_SYSTEM_PROMPT,
    "general": GENERAL_SYSTEM_PROMPT,
}


def get_system_prompt(agent_type: str, custom_prompt: Optional[str] = None) -> str:
    """Get system prompt for agent type, with optional custom override."""
    if custom_prompt:
        return custom_prompt
    return SYSTEM_PROMPTS.get(agent_type, GENERAL_SYSTEM_PROMPT)


# ============================================================================
# Agent Executor
# ============================================================================

@dataclass
class ExecutorConfig:
    """Configuration for agent executor."""
    max_iterations: int = 10
    max_tokens: int = 4096
    temperature: float = 0.1
    timeout_seconds: int = 120
    persist_messages: bool = True


@dataclass
class ExecutorContext:
    """Execution context with auth and session info."""
    session_id: str
    agent_id: str
    username: str
    auth_token: Optional[str] = None
    trigger_type: str = "user"
    trigger_id: Optional[str] = None


class AgentExecutor:
    """
    ReAct agent executor for network operations.

    Implements the classic Reason + Act loop:
    1. Observe: Get current state from user message and tool results
    2. Think: LLM reasons about what to do
    3. Act: Execute tools or provide final response
    4. Repeat until done or max iterations reached
    """

    def __init__(
        self,
        agent_type: str = "general",
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        config: Optional[ExecutorConfig] = None,
    ):
        self.agent_type = agent_type
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.system_prompt = system_prompt or get_system_prompt(agent_type)
        self.allowed_tools = allowed_tools
        self.config = config or ExecutorConfig()

        # Message history for the current conversation
        self.messages: List[Message] = []

        # Initialize LLM client
        try:
            self.llm = LLMClient(
                provider=llm_provider,
                model=llm_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
        except LLMError as e:
            log.warning(f"Failed to initialize LLM client: {e}")
            self.llm = None

    @classmethod
    def from_agent_config(cls, agent_id: str) -> "AgentExecutor":
        """Create executor from database agent configuration."""
        db_session = get_session()
        try:
            agent = db_session.query(AgentModel).filter(
                AgentModel.agent_id == agent_id
            ).first()

            if not agent:
                raise ValueError(f"Agent not found: {agent_id}")

            return cls(
                agent_type=agent.agent_type,
                llm_provider=agent.llm_provider,
                llm_model=agent.llm_model,
                system_prompt=agent.system_prompt,
                allowed_tools=agent.allowed_tools,
                config=ExecutorConfig(
                    max_iterations=agent.max_iterations or 10,
                    max_tokens=agent.max_tokens or 4096,
                    temperature=agent.temperature or 0.1,
                ),
            )
        finally:
            db_session.close()

    def get_tools(self) -> List[Dict]:
        """Get tool definitions for the LLM."""
        return get_tool_definitions(self.allowed_tools)

    async def run(
        self,
        user_message: str,
        context: ExecutorContext,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Run the agent with a user message, yielding events as they occur.

        This is the main ReAct loop that:
        1. Sends the message to the LLM
        2. Processes tool calls if any
        3. Continues until the LLM provides a final response

        Args:
            user_message: The user's input message
            context: Execution context with auth and session info

        Yields:
            AgentEvents for streaming to the client
        """
        if not self.llm:
            yield AgentEvent(
                type=EventType.ERROR,
                content="No LLM provider configured. Please configure an LLM provider in Settings > AI Settings."
            )
            return

        # Add user message to history
        self.messages.append(Message(role="user", content=user_message))

        # Persist user message
        if self.config.persist_messages:
            self._save_message(context.session_id, "user", user_message)

        # Get available tools
        tools = self.get_tools()

        iteration = 0
        while iteration < self.config.max_iterations:
            iteration += 1

            try:
                # Call the LLM
                response = await self.llm.chat(
                    messages=self.messages,
                    system_prompt=self.system_prompt,
                    tools=tools if tools else None,
                )

                # Check for tool calls
                if response.get("tool_calls"):
                    # Process each tool call
                    for tool_call in response["tool_calls"]:
                        tool_name = tool_call["name"]
                        tool_input = tool_call["input"]
                        tool_id = tool_call["id"]

                        # Yield tool call event
                        yield AgentEvent(
                            type=EventType.TOOL_CALL,
                            tool_name=tool_name,
                            tool_input=tool_input,
                            tool_call_id=tool_id,
                        )

                        # Save action to database
                        action_id = self._save_action(
                            context.session_id,
                            iteration,
                            "tool_call",
                            tool_name,
                            tool_input,
                        )

                        # Check if tool requires approval
                        tool_info = get_tool_info(tool_name)
                        if tool_info and tool_info.requires_approval:
                            yield AgentEvent(
                                type=EventType.ERROR,
                                content=f"Tool '{tool_name}' requires approval. This feature is not yet implemented.",
                                data={"requires_approval": True, "tool_name": tool_name}
                            )
                            # For now, skip tools requiring approval
                            tool_result = {"error": "Approval required - skipped"}
                        else:
                            # Execute the tool
                            tool_result = await execute_tool(
                                tool_name,
                                tool_input,
                                {"auth_token": context.auth_token}
                            )

                        # Yield tool result event
                        yield AgentEvent(
                            type=EventType.TOOL_RESULT,
                            tool_name=tool_name,
                            tool_result=tool_result,
                            tool_call_id=tool_id,
                        )

                        # Update action with result
                        self._update_action(action_id, tool_result)

                        # Check for handoff
                        if tool_name == "handoff_to_specialist" and tool_result.get("success"):
                            yield AgentEvent(
                                type=EventType.DONE,
                                content="Handoff initiated",
                                data={"handoff": tool_result.get("handoff")}
                            )
                            return

                        # Check for escalation
                        if tool_name == "escalate_to_human" and tool_result.get("success"):
                            yield AgentEvent(
                                type=EventType.DONE,
                                content="Escalated to human operator",
                                data={"escalation": tool_result.get("escalation")}
                            )
                            return

                        # Add tool result to message history
                        self.messages.append(Message(
                            role="assistant",
                            content=response.get("content", ""),
                            tool_calls=[tool_call],
                        ))
                        self.messages.append(Message(
                            role="tool",
                            content=json.dumps(tool_result),
                            tool_call_id=tool_id,
                        ))

                else:
                    # No tool calls - this is the final response
                    final_content = response.get("content", "")

                    if final_content:
                        # Add to message history
                        self.messages.append(Message(role="assistant", content=final_content))

                        # Persist assistant message
                        if self.config.persist_messages:
                            self._save_message(context.session_id, "assistant", final_content)

                        yield AgentEvent(
                            type=EventType.FINAL_RESPONSE,
                            content=final_content,
                        )

                    yield AgentEvent(type=EventType.DONE)
                    return

            except LLMError as e:
                yield AgentEvent(
                    type=EventType.ERROR,
                    content=f"LLM error: {str(e)}"
                )
                return

            except Exception as e:
                log.error(f"Agent execution error: {e}", exc_info=True)
                yield AgentEvent(
                    type=EventType.ERROR,
                    content=f"Execution error: {str(e)}"
                )
                return

        # Max iterations reached
        yield AgentEvent(
            type=EventType.ERROR,
            content=f"Maximum iterations ({self.config.max_iterations}) reached without completing the task."
        )

    async def stream_run(
        self,
        user_message: str,
        context: ExecutorContext,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Run the agent with streaming LLM responses.

        Similar to run() but streams text as it's generated.
        """
        if not self.llm:
            yield AgentEvent(
                type=EventType.ERROR,
                content="No LLM provider configured. Please configure an LLM provider in Settings > AI Settings."
            )
            return

        # Add user message to history
        self.messages.append(Message(role="user", content=user_message))

        # Persist user message
        if self.config.persist_messages:
            self._save_message(context.session_id, "user", user_message)

        # Get available tools
        tools = self.get_tools()

        iteration = 0
        while iteration < self.config.max_iterations:
            iteration += 1

            try:
                accumulated_text = ""
                tool_calls = []

                async for event in self.llm.stream_chat(
                    messages=self.messages,
                    system_prompt=self.system_prompt,
                    tools=tools if tools else None,
                ):
                    if event.type == EventType.TEXT:
                        accumulated_text += event.content
                        yield event

                    elif event.type == EventType.TOOL_CALL:
                        tool_calls.append({
                            "id": event.tool_call_id,
                            "name": event.tool_name,
                            "input": event.tool_input,
                        })
                        yield event

                    elif event.type == EventType.FINAL_RESPONSE:
                        # Add to message history
                        self.messages.append(Message(role="assistant", content=event.content))

                        # Persist
                        if self.config.persist_messages:
                            self._save_message(context.session_id, "assistant", event.content)

                        yield event

                    elif event.type == EventType.DONE:
                        if not tool_calls:
                            yield event
                            return

                    elif event.type == EventType.ERROR:
                        yield event
                        return

                # Process tool calls if any
                if tool_calls:
                    for tool_call in tool_calls:
                        tool_name = tool_call["name"]
                        tool_input = tool_call["input"]
                        tool_id = tool_call["id"]

                        # Save action
                        action_id = self._save_action(
                            context.session_id,
                            iteration,
                            "tool_call",
                            tool_name,
                            tool_input,
                        )

                        # Check approval
                        tool_info = get_tool_info(tool_name)
                        if tool_info and tool_info.requires_approval:
                            tool_result = {"error": "Approval required - skipped"}
                        else:
                            tool_result = await execute_tool(
                                tool_name,
                                tool_input,
                                {"auth_token": context.auth_token}
                            )

                        yield AgentEvent(
                            type=EventType.TOOL_RESULT,
                            tool_name=tool_name,
                            tool_result=tool_result,
                            tool_call_id=tool_id,
                        )

                        self._update_action(action_id, tool_result)

                        # Check for workflow events
                        if tool_name == "handoff_to_specialist" and tool_result.get("success"):
                            yield AgentEvent(type=EventType.DONE, data={"handoff": tool_result.get("handoff")})
                            return

                        if tool_name == "escalate_to_human" and tool_result.get("success"):
                            yield AgentEvent(type=EventType.DONE, data={"escalation": tool_result.get("escalation")})
                            return

                        # Add to history
                        self.messages.append(Message(
                            role="assistant",
                            content=accumulated_text,
                            tool_calls=[tool_call],
                        ))
                        self.messages.append(Message(
                            role="tool",
                            content=json.dumps(tool_result),
                            tool_call_id=tool_id,
                        ))

                else:
                    # No tool calls and we've yielded DONE, so exit
                    return

            except Exception as e:
                log.error(f"Streaming agent error: {e}", exc_info=True)
                yield AgentEvent(type=EventType.ERROR, content=str(e))
                return

        yield AgentEvent(
            type=EventType.ERROR,
            content=f"Maximum iterations ({self.config.max_iterations}) reached."
        )

    def _save_message(self, session_id: str, role: str, content: str):
        """Persist message to database."""
        try:
            db_session = get_session()
            message = AgentMessage(
                session_id=session_id,
                role=role,
                content=content,
            )
            db_session.add(message)
            db_session.commit()
            db_session.close()
        except Exception as e:
            log.error(f"Failed to save message: {e}")

    def _save_action(
        self,
        session_id: str,
        sequence: int,
        action_type: str,
        tool_name: str,
        tool_input: Dict,
    ) -> str:
        """Save action to database and return action_id."""
        action_id = str(uuid.uuid4())
        try:
            db_session = get_session()
            action = AgentAction(
                action_id=action_id,
                session_id=session_id,
                sequence=sequence,
                action_type=action_type,
                tool_name=tool_name,
                tool_input=tool_input,
                status="pending",
            )
            db_session.add(action)
            db_session.commit()
            db_session.close()
        except Exception as e:
            log.error(f"Failed to save action: {e}")
        return action_id

    def _update_action(self, action_id: str, tool_output: Dict):
        """Update action with tool output."""
        try:
            db_session = get_session()
            action = db_session.query(AgentAction).filter(
                AgentAction.action_id == action_id
            ).first()
            if action:
                action.tool_output = tool_output
                action.status = "completed" if not tool_output.get("error") else "failed"
                db_session.commit()
            db_session.close()
        except Exception as e:
            log.error(f"Failed to update action: {e}")


# ============================================================================
# Session Management
# ============================================================================

def create_agent_session(
    agent_id: str,
    username: str,
    trigger_type: str = "user",
    trigger_id: Optional[str] = None,
    initial_prompt: Optional[str] = None,
) -> str:
    """Create a new agent session and return session_id."""
    session_id = str(uuid.uuid4())

    db_session = get_session()
    try:
        session = AgentSession(
            session_id=session_id,
            agent_id=agent_id,
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            status="active",
            initial_prompt=initial_prompt,
            started_by=username,
        )
        db_session.add(session)

        # Update agent stats
        agent = db_session.query(AgentModel).filter(
            AgentModel.agent_id == agent_id
        ).first()
        if agent:
            agent.total_sessions = (agent.total_sessions or 0) + 1
            agent.last_active = datetime.utcnow()

        db_session.commit()
    finally:
        db_session.close()

    return session_id


def end_agent_session(
    session_id: str,
    status: str = "completed",
    summary: Optional[str] = None,
    resolution_status: Optional[str] = None,
):
    """End an agent session."""
    db_session = get_session()
    try:
        session = db_session.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()
        if session:
            session.status = status
            session.completed_at = datetime.utcnow()
            if summary:
                session.summary = summary
            if resolution_status:
                session.resolution_status = resolution_status
            db_session.commit()
    finally:
        db_session.close()


def get_session_messages(session_id: str) -> List[Dict]:
    """Get all messages for a session."""
    db_session = get_session()
    try:
        messages = db_session.query(AgentMessage).filter(
            AgentMessage.session_id == session_id
        ).order_by(AgentMessage.created_at).all()

        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]
    finally:
        db_session.close()
