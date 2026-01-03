"""SNMP Trap to Alert Mapping Configuration.

This module defines how SNMP traps are converted to NetStacks alerts.
OIDs can be mapped to specific alert types, severities, and titles.
"""
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field


@dataclass
class TrapMapping:
    """Mapping configuration for an SNMP trap OID."""
    oid_pattern: str  # Regex pattern or exact OID
    alert_type: str
    title_template: str  # Can use {var} placeholders
    severity: str = "warning"
    description_template: Optional[str] = None
    extract_device_from: Optional[str] = None  # varbind OID to extract device name


# Standard trap OID prefixes
SNMP_TRAPS_PREFIX = "1.3.6.1.6.3.1.1.5"  # SNMPv2-MIB::snmpTraps
ENTERPRISE_PREFIX = "1.3.6.1.4.1"  # Private enterprise OIDs

# Well-known trap mappings
DEFAULT_TRAP_MAPPINGS: List[TrapMapping] = [
    # Standard SNMP traps
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.6\.3\.1\.1\.5\.1",  # coldStart
        alert_type="device_restart",
        title_template="Device Cold Start: {agent_address}",
        severity="warning",
        description_template="Device {agent_address} has performed a cold start (full reboot)"
    ),
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.6\.3\.1\.1\.5\.2",  # warmStart
        alert_type="device_restart",
        title_template="Device Warm Start: {agent_address}",
        severity="info",
        description_template="Device {agent_address} has performed a warm start (software restart)"
    ),
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.6\.3\.1\.1\.5\.3",  # linkDown
        alert_type="link_down",
        title_template="Link Down: {agent_address}",
        severity="critical",
        description_template="Interface link down on {agent_address}"
    ),
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.6\.3\.1\.1\.5\.4",  # linkUp
        alert_type="link_up",
        title_template="Link Up: {agent_address}",
        severity="info",
        description_template="Interface link up on {agent_address}"
    ),
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.6\.3\.1\.1\.5\.5",  # authenticationFailure
        alert_type="auth_failure",
        title_template="Authentication Failure: {agent_address}",
        severity="warning",
        description_template="SNMP authentication failure on {agent_address}"
    ),

    # Cisco-specific traps (enterprise OID 1.3.6.1.4.1.9)
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.4\.1\.9\.9\.187\.0\.1",  # cBgpPeerDown
        alert_type="bgp",
        title_template="BGP Peer Down: {agent_address}",
        severity="critical",
        description_template="BGP peer session down on {agent_address}"
    ),
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.4\.1\.9\.9\.187\.0\.2",  # cBgpPeerUp
        alert_type="bgp",
        title_template="BGP Peer Up: {agent_address}",
        severity="info",
        description_template="BGP peer session established on {agent_address}"
    ),
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.4\.1\.9\.9\.46\.2\.0\.1",  # ospfNbrStateChange
        alert_type="ospf",
        title_template="OSPF Neighbor State Change: {agent_address}",
        severity="warning",
        description_template="OSPF neighbor state change on {agent_address}"
    ),
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.4\.1\.9\.9\.138\.0\.1",  # isisAdjacencyChange
        alert_type="isis",
        title_template="IS-IS Adjacency Change: {agent_address}",
        severity="warning",
        description_template="IS-IS adjacency state change on {agent_address}"
    ),

    # Juniper-specific traps (enterprise OID 1.3.6.1.4.1.2636)
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.4\.1\.2636\.4\.5\.0\.1",  # jnxBgpM2PeerFsmTransition
        alert_type="bgp",
        title_template="BGP FSM Transition: {agent_address}",
        severity="warning",
        description_template="BGP FSM state transition on {agent_address}"
    ),
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.4\.1\.2636\.4\.1\.0\.1",  # jnxOspfNbrStateChange
        alert_type="ospf",
        title_template="OSPF Neighbor Change: {agent_address}",
        severity="warning",
        description_template="OSPF neighbor state change on {agent_address}"
    ),

    # Generic hardware/environmental traps
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.4\.1\.\d+\..*[Ff]an",
        alert_type="hardware",
        title_template="Fan Alert: {agent_address}",
        severity="warning",
        description_template="Fan status alert on {agent_address}"
    ),
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.4\.1\.\d+\..*[Tt]emp",
        alert_type="hardware",
        title_template="Temperature Alert: {agent_address}",
        severity="warning",
        description_template="Temperature alert on {agent_address}"
    ),
    TrapMapping(
        oid_pattern=r"1\.3\.6\.1\.4\.1\.\d+\..*[Pp]ower",
        alert_type="hardware",
        title_template="Power Alert: {agent_address}",
        severity="critical",
        description_template="Power supply alert on {agent_address}"
    ),
]


class TrapMapper:
    """Maps SNMP traps to NetStacks alerts using configured mappings."""

    def __init__(self, custom_mappings: Optional[List[TrapMapping]] = None):
        """Initialize with default and custom mappings."""
        self.mappings = DEFAULT_TRAP_MAPPINGS.copy()
        if custom_mappings:
            # Custom mappings take precedence (added first)
            self.mappings = custom_mappings + self.mappings

    def find_mapping(self, trap_oid: str) -> Optional[TrapMapping]:
        """Find the first matching mapping for a trap OID."""
        for mapping in self.mappings:
            if re.match(mapping.oid_pattern, trap_oid):
                return mapping
        return None

    def map_trap_to_alert(
        self,
        trap_oid: str,
        agent_address: str,
        varbinds: Dict[str, Any],
        enterprise_oid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Convert an SNMP trap to a NetStacks alert payload.

        Args:
            trap_oid: The trap OID (snmpTrapOID.0 value)
            agent_address: IP address of the device sending the trap
            varbinds: Dictionary of OID -> value from trap
            enterprise_oid: Enterprise OID if present

        Returns:
            Alert payload dict ready for POST to /api/alerts/
        """
        mapping = self.find_mapping(trap_oid)

        # Template variables
        template_vars = {
            "agent_address": agent_address,
            "trap_oid": trap_oid,
            "enterprise_oid": enterprise_oid or "unknown",
        }

        # Add varbind values to template vars (use last part of OID as key)
        for oid, value in varbinds.items():
            oid_parts = oid.split(".")
            if len(oid_parts) > 0:
                # Create simple key from last few OID parts
                key = f"varbind_{oid_parts[-1]}"
                template_vars[key] = str(value)

        if mapping:
            # Use the mapping
            title = mapping.title_template.format(**template_vars)
            description = None
            if mapping.description_template:
                description = mapping.description_template.format(**template_vars)

            return {
                "title": title,
                "severity": mapping.severity,
                "description": description,
                "source": "snmp_trap",
                "device_name": agent_address,
                "alert_type": mapping.alert_type,
                "raw_data": {
                    "trap_oid": trap_oid,
                    "enterprise_oid": enterprise_oid,
                    "agent_address": agent_address,
                    "varbinds": varbinds,
                    "mapping_used": mapping.oid_pattern
                }
            }
        else:
            # No mapping found - create generic alert
            return {
                "title": f"SNMP Trap from {agent_address}",
                "severity": "info",
                "description": f"Received trap OID: {trap_oid}",
                "source": "snmp_trap",
                "device_name": agent_address,
                "alert_type": "snmp_generic",
                "raw_data": {
                    "trap_oid": trap_oid,
                    "enterprise_oid": enterprise_oid,
                    "agent_address": agent_address,
                    "varbinds": varbinds,
                    "mapping_used": None
                }
            }


# Global mapper instance
trap_mapper = TrapMapper()
