#!/usr/bin/env python3
"""
Seed Script for NetStacks Knowledge Base and Alerts

Seeds:
- Knowledge collections (RFC, Troubleshooting, Runbooks)
- Knowledge documents (BGP, OSPF, IS-IS, MPLS, Layer 2, Segment Routing)
- Test alerts for agent testing

Run with: docker exec netstacks-ai python /app/scripts/seed_knowledge_and_alerts.py
Or: python scripts/seed_knowledge_and_alerts.py
"""

import uuid
import random
from datetime import datetime, timedelta
import sys
import os

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from sqlalchemy import text
from netstacks_core.db import get_session, Alert, Incident


# =============================================================================
# KNOWLEDGE COLLECTIONS
# =============================================================================

COLLECTIONS = [
    {
        "name": "RFCs",
        "description": "IETF Request for Comments documents for routing protocols",
        "doc_type": "protocol",
    },
    {
        "name": "Troubleshooting Guides",
        "description": "Protocol-specific troubleshooting guides and procedures",
        "doc_type": "runbook",
    },
    {
        "name": "Vendor Documentation",
        "description": "Vendor-specific configuration and operational guides",
        "doc_type": "vendor",
    },
    {
        "name": "Runbooks",
        "description": "Standard operating procedures and incident response",
        "doc_type": "runbook",
    },
]


# =============================================================================
# KNOWLEDGE DOCUMENTS
# =============================================================================

