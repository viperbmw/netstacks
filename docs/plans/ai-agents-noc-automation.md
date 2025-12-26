# NetStacks AI Agent Enhancement Plan

## Overview

Transform NetStacks into an AI-powered NOC automation platform that replaces Tier 1/2 network operations using specialized AI agents with orchestration, RAG knowledge base, and multi-system integration.

---

## Architecture Summary

**Approach**: Microservices architecture for massive scale (thousands of agents, tens of thousands of devices).

**Scale Targets**:
- **Agents**: Scale to thousands of concurrent agent instances
- **Devices**: Auto-scale to 10,000+ managed devices
- **MOPs**: Bi-directional integration (agents in MOPs, MOPs in agents)

**Key Components**:
- **Microservices**: Separate services for agents, devices, knowledge, alerts, approvals
- **Message Bus**: Redis Streams / RabbitMQ for async communication
- **Multi-agent system** with ReAct pattern (Reason → Act → Observe)
- **Specialized agents**: Triage, BGP, ISIS, OSPF, STP, Layer2, Remediation, Custom
- **Vector database** (pgvector) for RAG knowledge base
- **Tool registry** with device service integration, SNMP, API, MCP support
- **MOP ↔ Agent integration**: Agents as MOP step types, agents can invoke MOPs
- **Risk-based approval workflow**
- **Real-time WebSocket** chat interface
- **Docker Swarm** for production orchestration and auto-scaling

---

## Microservices Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DOCKER SWARM CLUSTER                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Traefik   │  │   Traefik   │  │   Traefik   │  │   Traefik   │        │
│  │ (Load Bal.) │  │ (Load Bal.) │  │ (Load Bal.) │  │ (Load Bal.) │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         └────────────────┴────────────────┴────────────────┘                │
│                                    │                                         │
│  ┌─────────────────────────────────┴─────────────────────────────────┐      │
│  │                         API GATEWAY                                │      │
│  │                    (Authentication, Routing)                       │      │
│  └─────────────────────────────────┬─────────────────────────────────┘      │
│                                    │                                         │
│  ┌──────────────────────────┬──────┴──────┬──────────────────────────┐      │
│  │                          │             │                          │      │
│  ▼                          ▼             ▼                          ▼      │
│ ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│ │  NETSTACKS │  │   AGENT    │  │  KNOWLEDGE │  │   ALERT    │             │
│ │    CORE    │  │  SERVICE   │  │   SERVICE  │  │  SERVICE   │             │
│ │  (Flask)   │  │  (FastAPI) │  │  (FastAPI) │  │  (FastAPI) │             │
│ │            │  │            │  │            │  │            │             │
│ │ - UI       │  │ - Dispatch │  │ - RAG      │  │ - Webhooks │             │
│ │ - Templates│  │ - Sessions │  │ - Vectors  │  │ - Polling  │             │
│ │ - Stacks   │  │ - Chat WS  │  │ - Search   │  │ - Routing  │             │
│ │ - MOPs     │  │            │  │            │  │            │             │
│ │ - Settings │  │ Replicas:  │  │ Replicas:  │  │ Replicas:  │             │
│ │            │  │ 3-50+      │  │ 2-10       │  │ 2-5        │             │
│ └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘             │
│       │               │               │               │                     │
│  ┌────┴───────────────┴───────────────┴───────────────┴────┐               │
│  │                     REDIS STREAMS                        │               │
│  │         (Message Bus, Task Queue, Pub/Sub)               │               │
│  └────┬───────────────┬───────────────┬───────────────┬────┘               │
│       │               │               │               │                     │
│       ▼               ▼               ▼               ▼                     │
│ ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│ │   DEVICE   │  │   AGENT    │  │  APPROVAL  │  │    MOP     │             │
│ │  WORKERS   │  │  WORKERS   │  │  SERVICE   │  │  WORKERS   │             │
│ │  (Celery)  │  │  (Celery)  │  │  (FastAPI) │  │  (Celery)  │             │
│ │            │  │            │  │            │  │            │             │
│ │ - SSH/Net  │  │ - LLM Exec │  │ - Risk     │  │ - Execute  │             │
│ │ - SNMP     │  │ - Tool Run │  │ - Approve  │  │ - Steps    │             │
│ │ - Netbox   │  │ - ReAct    │  │ - Notify   │  │ - Agents   │             │
│ │            │  │            │  │            │  │            │             │
│ │ Replicas:  │  │ Replicas:  │  │ Replicas:  │  │ Replicas:  │             │
│ │ 10-100+    │  │ 10-100+    │  │ 2-5        │  │ 5-20       │             │
│ └────────────┘  └────────────┘  └────────────┘  └────────────┘             │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                         DATA LAYER                                 │      │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │      │
│  │  │ PostgreSQL  │  │ PostgreSQL  │  │   Redis     │                │      │
│  │  │  (Primary)  │  │  (pgvector) │  │  Cluster    │                │      │
│  │  │             │  │             │  │             │                │      │
│  │  │ - Devices   │  │ - Embeddings│  │ - Cache     │                │      │
│  │  │ - Agents    │  │ - Documents │  │ - Sessions  │                │      │
│  │  │ - Actions   │  │             │  │ - Streams   │                │      │
│  │  │ - Incidents │  │             │  │             │                │      │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Service Breakdown

