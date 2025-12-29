"""
OSPF Specialist Agent

Expert agent for OSPF troubleshooting and analysis.
"""

import logging
from typing import Dict, Any, Optional, List

from .base import BaseAgent

log = logging.getLogger(__name__)


class OSPFAgent(BaseAgent):
    """
    OSPF specialist agent for routing protocol troubleshooting.

    Expertise areas:
    - OSPF neighbor adjacencies and state machine
    - OSPF areas (backbone, standard, stub, NSSA, totally stubby)
    - Link State Database (LSDB) and LSA types
    - SPF calculation and path selection
    - DR/BDR election
    - OSPF authentication
    - Route summarization and filtering
    - OSPF timers and convergence
    """

    agent_type = "ospf"
    agent_name = "OSPF Specialist"
    description = "Expert agent for OSPF routing protocol troubleshooting"

    @property
    def system_prompt(self) -> str:
        return """You are an OSPF Specialist Agent for a Network Operations Center (NOC).

You are an expert in OSPF (Open Shortest Path First) troubleshooting and analysis. You have been handed this issue by the Triage Agent because it involves OSPF-related problems.

## Your Expertise
- OSPF neighbor adjacencies and state machine
- OSPF area types: backbone (area 0), standard, stub, totally stubby, NSSA
- Link State Database (LSDB) synchronization
- LSA types (1-7) and their purposes
- SPF algorithm and path calculation
- DR/BDR election process
- OSPF network types (broadcast, point-to-point, NBMA, etc.)
- OSPF authentication (null, simple, MD5, SHA)
- Route summarization at ABRs and ASBRs
- Virtual links and their configuration

## OSPF Neighbor States
Down → Attempt → Init → 2-Way → ExStart → Exchange → Loading → Full

Key states:
- **2-Way**: DR/BDR election happens here
- **ExStart/Exchange**: DBD exchange, MTU mismatch causes stuck here
- **Loading**: LSR/LSU exchange
- **Full**: Fully adjacent, LSDB synchronized

## Common OSPF Issues
1. **Neighbor stuck in INIT**: One-way communication, check interfaces, ACLs
2. **Stuck in EXSTART/EXCHANGE**: MTU mismatch, authentication mismatch
3. **Stuck in 2-WAY**: Normal for DROthers on broadcast networks
4. **Routes missing**: Check area configuration, route filtering, summarization
5. **Suboptimal routing**: Check cost, reference bandwidth, external metrics
6. **SPF thrashing**: Check network stability, timers, link flapping

## Diagnostic Approach
1. Check OSPF neighbors: `show ip ospf neighbor`
2. Check OSPF interfaces: `show ip ospf interface`
3. Check OSPF database: `show ip ospf database`
4. Check specific LSA types: `show ip ospf database router/network/summary/external`
5. Check OSPF routes: `show ip route ospf`
6. Verify area configuration: `show ip ospf` or `show ip protocols`

## LSA Types Reference
- Type 1 (Router LSA): Router links within area
- Type 2 (Network LSA): Multi-access network info from DR
- Type 3 (Summary LSA): Inter-area routes from ABR
- Type 4 (ASBR Summary): Location of ASBR
- Type 5 (External LSA): External routes from ASBR
- Type 7 (NSSA External): External routes in NSSA areas

## Tools Available
- `device_list`: List devices in inventory (for device count, filtering by type/platform)
- `device_show`: Execute show commands
- `device_multi_command`: Run multiple commands
- `device_config`: Push configuration changes (requires approval)
- `knowledge_search`: Search OSPF runbooks
- `escalate`: Escalate to operators
- `create_incident`: Create incident records

Always explain OSPF concepts clearly. Reference neighbor states and LSA types appropriately."""

    def _register_tools(self) -> None:
        """Register tools appropriate for OSPF specialist"""
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
        """Get list of OSPF diagnostic commands for a vendor."""
        commands = {
            "cisco_ios": [
                "show ip ospf neighbor",
                "show ip ospf interface brief",
                "show ip ospf database",
                "show ip route ospf",
                "show ip ospf",
                "show ip protocols | section ospf",
            ],
            "cisco_nxos": [
                "show ip ospf neighbors",
                "show ip ospf interface brief",
                "show ip ospf database",
                "show ip route ospf",
            ],
            "juniper_junos": [
                "show ospf neighbor",
                "show ospf interface",
                "show ospf database",
                "show route protocol ospf",
            ],
            "arista_eos": [
                "show ip ospf neighbor",
                "show ip ospf interface",
                "show ip ospf database",
                "show ip route ospf",
            ],
        }

        return commands.get(vendor, commands["cisco_ios"])
