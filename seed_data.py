#!/usr/bin/env python3
"""
Seed data for NetStacks - Knowledge Base, Alerts, Incidents
"""
import uuid
from datetime import datetime, timedelta
import random

# Knowledge Documents
KNOWLEDGE_DOCUMENTS = [
    # BGP Documentation
    {
        "title": "BGP Troubleshooting Guide",
        "doc_type": "markdown",
        "source": "internal",
        "collection": "troubleshooting",
        "content": """# BGP Troubleshooting Guide

## Common BGP Issues and Resolution

### 1. BGP Neighbor Not Establishing

**Symptoms:**
- Neighbor state stuck in Active or Idle
- No routes being received

**Diagnostic Commands:**
```
show ip bgp summary
show ip bgp neighbors <ip>
show ip bgp neighbors <ip> received-routes
```

**Common Causes:**
1. **TCP Connectivity**: Ensure TCP port 179 is reachable
2. **AS Number Mismatch**: Verify remote-as configuration
3. **Router-ID Conflict**: Check for duplicate router-ids
4. **Authentication**: Verify MD5 password matches
5. **Update-Source**: Ensure correct source interface

**Resolution Steps:**
1. Verify TCP connectivity: `ping <neighbor_ip>`
2. Check for ACLs blocking port 179
3. Verify BGP configuration matches on both peers
4. Check authentication passwords
5. Clear BGP session: `clear ip bgp <neighbor_ip>`

### 2. BGP Routes Not Being Advertised

**Symptoms:**
- Routes in RIB but not in BGP table
- Neighbor not receiving expected prefixes

**Common Causes:**
1. Network statement missing
2. Route-map filtering outbound
3. Prefix not in routing table
4. AS-path filtering

### 3. BGP Route Flapping

**Symptoms:**
- Routes appearing and disappearing
- High CPU on router

**Resolution:**
1. Check physical layer stability
2. Implement route dampening
3. Increase hold timers
"""
    },
    {
        "title": "RFC 4271 - BGP-4 Protocol Summary",
        "doc_type": "markdown",
        "source": "RFC",
        "collection": "vendor-docs",
        "content": """# RFC 4271 - Border Gateway Protocol 4 (BGP-4)

## Overview
BGP-4 is the current exterior gateway protocol used to exchange routing information between autonomous systems.

## Key Concepts

### Message Types
1. **OPEN**: Establish BGP peering
2. **UPDATE**: Advertise or withdraw routes
3. **KEEPALIVE**: Maintain session
4. **NOTIFICATION**: Report errors

### Path Attributes
- **ORIGIN**: How the route was learned
- **AS_PATH**: List of AS numbers traversed
- **NEXT_HOP**: IP address to forward to
- **MED**: Multi-Exit Discriminator
- **LOCAL_PREF**: Local preference for path selection
- **COMMUNITY**: Route tagging for policy

### Best Path Selection Algorithm
1. Highest LOCAL_PREF
2. Shortest AS_PATH
3. Lowest ORIGIN type
4. Lowest MED
5. Prefer eBGP over iBGP
6. Lowest IGP metric to NEXT_HOP
7. Oldest route
8. Lowest router-id
"""
    },
    {
        "title": "OSPF Troubleshooting Runbook",
        "doc_type": "markdown",
        "source": "internal",
        "collection": "runbooks",
        "content": """# OSPF Troubleshooting Runbook

## Pre-Check Commands
```
show ip ospf neighbor
show ip ospf interface
show ip ospf database
show ip route ospf
```

## Issue: OSPF Adjacency Not Forming

### Step 1: Verify Basic Connectivity
- Ping neighbor IP
- Check interface status
- Verify OSPF enabled on interface

### Step 2: Check OSPF Parameters
Must match between neighbors:
- Area ID
- Hello/Dead timers
- Network type
- Authentication
- MTU (if mtu-ignore not set)

### Step 3: Verify Network Statements
Ensure interfaces are in correct area.

## Issue: OSPF Routes Missing

### Step 1: Check OSPF Database
```
show ip ospf database
```

### Step 2: Verify Route Redistribution
Check for proper redistribution config.

## Issue: OSPF Flapping

### Symptoms
- Frequent SPF calculations
- Adjacency drops

### Resolution
1. Check MTU mismatches
2. Verify stable Layer 1/2
3. Check for duplicate router-IDs
"""
    },
    {
        "title": "IS-IS Troubleshooting Guide",
        "doc_type": "markdown",
        "source": "internal",
        "collection": "troubleshooting",
        "content": """# IS-IS Troubleshooting Guide

## Diagnostic Commands

### Cisco IOS
```
show isis neighbors
show isis database
show isis topology
show clns interface
```

### Juniper
```
show isis adjacency
show isis database
show isis spf log
```

## Common Issues

### 1. IS-IS Adjacency Not Forming

**Check Points:**
1. Interface enabled for IS-IS
2. Area addresses match (Level 1)
3. MTU matches
4. Authentication matches
5. Level type compatible

### 2. Level 1/Level 2 Issues

**Level 1**: Same area only
**Level 2**: Inter-area routing
**Level 1-2**: Both

Ensure L1-L2 routers exist for inter-area routing.

### 3. Metric Issues

- IS-IS uses wide metrics (up to 16777215)
- Narrow metrics max at 63
- Ensure consistent metric style
"""
    },
    {
        "title": "MPLS and LDP Troubleshooting",
        "doc_type": "markdown",
        "source": "internal",
        "collection": "troubleshooting",
        "content": """# MPLS and LDP Troubleshooting Guide

## Diagnostic Commands

### Cisco IOS/IOS-XE
```
show mpls interfaces
show mpls ldp neighbor
show mpls ldp bindings
show mpls forwarding-table
```

### Juniper
```
show ldp neighbor
show ldp interface
show ldp database
show route table mpls.0
```

## Common Issues

### 1. LDP Session Not Establishing

**Check Points:**
1. TCP/646 connectivity
2. Router-ID reachability
3. Transport address configuration

### 2. Missing Labels

**Check Points:**
1. LDP session established
2. Prefix advertised with label
3. Liberal vs conservative label retention

## L3VPN Troubleshooting

### VRF Not Learning Routes

1. Check RT import/export
2. Verify VPNv4 BGP peering
3. Check RD configuration
"""
    },
    {
        "title": "Layer 2 Switching Troubleshooting",
        "doc_type": "markdown",
        "source": "internal",
        "collection": "troubleshooting",
        "content": """# Layer 2 Switching Troubleshooting Guide

## Diagnostic Commands

### VLAN Issues
```
show vlan brief
show interfaces trunk
show interfaces switchport
```

### Spanning Tree
```
show spanning-tree
show spanning-tree summary
show spanning-tree blockedports
```

## Common Issues

### 1. VLAN Not Propagating

**Check Points:**
1. VLAN exists on all switches
2. Trunk allows VLAN
3. Native VLAN matches

### 2. Spanning Tree Issues

**Symptoms:**
- Network loops
- Broadcast storms

**Check Points:**
1. Root bridge location
2. Port roles and states
3. PortFast on edge ports only

### 3. MAC Flapping

**Common Causes:**
- Layer 2 loop
- Dual-homed host
- VM migration
"""
    },
    {
        "title": "Network Incident Response Runbook",
        "doc_type": "markdown",
        "source": "internal",
        "collection": "runbooks",
        "content": """# Network Incident Response Runbook

## Severity Levels

| Level | Description | Response Time |
|-------|-------------|---------------|
| P1 | Critical | 15 minutes |
| P2 | High | 30 minutes |
| P3 | Medium | 2 hours |
| P4 | Low | Next business day |

## Initial Response Steps

### 1. Acknowledge Alert
- Log incident in ticketing system
- Notify on-call team

### 2. Initial Assessment
- Identify affected services
- Determine blast radius

### 3. Information Gathering
```
show interfaces status err-disabled
show ip route summary
show ip bgp summary
show logging last 100
```

## Escalation Procedures

### Tier 1 to Tier 2
- Unable to resolve within 30 minutes
- Requires configuration changes

### Tier 2 to Tier 3
- Complex routing issues
- Vendor engagement needed
"""
    },
    {
        "title": "Segment Routing Overview",
        "doc_type": "markdown",
        "source": "internal",
        "collection": "vendor-docs",
        "content": """# Segment Routing (SR) Overview

## Introduction
Segment Routing simplifies network operations by eliminating per-flow state.

## Key Concepts

### Segment Types
- **Prefix Segment**: Identifies a destination prefix
- **Adjacency Segment**: Identifies a specific link
- **Node Segment**: Identifies a specific node

### SR-MPLS vs SRv6
| Feature | SR-MPLS | SRv6 |
|---------|---------|------|
| Encapsulation | MPLS labels | IPv6 headers |
| Header size | Small | Larger |

## Configuration Examples

### Cisco IOS-XR
```
segment-routing
 global-block 16000 23999
router isis 1
 segment-routing mpls
```

## Traffic Engineering with SR-TE
- No RSVP signaling required
- Simplified operations
- Flexible traffic steering
"""
    },
]

