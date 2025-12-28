"""
Agent Factory

Creates agent instances based on type.
"""

import logging
from typing import Dict, Any, Optional, List, Type

from .base import BaseAgent
from .triage import TriageAgent
from .bgp import BGPAgent
from .ospf import OSPFAgent
from .isis import ISISAgent

log = logging.getLogger(__name__)


# Registry of available agent types
AGENT_TYPES: Dict[str, Type[BaseAgent]] = {
    'triage': TriageAgent,
    'bgp': BGPAgent,
    'ospf': OSPFAgent,
    'isis': ISISAgent,
}


def create_agent(
    agent_type: str,
    session_id: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    config: Optional[Dict] = None
) -> BaseAgent:
    """
    Create an agent instance.

    Args:
        agent_type: Type of agent to create
        session_id: Optional session ID
        llm_provider: LLM provider to use
        llm_model: LLM model to use
        config: Additional configuration

    Returns:
        Configured agent instance

    Raises:
        ValueError: If agent type not found
    """
    if agent_type not in AGENT_TYPES:
        raise ValueError(
            f"Unknown agent type: {agent_type}. "
            f"Available types: {list(AGENT_TYPES.keys())}"
        )

    agent_class = AGENT_TYPES[agent_type]

    return agent_class(
        session_id=session_id,
        llm_provider=llm_provider,
        llm_model=llm_model,
        config=config
    )


def get_agent_types() -> List[Dict[str, Any]]:
    """
    Get list of available agent types with metadata.

    Returns:
        List of agent type info dicts
    """
    return [
        {
            'type': agent_type,
            'name': agent_class.agent_name,
            'description': agent_class.description,
        }
        for agent_type, agent_class in AGENT_TYPES.items()
    ]


def register_agent_type(agent_type: str, agent_class: Type[BaseAgent]) -> None:
    """
    Register a custom agent type.

    Args:
        agent_type: Type identifier
        agent_class: Agent class (must inherit from BaseAgent)
    """
    if not issubclass(agent_class, BaseAgent):
        raise ValueError("Agent class must inherit from BaseAgent")

    AGENT_TYPES[agent_type] = agent_class
    log.info(f"Registered agent type: {agent_type}")


def get_agent_for_handoff(
    handoff_data: Dict[str, Any],
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None
) -> BaseAgent:
    """
    Create an agent for handling a handoff.

    Args:
        handoff_data: Handoff data from source agent
        llm_provider: LLM provider
        llm_model: LLM model

    Returns:
        Configured specialist agent
    """
    target_type = handoff_data.get('target_agent', 'triage')

    agent = create_agent(
        agent_type=target_type,
        llm_provider=llm_provider,
        llm_model=llm_model,
        config={'handoff_data': handoff_data}
    )

    # Update context with handoff info
    agent.context['handoff'] = handoff_data

    return agent