KNOWLEDGE_DOCUMENTS = [
    # =========================================================================
    # BGP DOCUMENTATION
    # =========================================================================
    {
        "title": "RFC 4271 - BGP-4 Protocol Specification",
        "collection": "RFCs",
        "doc_type": "protocol",
        "content": """# RFC 4271 - Border Gateway Protocol 4 (BGP-4)

## Abstract
This document defines the Border Gateway Protocol (BGP), the de facto standard
inter-domain routing protocol of the Internet.

## 1. Introduction
The primary function of a BGP system is to exchange network reachability
information with other BGP systems. This network reachability information
includes information on the full path of ASes that traffic must traverse.

## 2. Terminology
- **Autonomous System (AS)**: A set of routers under single technical administration
- **BGP Peer**: Two BGP speakers that have formed a TCP connection
- **eBGP**: External BGP (between different AS)
- **iBGP**: Internal BGP (within same AS)

## 3. Message Types

### 3.1 OPEN Message
Sent after TCP connection establishment. Contains:
- BGP Version (currently 4)
- My Autonomous System number (2 bytes)
- Hold Time (proposed)
- BGP Identifier (Router ID)
- Optional Parameters (capabilities)

### 3.2 UPDATE Message
Used to advertise or withdraw routes. Contains:
- Withdrawn Routes Length
- Withdrawn Routes
- Total Path Attribute Length
- Path Attributes
- Network Layer Reachability Information (NLRI)

### 3.3 KEEPALIVE Message
Sent periodically to maintain the connection. Sent at 1/3 of the Hold Time.

### 3.4 NOTIFICATION Message
Sent when an error is detected. Causes connection to close.

## 4. Path Attributes

### 4.1 Mandatory Attributes
- **ORIGIN**: IGP, EGP, or INCOMPLETE
- **AS_PATH**: Sequence of ASes the route has traversed
- **NEXT_HOP**: IP address of next hop

### 4.2 Well-Known Discretionary
- **LOCAL_PREF**: Used within AS for path selection (default 100)
- **ATOMIC_AGGREGATE**: Indicates route aggregation

### 4.3 Optional Transitive
- **COMMUNITY**: Route tagging mechanism
- **EXTENDED_COMMUNITY**: 8-byte community values

### 4.4 Optional Non-Transitive
- **MED** (Multi-Exit Discriminator): Influences inbound traffic

## 5. Best Path Selection Algorithm

BGP selects the best path using these criteria in order:
1. Highest Weight (Cisco-specific, local)
2. Highest LOCAL_PREF
3. Locally originated routes preferred
4. Shortest AS_PATH
5. Lowest ORIGIN type (IGP < EGP < INCOMPLETE)
6. Lowest MED (only compared within same AS)
7. eBGP preferred over iBGP
8. Lowest IGP metric to NEXT_HOP
9. Oldest route (for stability)
10. Lowest Router ID
11. Lowest neighbor IP address

## 6. FSM States

1. **Idle**: Initial state
2. **Connect**: Waiting for TCP connection
3. **Active**: Initiating TCP connection
4. **OpenSent**: OPEN message sent
5. **OpenConfirm**: Waiting for KEEPALIVE
6. **Established**: Session operational

## 7. Error Codes

| Code | Meaning |
|------|---------|
| 1 | Message Header Error |
| 2 | OPEN Message Error |
| 3 | UPDATE Message Error |
| 4 | Hold Timer Expired |
| 5 | FSM Error |
| 6 | Cease |
"""
    },
    {
        "title": "RFC 7947 - Internet Exchange BGP Route Server",
        "collection": "RFCs",
        "doc_type": "protocol",
        "content": """# RFC 7947 - Internet Exchange BGP Route Server

## Overview
A route server at an Internet Exchange Point (IXP) enables multilateral peering.
Instead of establishing N*(N-1)/2 bilateral sessions, each participant needs
only one session to the route server.

## Key Concepts

### Route Server Behavior
- Route server does NOT modify NEXT_HOP (transparent)
- Route server does NOT prepend its own ASN to AS_PATH
- Route server propagates routes between clients

### Configuration Requirements
- Clients must accept third-party NEXT_HOP
- Clients should not use `next-hop-self`
- Route server should use `no-client-to-client-reflection`

### Best Practices
1. Implement RPKI validation at route server
2. Use BGP communities for filtering
3. Enable BFD for fast failure detection
4. Maintain route server redundancy
"""
    },
    {
        "title": "BGP Troubleshooting Guide",
        "collection": "Troubleshooting Guides",
        "doc_type": "runbook",
        "content": """# BGP Troubleshooting Guide

## Diagnostic Commands

### Cisco IOS/IOS-XE
```
show ip bgp summary
show ip bgp neighbors [IP]
show ip bgp neighbors [IP] advertised-routes
show ip bgp neighbors [IP] received-routes
show ip bgp [prefix]
show ip bgp regexp [as-path-regex]
debug ip bgp updates
debug ip bgp events
```

### Juniper Junos
```
show bgp summary
show bgp neighbor [IP]
show route advertising-protocol bgp [IP]
show route receive-protocol bgp [IP]
show route protocol bgp [prefix]
traceoptions
```

## Common Issues and Resolution

### 1. BGP Neighbor Not Establishing

**Symptoms:**
- Neighbor state stuck in Active or Idle
- No routes being received

**Diagnostic Steps:**
1. Verify TCP connectivity to port 179
   ```
   telnet [neighbor_ip] 179
   ```
2. Check for ACLs/firewalls blocking TCP 179
3. Verify AS number configuration
4. Check router-ID uniqueness
5. Verify MD5 authentication password

**Resolution:**
- Correct AS number mismatch
- Add ACL to permit BGP
- Fix authentication password
- Clear BGP session: `clear ip bgp [neighbor]`

### 2. Routes Not Being Advertised

**Symptoms:**
- Routes in IGP but not in BGP
- Neighbor not receiving expected prefixes

**Common Causes:**
1. Network statement missing or incorrect
2. Route-map filtering outbound
3. Prefix not in routing table exactly
4. AS-path filtering (as-path access-list)
5. Prefix-list filtering

**Resolution:**
- Verify network statements match RIB exactly
- Check outbound route-maps and prefix-lists
- Ensure route exists in routing table

### 3. BGP Session Flapping

**Symptoms:**
- Session repeatedly going up/down
- Log messages showing "Hold timer expired"

**Common Causes:**
1. Physical layer issues (link flapping)
2. CPU overload causing missed keepalives
3. MTU issues
4. Network congestion

**Resolution:**
1. Check physical interface for errors
2. Increase hold timer (3x keepalive)
3. Enable BFD for faster detection
4. Check CPU utilization

### 4. Route Not Installed in RIB

**Symptoms:**
- Route in BGP table but not routing table
- `r>` instead of `*>` in BGP table

**Common Causes:**
1. Next-hop unreachable
2. Recursive lookup failure
3. Administrative distance conflict
4. Maximum-paths exceeded

**Resolution:**
- Verify next-hop is reachable via IGP
- Check `next-hop-self` configuration for iBGP
- Verify IGP route to next-hop

### 5. Suboptimal Path Selection

**Symptoms:**
- Traffic taking longer path than expected
- MED or LOCAL_PREF not being applied

**Diagnostic Steps:**
1. Check LOCAL_PREF values
2. Verify AS_PATH length
3. Check MED values
4. Review route-map configurations

**Resolution:**
- Adjust LOCAL_PREF for preferred paths
- Use AS_PATH prepending for backup paths
- Configure appropriate route-maps
"""
    },
    {
        "title": "BGP Best Practices and Security",
        "collection": "Runbooks",
        "doc_type": "runbook",
        "content": """# BGP Best Practices and Security

## Session Security

### MD5 Authentication
Always use MD5 authentication for eBGP sessions:
```
router bgp 65001
 neighbor 10.0.0.1 password SecurePassword123
```

### TTL Security (GTSM)
Enable TTL security to prevent remote attacks:
```
router bgp 65001
 neighbor 10.0.0.1 ttl-security hops 1
```

### Maximum Prefix Limits
Prevent route table overflow:
```
neighbor 10.0.0.1 maximum-prefix 100000 warning-only
neighbor 10.0.0.1 maximum-prefix 150000 shutdown
```

## Filtering Best Practices

### Prefix Filtering
1. Always filter inbound on eBGP
2. Block bogons and private space from internet peers
3. Use IRR-based prefix lists
4. Implement RPKI validation

### AS-Path Filtering
Block paths containing:
- Private AS numbers (64512-65534)
- Reserved AS numbers
- Your own AS (prevent loops)

### Community-Based Filtering
Use BGP communities for:
- Traffic engineering
- Route tagging by source
- Customer/peer/transit classification

## RPKI Implementation

### Route Origin Validation
```
router bgp 65001
 bgp rpki server tcp 10.0.0.100 port 3323 refresh 900
 neighbor 10.0.0.1 route-map RPKI-VALIDATE in
```

### ROA States
- **Valid**: Origin AS matches ROA
- **Invalid**: Origin AS doesn't match ROA
- **Unknown**: No ROA exists for prefix

## Graceful Restart

Enable to maintain forwarding during control plane restart:
```
router bgp 65001
 bgp graceful-restart
 bgp graceful-restart restart-time 120
 bgp graceful-restart stalepath-time 360
```
"""
    },
    # =========================================================================
    # OSPF DOCUMENTATION
    # =========================================================================
    {
        "title": "RFC 2328 - OSPF Version 2",
        "collection": "RFCs",
        "doc_type": "protocol",
        "content": """# RFC 2328 - OSPF Version 2

## Overview
OSPF (Open Shortest Path First) is a link-state routing protocol that operates
within a single Autonomous System.

## Key Concepts

### Link State Database
Each router maintains identical LSDB containing:
- Router LSAs (Type 1)
- Network LSAs (Type 2)
- Summary LSAs (Type 3, 4)
- External LSAs (Type 5, 7)

### SPF Algorithm
Dijkstra's algorithm computes shortest path tree with router as root.

## Packet Types

| Type | Name | Purpose |
|------|------|---------|
| 1 | Hello | Neighbor discovery/maintenance |
| 2 | DBD | Database description |
| 3 | LSR | Link-state request |
| 4 | LSU | Link-state update |
| 5 | LSAck | Link-state acknowledgment |

## Neighbor States

1. **Down**: No hellos received
2. **Attempt**: (NBMA only) Sending unicast hellos
3. **Init**: Hello received, not bidirectional
4. **2-Way**: Bidirectional, DR election can occur
5. **ExStart**: Master/Slave determination
6. **Exchange**: DBD exchange
7. **Loading**: Requesting missing LSAs
8. **Full**: Fully adjacent

## Area Types

### Backbone (Area 0)
- Central area connecting all other areas
- All inter-area traffic transits backbone

### Standard Area
- Accepts all LSA types
- Full routing table

### Stub Area
- No Type 5 (external) LSAs
- Default route for external destinations

### Totally Stubby Area
- No Type 3, 4, or 5 LSAs
- Single default route from ABR

### NSSA (Not-So-Stubby Area)
- No Type 5 LSAs
- Type 7 LSAs for local external routes
- Type 7 to Type 5 translation at ABR

## Timers
- Hello interval: 10s (broadcast), 30s (NBMA)
- Dead interval: 4x hello interval
- SPF delay: Typically 5 seconds
- LSA refresh: 30 minutes
"""
    },
    {
        "title": "OSPF Troubleshooting Guide",
        "collection": "Troubleshooting Guides",
        "doc_type": "runbook",
        "content": """# OSPF Troubleshooting Guide

## Diagnostic Commands

### Cisco IOS/IOS-XE
```
show ip ospf neighbor
show ip ospf interface [interface]
show ip ospf database
show ip ospf border-routers
show ip route ospf
debug ip ospf adj
debug ip ospf events
```

### Juniper Junos
```
show ospf neighbor
show ospf interface
show ospf database
show route protocol ospf
traceoptions
```

## Common Issues and Resolution

### 1. OSPF Adjacency Not Forming

**Symptoms:**
- Neighbor stuck in Init or 2-Way
- No OSPF routes learned

**Must Match Between Neighbors:**
- Area ID
- Hello/Dead intervals
- Network type
- Authentication
- MTU (unless `ip ospf mtu-ignore`)
- Subnet mask (on broadcast networks)

**Diagnostic Steps:**
1. Verify OSPF enabled on interface
   ```
   show ip ospf interface
   ```
2. Check hello/dead timers match
3. Verify authentication settings
4. Check MTU on both sides
5. Ensure area IDs match

**Resolution:**
- Correct timer mismatches
- Fix authentication configuration
- Add `ip ospf mtu-ignore` if MTU differs
- Verify correct area assignment

### 2. DR/BDR Election Issues

**Symptoms:**
- Unexpected DR/BDR
- Suboptimal flooding

**Important Facts:**
- Election is NOT preemptive
- Highest priority wins (default 1)
- Priority 0 = never become DR/BDR
- Highest Router-ID breaks ties

**Resolution:**
- Set appropriate priorities
- Clear OSPF process to force re-election
- Consider using `ip ospf network point-to-point`

### 3. OSPF Routes Not in Routing Table

**Symptoms:**
- Routes in OSPF database but not RIB
- SPF calculation not completing

**Common Causes:**
1. Lower AD route exists (connected, static)
2. SPF calculation blocked
3. Filter on ABR/ASBR
4. Area not connected to backbone

**Resolution:**
- Check for duplicate prefixes
- Verify virtual link if needed
- Review distribute-lists and route-maps

### 4. Type 7 to Type 5 Translation Issues

**Symptoms:**
- NSSA external routes not visible outside NSSA
- Missing Type 5 LSAs

**Check Points:**
1. ABR performing translation
2. No suppress-fa configured
3. Forwarding address reachable
4. P-bit set in Type 7 LSA

### 5. OSPF Flapping

**Symptoms:**
- Frequent SPF calculations
- Adjacency drops/reforms

**Common Causes:**
1. MTU mismatch causing DBD retransmissions
2. Physical layer instability
3. Duplicate Router-IDs
4. CPU overload

**Resolution:**
1. Fix MTU mismatch
2. Check interface for errors
3. Ensure unique router-IDs
4. Increase SPF throttle timers
"""
    },
    # =========================================================================
    # IS-IS DOCUMENTATION
    # =========================================================================
    {
        "title": "RFC 1195 - IS-IS for IP",
        "collection": "RFCs",
        "doc_type": "protocol",
        "content": """# RFC 1195 - Use of OSI IS-IS for Routing in TCP/IP and Dual Environments

## Overview
IS-IS (Intermediate System to Intermediate System) is a link-state routing
protocol originally designed for OSI networks, extended to support IP.

## Key Concepts

### NET (Network Entity Title)
Format: Area.SystemID.Selector
Example: 49.0001.1921.6800.1001.00
- 49.0001 = Area
- 1921.6800.1001 = System ID (derived from IP)
- 00 = Selector (always 00 for routers)

### Levels
- **Level 1**: Intra-area routing
- **Level 2**: Inter-area routing
- **Level 1-2**: Both (like OSPF ABR)

### Packet Types
- **IIH**: IS-IS Hello
- **LSP**: Link-State PDU
- **CSNP**: Complete Sequence Number PDU
- **PSNP**: Partial Sequence Number PDU

## TLVs (Type-Length-Value)

| TLV | Name | Purpose |
|-----|------|---------|
| 1 | Area Addresses | List of areas |
| 2 | IS Reachability | Neighbor info |
| 22 | Extended IS Reach | TE extensions |
| 128 | IP Internal Reach | Internal IP prefixes |
| 130 | IP External Reach | External IP prefixes |
| 135 | Extended IP Reach | Wide metrics |

## Metrics
- **Narrow metrics**: 6-bit, max 63 per link
- **Wide metrics**: 24-bit, max 16777215
- Always use wide metrics in modern networks

## Adjacency Requirements
- Same MTU
- Level compatibility
- Area match (Level 1 only)
- Authentication match

## DIS (Designated IS)
- Similar to OSPF DR but:
  - Election IS preemptive
  - Highest priority, then highest SNPA
  - No Backup DIS concept
  - Hello interval 1/3 of regular
"""
    },
    {
        "title": "IS-IS Troubleshooting Guide",
        "collection": "Troubleshooting Guides",
        "doc_type": "runbook",
        "content": """# IS-IS Troubleshooting Guide

## Diagnostic Commands

### Cisco IOS/IOS-XE
```
show isis neighbors
show isis database [detail]
show isis topology
show isis interface
show clns neighbors
debug isis adj-packets
debug isis update-packets
```

### Juniper Junos
```
show isis adjacency [detail]
show isis database [extensive]
show isis spf log
show isis interface
traceoptions
```

## Common Issues and Resolution

### 1. IS-IS Adjacency Not Forming

**Symptoms:**
- No IS-IS neighbors
- Interface stuck in "Init" state

**Must Match:**
- MTU (or use point-to-point)
- Level type (L1, L2, or L1-L2)
- Area address (for Level 1)
- Authentication

**Diagnostic Steps:**
1. Verify IS-IS enabled on interface
   ```
   show isis interface [interface]
   ```
2. Check hello packets with debug
3. Verify area addresses
4. Check authentication settings

**Resolution:**
- Enable IS-IS on interface
- Match MTU values
- Configure compatible levels
- Fix authentication

### 2. Level 1/Level 2 Connectivity Issues

**Symptoms:**
- L1 routers can't reach other areas
- Missing inter-area routes

**Requirements:**
- At least one L1-L2 router per area
- L1-L2 routers must have L2 connectivity
- ATT (Attached) bit set on L1-L2

**Resolution:**
- Verify L1-L2 router exists
- Check L2 adjacencies are up
- Review overload-bit configuration

### 3. Metric Mismatch Issues

**Symptoms:**
- Suboptimal routing
- Metric calculation errors

**Important:**
- Narrow metrics: max 63 per link
- Wide metrics: max 16777215 per link
- Don't mix metric styles in same area

**Resolution:**
- Convert all routers to wide metrics
- Use consistent metric values
- Check for metric-style configuration

### 4. IS-IS Database Inconsistency

**Symptoms:**
- Routes appear/disappear
- SPF calculation loops

**Common Causes:**
1. Duplicate System IDs
2. LSP corruption
3. MTU issues causing fragmentation

**Resolution:**
1. Verify unique System IDs
2. Clear IS-IS database
3. Check interface MTU
4. Verify no loops in topology

### 5. IS-IS Authentication Issues

**Symptoms:**
- Adjacency not forming
- Debug shows authentication mismatch

**Check Points:**
1. Same key-chain on both sides
2. Same authentication type (MD5/plaintext)
3. Level-specific authentication
4. SNP authentication if enabled
"""
    },
    # =========================================================================
    # MPLS DOCUMENTATION
    # =========================================================================
    {
        "title": "MPLS and LDP Fundamentals",
        "collection": "Vendor Documentation",
        "doc_type": "vendor",
        "content": """# MPLS and LDP Fundamentals

## MPLS Overview

MPLS (Multiprotocol Label Switching) provides:
- High-performance packet forwarding
- Traffic engineering capabilities
- VPN services (L2VPN, L3VPN)

## Label Stack

### Label Format (32 bits)
- Label (20 bits): Values 0-1048575
- TC (3 bits): Traffic Class (QoS)
- S (1 bit): Bottom of Stack
- TTL (8 bits): Time to Live

### Reserved Labels
- 0: Explicit NULL (IPv4)
- 1: Router Alert
- 2: Explicit NULL (IPv6)
- 3: Implicit NULL (PHP)

## LDP (Label Distribution Protocol)

### Session Establishment
1. Hello messages (UDP port 646)
2. TCP connection (port 646)
3. Initialization exchange
4. Label mapping exchange

### LDP Messages
| Message | Purpose |
|---------|---------|
| Hello | Discover LDP neighbors |
| Initialization | Negotiate session parameters |
| Address | Advertise interface addresses |
| Label Mapping | Advertise label bindings |
| Label Request | Request label for FEC |
| Label Withdraw | Remove label binding |
| Label Release | Release label binding |
| Notification | Signal events/errors |

## Label Allocation Modes

### Downstream Unsolicited
- Labels advertised without request
- Most common mode
- Default in most implementations

### Downstream on Demand
- Labels only advertised when requested
- Used in ATM networks

## Label Retention Modes

### Liberal
- Keep all received labels
- Faster convergence
- More memory usage

### Conservative
- Keep only best path labels
- Less memory usage
- Slower convergence

## PHP (Penultimate Hop Popping)

Removes MPLS header at second-to-last hop:
- Reduces load on egress router
- Implicit NULL label (3) signals PHP
- Can be disabled per-prefix

## Troubleshooting Commands

### Cisco
```
show mpls interfaces
show mpls ldp neighbor [detail]
show mpls ldp bindings
show mpls forwarding-table
debug mpls ldp messages
```

### Juniper
```
show ldp neighbor
show ldp interface
show ldp database
show route table mpls.0
```
"""
    },
    {
        "title": "MPLS L3VPN Troubleshooting",
        "collection": "Troubleshooting Guides",
        "doc_type": "runbook",
        "content": """# MPLS L3VPN Troubleshooting Guide

## Architecture Overview

### Components
- **PE (Provider Edge)**: Customer-facing router
- **P (Provider)**: Core MPLS router
- **CE (Customer Edge)**: Customer router
- **VRF**: Virtual Routing and Forwarding instance
- **RD**: Route Distinguisher (makes routes unique)
- **RT**: Route Target (controls route import/export)

## Diagnostic Commands

### Cisco IOS/IOS-XE
```
show vrf detail [vrf-name]
show ip bgp vpnv4 all
show ip bgp vpnv4 vrf [vrf] summary
show ip route vrf [vrf]
show mpls forwarding-table vrf [vrf]
show ip cef vrf [vrf]
```

### Juniper
```
show route instance [vrf] detail
show bgp summary instance [vrf]
show route table [vrf].inet.0
show route label-switched-path
```

## Common Issues and Resolution

### 1. VRF Routes Not Learning

**Symptoms:**
- PE-CE routes not in VRF table
- No routes from remote VRF

**Diagnostic Steps:**
1. Check PE-CE protocol
   ```
   show ip bgp vpnv4 vrf [vrf] summary
   show ip ospf vrf [vrf] neighbor
   ```
2. Verify RT configuration
3. Check VPNv4 BGP peering

**Resolution:**
- Fix PE-CE protocol config
- Correct RT import/export
- Verify VPNv4 BGP session

### 2. RT Import/Export Issues

**Symptoms:**
- Routes learned but not imported
- Routes not exported to MP-BGP

**Check Points:**
1. Export RT on source VRF
2. Import RT on destination VRF
3. RTs must match (export = import)

**Common Configurations:**
```
! Hub-spoke
Hub exports: RT 100:1
Spoke imports: RT 100:1
Spoke exports: RT 100:2
Hub imports: RT 100:2

! Full mesh
All export/import: RT 100:100
```

### 3. Label Issues

**Symptoms:**
- Routes in VPNv4 table but not forwarding
- MPLS labels not being allocated

**Diagnostic Steps:**
1. Check MPLS enabled on interfaces
2. Verify LDP/RSVP sessions
3. Check label stack
   ```
   show mpls forwarding-table vrf [vrf]
   ```

**Resolution:**
- Enable MPLS on core-facing interfaces
- Verify LDP sessions established
- Check for label space exhaustion

### 4. VRF Route Leaking Issues

**Symptoms:**
- Routes appearing in wrong VRF
- Security concerns with overlapping routes

**Check Points:**
1. Review RT configuration
2. Check for unintended import statements
3. Verify route-maps on RT import

### 5. PE-CE Protocol Issues

**OSPF PE-CE:**
- Check OSPF process in VRF
- Verify network statements
- Check for sham-link if backdoor

**BGP PE-CE:**
- Verify eBGP session in VRF
- Check AS number configuration
- Review route-maps and filters

**Static PE-CE:**
- Verify VRF in static route
- Check redistribute connected
- Verify next-hop reachable in VRF
"""
    },
    # =========================================================================
    # LAYER 2 DOCUMENTATION
    # =========================================================================
    {
        "title": "Layer 2 Switching and Spanning Tree",
        "collection": "Troubleshooting Guides",
        "doc_type": "runbook",
        "content": """# Layer 2 Switching and Spanning Tree Guide

## Spanning Tree Overview

### Protocol Versions
| Protocol | Standard | Convergence |
|----------|----------|-------------|
| STP (802.1D) | Original | 30-50 seconds |
| RSTP (802.1w) | 2004 | < 1 second |
| MST (802.1s) | Multiple instances | < 1 second |

### Port States (RSTP)
- **Discarding**: Not forwarding, not learning
- **Learning**: Learning MACs, not forwarding
- **Forwarding**: Full operation

### Port Roles
- **Root**: Best path to root bridge
- **Designated**: Forwarding port toward downstream
- **Alternate**: Backup to root port
- **Backup**: Backup to designated port

## Diagnostic Commands

### Cisco
```
show spanning-tree
show spanning-tree summary
show spanning-tree interface [int] detail
show spanning-tree blockedports
show mac address-table
show interfaces trunk
```

## Common Issues

### 1. Spanning Tree Loop

**Symptoms:**
- Broadcast storm
- High CPU on switches
- MAC flapping

**Causes:**
1. BPDUs not being received (unidirectional link)
2. Root guard/BPDU guard not configured
3. Non-STP device in path

**Resolution:**
1. Enable UDLD
2. Configure root guard on edge
3. Enable BPDU guard on access ports
4. Use STP loop guard

### 2. Suboptimal Root Bridge

**Symptoms:**
- Traffic taking longer paths
- Unexpected blocked ports

**Resolution:**
- Set explicit root bridge
```
spanning-tree vlan [vlan] root primary
spanning-tree vlan [vlan] priority 4096
```

### 3. TCN (Topology Change) Storm

**Symptoms:**
- Frequent MAC table flushes
- Packet loss during changes

**Causes:**
1. Frequent link status changes
2. Incorrect PortFast configuration
3. VM migration

**Resolution:**
1. Enable PortFast on access ports
2. Use BPDU guard with PortFast
3. Consider root bridge placement

### 4. VLAN Issues

**Symptoms:**
- Hosts can't communicate across switches
- VLAN traffic not passing trunk

**Check Points:**
1. VLAN exists on all switches
2. VLAN allowed on trunk
3. Native VLAN matches
4. Trunk is actually trunking

**Commands:**
```
show vlan brief
show interfaces trunk
show interfaces [int] switchport
```

### 5. MAC Flapping

**Symptoms:**
- Log messages about MAC moving
- Intermittent connectivity

**Causes:**
1. Layer 2 loop
2. Dual-homed host (incorrect)
3. VM migration
4. Spanning tree misconfiguration

**Resolution:**
1. Find and break the loop
2. Verify STP operation
3. Check for misconfigured NIC teaming
"""
    },
    # =========================================================================
    # SEGMENT ROUTING
    # =========================================================================
    {
        "title": "Segment Routing Overview",
        "collection": "Vendor Documentation",
        "doc_type": "vendor",
        "content": """# Segment Routing (SR) Overview

## Introduction

Segment Routing simplifies network operations by:
- Eliminating per-flow state in the network
- Enabling source-based routing
- Reducing protocol complexity (no LDP/RSVP)

## Key Concepts

### Segment Types

1. **Prefix Segment (Prefix-SID)**
   - Identifies a destination prefix
   - Global significance
   - Typically 16000-23999

2. **Adjacency Segment (Adj-SID)**
   - Identifies a specific link
   - Local significance
   - Typically 24000+

3. **Node Segment (Node-SID)**
   - Identifies a specific node
   - Derived from prefix-SID of loopback

### SRGB (Segment Routing Global Block)
- Label range reserved for SR
- Default: 16000-23999
- Must be consistent across domain

## SR-MPLS Configuration

### Cisco IOS-XR
```
segment-routing
 global-block 16000 23999

router isis 1
 address-family ipv4 unicast
  segment-routing mpls
 interface Loopback0
  address-family ipv4 unicast
   prefix-sid index 1
```

### Juniper
```
protocols {
    isis {
        source-packet-routing {
            srgb start-label 16000 index-range 8000;
            node-segment {
                ipv4-index 1;
            }
        }
    }
}
```

## SR-TE (Traffic Engineering)

### SR-TE Policy Components
- Headend: Source router
- Color: Policy identifier
- Endpoint: Destination
- Segment List: Path through network

### Example Policy
```
segment-routing
 traffic-eng
  policy TO-NYC
   color 100 end-point ipv4 10.0.0.5
   candidate-paths
    preference 100
     explicit segment-list PATH1
      index 10 mpls label 16001
      index 20 mpls label 16002
      index 30 mpls label 16005
```

## TI-LFA (Topology Independent LFA)

Provides sub-50ms failover:
1. Pre-computes backup paths
2. Uses segment lists for repair paths
3. Protects against node and link failures

### Configuration
```
router isis 1
 address-family ipv4 unicast
  fast-reroute per-prefix
  fast-reroute per-prefix ti-lfa
```

## Troubleshooting

### Verification Commands
```
show segment-routing mapping-server prefix-sid-map
show isis segment-routing prefix-sid-map
show mpls forwarding labels [start] [end]
show segment-routing traffic-eng policy
```
"""
    },
    # =========================================================================
    # INCIDENT RESPONSE
    # =========================================================================
    {
        "title": "Network Incident Response Runbook",
        "collection": "Runbooks",
        "doc_type": "runbook",
        "content": """# Network Incident Response Runbook

## Severity Levels

| Level | Name | Examples | Response |
|-------|------|----------|----------|
| P1 | Critical | Core outage, DC down | 15 min, 24x7 |
| P2 | High | Site down, major degradation | 30 min, 24x7 |
| P3 | Medium | Single device, limited impact | 2 hours |
| P4 | Low | Monitoring alert, no impact | Next BD |

## Incident Response Process

### 1. Detection and Triage
- Acknowledge alert within SLA
- Assess severity and impact
- Notify stakeholders per severity

### 2. Initial Diagnosis

#### Quick Health Check Commands
```
! Check interface status
show interfaces status err-disabled

! Check routing
show ip route summary
show ip bgp summary
show ip ospf neighbor

! Check CPU/memory
show processes cpu sorted
show memory statistics

! Check recent events
show logging last 100
```

### 3. Containment
- Isolate affected components if necessary
- Implement temporary workaround
- Document all actions

### 4. Resolution
- Identify root cause
- Implement fix
- Verify resolution

### 5. Post-Incident
- Document timeline
- Update runbooks
- Schedule RCA if needed

## Common Scenarios

### BGP Peer Down
1. Check physical connectivity
2. Verify BGP configuration
3. Check for filters/ACLs
4. Review logs for error messages

### Interface Flapping
1. Check for physical issues
2. Review error counters
3. Check for duplex mismatch
4. Verify STP stability

### High CPU
1. Identify top process
2. Check for routing instability
3. Look for control plane attacks
4. Review BGP/OSPF stability

## Escalation Matrix

| Severity | Level 1 | Level 2 | Level 3 |
|----------|---------|---------|---------|
| P1 | Immediate | +15 min | +30 min |
| P2 | Immediate | +30 min | +1 hour |
| P3 | 2 hours | +4 hours | +8 hours |

## Communication Templates

### Initial Notification
```
INCIDENT: [Brief Title]
SEVERITY: [P1-P4]
IMPACT: [Affected services/users]
STATUS: Investigating
NEXT UPDATE: [Time]
```

### Resolution Notification
```
RESOLVED: [Brief Title]
ROOT CAUSE: [Summary]
RESOLUTION: [Actions taken]
DURATION: [Start - End time]
```
"""
    },
]