# Alert Definitions
ALERTS = [
    {
        "title": "BGP Neighbor Down - core-rtr-01 to peer-rtr-01",
        "description": "BGP session with peer 10.0.1.1 (AS 65001) has transitioned to Idle state.",
        "severity": "critical",
        "status": "new",
        "source": "network-monitor",
        "device": "core-rtr-01",
        "alert_data": {"neighbor_ip": "10.0.1.1", "remote_as": "65001", "error": "Hold timer expired"}
    },
    {
        "title": "High CPU Utilization - dist-sw-03",
        "description": "CPU utilization has exceeded 85% threshold. Current: 92%",
        "severity": "warning",
        "status": "new",
        "source": "snmp-poller",
        "device": "dist-sw-03",
        "alert_data": {"metric": "cpu_utilization", "current_value": 92, "threshold": 85}
    },
    {
        "title": "Interface Down - core-rtr-02 Gi0/0/1",
        "description": "Interface GigabitEthernet0/0/1 has gone down.",
        "severity": "error",
        "status": "acknowledged",
        "source": "syslog",
        "device": "core-rtr-02",
        "alert_data": {"interface": "GigabitEthernet0/0/1", "current_state": "down"}
    },
    {
        "title": "OSPF Adjacency Flapping - edge-rtr-01",
        "description": "OSPF adjacency with 10.1.1.1 has flapped 5 times in 10 minutes.",
        "severity": "warning",
        "status": "new",
        "source": "network-monitor",
        "device": "edge-rtr-01",
        "alert_data": {"neighbor_ip": "10.1.1.1", "area": "0.0.0.0", "flap_count": 5}
    },
    {
        "title": "LDP Session Down - mpls-pe-01",
        "description": "LDP session with 10.255.0.2 has been lost.",
        "severity": "error",
        "status": "new",
        "source": "network-monitor",
        "device": "mpls-pe-01",
        "alert_data": {"neighbor_ip": "10.255.0.2", "session_state": "down"}
    },
    {
        "title": "Spanning Tree Topology Change - access-sw-12",
        "description": "Multiple spanning tree topology changes detected.",
        "severity": "warning",
        "status": "new",
        "source": "syslog",
        "device": "access-sw-12",
        "alert_data": {"vlan": 100, "tc_count": 15, "period_minutes": 5}
    },
    {
        "title": "Memory Utilization Critical - core-rtr-01",
        "description": "Memory utilization has exceeded critical threshold. Current: 95%",
        "severity": "critical",
        "status": "processing",
        "source": "snmp-poller",
        "device": "core-rtr-01",
        "alert_data": {"metric": "memory_utilization", "current_value": 95, "threshold": 90}
    },
    {
        "title": "BGP Prefix Limit Warning - edge-rtr-02",
        "description": "BGP neighbor 192.0.2.1 has reached 80% of maximum prefix limit.",
        "severity": "warning",
        "status": "new",
        "source": "network-monitor",
        "device": "edge-rtr-02",
        "alert_data": {"neighbor_ip": "192.0.2.1", "current_prefixes": 80000, "max_prefixes": 100000}
    },
]

