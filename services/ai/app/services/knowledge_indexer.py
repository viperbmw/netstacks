# services/ai/app/services/knowledge_indexer.py
"""
Knowledge Indexer Service

Handles document chunking and embedding generation for RAG.
Uses OpenAI-compatible embedding APIs (OpenAI, OpenRouter, local).
"""

import logging
import re
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import httpx
from sqlalchemy import text

from netstacks_core.db import get_session, LLMProvider

log = logging.getLogger(__name__)

# Embedding configurations
DEFAULT_CHUNK_SIZE = 1000  # characters
DEFAULT_CHUNK_OVERLAP = 200  # characters
EMBEDDING_DIMENSION = 1536  # OpenAI ada-002 dimension

# Embedding API endpoints
OPENAI_EMBEDDING_URL = "https://api.openai.com/v1/embeddings"
OPENROUTER_EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"


@dataclass
class DocumentChunk:
    """A chunk of document text."""
    text: str
    index: int
    token_count: int = 0


class EmbeddingError(Exception):
    """Error generating embeddings."""
    pass


def get_embedding_config() -> tuple[str, str, str]:
    """
    Get embedding API configuration.

    Returns: (api_key, api_url, model)
    """
    session = get_session()
    try:
        # Try OpenAI first (best embeddings)
        provider = session.query(LLMProvider).filter(
            LLMProvider.name == "openai",
            LLMProvider.is_enabled == True
        ).first()

        if provider and provider.api_key:
            return (
                provider.api_key,
                OPENAI_EMBEDDING_URL,
                "text-embedding-ada-002"
            )

        # Try OpenRouter
        provider = session.query(LLMProvider).filter(
            LLMProvider.name == "openrouter",
            LLMProvider.is_enabled == True
        ).first()

        if provider and provider.api_key:
            return (
                provider.api_key,
                OPENROUTER_EMBEDDING_URL,
                "openai/text-embedding-ada-002"
            )

        # Try Anthropic's embedding via OpenRouter
        provider = session.query(LLMProvider).filter(
            LLMProvider.name == "anthropic",
            LLMProvider.is_enabled == True
        ).first()

        if provider:
            log.warning("Anthropic doesn't provide embeddings directly, using text matching")
            return (None, None, None)

        raise EmbeddingError("No embedding provider configured. Add OpenAI or OpenRouter API key.")

    finally:
        session.close()


def chunk_document(
    content: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
) -> List[DocumentChunk]:
    """
    Split document into overlapping chunks.

    Uses smart splitting on paragraph/section boundaries when possible.
    """
    if not content or not content.strip():
        return []

    chunks = []

    # First, try to split on markdown headers or double newlines
    sections = re.split(r'\n(?=#{1,3}\s|\n)', content)

    current_chunk = ""
    chunk_index = 0

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # If section fits in current chunk, add it
        if len(current_chunk) + len(section) + 2 <= chunk_size:
            current_chunk += ("\n\n" if current_chunk else "") + section
        else:
            # Save current chunk if non-empty
            if current_chunk.strip():
                chunks.append(DocumentChunk(
                    text=current_chunk.strip(),
                    index=chunk_index,
                    token_count=len(current_chunk.split())  # Rough token estimate
                ))
                chunk_index += 1

            # If section itself is too large, split it further
            if len(section) > chunk_size:
                # Split on sentences or lines
                sentences = re.split(r'(?<=[.!?])\s+|\n', section)
                current_chunk = ""

                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 1 <= chunk_size:
                        current_chunk += (" " if current_chunk else "") + sentence
                    else:
                        if current_chunk.strip():
                            chunks.append(DocumentChunk(
                                text=current_chunk.strip(),
                                index=chunk_index,
                                token_count=len(current_chunk.split())
                            ))
                            chunk_index += 1

                        # Keep overlap from previous chunk
                        if chunk_overlap > 0 and chunks:
                            overlap_text = chunks[-1].text[-chunk_overlap:]
                            current_chunk = overlap_text + " " + sentence
                        else:
                            current_chunk = sentence
            else:
                # Keep overlap from previous chunk
                if chunk_overlap > 0 and chunks:
                    overlap_text = chunks[-1].text[-chunk_overlap:]
                    current_chunk = overlap_text + "\n\n" + section
                else:
                    current_chunk = section

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(DocumentChunk(
            text=current_chunk.strip(),
            index=chunk_index,
            token_count=len(current_chunk.split())
        ))

    log.info(f"Split document into {len(chunks)} chunks")
    return chunks


async def generate_embeddings(
    texts: List[str],
    api_key: str,
    api_url: str,
    model: str
) -> List[List[float]]:
    """
    Generate embeddings for a list of texts.

    Returns list of embedding vectors.
    """
    if not texts:
        return []

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "input": texts,
                "model": model,
            }
        )

        if response.status_code != 200:
            error_text = response.text
            log.error(f"Embedding API error: {response.status_code} - {error_text}")
            raise EmbeddingError(f"Embedding API error: {response.status_code}")

        data = response.json()
        embeddings = [item["embedding"] for item in data["data"]]

        log.info(f"Generated {len(embeddings)} embeddings")
        return embeddings