# =============================================================================
# TEST ALERTS
# =============================================================================

ALERTS = [
    {
        "title": "BGP Neighbor Down - PE1-NYC to TRANSIT-A",
        "description": "BGP session with peer 198.51.100.1 (AS 65100) has transitioned to Idle state. Hold timer expired.",
        "severity": "critical",
        "status": "new",
        "source": "network-monitor",
        "device_name": "PE1-NYC",
        "alert_type": "bgp_down",
        "raw_data": {
            "neighbor_ip": "198.51.100.1",
            "remote_as": "65100",
            "error": "Hold timer expired",
            "last_state": "Established",
            "uptime_before_down": "45 days 12:34:56"
        }
    },
    {
        "title": "OSPF Adjacency Flapping - CORE-RTR-01",
        "description": "OSPF adjacency with 10.1.1.2 in area 0 has flapped 5 times in the last 10 minutes.",
        "severity": "warning",
        "status": "new",
        "source": "network-monitor",
        "device_name": "CORE-RTR-01",
        "alert_type": "ospf_flapping",
        "raw_data": {
            "neighbor_ip": "10.1.1.2",
            "area": "0.0.0.0",
            "flap_count": 5,
            "period_minutes": 10,
            "neighbor_router_id": "10.255.0.2"
        }
    },
    {
        "title": "High CPU Utilization - DIST-SW-03",
        "description": "CPU utilization has exceeded 85% threshold. Current: 92%",
        "severity": "warning",
        "status": "new",
        "source": "snmp-poller",
        "device_name": "DIST-SW-03",
        "alert_type": "high_cpu",
        "raw_data": {
            "metric": "cpu_utilization",
            "current_value": 92,
            "threshold": 85,
            "top_process": "IP Input"
        }
    },
    {
        "title": "Interface Down - PE2-LAX Gi0/0/1",
        "description": "Interface GigabitEthernet0/0/1 (uplink to core) has gone down.",
        "severity": "critical",
        "status": "new",
        "source": "syslog",
        "device_name": "PE2-LAX",
        "alert_type": "interface_down",
        "raw_data": {
            "interface": "GigabitEthernet0/0/1",
            "description": "Uplink to CORE-RTR-02",
            "last_state": "up",
            "input_errors": 0,
            "output_errors": 0
        }
    },
    {
        "title": "IS-IS Adjacency Down - P-RTR-01",
        "description": "IS-IS Level-2 adjacency to P-RTR-02 has gone down.",
        "severity": "critical",
        "status": "new",
        "source": "network-monitor",
        "device_name": "P-RTR-01",
        "alert_type": "isis_down",
        "raw_data": {
            "neighbor_sysid": "0000.0000.0002",
            "level": "L2",
            "interface": "TenGigE0/0/0/1",
            "last_state": "Up"
        }
    },
    {
        "title": "LDP Session Down - PE3-CHI",
        "description": "LDP session with 10.255.0.5 has been lost.",
        "severity": "critical",
        "status": "new",
        "source": "network-monitor",
        "device_name": "PE3-CHI",
        "alert_type": "ldp_down",
        "raw_data": {
            "neighbor_ip": "10.255.0.5",
            "session_state": "down",
            "labels_withdrawn": 1523
        }
    },
    {
        "title": "Spanning Tree Topology Change - ACCESS-SW-12",
        "description": "Multiple spanning tree topology changes detected on VLAN 100.",
        "severity": "warning",
        "status": "new",
        "source": "syslog",
        "device_name": "ACCESS-SW-12",
        "alert_type": "stp_topology_change",
        "raw_data": {
            "vlan": 100,
            "tc_count": 15,
            "period_minutes": 5,
            "root_bridge": "00:11:22:33:44:55"
        }
    },
    {
        "title": "Memory Utilization Critical - CORE-RTR-01",
        "description": "Memory utilization has exceeded critical threshold. Current: 95%",
        "severity": "critical",
        "status": "new",
        "source": "snmp-poller",
        "device_name": "CORE-RTR-01",
        "alert_type": "high_memory",
        "raw_data": {
            "metric": "memory_utilization",
            "current_value": 95,
            "threshold": 90,
            "free_memory_mb": 256
        }
    },
    {
        "title": "BGP Prefix Limit Warning - EDGE-RTR-02",
        "description": "BGP neighbor 192.0.2.1 has reached 80% of maximum prefix limit.",
        "severity": "warning",
        "status": "new",
        "source": "network-monitor",
        "device_name": "EDGE-RTR-02",
        "alert_type": "bgp_prefix_limit",
        "raw_data": {
            "neighbor_ip": "192.0.2.1",
            "current_prefixes": 80000,
            "max_prefixes": 100000,
            "warning_threshold": 80
        }
    },
    {
        "title": "MPLS VPN Label Exhaustion - PE1-NYC",
        "description": "VPN label allocation approaching limit. 95% of labels in use.",
        "severity": "warning",
        "status": "new",
        "source": "network-monitor",
        "device_name": "PE1-NYC",
        "alert_type": "label_exhaustion",
        "raw_data": {
            "labels_used": 95000,
            "labels_total": 100000,
            "vrf_count": 150
        }
    },
]


# =============================================================================
# TEST INCIDENTS
# =============================================================================

INCIDENTS = [
    {
        "title": "Core Network Outage - NYC Data Center",
        "description": "Multiple core routers experiencing BGP session failures affecting east coast traffic.",
        "severity": "critical",
        "status": "investigating",
        "incident_type": "bgp",
        "affected_devices": ["CORE-RTR-01", "CORE-RTR-02", "PE1-NYC"],
        "created_by": "auto-correlation"
    },
    {
        "title": "MPLS VPN Service Degradation",
        "description": "L3VPN customers reporting intermittent connectivity. Possible MTU issues.",
        "severity": "major",
        "status": "identified",
        "incident_type": "mpls",
        "affected_devices": ["PE1-NYC", "PE2-LAX", "PE3-CHI"],
        "root_cause": "MTU mismatch on core links",
        "created_by": "noc"
    },
    {
        "title": "Spanning Tree Instability - Building A",
        "description": "Frequent topology changes causing network flapping in Building A.",
        "severity": "major",
        "status": "investigating",
        "incident_type": "layer2",
        "affected_devices": ["ACCESS-SW-12", "ACCESS-SW-13", "DIST-SW-03"],
        "created_by": "auto-correlation"
    },
]


# =============================================================================
# SEEDING FUNCTIONS
# =============================================================================

