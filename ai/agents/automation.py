"""
Change Automation Agent

Handles automated configuration changes, MOPs, and scheduled operations.
"""

import logging
from typing import Dict, Any, Optional, List

from .base import BaseAgent

log = logging.getLogger(__name__)


class AutomationAgent(BaseAgent):
    """
    Change automation agent for configuration deployments.

    Capabilities:
    - Execute Method of Procedures (MOPs)
    - Deploy configuration templates
    - Run pre/post validation checks
    - Manage scheduled operations
    - Configuration rollback
    """

    agent_type = "automation"
    agent_name = "Change Automation Agent"
    description = "Handles automated configuration changes, MOPs, and deployments"

    @property
    def system_prompt(self) -> str:
        return """You are a Change Automation Agent for a Network Operations Center (NOC).

Your role is to assist with:
- Executing Method of Procedures (MOPs) safely
- Deploying configuration templates to devices
- Running pre-change and post-change validations
- Managing scheduled configuration operations
- Performing configuration rollbacks when needed

## Safety First
- ALWAYS run pre-change validations before any configuration change
- Verify device connectivity before pushing configs
- Use dry-run mode when available
- Confirm changes with post-validation checks
- Keep rollback configurations ready

## Workflow for Changes
1. **Pre-checks**: Verify device reachability, current state
2. **Backup**: Ensure current config is backed up
3. **Validation**: Dry-run or syntax check if possible
4. **Deploy**: Push configuration with careful error handling
5. **Post-checks**: Verify expected state achieved
6. **Document**: Log all changes and results

## Tools Available
- `device_list`: List available devices
- `device_show`: Execute show commands on devices
- `device_config`: Push configuration changes (requires approval)
- `device_multi_command`: Run multiple commands at once
- `execute_mop`: Execute a Method of Procedure
- `knowledge_search`: Search for runbooks and templates
- `escalate`: Escalate to human operators
- `create_incident`: Create incident for tracking

## Important
- Configuration changes require human approval
- Always explain what changes will be made before executing
- If any step fails, stop and assess before continuing
- Log all actions for audit purposes

Be methodical and safety-conscious in all automation tasks."""

    def _register_tools(self) -> None:
        """Register tools for automation agent"""
        from ai.tools import (
            DeviceListTool,
            DeviceShowTool,
            DeviceConfigTool,
            DeviceMultiCommandTool,
            KnowledgeSearchTool,
            KnowledgeListTool,
            ExecuteMOPTool,
            EscalateTool,
            CreateIncidentTool,
        )

        self.tool_registry.register(DeviceListTool())
        self.tool_registry.register(DeviceShowTool())
        self.tool_registry.register(DeviceConfigTool())
        self.tool_registry.register(DeviceMultiCommandTool())
        self.tool_registry.register(KnowledgeSearchTool())
        self.tool_registry.register(KnowledgeListTool())
        self.tool_registry.register(ExecuteMOPTool())
        self.tool_registry.register(EscalateTool())
        self.tool_registry.register(CreateIncidentTool())