| Service | Technology | Scaling | Purpose |
|---------|------------|---------|---------|
| **netstacks-core** | Flask | 2-5 | UI, templates, stacks, MOPs, settings |
| **agent-service** | FastAPI | 3-50+ | Agent dispatch, sessions, WebSocket chat |
| **agent-workers** | Celery | 10-100+ | LLM execution, ReAct loops, tool calls |
| **device-workers** | Celery | 10-100+ | SSH/Netmiko, SNMP, Netbox queries |
| **knowledge-service** | FastAPI | 2-10 | RAG, vector search, embeddings |
| **alert-service** | FastAPI | 2-5 | Webhook intake, polling, alert routing |
| **approval-service** | FastAPI | 2-5 | Risk assessment, approval workflow |
| **mop-workers** | Celery | 5-20 | MOP execution with agent step support |

### Inter-Service Communication

```
Redis Streams (async messaging):
├── alerts.incoming          → Alert service → Agent dispatcher
├── agents.tasks.{type}      → Agent workers (BGP, ISIS, etc.)
├── agents.results           → Agent service (session updates)
├── agents.handoff           → Agent-to-agent transfers
├── devices.commands         → Device workers
├── devices.results          → Tool callbacks
├── mops.execute             → MOP workers
├── mops.agent_step          → Agent invocation from MOPs
├── approvals.pending        → Approval service
└── approvals.decisions      → Agent workers (resume execution)
```

---

## Database Schema (New Tables)

### Core Agent Tables
```
agents              - Agent definitions and configuration
agent_sessions      - Conversation sessions (user or alert-triggered)
agent_actions       - Audit log of all agent thoughts/actions/observations
```

### Tool System
```
agent_tools         - Built-in and custom tool definitions
mcp_servers         - MCP server connections and discovered tools
```

### Knowledge Base
```
knowledge_collections - Logical groupings (BGP Runbooks, Vendor Docs, etc.)
knowledge_documents   - Documents with metadata
knowledge_embeddings  - Vector embeddings (pgvector) for RAG
```

### Alert & Incident Management
```
alerts              - Incoming alerts from monitoring systems
incidents           - Grouped/correlated incidents
alert_sources       - Webhook/polling source configurations
```

### Approval Workflow
```
approval_requests   - Pending approvals for high-risk actions
```

### LLM Configuration
```
llm_providers       - Provider configs (Anthropic, OpenRouter)
```

---

## Directory Structure (Microservices)