def seed_collections(session):
    """Create knowledge collections using raw SQL (model/schema mismatch)."""
    print("Seeding knowledge collections...")

    created = 0
    for coll_data in COLLECTIONS:
        # Check if exists
        result = session.execute(
            text("SELECT id FROM knowledge_collections WHERE name = :name"),
            {"name": coll_data["name"]}
        ).fetchone()

        if not result:
            session.execute(
                text("""
                    INSERT INTO knowledge_collections
                    (collection_id, name, description, doc_type, is_enabled, document_count, created_by, created_at)
                    VALUES (:collection_id, :name, :description, :doc_type, :is_enabled, :document_count, :created_by, :created_at)
                """),
                {
                    "collection_id": str(uuid.uuid4()),
                    "name": coll_data["name"],
                    "description": coll_data["description"],
                    "doc_type": coll_data["doc_type"],
                    "is_enabled": True,
                    "document_count": 0,
                    "created_by": "seed-script",
                    "created_at": datetime.utcnow()
                }
            )
            created += 1

    session.commit()
    print(f"  Created {created} collections")


def seed_documents(session):
    """Create knowledge documents using raw SQL (model/schema mismatch)."""
    print("Seeding knowledge documents...")

    # Get collections map - use the integer id (primary key)
    collections = {}
    result = session.execute(text("SELECT id, name FROM knowledge_collections"))
    for row in result:
        collections[row.name] = row.id

    created = 0
    for doc_data in KNOWLEDGE_DOCUMENTS:
        # Check if exists
        existing = session.execute(
            text("SELECT doc_id FROM knowledge_documents WHERE title = :title"),
            {"title": doc_data["title"]}
        ).fetchone()

        if not existing:
            collection_id = collections.get(doc_data["collection"])

            import json
            session.execute(
                text("""
                    INSERT INTO knowledge_documents
                    (doc_id, title, content, doc_type, collection_id, is_indexed, doc_metadata, created_by, created_at, chunk_count)
                    VALUES (:doc_id, :title, :content, :doc_type, :collection_id, :is_indexed, :doc_metadata, :created_by, :created_at, :chunk_count)
                """),
                {
                    "doc_id": str(uuid.uuid4()),
                    "title": doc_data["title"],
                    "content": doc_data["content"],
                    "doc_type": doc_data["doc_type"],
                    "collection_id": collection_id,
                    "is_indexed": False,
                    "doc_metadata": json.dumps({"source": "seed-script"}),
                    "created_by": "seed-script",
                    "created_at": datetime.utcnow(),
                    "chunk_count": 0
                }
            )

            # Update collection document count
            if collection_id:
                session.execute(
                    text("UPDATE knowledge_collections SET document_count = document_count + 1 WHERE id = :id"),
                    {"id": collection_id}
                )

            created += 1

    session.commit()
    print(f"  Created {created} documents")


