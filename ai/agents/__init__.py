"""
AI Agents Module

Provides specialized agents for network troubleshooting and automation.
Implements the ReAct (Reason → Act → Observe) pattern for agent execution.
"""

from .base import BaseAgent, AgentEvent, AgentEventType
from .triage import TriageAgent
from .bgp import BGPAgent
from .ospf import OSPFAgent
from .isis import ISISAgent
from .factory import create_agent, get_agent_types

__all__ = [
    'BaseAgent',
    'AgentEvent',
    'AgentEventType',
    'TriageAgent',
    'BGPAgent',
    'OSPFAgent',
    'ISISAgent',
    'create_agent',
    'get_agent_types',
]
