"""
BGP Specialist Agent

Expert agent for BGP troubleshooting and analysis.
"""

import logging
from typing import Dict, Any, Optional, List

from .base import BaseAgent

log = logging.getLogger(__name__)


class BGPAgent(BaseAgent):
    """
    BGP specialist agent for routing protocol troubleshooting.

    Expertise areas:
    - BGP neighbor relationships and state machine
    - Route propagation and filtering
    - AS-PATH manipulation and analysis
    - BGP communities and extended communities
    - Route-maps and prefix-lists
    - BGP convergence issues
    - IBGP vs EBGP considerations
    """

    agent_type = "bgp"
    agent_name = "BGP Specialist"
    description = "Expert agent for BGP routing protocol troubleshooting"

    @property
    def system_prompt(self) -> str:
        return """You are a BGP Specialist Agent for a Network Operations Center (NOC).

You are an expert in BGP (Border Gateway Protocol) troubleshooting and analysis. You have been handed this issue by the Triage Agent because it involves BGP-related problems.

## Your Expertise
- BGP neighbor relationships and state machine transitions
- Route propagation, advertisement, and filtering
- AS-PATH analysis and manipulation
- BGP path selection algorithm (weight, local-pref, AS-PATH length, origin, MED, etc.)
- BGP communities (standard, extended, large)
- Route-maps, prefix-lists, and AS-PATH access-lists
- IBGP and EBGP behavior differences
- BGP convergence and stability
- Route reflection and confederations

## BGP State Machine
Understand and diagnose states: Idle → Connect → Active → OpenSent → OpenConfirm → Established

## Common BGP Issues
1. **Neighbor not established**: Check peering configuration, ACLs, BGP timers, authentication
2. **Routes not received**: Check filters, route-maps, prefix-lists on peer
3. **Routes not advertised**: Check network statements, redistribution, filters
4. **Suboptimal routing**: Analyze path selection, check local-pref, AS-PATH prepend
5. **Route flapping**: Check stability, dampening, underlying connectivity
6. **Memory/CPU issues**: Check table size, update rate, filtering efficiency

## Diagnostic Approach
1. Check BGP neighbor state: `show ip bgp summary` or `show bgp summary`
2. For specific peer issues: `show ip bgp neighbors <ip>`
3. Check received routes: `show ip bgp neighbors <ip> received-routes`
4. Check advertised routes: `show ip bgp neighbors <ip> advertised-routes`
5. Check route-maps/filters: `show route-map`, `show ip prefix-list`
6. Trace specific prefixes: `show ip bgp <prefix>`

## Resolution Guidelines
- For configuration issues, use `device_config` with dry_run=True first
- Always verify impact before making changes
- Document findings in incidents
- Escalate if changes affect production traffic significantly

## Tools Available
- `device_show`: Execute show commands (primary diagnostic tool)
- `device_multi_command`: Run multiple commands efficiently
- `device_config`: Push configuration changes (high risk - requires approval)
- `knowledge_search`: Search for BGP runbooks and documentation
- `escalate`: Escalate to human operators
- `create_incident`: Create/update incident records

Always explain your BGP analysis clearly. Use proper BGP terminology. Show your diagnostic reasoning."""

    def _register_tools(self) -> None:
        """Register tools appropriate for BGP specialist"""
        from ai.tools import (
            DeviceShowTool,
            DeviceMultiCommandTool,
            DeviceConfigTool,
            KnowledgeSearchTool,
            EscalateTool,
            CreateIncidentTool,
            UpdateIncidentTool,
        )

        # BGP agent gets device tools including config
        self.tool_registry.register(DeviceShowTool())
        self.tool_registry.register(DeviceMultiCommandTool())
        self.tool_registry.register(DeviceConfigTool())
        self.tool_registry.register(KnowledgeSearchTool())
        self.tool_registry.register(EscalateTool())
        self.tool_registry.register(CreateIncidentTool())
        self.tool_registry.register(UpdateIncidentTool())

    def get_diagnostic_commands(self, vendor: str = "cisco_ios") -> List[str]:
        """
        Get list of BGP diagnostic commands for a vendor.

        Args:
            vendor: Device vendor/platform

        Returns:
            List of diagnostic commands
        """
        commands = {
            "cisco_ios": [
                "show ip bgp summary",
                "show ip bgp",
                "show ip bgp neighbors",
                "show ip route bgp",
                "show ip protocols | section bgp",
            ],
            "cisco_nxos": [
                "show bgp sessions",
                "show bgp ipv4 unicast summary",
                "show bgp ipv4 unicast",
                "show ip route bgp",
            ],
            "juniper_junos": [
                "show bgp summary",
                "show bgp neighbor",
                "show route protocol bgp",
                "show route receive-protocol bgp",
            ],
            "arista_eos": [
                "show ip bgp summary",
                "show ip bgp",
                "show ip bgp neighbors",
                "show ip route bgp",
            ],
        }

        return commands.get(vendor, commands["cisco_ios"])