```
/home/cwdavis/netstacks/                    # EXISTING - Enhanced
├── app.py                                  # Flask UI + existing functionality
├── tasks.py                                # Existing Celery tasks (device ops)
├── mop_engine.py                           # Add invoke_agent step type
├── templates/                              # Add agent/alert UI pages
│   ├── agents.html
│   ├── agent_chat.html
│   ├── alerts.html
│   ├── incidents.html
│   └── knowledge.html
├── static/js/
│   ├── agents.js
│   ├── agent-chat.js                       # WebSocket chat client
│   └── ...
└── routes/
    └── agent_proxy.py                      # Proxy routes to agent-service

/home/cwdavis/netstacks-ai/                 # NEW - AI Services
├── docker-compose.yml                      # All AI microservices
├── shared/                                 # Shared code library
│   ├── models/                             # SQLAlchemy models
│   ├── messaging/                          # Redis stream utilities
│   └── auth/                               # JWT validation
│
├── services/
│   ├── agent-service/                      # FastAPI - Agent orchestration
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── routes/
│   │   │   │   ├── agents.py               # CRUD, list, status
│   │   │   │   ├── sessions.py             # Chat sessions
│   │   │   │   └── websocket.py            # Real-time chat
│   │   │   ├── dispatch/
│   │   │   │   ├── dispatcher.py           # Route to workers
│   │   │   │   └── scheduler.py            # Persistent agents
│   │   │   └── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── agent-worker/                       # Celery - Agent execution
│   │   ├── app/
│   │   │   ├── worker.py
│   │   │   ├── agents/
│   │   │   │   ├── base.py                 # ReAct loop
│   │   │   │   ├── triage.py
│   │   │   │   ├── bgp.py
│   │   │   │   ├── isis.py
│   │   │   │   ├── ospf.py
│   │   │   │   ├── stp.py
│   │   │   │   ├── layer2.py
│   │   │   │   ├── remediation.py
│   │   │   │   └── custom.py
│   │   │   ├── tools/
│   │   │   │   ├── registry.py
│   │   │   │   ├── device.py               # Calls device-worker
│   │   │   │   ├── knowledge.py            # Calls knowledge-service
│   │   │   │   ├── mop.py                  # execute_mop tool
│   │   │   │   ├── escalate.py
│   │   │   │   └── handoff.py
│   │   │   ├── llm/
│   │   │   │   ├── anthropic.py
│   │   │   │   └── openrouter.py
│   │   │   └── prompts/
│   │   └── Dockerfile
│   │
│   ├── device-worker/                      # Celery - Device operations
│   │   ├── app/
│   │   │   ├── worker.py
│   │   │   ├── tasks/
│   │   │   │   ├── ssh.py                  # Netmiko operations
│   │   │   │   ├── snmp.py                 # pysnmp operations
│   │   │   │   └── netbox.py               # NetBox queries
│   │   │   └── device_service.py           # Connection management
│   │   └── Dockerfile
│   │
│   ├── knowledge-service/                  # FastAPI - RAG
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── routes/
│   │   │   │   ├── documents.py
│   │   │   │   ├── collections.py
│   │   │   │   └── search.py
│   │   │   ├── embeddings/
│   │   │   │   ├── generator.py
│   │   │   │   └── chunking.py
│   │   │   └── vector_store.py
│   │   └── Dockerfile
│   │
│   ├── alert-service/                      # FastAPI - Alert intake
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── routes/
│   │   │   │   ├── webhooks.py
│   │   │   │   ├── polling.py
│   │   │   │   └── incidents.py
│   │   │   ├── parsers/
│   │   │   │   ├── solarwinds.py
│   │   │   │   ├── prometheus.py
│   │   │   │   └── generic.py
│   │   │   └── normalizer.py
│   │   └── Dockerfile
│   │
│   ├── approval-service/                   # FastAPI - Approvals
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── routes/
│   │   │   │   ├── approvals.py
│   │   │   │   └── notifications.py
│   │   │   └── risk_engine.py
│   │   └── Dockerfile
│   │
│   └── mop-worker/                         # Celery - MOP execution
│       ├── app/
│       │   ├── worker.py
│       │   ├── mop_engine.py               # Extended with invoke_agent
│       │   └── step_types/
│       │       ├── invoke_agent.py
│       │       └── ...
│       └── Dockerfile
│
└── knowledge/                              # Default knowledge content
    ├── runbooks/
    ├── vendor_docs/
    └── protocols/
```

---

## Agent Types & Capabilities

| Agent | Purpose | Key Tools |
|-------|---------|-----------|
| **Triage** | Alert classification, routing to specialists | classify_alert, get_device_context, handoff |
| **BGP** | BGP troubleshooting (peers, routes, AS-PATH) | show_bgp_*, clear_bgp_neighbor, knowledge_search |
| **ISIS** | IS-IS adjacencies, LSP analysis | show_isis_*, show_ip_route |
| **OSPF** | OSPF neighbor/route issues | show_ip_ospf_*, show_ip_route |
| **STP** | Spanning tree, loops, root issues | show_spanning-tree, show_mac |
| **Layer2** | Interface, VLAN, MAC issues | show_interface, show_vlan, show_mac |
| **Remediation** | Apply fixes (with approval) | config_template, rollback, apply_config |
| **Custom** | User-defined behavior | User-selected tools + knowledge |