def seed_alerts(session):
    """Create test alerts."""
    print("Seeding test alerts...")

    # Check existing count
    existing_count = session.query(Alert).count()
    if existing_count >= len(ALERTS):
        print(f"  Alerts already seeded ({existing_count} exist)")
        return

    created = 0
    for alert_data in ALERTS:
        # Create alert with random time in past 2 hours
        minutes_ago = random.randint(5, 120)

        alert = Alert(
            alert_id=str(uuid.uuid4()),
            title=alert_data["title"],
            description=alert_data["description"],
            severity=alert_data["severity"],
            status=alert_data["status"],
            source=alert_data["source"],
            device_name=alert_data.get("device_name"),
            alert_type=alert_data.get("alert_type"),
            raw_data=alert_data.get("raw_data", {}),
            auto_triage=True,
            created_at=datetime.utcnow() - timedelta(minutes=minutes_ago)
        )
        session.add(alert)
        created += 1

    session.commit()
    print(f"  Created {created} alerts")


def seed_incidents(session):
    """Create test incidents."""
    print("Seeding test incidents...")

    existing_count = session.query(Incident).count()
    if existing_count >= len(INCIDENTS):
        print(f"  Incidents already seeded ({existing_count} exist)")
        return

    created = 0
    for inc_data in INCIDENTS:
        hours_ago = random.randint(1, 24)

        incident = Incident(
            incident_id=str(uuid.uuid4()),
            title=inc_data["title"],
            description=inc_data["description"],
            severity=inc_data["severity"],
            status=inc_data["status"],
            incident_type=inc_data.get("incident_type"),
            affected_devices=inc_data.get("affected_devices", []),
            root_cause=inc_data.get("root_cause"),
            created_at=datetime.utcnow() - timedelta(hours=hours_ago),
            created_by=inc_data.get("created_by", "seed-script")
        )
        session.add(incident)
        created += 1

    session.commit()
    print(f"  Created {created} incidents")


def main():
    """Main seeding function."""
    print("=" * 60)
    print("NetStacks Knowledge Base and Alert Seeder")
    print("=" * 60)

    session = get_session()

    try:
        seed_collections(session)
        seed_documents(session)
        seed_alerts(session)
        seed_incidents(session)

        print("=" * 60)
        print("Seeding complete!")
        print("=" * 60)

        # Summary using raw SQL
        doc_count = session.execute(text("SELECT COUNT(*) FROM knowledge_documents")).scalar()
        coll_count = session.execute(text("SELECT COUNT(*) FROM knowledge_collections")).scalar()
        alert_count = session.query(Alert).count()
        incident_count = session.query(Incident).count()

        print(f"\nDatabase Summary:")
        print(f"  - Collections: {coll_count}")
        print(f"  - Documents: {doc_count}")
        print(f"  - Alerts: {alert_count}")
        print(f"  - Incidents: {incident_count}")

    except Exception as e:
        print(f"\nError during seeding: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