# Incident Definitions
INCIDENTS = [
    {
        "title": "Core Network Outage - Primary Data Center",
        "description": "Multiple core routers experiencing BGP session failures.",
        "severity": "critical",
        "status": "investigating",
        "source": "auto-correlation",
        "incident_data": {"affected_devices": ["core-rtr-01", "core-rtr-02"], "impact": "Major"}
    },
    {
        "title": "Intermittent Packet Loss - WAN Circuit",
        "description": "Users reporting intermittent connectivity to remote sites.",
        "severity": "warning",
        "status": "investigating",
        "source": "user-report",
        "incident_data": {"packet_loss_percentage": 5, "affected_sites": ["remote-site-01"]}
    },
    {
        "title": "MPLS VPN Service Degradation",
        "description": "L3VPN customers reporting connectivity issues.",
        "severity": "error",
        "status": "identified",
        "source": "noc",
        "resolution": "Identified MTU mismatch on core links.",
        "incident_data": {"affected_vrfs": ["customer-a", "customer-b"]}
    },
    {
        "title": "Switch Stack Failure - Building A",
        "description": "Switch stack has lost member switch. Users affected.",
        "severity": "error",
        "status": "resolved",
        "source": "snmp-trap",
        "resolution": "Replaced failed switch. Stack reformed.",
        "incident_data": {"switch_stack": "bldg-a-stack-01", "failed_member": "Member 3"}
    },
]