---

## Tool Registry

### Built-in Tools (Microservices Communication)

Agent tools communicate with other services via **Redis Streams** - NO direct SSH/device logic in agent-worker.

| Tool | Calls Service | Risk | Description |
|------|---------------|------|-------------|
| `device_show` | device-worker | Low | Execute show commands (TextFSM/Genie parsing) |
| `device_config` | device-worker | High | Push configuration (template or lines) |
| `device_commands` | device-worker | Low-High | Run multiple commands |
| `device_validate` | device-worker | Low | Validate config patterns |
| `device_backup` | device-worker | Low | Backup device config |
| `snmp_query` | device-worker | Low | SNMP GET/WALK |
| `netbox_lookup` | device-worker | Low | Query NetBox for device/circuit info |
| `knowledge_search` | knowledge-service | Low | Vector similarity search |
| `execute_mop` | mop-worker | High | Execute a MOP workflow |
| `escalate` | approval-service | Low | Create human escalation |
| `handoff` | agent-service | Low | Transfer to specialist agent |
| `create_incident` | alert-service | Medium | Create incident ticket |

### Tool Implementation Pattern (Async via Redis Streams)
```python
# agent-worker/app/tools/device.py
class DeviceShowTool(BaseTool):
    name = "device_show"
    description = "Execute show command on network device"
    risk_level = "low"

    async def execute(self, device_name: str, command: str, parse: bool = True):
        # Create unique request ID
        request_id = str(uuid.uuid4())

        # Send request to device-worker via Redis Stream
        await redis.xadd('devices.commands', {
            'request_id': request_id,
            'action': 'get_config',
            'device_name': device_name,
            'command': command,
            'use_textfsm': parse,
            'use_genie': parse,
            'reply_to': f'agents.results.{self.session_id}'
        })

        # Wait for response on reply stream
        result = await self.wait_for_response(request_id, timeout=300)
        return result
```

### Service-to-Service Flow
```
Agent Tool Call:
┌──────────────┐     Redis Stream      ┌────────────────┐
│ Agent Worker │ ──devices.commands──▶ │ Device Worker  │
│              │                       │                │
│ (waiting...) │ ◀──agents.results──── │ (SSH/SNMP)     │
└──────────────┘                       └────────────────┘
```

### MCP Server Integration
- Configure MCP servers in Settings UI
- Auto-discover tools from connected servers
- MCP tools appear in tool selection for custom agents

### Custom Tools
- Define HTTP-based tools (REST API calls)
- Define command templates (command + expected parsing)
- Set risk levels and input schemas
- **All device operations route through device-workers service**

---

## MOP ↔ Agent Integration

### Agents as MOP Step Types

Add new step type `invoke_agent` to MOP engine:

```yaml
# Example MOP with agent steps
name: "BGP Maintenance Window"
description: "AI-assisted BGP maintenance"
devices:
  - core-rtr-01
  - core-rtr-02

steps:
  - name: "Pre-check with AI Agent"
    type: invoke_agent
    agent_type: bgp
    prompt: "Analyze current BGP state and identify any issues before maintenance"
    wait_for_completion: true
    timeout: 300
    on_failure: abort_maintenance

  - name: "Apply Configuration"
    type: deploy_stack
    stack_id: "bgp-maintenance-config"
    on_success: post_check

  - name: "Post-check with AI Agent"
    id: post_check
    type: invoke_agent
    agent_type: bgp
    prompt: "Verify BGP convergence and confirm all neighbors are established"
    context_from_step: "Pre-check with AI Agent"  # Pass previous analysis
    on_failure: rollback_with_agent

  - name: "AI-Assisted Rollback"
    id: rollback_with_agent
    type: invoke_agent
    agent_type: remediation
    prompt: "BGP post-check failed. Analyze the issue and perform rollback"
    allow_config_changes: true
```

