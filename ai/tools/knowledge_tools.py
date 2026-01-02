"""
Knowledge Tools

Tools for searching the knowledge base using vector similarity (RAG).
"""

import logging
from typing import Dict, Any, Optional, List

from .base import BaseTool, ToolResult

log = logging.getLogger(__name__)


class KnowledgeSearchTool(BaseTool):
    """
    Search the knowledge base using semantic similarity.

    Uses pgvector for vector similarity search against embedded documents.
    Returns relevant documentation chunks with context.
    """

    name = "knowledge_search"
    description = """Search the knowledge base for relevant documentation, runbooks, and troubleshooting guides.
Uses semantic search to find the most relevant information based on meaning, not just keywords.
Use this to find SOPs, past incident resolutions, vendor documentation, and network-specific knowledge."""
    category = "knowledge"
    risk_level = "low"
    requires_approval = False

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query describing what information you need"
                },
                "collection": {
                    "type": "string",
                    "description": "Optional: Limit search to a specific collection (e.g., 'runbooks', 'vendor-docs')"
                },
                "doc_type": {
                    "type": "string",
                    "description": "Optional: Filter by document type (e.g., 'runbook', 'sop', 'troubleshooting')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20
                }
            },
            "required": ["query"]
        }

    def execute(
        self,
        query: str,
        collection: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 5
    ) -> ToolResult:
        """Search knowledge base using vector similarity"""
        try:
            # Generate query embedding
            query_embedding = self._generate_embedding(query)
            if not query_embedding:
                return ToolResult(
                    success=False,
                    error="Failed to generate query embedding"
                )

            # Perform vector search
            results = self._vector_search(
                query_embedding,
                collection=collection,
                doc_type=doc_type,
                limit=limit
            )

            return ToolResult(
                success=True,
                data={
                    'query': query,
                    'results': results,
                    'count': len(results)
                }
            )

        except Exception as e:
            log.error(f"Knowledge search error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )

    def _generate_embedding(self, query_text: str) -> Optional[List[float]]:
        """Generate embedding using OpenAI API"""
        try:
            import database as db
            from sqlalchemy import text as sql_text

            # Get OpenAI API key from llm_providers table
            with db.get_db() as session:
                result = session.execute(
                    sql_text("SELECT api_key FROM llm_providers WHERE name = 'openai' AND is_enabled = true")
                ).fetchone()

                if not result or not result[0]:
                    log.error("OpenAI API key not configured in LLM providers")
                    return None

                api_key = result[0]
                # Handle space-separated key format (some keys have extra data)
                if ' ' in api_key:
                    api_key = api_key.split(' ')[0]
                if api_key.startswith('enc:'):
                    from credential_encryption import decrypt_value
                    api_key = decrypt_value(api_key)

            # Call OpenAI embeddings API
            import requests
            response = requests.post(
                'https://api.openai.com/v1/embeddings',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'text-embedding-3-small',
                    'input': query_text
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return data['data'][0]['embedding']
            else:
                log.error(f"OpenAI API error: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            log.error(f"Error generating embedding: {e}")
            return None

    def _vector_search(
        self,
        query_embedding: List[float],
        collection: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict]:
        """Perform vector similarity search using pgvector"""
        try:
            import database as db
            from sqlalchemy import text

            with db.get_db() as session:
                # Build the query with optional filters
                filters = []
                params = {
                    'embedding': str(query_embedding),
                    'limit': limit
                }

                if collection:
                    filters.append("kd.collection_id = (SELECT id FROM knowledge_collections WHERE name = :collection)")
                    params['collection'] = collection

                if doc_type:
                    filters.append("kd.doc_type = :doc_type")
                    params['doc_type'] = doc_type

                where_clause = ""
                if filters:
                    where_clause = "WHERE " + " AND ".join(filters)

                # pgvector similarity search using cosine distance
                # Note: Use CAST() syntax instead of :: to avoid SQLAlchemy parameter parsing issues
                query = text(f"""
                    SELECT
                        ke.id,
                        ke.chunk_text,
                        ke.chunk_index,
                        kd.title,
                        kd.doc_type,
                        kd.source,
                        kc.name as collection_name,
                        1 - (ke.embedding <=> CAST(:embedding AS vector)) as similarity
                    FROM knowledge_embeddings ke
                    JOIN knowledge_documents kd ON ke.doc_id = kd.doc_id
                    LEFT JOIN knowledge_collections kc ON kd.collection_id = kc.id
                    {where_clause}
                    ORDER BY ke.embedding <=> CAST(:embedding AS vector)
                    LIMIT :limit
                """)

                results = session.execute(query, params).fetchall()

                return [
                    {
                        'id': row[0],
                        'content': row[1],
                        'chunk_index': row[2],
                        'title': row[3],
                        'doc_type': row[4],
                        'source': row[5],
                        'collection': row[6],
                        'similarity': float(row[7]) if row[7] else 0
                    }
                    for row in results
                ]

        except Exception as e:
            log.error(f"Vector search error: {e}", exc_info=True)
            return []


class KnowledgeContextTool(BaseTool):
    """
    Get full document context from a knowledge search result.

    After finding relevant chunks, use this to get surrounding context.
    """

    name = "knowledge_context"
    description = """Get expanded context around a knowledge search result.
Use this when you need more context than what was returned in the initial search result."""
    category = "knowledge"
    risk_level = "low"
    requires_approval = False

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "string",
                    "description": "Document ID from the search result"
                },
                "chunk_index": {
                    "type": "integer",
                    "description": "Chunk index from the search result"
                },
                "context_chunks": {
                    "type": "integer",
                    "description": "Number of chunks before and after to include",
                    "default": 2
                }
            },
            "required": ["doc_id", "chunk_index"]
        }

    def execute(
        self,
        doc_id: str,
        chunk_index: int,
        context_chunks: int = 2
    ) -> ToolResult:
        """Get expanded context around a chunk"""
        try:
            import database as db
            from shared.netstacks_core.db.models import KnowledgeDocument, KnowledgeEmbedding
            from sqlalchemy import and_

            with db.get_db() as session:
                # Get the document
                doc = session.query(KnowledgeDocument).filter(
                    KnowledgeDocument.doc_id == doc_id
                ).first()

                if not doc:
                    return ToolResult(
                        success=False,
                        error=f"Document not found: {doc_id}"
                    )

                # Get surrounding chunks
                start_index = max(0, chunk_index - context_chunks)
                end_index = chunk_index + context_chunks

                chunks = session.query(KnowledgeEmbedding).filter(
                    and_(
                        KnowledgeEmbedding.doc_id == doc_id,
                        KnowledgeEmbedding.chunk_index >= start_index,
                        KnowledgeEmbedding.chunk_index <= end_index
                    )
                ).order_by(KnowledgeEmbedding.chunk_index).all()

                # Combine chunk text
                context_text = "\n\n".join([c.chunk_text for c in chunks])

                return ToolResult(
                    success=True,
                    data={
                        'doc_id': doc_id,
                        'title': doc.title,
                        'doc_type': doc.doc_type,
                        'source': doc.source,
                        'context': context_text,
                        'chunks_included': [c.chunk_index for c in chunks]
                    }
                )

        except Exception as e:
            log.error(f"Knowledge context error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )


class KnowledgeListTool(BaseTool):
    """
    List available knowledge collections and documents.

    Helps agents understand what knowledge is available.
    """

    name = "knowledge_list"
    description = """List available knowledge collections and their document counts.
Use this to understand what knowledge is available before searching."""
    category = "knowledge"
    risk_level = "low"
    requires_approval = False

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "collection": {
                    "type": "string",
                    "description": "Optional: Show documents in a specific collection"
                }
            },
            "required": []
        }

    def execute(self, collection: Optional[str] = None) -> ToolResult:
        """List knowledge collections and documents"""
        try:
            import database as db
            from shared.netstacks_core.db.models import KnowledgeCollection, KnowledgeDocument
            from sqlalchemy import func

            with db.get_db() as session:
                if collection:
                    # List documents in collection
                    coll = session.query(KnowledgeCollection).filter(
                        KnowledgeCollection.name == collection
                    ).first()

                    if not coll:
                        return ToolResult(
                            success=False,
                            error=f"Collection not found: {collection}"
                        )

                    docs = session.query(KnowledgeDocument).filter(
                        KnowledgeDocument.collection_id == coll.id
                    ).all()

                    return ToolResult(
                        success=True,
                        data={
                            'collection': collection,
                            'description': coll.description,
                            'documents': [
                                {
                                    'doc_id': d.doc_id,
                                    'title': d.title,
                                    'doc_type': d.doc_type,
                                    'source': d.source
                                }
                                for d in docs
                            ]
                        }
                    )
                else:
                    # List all collections with counts
                    collections = session.query(
                        KnowledgeCollection.name,
                        KnowledgeCollection.description,
                        func.count(KnowledgeDocument.doc_id).label('doc_count')
                    ).outerjoin(
                        KnowledgeDocument,
                        KnowledgeCollection.id == KnowledgeDocument.collection_id
                    ).group_by(
                        KnowledgeCollection.id
                    ).all()

                    return ToolResult(
                        success=True,
                        data={
                            'collections': [
                                {
                                    'name': c[0],
                                    'description': c[1],
                                    'document_count': c[2]
                                }
                                for c in collections
                            ]
                        }
                    )

        except Exception as e:
            log.error(f"Knowledge list error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )
