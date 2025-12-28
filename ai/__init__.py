"""
NetStacks AI Module

Provides AI agent capabilities for network automation and troubleshooting.

Components:
- llm: LLM provider clients (Anthropic, OpenRouter)
- tools: Tool registry and implementations
- agents: Agent types and execution engine
- knowledge: RAG knowledge base with pgvector
"""

__version__ = "1.0.0"

# Expose key components at package level
from .llm import get_llm_client, LLMClient, LLMResponse
from .tools import ToolRegistry, get_registry, register_all_tools
from .agents import (
    BaseAgent,
    TriageAgent,
    BGPAgent,
    OSPFAgent,
    ISISAgent,
    create_agent,
    get_agent_types,
)

__all__ = [
    # LLM
    'get_llm_client',
    'LLMClient',
    'LLMResponse',
    # Tools
    'ToolRegistry',
    'get_registry',
    'register_all_tools',
    # Agents
    'BaseAgent',
    'TriageAgent',
    'BGPAgent',
    'OSPFAgent',
    'ISISAgent',
    'create_agent',
    'get_agent_types',
]