### Agents Invoking MOPs

Agents can execute MOPs as a tool:

```python
# Agent tool for MOP execution
class ExecuteMOPTool(BaseTool):
    name = "execute_mop"
    description = "Execute a Method of Procedure (MOP) workflow"
    risk_level = "high"  # MOPs can make changes

    async def execute(self, mop_id: str, variables: dict = None):
        # Send to MOP workers via Redis stream
        await redis.xadd('mops.execute', {
            'mop_id': mop_id,
            'variables': json.dumps(variables),
            'triggered_by': 'agent',
            'agent_session_id': self.session_id
        })

        # Wait for completion or return task_id
        result = await self.wait_for_mop_completion(mop_id)
        return result
```

### Bi-directional Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     MOP ↔ AGENT INTEGRATION                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  MOP INVOKING AGENT:                                            │
│  ┌─────────┐    invoke_agent    ┌─────────────┐                 │
│  │   MOP   │ ──────step──────▶ │   Agent     │                 │
│  │ Worker  │                    │   Worker    │                 │
│  │         │ ◀────result─────── │   (BGP)     │                 │
│  └─────────┘                    └─────────────┘                 │
│                                                                  │
│  AGENT INVOKING MOP:                                            │
│  ┌─────────────┐  execute_mop   ┌─────────┐                     │
│  │   Agent     │ ────tool────▶ │   MOP   │                     │
│  │   Worker    │                │  Worker │                     │
│  │ (Remediate) │ ◀───result──── │         │                     │
│  └─────────────┘                └─────────┘                     │
│                                                                  │
│  NESTED EXAMPLE:                                                 │
│  User triggers MOP                                               │
│    → MOP step: invoke_agent (triage)                            │
│      → Agent decides: need BGP specialist                        │
│        → Agent handoff to BGP agent                              │
│          → BGP agent: execute_mop (bgp-remediation-mop)         │
│            → MOP completes rollback                              │
│          ← BGP agent reports success                             │
│        ← Handoff complete                                        │
│      ← Triage reports resolution                                 │
│    ← MOP step complete                                           │
│  MOP continues to next step                                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Risk & Approval Workflow

| Risk Level | Behavior | Examples |
|------------|----------|----------|
| **LOW** | Auto-approve | Show commands, SNMP reads, searches |
| **MEDIUM** | 5-min delay + notification | Interface status change, soft clears |
| **HIGH** | Requires approval | Config changes, hard resets |
| **CRITICAL** | Requires 2+ approvals | Routing changes, ACLs, core devices |

Approvals start in-app, designed for future Slack/Teams/Email integration.

---

## External Integrations

### Alert Intake
- **Webhook**: `/api/webhooks/{source}` endpoints for SolarWinds, Prometheus, etc.
- **Polling**: Configurable polling intervals for systems without webhooks
- **Field Mapping**: Normalize source-specific fields to common schema

### Device Access
- **SSH/Netmiko**: Existing infrastructure (tasks.py)
- **SNMP**: New pysnmp integration for polling
- **Netbox**: Enhanced queries for device context

---

## Frontend Pages (Flask/Jinja2)

| Page | Route | Description |
|------|-------|-------------|
| Agents | /agents | Agent list, create, enable/disable |
| Agent Detail | /agents/{id} | Config, activity log, statistics |
| Agent Chat | /agents/{id}/chat | Real-time chat with agent |
| Alerts | /alerts | Alert dashboard, status, assignment |
| Incidents | /incidents | Incident list, timeline, resolution |
| Knowledge | /knowledge | Document upload, collections, search |
| Approvals | /approvals | Pending approval queue |
| AI Settings | /settings/ai | LLM providers, API keys, defaults |
| Tools | /settings/tools | Tool management, MCP servers |

### Real-time Updates
- Flask-SocketIO for WebSocket support
- Stream agent actions to chat UI
- Live alert/incident updates

---

## Docker Swarm Configuration

Update `docker-compose.yml` for Swarm:

```yaml
services:
  netstacks:
    deploy:
      replicas: 2
      update_config:
        parallelism: 1
        delay: 10s

  celery-worker:
    command: celery -A tasks worker -Q device_tasks,agent_tasks,default
    deploy:
      replicas: 3  # Scale based on load

  postgres:
    image: pgvector/pgvector:pg15  # pgvector for RAG
    deploy:
      placement:
        constraints: [node.role == manager]

networks:
  netstacks-network:
    driver: overlay
```

