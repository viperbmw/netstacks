"""
Triage Agent

First-line agent that analyzes incoming issues and routes to specialist agents.
Performs initial diagnostics and classification.
"""

import logging
from typing import Dict, Any, Optional, List

from .base import BaseAgent

log = logging.getLogger(__name__)


class TriageAgent(BaseAgent):
    """
    Triage agent for initial issue analysis and routing.

    Responsibilities:
    - Analyze incoming alerts and user requests
    - Gather initial diagnostic information
    - Classify the issue type (BGP, OSPF, ISIS, Layer2, etc.)
    - Hand off to appropriate specialist agent
    - Handle issues that don't require specialist expertise
    """

    agent_type = "triage"
    agent_name = "Triage Agent"
    description = "First-line agent for issue analysis and routing to specialists"

    @property
    def system_prompt(self) -> str:
        return """You are a Triage Agent for a Network Operations Center (NOC).

Your role is to:
1. Analyze incoming network issues, alerts, and user requests
2. Gather initial diagnostic information from devices
3. Classify the issue type and severity
4. Either resolve simple issues directly OR hand off to specialist agents

## Available Specialist Agents
- **bgp**: BGP routing specialist - for BGP peering, route propagation, AS-PATH issues
- **ospf**: OSPF specialist - for OSPF adjacency, area configuration, SPF issues
- **isis**: IS-IS specialist - for IS-IS adjacency, LSP, metric issues
- **layer2**: Layer 2 specialist - for VLAN, STP, MAC table issues

## Diagnostic Approach
1. First understand the issue from the alert or user description
2. Use `device_show` to gather relevant information:
   - For connectivity issues: check interfaces, ARP, routes
   - For routing issues: check routing protocols, neighbors, tables
   - For performance issues: check interface counters, CPU, memory
3. Check `knowledge_search` for relevant runbooks or past resolutions
4. Classify the issue based on findings

## When to Hand Off
Hand off to specialists when:
- The issue is clearly within their domain (e.g., BGP neighbor down → BGP agent)
- You've gathered initial info but deeper analysis is needed
- The resolution requires protocol-specific expertise

## When to Resolve Directly
Handle directly when:
- Simple informational requests
- Clear, straightforward issues you can diagnose
- Interface up/down that doesn't affect routing

## Tools Available
- `device_show`: Execute show commands on devices
- `device_multi_command`: Run multiple show commands at once
- `knowledge_search`: Search documentation and runbooks
- `handoff`: Transfer to specialist agent
- `escalate`: Escalate to human operators
- `create_incident`: Create incident for tracking

Always explain your reasoning before taking actions. Be thorough but efficient."""

    def _register_tools(self) -> None:
        """Register tools appropriate for triage"""
        from ai.tools import (
            DeviceShowTool,
            DeviceMultiCommandTool,
            KnowledgeSearchTool,
            KnowledgeListTool,
            HandoffTool,
            EscalateTool,
            CreateIncidentTool,
        )

        # Triage gets read-only device tools and workflow tools
        self.tool_registry.register(DeviceShowTool())
        self.tool_registry.register(DeviceMultiCommandTool())
        self.tool_registry.register(KnowledgeSearchTool())
        self.tool_registry.register(KnowledgeListTool())
        self.tool_registry.register(HandoffTool())
        self.tool_registry.register(EscalateTool())
        self.tool_registry.register(CreateIncidentTool())

    def classify_issue(self, description: str, diagnostics: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Classify an issue based on description and diagnostics.

        This is a helper method that can be called programmatically
        without running the full ReAct loop.

        Args:
            description: Issue description
            diagnostics: Optional diagnostic data already gathered

        Returns:
            Classification with recommended agent and confidence
        """
        # Keywords for classification
        classifications = {
            'bgp': ['bgp', 'neighbor', 'peering', 'as-path', 'prefix', 'route-map', 'ebgp', 'ibgp'],
            'ospf': ['ospf', 'adjacency', 'lsa', 'area', 'spf', 'dr', 'bdr', 'hello'],
            'isis': ['isis', 'is-is', 'adjacency', 'lsp', 'level-1', 'level-2', 'clns'],
            'layer2': ['vlan', 'spanning-tree', 'stp', 'mac', 'trunk', 'access', 'port-channel', 'lacp'],
        }

        description_lower = description.lower()
        scores = {agent: 0 for agent in classifications}

        for agent, keywords in classifications.items():
            for keyword in keywords:
                if keyword in description_lower:
                    scores[agent] += 1

        # Add diagnostic hints
        if diagnostics:
            output = str(diagnostics).lower()
            for agent, keywords in classifications.items():
                for keyword in keywords:
                    if keyword in output:
                        scores[agent] += 0.5

        # Find best match
        best_agent = max(scores, key=scores.get)
        best_score = scores[best_agent]

        if best_score > 0:
            confidence = min(best_score / 3.0, 1.0)  # Normalize to 0-1
            return {
                'recommended_agent': best_agent,
                'confidence': confidence,
                'scores': scores,
                'should_handoff': confidence > 0.5
            }
        else:
            return {
                'recommended_agent': None,
                'confidence': 0,
                'scores': scores,
                'should_handoff': False
            }
