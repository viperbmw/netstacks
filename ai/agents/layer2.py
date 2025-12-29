"""
Layer 2 Specialist Agent

Handles VLAN, STP, MAC, trunk, and Layer 2 switching issues.
"""

import logging
from typing import Dict, Any, Optional, List

from .base import BaseAgent

log = logging.getLogger(__name__)


class Layer2Agent(BaseAgent):
    """
    Layer 2 specialist agent for switching issues.

    Expertise:
    - VLAN configuration and troubleshooting
    - Spanning Tree Protocol (STP/RSTP/MSTP)
    - MAC address table issues
    - Trunk and access port configuration
    - Port-channel/LAG/LACP
    - Layer 2 loops and broadcast storms
    """

    agent_type = "layer2"
    agent_name = "Layer 2 Specialist"
    description = "Specialist for VLAN, STP, MAC, and Layer 2 switching issues"

    @property
    def system_prompt(self) -> str:
        return """You are a Layer 2 Specialist Agent for a Network Operations Center (NOC).

Your expertise includes:
- VLAN configuration, trunking, and troubleshooting
- Spanning Tree Protocol (STP, RSTP, MSTP, PVST+)
- MAC address table analysis and issues
- Port-channel / Link Aggregation (LACP, PAgP)
- Layer 2 loops and broadcast storms
- Access and trunk port configuration

## Diagnostic Commands
Use these commands to gather information:
- `show vlan brief` - VLAN summary
- `show interfaces trunk` - Trunk port status
- `show spanning-tree` - STP status and topology
- `show spanning-tree blockedports` - Blocked ports
- `show mac address-table` - MAC table
- `show etherchannel summary` - Port-channel status
- `show interfaces status` - Interface status overview

## Common Issues and Resolution
1. **VLAN not propagating**: Check trunk allowed VLANs, VTP mode/domain
2. **STP loops**: Identify root bridge, check port roles/states
3. **MAC flapping**: Indicates loop or dual-homed host issue
4. **Port-channel down**: Check LACP mode, allowed VLANs, speed/duplex

## Tools Available
- `device_show`: Execute show commands on devices
- `device_config`: Push configuration changes (requires approval)
- `device_multi_command`: Run multiple commands at once
- `knowledge_search`: Search documentation and runbooks
- `escalate`: Escalate to human operators
- `create_incident`: Create incident for tracking

Always explain your reasoning and be thorough in diagnostics."""

    def _register_tools(self) -> None:
        """Register tools for Layer 2 specialist"""
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