def seed_knowledge(session):
    """Seed knowledge documents"""
    from models import KnowledgeDocument, KnowledgeCollection

    # Get or create collections
    collections = {}
    for coll_name in ["runbooks", "vendor-docs", "troubleshooting", "network-topology"]:
        coll = session.query(KnowledgeCollection).filter_by(name=coll_name).first()
        if not coll:
            coll = KnowledgeCollection(name=coll_name, description=f"{coll_name.replace('-', ' ').title()}")
            session.add(coll)
            session.flush()
        collections[coll_name] = coll.id

    # Check existing documents
    existing = session.query(KnowledgeDocument.title).all()
    existing_titles = {t[0] for t in existing}

    added = 0
    for doc in KNOWLEDGE_DOCUMENTS:
        if doc["title"] not in existing_titles:
            new_doc = KnowledgeDocument(
                doc_id=str(uuid.uuid4()),
                title=doc["title"],
                content=doc["content"],
                doc_type=doc["doc_type"],
                source=doc["source"],
                collection_id=collections.get(doc["collection"]),
                is_indexed=False,
                doc_metadata={"seed": True},
                created_at=datetime.utcnow()
            )
            session.add(new_doc)
            added += 1

    session.commit()
    print(f"Added {added} knowledge documents")


def seed_alerts(session):
    """Seed alerts"""
    from models import Alert

    existing = session.query(Alert).count()
    if existing >= 5:
        print(f"Alerts already seeded ({existing} exist)")
        return

    added = 0
    for alert_data in ALERTS:
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            title=alert_data["title"],
            description=alert_data["description"],
            severity=alert_data["severity"],
            status=alert_data["status"],
            source=alert_data["source"],
            device=alert_data.get("device"),
            alert_data=alert_data.get("alert_data", {}),
            created_at=datetime.utcnow() - timedelta(minutes=random.randint(5, 120))
        )
        session.add(alert)
        added += 1

    session.commit()
    print(f"Added {added} alerts")


def seed_incidents(session):
    """Seed incidents"""
    from models import Incident

    existing = session.query(Incident).count()
    if existing >= 3:
        print(f"Incidents already seeded ({existing} exist)")
        return

    added = 0
    for inc_data in INCIDENTS:
        incident = Incident(
            incident_id=str(uuid.uuid4()),
            title=inc_data["title"],
            description=inc_data["description"],
            severity=inc_data["severity"],
            status=inc_data["status"],
            source=inc_data["source"],
            resolution=inc_data.get("resolution"),
            incident_data=inc_data.get("incident_data", {}),
            created_at=datetime.utcnow() - timedelta(hours=random.randint(1, 48)),
            resolved_at=datetime.utcnow() if inc_data["status"] == "resolved" else None
        )
        session.add(incident)
        added += 1

    session.commit()
    print(f"Added {added} incidents")


if __name__ == "__main__":
    from models import get_engine, get_session

    engine = get_engine()
    session = get_session(engine)

    try:
        print("Seeding knowledge base...")
        seed_knowledge(session)

        print("Seeding alerts...")
        seed_alerts(session)

        print("Seeding incidents...")
        seed_incidents(session)

        print("Done!")
    except Exception as e:
        print(f"Error: {e}")
        session.rollback()
        raise
    finally:
        session.close()