async def index_document(doc_id: str) -> Dict[str, Any]:
    """
    Index a single document: chunk it and generate embeddings.

    Returns status dict with chunk_count and any errors.
    """
    session = get_session()

    try:
        # Get document
        result = session.execute(
            text("SELECT doc_id, title, content FROM knowledge_documents WHERE doc_id = :doc_id"),
            {"doc_id": doc_id}
        ).fetchone()

        if not result:
            return {"success": False, "error": "Document not found"}

        doc_id, title, content = result.doc_id, result.title, result.content

        if not content:
            return {"success": False, "error": "Document has no content"}

        # Get embedding config
        try:
            api_key, api_url, model = get_embedding_config()
        except EmbeddingError as e:
            # Fall back to text-only indexing (no vectors)
            log.warning(f"No embedding provider: {e}. Using text-only indexing.")
            api_key = None

        # Chunk the document
        chunks = chunk_document(content)

        if not chunks:
            return {"success": False, "error": "Document produced no chunks"}

        # Delete existing embeddings for this document
        session.execute(
            text("DELETE FROM knowledge_embeddings WHERE doc_id = :doc_id"),
            {"doc_id": doc_id}
        )

        # Generate embeddings if we have an API key
        embeddings = None
        if api_key:
            try:
                chunk_texts = [chunk.text for chunk in chunks]
                embeddings = await generate_embeddings(chunk_texts, api_key, api_url, model)
            except Exception as e:
                log.error(f"Error generating embeddings: {e}")
                # Continue without embeddings

        # Store chunks (with or without embeddings)
        for i, chunk in enumerate(chunks):
            embedding = embeddings[i] if embeddings and i < len(embeddings) else None

            if embedding:
                # Store with vector embedding
                session.execute(
                    text("""
                        INSERT INTO knowledge_embeddings
                        (doc_id, chunk_index, chunk_text, token_count, embedding, created_at)
                        VALUES (:doc_id, :chunk_index, :chunk_text, :token_count, :embedding, NOW())
                    """),
                    {
                        "doc_id": doc_id,
                        "chunk_index": chunk.index,
                        "chunk_text": chunk.text,
                        "token_count": chunk.token_count,
                        "embedding": str(embedding),  # PostgreSQL vector format
                    }
                )
            else:
                # Store without embedding (text search only)
                session.execute(
                    text("""
                        INSERT INTO knowledge_embeddings
                        (doc_id, chunk_index, chunk_text, token_count, created_at)
                        VALUES (:doc_id, :chunk_index, :chunk_text, :token_count, NOW())
                    """),
                    {
                        "doc_id": doc_id,
                        "chunk_index": chunk.index,
                        "chunk_text": chunk.text,
                        "token_count": chunk.token_count,
                    }
                )

        # Update document status
        session.execute(
            text("""
                UPDATE knowledge_documents
                SET is_indexed = TRUE, chunk_count = :chunk_count, updated_at = NOW()
                WHERE doc_id = :doc_id
            """),
            {"doc_id": doc_id, "chunk_count": len(chunks)}
        )

        session.commit()

        return {
            "success": True,
            "doc_id": doc_id,
            "title": title,
            "chunk_count": len(chunks),
            "has_embeddings": embeddings is not None,
        }

    except Exception as e:
        session.rollback()
        log.error(f"Error indexing document {doc_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        session.close()


async def index_all_documents() -> Dict[str, Any]:
    """
    Index all unindexed documents.

    Returns summary of indexing results.
    """
    session = get_session()

    try:
        # Get all unindexed documents
        result = session.execute(
            text("SELECT doc_id FROM knowledge_documents WHERE is_indexed = FALSE OR is_indexed IS NULL")
        )
        doc_ids = [row.doc_id for row in result]

        if not doc_ids:
            return {
                "success": True,
                "message": "All documents are already indexed",
                "indexed": 0,
                "failed": 0,
            }

        log.info(f"Indexing {len(doc_ids)} documents...")

        indexed = 0
        failed = 0
        errors = []

        for doc_id in doc_ids:
            result = await index_document(doc_id)
            if result.get("success"):
                indexed += 1
            else:
                failed += 1
                errors.append({"doc_id": doc_id, "error": result.get("error")})

        return {
            "success": True,
            "message": f"Indexed {indexed} documents, {failed} failed",
            "indexed": indexed,
            "failed": failed,
            "errors": errors if errors else None,
        }

    finally:
        session.close()


async def search_knowledge(
    query: str,
    collection_id: Optional[int] = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Search knowledge base using text matching.

    Falls back to ILIKE if no embeddings available.
    TODO: Add vector similarity search when embeddings are available.
    """
    session = get_session()

    try:
        # For now, use text search (ILIKE)
        # TODO: Add vector similarity search using pgvector

        if collection_id:
            result = session.execute(
                text("""
                    SELECT
                        d.doc_id,
                        d.title,
                        d.doc_type,
                        e.chunk_text,
                        e.chunk_index
                    FROM knowledge_embeddings e
                    JOIN knowledge_documents d ON e.doc_id = d.doc_id
                    WHERE d.collection_id = :collection_id
                      AND (e.chunk_text ILIKE :query OR d.title ILIKE :query)
                    ORDER BY d.title, e.chunk_index
                    LIMIT :limit
                """),
                {
                    "collection_id": collection_id,
                    "query": f"%{query}%",
                    "limit": limit,
                }
            )
        else:
            result = session.execute(
                text("""
                    SELECT
                        d.doc_id,
                        d.title,
                        d.doc_type,
                        e.chunk_text,
                        e.chunk_index
                    FROM knowledge_embeddings e
                    JOIN knowledge_documents d ON e.doc_id = d.doc_id
                    WHERE e.chunk_text ILIKE :query OR d.title ILIKE :query
                    ORDER BY d.title, e.chunk_index
                    LIMIT :limit
                """),
                {
                    "query": f"%{query}%",
                    "limit": limit,
                }
            )

        results = []
        for row in result:
            results.append({
                "doc_id": row.doc_id,
                "title": row.title,
                "doc_type": row.doc_type,
                "chunk_text": row.chunk_text,
                "chunk_index": row.chunk_index,
                "score": 1.0,  # Placeholder - real score would come from vector similarity
            })

        return results

    finally:
        session.close()
