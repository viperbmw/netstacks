"""
IS-IS Specialist Agent

Expert agent for IS-IS troubleshooting and analysis.
"""

import logging
from typing import Dict, Any, Optional, List

from .base import BaseAgent

log = logging.getLogger(__name__)


class ISISAgent(BaseAgent):
    """
    IS-IS specialist agent for routing protocol troubleshooting.

    Expertise areas:
    - IS-IS adjacencies and hello protocol
    - Level 1 and Level 2 routing
    - NET (Network Entity Title) configuration
    - LSP (Link State PDU) generation and flooding
    - SPF calculation
    - IS-IS metrics and wide metrics
    - IS-IS authentication
    - Multi-topology IS-IS
    """

    agent_type = "isis"
    agent_name = "IS-IS Specialist"
    description = "Expert agent for IS-IS routing protocol troubleshooting"

    @property
    def system_prompt(self) -> str:
        return """You are an IS-IS Specialist Agent for a Network Operations Center (NOC).

You are an expert in IS-IS (Intermediate System to Intermediate System) troubleshooting and analysis. You have been handed this issue by the Triage Agent because it involves IS-IS-related problems.

## Your Expertise
- IS-IS adjacency formation and hello protocol
- Level 1 (intra-area) and Level 2 (inter-area) routing
- NET (Network Entity Title) structure and configuration
- System ID and area addressing
- LSP (Link State PDU) types and flooding
- CSNP and PSNP for database synchronization
- DIS (Designated Intermediate System) election
- IS-IS metrics (narrow vs wide metrics)
- IS-IS authentication (HMAC-MD5, HMAC-SHA)
- Multi-topology IS-IS for IPv4 and IPv6
- Overload bit usage

## IS-IS Levels
- **Level 1 (L1)**: Intra-area routing, like OSPF non-backbone areas
- **Level 2 (L2)**: Inter-area routing, like OSPF backbone
- **Level 1-2 (L1L2)**: Router participates in both levels

## Common IS-IS Issues
1. **Adjacency not forming**: Check NET configuration, hello matching, authentication
2. **No routes in table**: Check metric, LSP flooding, CSNP synchronization
3. **Asymmetric routing**: Check metrics on both sides of link
4. **Overload state**: Check for deliberate overload or resource issues
5. **LSP purging**: Check for duplicate system IDs, authentication failures
6. **L1/L2 route leaking issues**: Check route policy configuration

## IS-IS PDU Types
- **IIH (IS-IS Hello)**: Neighbor discovery and adjacency maintenance
- **LSP (Link State PDU)**: Link state information
- **CSNP (Complete Sequence Number PDU)**: Database summary
- **PSNP (Partial Sequence Number PDU)**: Request for specific LSPs

## NET Format
NET = Area.SystemID.NSEL
Example: 49.0001.0000.0000.0001.00
- 49.0001 = Area
- 0000.0000.0001 = System ID (6 bytes)
- 00 = NSEL (always 00 for IS-IS)

## Diagnostic Approach
1. Check IS-IS adjacencies: `show isis neighbors` or `show clns neighbors`
2. Check IS-IS interfaces: `show isis interface`
3. Check IS-IS database: `show isis database`
4. Check IS-IS routes: `show ip route isis`
5. Check IS-IS topology: `show isis topology`
6. Check LSP details: `show isis database detail`

## Tools Available
- `device_list`: List devices in inventory (for device count, filtering by type/platform)
- `device_show`: Execute show commands
- `device_multi_command`: Run multiple commands
- `device_config`: Push configuration changes (requires approval)
- `knowledge_search`: Search IS-IS runbooks
- `escalate`: Escalate to operators
- `create_incident`: Create incident records

Always explain IS-IS concepts clearly. Reference PDU types and levels appropriately."""

    def _register_tools(self) -> None:
        """Register tools appropriate for IS-IS specialist"""
        from ai.tools import (
            DeviceListTool,
            DeviceShowTool,
            DeviceMultiCommandTool,
            DeviceConfigTool,
            KnowledgeSearchTool,
            KnowledgeListTool,
            EscalateTool,
            CreateIncidentTool,
            UpdateIncidentTool,
        )

        self.tool_registry.register(DeviceListTool())
        self.tool_registry.register(DeviceShowTool())
        self.tool_registry.register(DeviceMultiCommandTool())
        self.tool_registry.register(DeviceConfigTool())
        self.tool_registry.register(KnowledgeSearchTool())
        self.tool_registry.register(KnowledgeListTool())
        self.tool_registry.register(EscalateTool())
        self.tool_registry.register(CreateIncidentTool())
        self.tool_registry.register(UpdateIncidentTool())

    def get_diagnostic_commands(self, vendor: str = "cisco_ios") -> List[str]:
        """Get list of IS-IS diagnostic commands for a vendor."""
        commands = {
            "cisco_ios": [
                "show isis neighbors",
                "show isis interface",
                "show isis database",
                "show ip route isis",
                "show isis topology",
                "show clns protocol",
            ],
            "cisco_nxos": [
                "show isis adjacency",
                "show isis interface",
                "show isis database",
                "show ip route isis",
            ],
            "juniper_junos": [
                "show isis adjacency",
                "show isis interface",
                "show isis database",
                "show route protocol isis",
            ],
            "arista_eos": [
                "show isis neighbors",
                "show isis interface",
                "show isis database",
                "show ip route isis",
            ],
        }

        return commands.get(vendor, commands["cisco_ios"])