---

## Implementation Phases

### Phase 1: Microservices Foundation
- [ ] Create `/home/cwdavis/netstacks-ai/` project structure
- [ ] Shared library (models, messaging, auth)
- [ ] Docker Compose for all services
- [ ] Redis Streams messaging utilities
- [ ] PostgreSQL schema migrations (all new tables)
- [ ] Service-to-service authentication

**Deliverables**:
- `netstacks-ai/shared/` - Common code
- `netstacks-ai/docker-compose.yml` - All services defined
- Database migrations for agents, sessions, actions, tools, knowledge, alerts, incidents, approvals

### Phase 2: Device Worker Service
- [ ] Celery worker for device operations
- [ ] Port existing `tasks.py` logic (get_config, set_config, run_commands, etc.)
- [ ] Add SNMP polling (pysnmp)
- [ ] Redis Stream consumer for `devices.commands`
- [ ] Response publishing to `devices.results`
- [ ] Device connection pooling for scale

**Deliverables**:
- `netstacks-ai/services/device-worker/`
- Consumes from `devices.commands`, publishes to reply streams
- Handles 10,000+ devices with connection management

### Phase 3: Knowledge Service
- [ ] FastAPI service for RAG
- [ ] pgvector setup and embeddings table
- [ ] Document upload/processing API
- [ ] Chunking strategies (runbooks, vendor docs, protocols)
- [ ] Embedding generation (async workers)
- [ ] Vector similarity search API
- [ ] REST endpoints for agent tools

**Deliverables**:
- `netstacks-ai/services/knowledge-service/`
- `/api/knowledge/search` - Vector search endpoint
- `/api/knowledge/documents` - CRUD operations

### Phase 4: Agent Service & Workers
- [ ] FastAPI service for agent orchestration
- [ ] Agent CRUD API
- [ ] Session management
- [ ] WebSocket endpoint for real-time chat
- [ ] Agent dispatcher (route to workers by type)
- [ ] Celery workers for agent execution
- [ ] BaseAgent with ReAct loop
- [ ] LLM clients (Anthropic + OpenRouter)
- [ ] Tool registry and base tool class

**Deliverables**:
- `netstacks-ai/services/agent-service/` - API + WebSocket
- `netstacks-ai/services/agent-worker/` - Celery execution
- Consumes from `agents.tasks.*`, publishes actions/results

### Phase 5: Specialized Agents
- [ ] TriageAgent with alert classification
- [ ] BGPAgent with protocol-specific prompts
- [ ] ISISAgent, OSPFAgent
- [ ] STPAgent, Layer2Agent
- [ ] Agent handoff via Redis Streams
- [ ] System prompts tuned per agent type

**Deliverables**:
- `agent-worker/app/agents/triage.py`, `bgp.py`, `isis.py`, etc.
- `agent-worker/app/prompts/` - System prompts
- Handoff tool publishing to `agents.handoff` stream

### Phase 6: Alert Service
- [ ] FastAPI service for alert intake
- [ ] Webhook endpoints (`/api/webhooks/{source}`)
- [ ] Polling service for SolarWinds, etc.
- [ ] Alert normalization and parsing
- [ ] Incident CRUD and linking
- [ ] Route alerts to agent dispatcher

**Deliverables**:
- `netstacks-ai/services/alert-service/`
- Publishes to `alerts.incoming` stream
- SolarWinds, Prometheus, generic parsers

### Phase 7: Approval Service
- [ ] FastAPI service for approvals
- [ ] Risk assessment engine
- [ ] Approval request API
- [ ] Timeout handling
- [ ] Notification hooks (in-app, future: Slack/Teams)
- [ ] Agent pause/resume on approval

**Deliverables**:
- `netstacks-ai/services/approval-service/`
- Consumes `approvals.pending`, publishes `approvals.decisions`
- Agent workers pause and resume on approval

### Phase 8: MOP Worker & Agent Integration
- [ ] Celery worker for MOP execution
- [ ] Port existing `mop_engine.py` with enhancements
- [ ] Add `invoke_agent` step type
- [ ] `execute_mop` tool for agents
- [ ] Bi-directional MOP ↔ Agent communication

