# services/ai/app/routes/agents.py
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import uuid
import logging

from netstacks_core.db import get_session, Agent as AgentModel
from netstacks_core.auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter()


class AgentBase(BaseModel):
    name: Optional[str] = None
    agent_name: Optional[str] = None  # Frontend sends agent_name
    agent_type: str
    description: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: List[str] = []
    is_active: bool = False

    @property
    def resolved_name(self) -> str:
        """Return name or agent_name, preferring name if both provided."""
        return self.name or self.agent_name or ""


class AgentCreate(AgentBase):
    pass


class AgentResponse(AgentBase):
    agent_id: str
    status: str = "idle"
    session_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class CustomToolCreate(BaseModel):
    name: str
    category: str = "general"
    execution_type: str = "python"
    description: str
    parameters: dict = {}
    implementation: Optional[str] = None


class MCPServerCreate(BaseModel):
    name: str
    transport: str = "stdio"
    endpoint: str
    description: Optional[str] = None
    env: dict = {}


# In-memory storage (will be moved to DB later)
_custom_tools = []
_mcp_servers = []


# ============================================================================
# Static routes MUST be defined BEFORE dynamic /{agent_id} routes
# ============================================================================

@router.get("/types/available")
async def get_agent_types(user=Depends(get_current_user)):
    """Get available agent types."""
    return {
        "types": [
            {"id": "triage", "name": "Triage Agent", "description": "Initial alert processing"},
            {"id": "bgp", "name": "BGP Specialist", "description": "BGP troubleshooting"},
            {"id": "ospf", "name": "OSPF Specialist", "description": "OSPF troubleshooting"},
            {"id": "general", "name": "General Purpose", "description": "General network tasks"},
        ]
    }


@router.get("/tools")
@router.get("/tools/available")
async def get_available_tools(user=Depends(get_current_user)):
    """Get tools available for agents."""
    return {
        "tools": [
            {"name": "show_command", "category": "device", "risk": "low"},
            {"name": "get_device_config", "category": "device", "risk": "low"},
            {"name": "search_knowledge", "category": "knowledge", "risk": "low"},
            {"name": "get_platform_stats", "category": "platform", "risk": "low"},
            {"name": "create_incident", "category": "incident", "risk": "medium"},
        ]
    }


@router.get("/stats")
async def get_agent_stats(user=Depends(get_current_user)):
    """Get agent statistics."""
    session = get_session()
    try:
        from sqlalchemy import func
        from netstacks_core.db import AgentSession

        # Get sessions created today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        sessions_today = session.query(func.count(AgentSession.session_id)).filter(
            AgentSession.started_at >= today_start
        ).scalar() or 0

        # Get total sessions
        total_sessions = session.query(func.count(AgentSession.session_id)).scalar() or 0

        # Get active agents count
        active_agents = session.query(func.count(AgentModel.agent_id)).filter(
            AgentModel.is_enabled == True
        ).scalar() or 0

        return {
            "success": True,
            "sessions_today": sessions_today,
            "total_sessions": total_sessions,
            "active_agents": active_agents,
        }
    finally:
        session.close()


# ============================================================================
# Custom Tools Endpoints (static routes - must be before /{agent_id})
# ============================================================================

@router.get("/custom-tools", response_model=dict)
async def list_custom_tools(user=Depends(get_current_user)):
    """List all custom tools."""
    return {
        "success": True,
        "tools": _custom_tools
    }


@router.post("/custom-tools", response_model=dict)
async def create_custom_tool(tool: CustomToolCreate, user=Depends(get_current_user)):
    """Create a custom tool."""
    # Check for duplicate name
    if any(t["name"] == tool.name for t in _custom_tools):
        raise HTTPException(status_code=400, detail="Tool name already exists")

    new_tool = {
        "id": str(uuid.uuid4()),
        "name": tool.name,
        "category": tool.category,
        "execution_type": tool.execution_type,
        "description": tool.description,
        "parameters": tool.parameters,
        "implementation": tool.implementation,
        "is_active": True,
        "created_at": datetime.utcnow().isoformat(),
    }
    _custom_tools.append(new_tool)
    log.info(f"Created custom tool: {tool.name}")

    return {"success": True, "id": new_tool["id"]}


@router.get("/custom-tools/{tool_id}", response_model=dict)
async def get_custom_tool(tool_id: str, user=Depends(get_current_user)):
    """Get a custom tool by ID."""
    tool = next((t for t in _custom_tools if t["id"] == tool_id), None)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"success": True, "tool": tool}


@router.delete("/custom-tools/{tool_id}", response_model=dict)
async def delete_custom_tool(tool_id: str, user=Depends(get_current_user)):
    """Delete a custom tool."""
    global _custom_tools
    tool = next((t for t in _custom_tools if t["id"] == tool_id), None)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    _custom_tools = [t for t in _custom_tools if t["id"] != tool_id]
    log.info(f"Deleted custom tool: {tool['name']}")

    return {"success": True, "message": "Tool deleted"}


# ============================================================================
# MCP Server Endpoints (static routes - must be before /{agent_id})
# ============================================================================

@router.get("/mcp-servers", response_model=dict)
async def list_mcp_servers(user=Depends(get_current_user)):
    """List all MCP servers."""
    return {
        "success": True,
        "servers": _mcp_servers
    }


@router.post("/mcp-servers", response_model=dict)
async def create_mcp_server(server: MCPServerCreate, user=Depends(get_current_user)):
    """Add an MCP server."""
    # Check for duplicate name
    if any(s["name"] == server.name for s in _mcp_servers):
        raise HTTPException(status_code=400, detail="Server name already exists")

    new_server = {
        "id": str(uuid.uuid4()),
        "name": server.name,
        "transport": server.transport,
        "endpoint": server.endpoint,
        "description": server.description,
        "env": server.env,
        "is_connected": False,
        "tool_count": 0,
        "created_at": datetime.utcnow().isoformat(),
    }
    _mcp_servers.append(new_server)
    log.info(f"Added MCP server: {server.name}")

    return {"success": True, "id": new_server["id"]}


