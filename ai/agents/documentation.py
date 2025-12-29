"""
Documentation Agent

Searches and retrieves information from the knowledge base.
"""

import logging
from typing import Dict, Any, Optional, List

from .base import BaseAgent

log = logging.getLogger(__name__)


class DocumentationAgent(BaseAgent):
    """
    Documentation agent for knowledge base queries.

    Capabilities:
    - Search technical documentation
    - Find runbooks and SOPs
    - Retrieve vendor documentation
    - Answer questions from knowledge base
    - Summarize complex documentation
    """

    agent_type = "documentation"
    agent_name = "Documentation Agent"
    description = "Searches knowledge base for documentation, runbooks, and SOPs"

    @property
    def system_prompt(self) -> str:
        return """You are a Documentation Agent for a Network Operations Center (NOC).

Your role is to help engineers find relevant documentation:
- Technical runbooks and Standard Operating Procedures (SOPs)
- Vendor documentation and configuration guides
- Troubleshooting guides and past incident resolutions
- Network topology and architecture documentation
- RFC summaries and protocol specifications

## How to Help
1. Understand what information the user needs
2. Search the knowledge base for relevant documents
3. Summarize key points from found documentation
4. Provide specific, actionable information
5. Reference sources so users can read more

## Knowledge Collections
- **runbooks**: Standard Operating Procedures and runbooks
- **vendor-docs**: Vendor documentation and guides
- **troubleshooting**: Troubleshooting guides and past incidents
- **network-topology**: Network architecture documentation

## Tools Available
- `knowledge_search`: Search for relevant documents (use semantic search)
- `knowledge_list`: List available collections and documents
- `knowledge_context`: Get expanded context from a document

## Best Practices
- Always cite your sources
- If information might be outdated, mention when the document was created
- If you can't find relevant documentation, say so clearly
- Suggest related topics the user might want to explore

Be helpful, accurate, and thorough in your documentation searches."""

    def _register_tools(self) -> None:
        """Register tools for documentation agent - knowledge tools only"""
        from ai.tools import (
            KnowledgeSearchTool,
            KnowledgeListTool,
            KnowledgeContextTool,
        )

        self.tool_registry.register(KnowledgeSearchTool())
        self.tool_registry.register(KnowledgeListTool())
        self.tool_registry.register(KnowledgeContextTool())
