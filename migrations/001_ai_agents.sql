-- NetStacks AI Agent Tables Migration
-- Run this script to add AI agent tables to an existing database
-- For new installations, tables are created automatically via SQLAlchemy create_all()

-- Enable pgvector extension for vector embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- LLM PROVIDERS
-- =============================================================================

CREATE TABLE IF NOT EXISTS llm_providers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100),
    api_key VARCHAR(500) NOT NULL,
    api_base_url VARCHAR(255),
    default_model VARCHAR(100),
    available_models JSONB DEFAULT '[]',
    is_enabled BOOLEAN DEFAULT TRUE,
    is_default BOOLEAN DEFAULT FALSE,
    config JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- AGENTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS agents (
    agent_id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    description TEXT,
    system_prompt TEXT,
    is_enabled BOOLEAN DEFAULT TRUE,
    is_persistent BOOLEAN DEFAULT FALSE,
    is_default BOOLEAN DEFAULT FALSE,
    llm_provider VARCHAR(50) DEFAULT 'anthropic',
    llm_model VARCHAR(100),
    temperature FLOAT DEFAULT 0.1,
    max_tokens INTEGER DEFAULT 4096,
    max_iterations INTEGER DEFAULT 10,
    allowed_tools JSONB DEFAULT '[]',
    allowed_devices JSONB DEFAULT '[]',
    autonomy_level VARCHAR(20) DEFAULT 'diagnose',
    config JSONB DEFAULT '{}',
    stats JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_agents_type ON agents(agent_type);
CREATE INDEX IF NOT EXISTS idx_agents_enabled ON agents(is_enabled);

-- =============================================================================
-- AGENT SESSIONS
-- =============================================================================

CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id VARCHAR(36) PRIMARY KEY,
    agent_id VARCHAR(36) NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    trigger_type VARCHAR(20) NOT NULL,
    trigger_id VARCHAR(36),
    parent_session_id VARCHAR(36),
    status VARCHAR(20) DEFAULT 'active',
    initial_prompt TEXT,
    context JSONB DEFAULT '{}',
    summary TEXT,
    resolution_status VARCHAR(20),
    token_count INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0,
    iteration_count INTEGER DEFAULT 0,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    started_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent ON agent_sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_status ON agent_sessions(status);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_trigger ON agent_sessions(trigger_type, trigger_id);

-- =============================================================================
-- AGENT MESSAGES
-- =============================================================================

CREATE TABLE IF NOT EXISTS agent_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    tool_call_id VARCHAR(100),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_messages_session ON agent_messages(session_id);

-- =============================================================================
-- AGENT ACTIONS (Audit Trail)
-- =============================================================================

CREATE TABLE IF NOT EXISTS agent_actions (
    action_id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    action_type VARCHAR(20) NOT NULL,
    content TEXT,
    tool_name VARCHAR(100),
    tool_input JSONB DEFAULT '{}',
    tool_output JSONB DEFAULT '{}',
    risk_level VARCHAR(20),
    status VARCHAR(20) DEFAULT 'pending',
    error TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_actions_session ON agent_actions(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_actions_type ON agent_actions(action_type);

-- =============================================================================
-- AGENT TOOLS
-- =============================================================================

CREATE TABLE IF NOT EXISTS agent_tools (
    tool_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    is_builtin BOOLEAN DEFAULT TRUE,
    is_enabled BOOLEAN DEFAULT TRUE,
    risk_level VARCHAR(20) DEFAULT 'low',
    requires_approval BOOLEAN DEFAULT FALSE,
    input_schema JSONB DEFAULT '{}',
    output_schema JSONB DEFAULT '{}',
    config JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_tools_category ON agent_tools(category);

-- =============================================================================
-- KNOWLEDGE COLLECTIONS
-- =============================================================================

CREATE TABLE IF NOT EXISTS knowledge_collections (
    collection_id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    doc_type VARCHAR(50) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    config JSONB DEFAULT '{}',
    document_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255)
);

-- =============================================================================
-- KNOWLEDGE DOCUMENTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS knowledge_documents (
    doc_id VARCHAR(36) PRIMARY KEY,
    collection_id VARCHAR(36) REFERENCES knowledge_collections(collection_id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    doc_type VARCHAR(50) NOT NULL,
    source_url VARCHAR(500),
    file_path VARCHAR(500),
    file_type VARCHAR(20),
    metadata JSONB DEFAULT '{}',
    is_indexed BOOLEAN DEFAULT FALSE,
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_type ON knowledge_documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_collection ON knowledge_documents(collection_id);

-- =============================================================================
-- KNOWLEDGE EMBEDDINGS (pgvector)
-- =============================================================================

CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(36) NOT NULL REFERENCES knowledge_documents(doc_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI text-embedding-3-small dimension
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_doc ON knowledge_embeddings(doc_id);

-- Create HNSW index for fast similarity search (if pgvector supports it)
-- Note: Run this separately if using pgvector 0.5.0+
-- CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_vector ON knowledge_embeddings
--     USING hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- ALERT SOURCES
-- =============================================================================

CREATE TABLE IF NOT EXISTS alert_sources (
    source_id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    source_type VARCHAR(20) NOT NULL,
    system_type VARCHAR(50) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    config JSONB DEFAULT '{}',
    webhook_secret VARCHAR(255),
    polling_interval_seconds INTEGER,
    last_poll_at TIMESTAMP,
    alert_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- INCIDENTS (must be created before alerts due to FK)
-- =============================================================================

CREATE TABLE IF NOT EXISTS incidents (
    incident_id VARCHAR(36) PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    severity VARCHAR(20) NOT NULL,
    priority VARCHAR(20) DEFAULT 'medium',
    status VARCHAR(20) DEFAULT 'open',
    incident_type VARCHAR(100),
    affected_devices JSONB DEFAULT '[]',
    affected_services JSONB DEFAULT '[]',
    root_cause TEXT,
    resolution TEXT,
    timeline JSONB DEFAULT '[]',
    metrics JSONB DEFAULT '{}',
    assigned_to VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    identified_at TIMESTAMP,
    resolved_at TIMESTAMP,
    closed_at TIMESTAMP,
    created_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);
CREATE INDEX IF NOT EXISTS idx_incidents_created ON incidents(created_at);

-- =============================================================================
-- ALERTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS alerts (
    alert_id VARCHAR(36) PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    source_id VARCHAR(36),
    external_id VARCHAR(255),
    severity VARCHAR(20) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    device_name VARCHAR(255),
    device_ip VARCHAR(50),
    alert_type VARCHAR(100),
    raw_data JSONB DEFAULT '{}',
    normalized_data JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'new',
    assigned_agent_id VARCHAR(36),
    assigned_session_id VARCHAR(36),
    incident_id VARCHAR(36) REFERENCES incidents(incident_id) ON DELETE SET NULL,
    auto_triage BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP,
    resolved_at TIMESTAMP,
    acknowledged_by VARCHAR(255),
    resolution_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_device ON alerts(device_name);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_incident ON alerts(incident_id);

-- =============================================================================
-- PENDING APPROVALS
-- =============================================================================

CREATE TABLE IF NOT EXISTS pending_approvals (
    approval_id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
    action_id VARCHAR(36) NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    target_device VARCHAR(255),
    proposed_action JSONB DEFAULT '{}',
    context JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'pending',
    requires_count INTEGER DEFAULT 1,
    approved_count INTEGER DEFAULT 0,
    approvers JSONB DEFAULT '[]',
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    decided_at TIMESTAMP,
    decided_by VARCHAR(255),
    decision_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_approvals_status ON pending_approvals(status);
CREATE INDEX IF NOT EXISTS idx_pending_approvals_session ON pending_approvals(session_id);

-- =============================================================================
-- SEED DEFAULT DATA
-- =============================================================================

-- Insert default LLM providers (disabled until API keys configured)
INSERT INTO llm_providers (name, display_name, api_key, api_base_url, default_model, available_models, is_enabled, is_default)
VALUES
    ('anthropic', 'Anthropic Claude', '', 'https://api.anthropic.com', 'claude-sonnet-4-20250514',
     '[{"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"}, {"id": "claude-opus-4-20250514", "name": "Claude Opus 4"}, {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"}]',
     FALSE, TRUE),
    ('openrouter', 'OpenRouter', '', 'https://openrouter.ai/api/v1', 'anthropic/claude-3.5-sonnet',
     '[{"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet"}, {"id": "openai/gpt-4-turbo", "name": "GPT-4 Turbo"}]',
     FALSE, FALSE)
ON CONFLICT (name) DO NOTHING;

-- Insert default agent tools
INSERT INTO agent_tools (tool_id, name, description, category, is_builtin, risk_level, requires_approval, input_schema)
VALUES
    ('device_show', 'device_show', 'Execute show commands on network devices', 'device', TRUE, 'low', FALSE,
     '{"type": "object", "properties": {"device_name": {"type": "string"}, "command": {"type": "string"}, "parse": {"type": "boolean", "default": true}}, "required": ["device_name", "command"]}'),
    ('device_config', 'device_config', 'Push configuration to network devices', 'device', TRUE, 'high', TRUE,
     '{"type": "object", "properties": {"device_name": {"type": "string"}, "config_lines": {"type": "array"}, "save_config": {"type": "boolean", "default": true}}, "required": ["device_name", "config_lines"]}'),
    ('knowledge_search', 'knowledge_search', 'Search knowledge base for documentation', 'knowledge', TRUE, 'low', FALSE,
     '{"type": "object", "properties": {"query": {"type": "string"}, "doc_type": {"type": "string", "default": "all"}, "limit": {"type": "integer", "default": 5}}, "required": ["query"]}'),
    ('execute_mop', 'execute_mop', 'Execute a Method of Procedure workflow', 'workflow', TRUE, 'high', TRUE,
     '{"type": "object", "properties": {"mop_name": {"type": "string"}, "devices": {"type": "array"}, "variables": {"type": "object"}}, "required": ["mop_name"]}'),
    ('handoff', 'handoff', 'Transfer to specialist agent', 'workflow', TRUE, 'low', FALSE,
     '{"type": "object", "properties": {"target_agent_type": {"type": "string"}, "reason": {"type": "string"}, "context": {"type": "object"}}, "required": ["target_agent_type", "reason"]}'),
    ('escalate', 'escalate', 'Escalate to human operator', 'workflow', TRUE, 'low', FALSE,
     '{"type": "object", "properties": {"reason": {"type": "string"}, "severity": {"type": "string", "default": "medium"}, "findings": {"type": "object"}}, "required": ["reason"]}'),
    ('create_incident', 'create_incident', 'Create incident ticket', 'workflow', TRUE, 'medium', FALSE,
     '{"type": "object", "properties": {"title": {"type": "string"}, "description": {"type": "string"}, "severity": {"type": "string"}, "affected_devices": {"type": "array"}}, "required": ["title", "severity"]}')
ON CONFLICT (tool_id) DO NOTHING;

-- Insert default agents
INSERT INTO agents (agent_id, name, agent_type, description, is_enabled, is_default, autonomy_level, allowed_tools)
VALUES
    ('00000000-0000-0000-0000-000000000001', 'Triage Agent', 'triage',
     'Initial triage agent that analyzes alerts and routes to specialist agents', TRUE, TRUE, 'diagnose',
     '["device_show", "knowledge_search", "handoff", "escalate", "create_incident"]'),
    ('00000000-0000-0000-0000-000000000002', 'BGP Specialist', 'bgp',
     'BGP troubleshooting specialist for neighbor, route, and policy issues', TRUE, TRUE, 'diagnose',
     '["device_show", "knowledge_search", "handoff", "escalate"]'),
    ('00000000-0000-0000-0000-000000000003', 'OSPF Specialist', 'ospf',
     'OSPF troubleshooting specialist for adjacency, LSA, and routing issues', TRUE, TRUE, 'diagnose',
     '["device_show", "knowledge_search", "handoff", "escalate"]'),
    ('00000000-0000-0000-0000-000000000004', 'ISIS Specialist', 'isis',
     'IS-IS troubleshooting specialist for adjacency and LSP issues', TRUE, TRUE, 'diagnose',
     '["device_show", "knowledge_search", "handoff", "escalate"]')
ON CONFLICT (agent_id) DO NOTHING;

-- Create default knowledge collections
INSERT INTO knowledge_collections (collection_id, name, description, doc_type)
VALUES
    ('00000000-0000-0000-0000-000000000001', 'BGP Runbooks', 'BGP troubleshooting procedures and runbooks', 'runbook'),
    ('00000000-0000-0000-0000-000000000002', 'OSPF Runbooks', 'OSPF troubleshooting procedures and runbooks', 'runbook'),
    ('00000000-0000-0000-0000-000000000003', 'ISIS Runbooks', 'IS-IS troubleshooting procedures and runbooks', 'runbook'),
    ('00000000-0000-0000-0000-000000000004', 'Vendor Documentation', 'Vendor-specific documentation (Cisco, Juniper, etc.)', 'vendor'),
    ('00000000-0000-0000-0000-000000000005', 'Protocol References', 'RFC and protocol specification references', 'protocol')
ON CONFLICT (collection_id) DO NOTHING;

-- Done!
SELECT 'AI Agent tables created successfully!' as status;