**Deliverables**:
- `netstacks-ai/services/mop-worker/`
- MOPs can invoke agents as steps
- Agents can execute MOPs as tools

### Phase 9: NetStacks Core Integration
- [ ] Add agent/alert/knowledge pages to Flask UI
- [ ] Proxy routes to AI services
- [ ] WebSocket client for agent chat
- [ ] Settings UI for LLM providers, MCP servers
- [ ] Custom tool and agent creation UI

**Deliverables**:
- `netstacks/templates/agents.html`, `agent_chat.html`, `alerts.html`, etc.
- `netstacks/static/js/agent-chat.js` - WebSocket client
- `netstacks/routes/agent_proxy.py` - API proxy

### Phase 10: Custom Agents & MCP
- [ ] CustomAgent framework
- [ ] Agent prompt editor UI
- [ ] MCP client implementation
- [ ] MCP server management UI
- [ ] Tool discovery from MCP servers
- [ ] Custom tool definition UI

**Deliverables**:
- `agent-worker/app/agents/custom.py`
- `agent-worker/app/tools/mcp.py`
- Settings pages for MCP and custom tools

### Phase 11: Docker Swarm Production
- [ ] Swarm-ready docker-compose.yml
- [ ] Traefik load balancer configuration
- [ ] Service replicas and scaling rules
- [ ] Health checks for all services
- [ ] Logging aggregation (ELK/Loki)
- [ ] Metrics collection (Prometheus)
- [ ] Auto-scaling policies

**Deliverables**:
- `netstacks-ai/docker-compose.swarm.yml`
- Production deployment documentation
- Monitoring dashboards

---

## Critical Files to Modify

| File | Changes |
|------|---------|
| `/home/cwdavis/netstacks/app.py` | Register new blueprints, add SocketIO |
| `/home/cwdavis/netstacks/tasks.py` | Add agent/embedding/polling tasks |
| `/home/cwdavis/netstacks/database_postgres.py` | Add all new table operations |
| `/home/cwdavis/netstacks/docker-compose.yml` | Swarm config, pgvector image |
| `/home/cwdavis/netstacks/templates/base.html` | Add new nav items |
| `/home/cwdavis/netstacks/static/css/style.css` | Chat UI styles |

---

## Environment Variables (New)

```bash
# LLM Configuration
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...
DEFAULT_LLM_PROVIDER=anthropic
DEFAULT_LLM_MODEL=claude-sonnet-4-20250514

# Agent Configuration
MAX_CONCURRENT_AGENTS=10
AGENT_TASK_TIMEOUT=600
APPROVAL_TIMEOUT_MINUTES=30

# Knowledge Base
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536
```

---

## Questions Addressed

1. **Architecture**: Microservices for scale (thousands of agents, 10K+ devices)
2. **Integrations**: SSH, SNMP, SolarWinds, Netbox, MCP servers, custom tools
3. **UI**: Flask/Jinja2 consistent with existing, WebSocket for real-time chat
4. **Orchestration**: Docker Swarm for production auto-scaling
5. **Alert Intake**: Both webhooks and polling
6. **LLM Providers**: Anthropic + OpenRouter
7. **Approvals**: In-app first, designed for future multi-channel
8. **Scope**: Full implementation (11 phases)
9. **Knowledge**: Support all document types (runbooks, vendor docs, internal procedures)
10. **Autonomy**: Graduated - start diagnose-only, add execution per-agent as trust builds
11. **MOP Integration**: Bi-directional - agents as MOP steps, agents can invoke MOPs
12. **Device Ops**: Use existing NetStacks task patterns via device-worker service

---

## Agent Autonomy Model

| Agent | Initial Mode | Can Upgrade To |
|-------|--------------|----------------|
| Triage | Diagnose + Route | - |
| BGP/ISIS/OSPF/STP/L2 | Diagnose + Recommend | Execute (with approval) |
| Remediation | Diagnose + Recommend | Execute (with approval) |
| Custom | User-configured | User-configured |

Execution capability enabled per-agent in settings after confidence is established.

---

## Next Steps

Ready to begin implementation with Phase 1: Core Infrastructure.