@router.get("/mcp-servers/{server_id}", response_model=dict)
async def get_mcp_server(server_id: str, user=Depends(get_current_user)):
    """Get an MCP server by ID."""
    server = next((s for s in _mcp_servers if s["id"] == server_id), None)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return {"success": True, "server": server}


@router.post("/mcp-servers/{server_id}/connect", response_model=dict)
async def connect_mcp_server(server_id: str, user=Depends(get_current_user)):
    """Connect to an MCP server."""
    server = next((s for s in _mcp_servers if s["id"] == server_id), None)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    # TODO: Implement actual MCP connection
    server["is_connected"] = True
    log.info(f"Connected to MCP server: {server['name']}")

    return {"success": True, "message": "Connected"}


@router.delete("/mcp-servers/{server_id}", response_model=dict)
async def delete_mcp_server(server_id: str, user=Depends(get_current_user)):
    """Delete an MCP server."""
    global _mcp_servers
    server = next((s for s in _mcp_servers if s["id"] == server_id), None)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    _mcp_servers = [s for s in _mcp_servers if s["id"] != server_id]
    log.info(f"Deleted MCP server: {server['name']}")

    return {"success": True, "message": "Server deleted"}


# ============================================================================
# Main Agent CRUD routes
# ============================================================================

@router.get("/", response_model=dict)
async def list_agents(user=Depends(get_current_user)):
    """List all agents."""
    session = get_session()
    try:
        agents = session.query(AgentModel).all()
        return {
            "success": True,
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "agent_name": a.name,  # Frontend expects agent_name
                    "name": a.name,
                    "agent_type": a.agent_type,
                    "description": a.description,
                    "is_active": a.is_enabled,
                    "status": a.status or "idle",
                    "llm_provider": a.llm_provider,
                    "llm_model": a.llm_model,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "session_count": a.total_sessions or 0
                }
                for a in agents
            ]
        }
    finally:
        session.close()


@router.post("/", response_model=dict)
async def create_agent(agent: AgentCreate, user=Depends(get_current_user)):
    """Create a new agent."""
    session = get_session()
    try:
        agent_name = agent.resolved_name
        if not agent_name:
            raise HTTPException(status_code=400, detail="Agent name is required")
        new_agent = AgentModel(
            agent_id=str(uuid.uuid4()),
            name=agent_name,
            agent_type=agent.agent_type,
            description=agent.description,
            llm_provider=agent.llm_provider,
            llm_model=agent.llm_model,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            allowed_tools=agent.tools,
            is_enabled=agent.is_active,
            status="idle"
        )
        session.add(new_agent)
        session.commit()
        return {"success": True, "agent_id": new_agent.agent_id}
    finally:
        session.close()


# ============================================================================
# Dynamic routes with {agent_id} parameter - MUST be LAST
# ============================================================================

@router.get("/{agent_id}", response_model=dict)
async def get_agent(agent_id: str, user=Depends(get_current_user)):
    """Get agent by ID."""
    session = get_session()
    try:
        agent = session.query(AgentModel).filter(AgentModel.agent_id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {
            "success": True,
            "agent": {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "agent_type": agent.agent_type,
                "description": agent.description,
                "is_active": agent.is_enabled,
                "status": agent.status or "idle",
                "llm_provider": agent.llm_provider,
                "llm_model": agent.llm_model,
                "system_prompt": agent.system_prompt,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "tools": agent.allowed_tools or [],
                "created_at": agent.created_at.isoformat() if agent.created_at else None,
            }
        }
    finally:
        session.close()


@router.patch("/{agent_id}", response_model=dict)
async def update_agent(agent_id: str, updates: dict, user=Depends(get_current_user)):
    """Update an agent."""
    session = get_session()
    try:
        agent = session.query(AgentModel).filter(AgentModel.agent_id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        field_mapping = {
            "is_active": "is_enabled",
            "tools": "allowed_tools",
        }
        for key, value in updates.items():
            db_key = field_mapping.get(key, key)
            if hasattr(agent, db_key):
                setattr(agent, db_key, value)

        session.commit()
        return {"success": True, "message": "Agent updated"}
    finally:
        session.close()


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, user=Depends(get_current_user)):
    """Delete an agent."""
    session = get_session()
    try:
        agent = session.query(AgentModel).filter(AgentModel.agent_id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        session.delete(agent)
        session.commit()
        return {"success": True, "message": "Agent deleted"}
    finally:
        session.close()


@router.post("/{agent_id}/toggle", response_model=dict)
async def toggle_agent(agent_id: str, user=Depends(get_current_user)):
    """Toggle agent active status."""
    session = get_session()
    try:
        agent = session.query(AgentModel).filter(AgentModel.agent_id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent.is_enabled = not agent.is_enabled
        session.commit()
        return {"success": True, "is_active": agent.is_enabled}
    finally:
        session.close()


@router.post("/{agent_id}/start")
async def start_agent(agent_id: str, user=Depends(get_current_user)):
    """Start an agent."""
    # TODO: Implement agent start logic
    return {"success": True, "message": "Agent start requested"}


@router.post("/{agent_id}/stop")
async def stop_agent(agent_id: str, user=Depends(get_current_user)):
    """Stop an agent."""
    # TODO: Implement agent stop logic
    return {"success": True, "message": "Agent stop requested"}
