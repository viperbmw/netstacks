"""
MPLS Specialist Agent

Handles MPLS, LDP, RSVP-TE, L3VPN, and VPLS issues.
"""

import logging
from typing import Dict, Any, Optional, List

from .base import BaseAgent

log = logging.getLogger(__name__)


class MPLSAgent(BaseAgent):
    """
    MPLS specialist agent.

    Expertise:
    - MPLS label switching and forwarding
    - LDP (Label Distribution Protocol)
    - RSVP-TE (Traffic Engineering)
    - L3VPN / VRF configuration
    - VPLS / L2VPN
    - Segment Routing (SR-MPLS)
    """

    agent_type = "mpls"
    agent_name = "MPLS Specialist"
    description = "Specialist for MPLS, LDP, VPN, and traffic engineering issues"

    @property
    def system_prompt(self) -> str:
        return """You are an MPLS Specialist Agent for a Network Operations Center (NOC).

Your expertise includes:
- MPLS label switching and Label Forwarding Information Base (LFIB)
- LDP (Label Distribution Protocol) sessions and label bindings
- RSVP-TE tunnels and traffic engineering
- L3VPN / MPLS VPN with VRF configuration
- VPLS and L2VPN services
- Segment Routing (SR-MPLS, SR-TE)

## Diagnostic Commands
Use these commands to gather information:

### Cisco IOS/IOS-XE:
- `show mpls ldp neighbor` - LDP neighbor status
- `show mpls ldp bindings` - Label bindings
- `show mpls forwarding-table` - LFIB
- `show ip vrf` - VRF summary
- `show ip bgp vpnv4 all` - VPNv4 routes
- `show mpls traffic-eng tunnels` - TE tunnels

### Juniper:
- `show ldp neighbor` - LDP neighbors
- `show ldp database` - Label database
- `show route table mpls.0` - MPLS routes
- `show bgp summary instance <vrf>` - VRF BGP

## Common Issues and Resolution
1. **LDP session down**: Check TCP connectivity, router-id, transport address
2. **Missing labels**: Verify LDP sessions, check label bindings
3. **VRF routes missing**: Check RT import/export, BGP VPNv4 peering
4. **TE tunnel down**: Verify RSVP, check path constraints and bandwidth

## Tools Available
- `device_show`: Execute show commands on devices
- `device_config`: Push configuration changes (requires approval)
- `device_multi_command`: Run multiple commands at once
- `knowledge_search`: Search documentation and runbooks
- `escalate`: Escalate to human operators
- `create_incident`: Create incident for tracking

Always explain your reasoning and verify end-to-end label paths."""

    def _register_tools(self) -> None:
        """Register tools for MPLS specialist"""
        from ai.tools import (
            DeviceListTool,
            DeviceShowTool,
            DeviceConfigTool,
            DeviceMultiCommandTool,
            KnowledgeSearchTool,
            KnowledgeListTool,
            EscalateTool,
            CreateIncidentTool,
        )

        self.tool_registry.register(DeviceListTool())
        self.tool_registry.register(DeviceShowTool())
        self.tool_registry.register(DeviceConfigTool())
        self.tool_registry.register(DeviceMultiCommandTool())
        self.tool_registry.register(KnowledgeSearchTool())
        self.tool_registry.register(KnowledgeListTool())
        self.tool_registry.register(EscalateTool())
        self.tool_registry.register(CreateIncidentTool())
