"""
Document Indexer

Handles chunking and embedding generation for knowledge documents.
"""

import logging
from typing import Optional, List

from .chunking import chunk_document
from .embeddings import generate_embedding, generate_embeddings_batch

log = logging.getLogger(__name__)


def index_document(doc_id: str) -> bool:
    """
    Index a document: chunk it and generate embeddings.

    Args:
        doc_id: Document ID to index

    Returns:
        True if successful, False otherwise
    """
    try:
        import database as db
        from shared.netstacks_core.db.models import KnowledgeDocument, KnowledgeEmbedding

        with db.get_db() as session:
            # Get document
            doc = session.query(KnowledgeDocument).filter(
                KnowledgeDocument.doc_id == doc_id
            ).first()

            if not doc:
                log.error(f"Document not found: {doc_id}")
                return False

            if not doc.content:
                log.warning(f"Document has no content: {doc_id}")
                doc.is_indexed = True
                return True

            # Chunk the document
            chunks = chunk_document(doc.content, doc.doc_type)

            if not chunks:
                log.warning(f"No chunks generated for document: {doc_id}")
                doc.is_indexed = True
                return True

            log.info(f"Generated {len(chunks)} chunks for document {doc_id}")

            # Generate embeddings in batch
            chunk_texts = [c.text for c in chunks]
            embeddings = generate_embeddings_batch(chunk_texts)

            # Store embeddings
            for chunk, embedding in zip(chunks, embeddings):
                if embedding is None:
                    log.warning(f"Failed to generate embedding for chunk {chunk.index}")
                    continue

                db_embedding = KnowledgeEmbedding(
                    doc_id=doc_id,
                    chunk_index=chunk.index,
                    chunk_text=chunk.text,
                    embedding=embedding,
                    token_count=chunk.token_count,
                )
                session.add(db_embedding)

            # Mark document as indexed
            doc.is_indexed = True

            log.info(f"Successfully indexed document {doc_id}")
            return True

    except Exception as e:
        log.error(f"Error indexing document {doc_id}: {e}", exc_info=True)
        return False


def reindex_collection(collection_id: int) -> dict:
    """
    Reindex all documents in a collection.

    Args:
        collection_id: Collection ID to reindex

    Returns:
        Dict with success count and failures
    """
    try:
        import database as db
        from shared.netstacks_core.db.models import KnowledgeDocument, KnowledgeEmbedding

        results = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'failed_docs': []
        }

        with db.get_db() as session:
            # Get all documents in collection
            docs = session.query(KnowledgeDocument).filter(
                KnowledgeDocument.collection_id == collection_id
            ).all()

            results['total'] = len(docs)

            for doc in docs:
                # Delete existing embeddings
                session.query(KnowledgeEmbedding).filter(
                    KnowledgeEmbedding.doc_id == doc.doc_id
                ).delete()
                doc.is_indexed = False

        # Reindex each document (uses its own session)
        for doc_id in [d.doc_id for d in docs]:
            if index_document(doc_id):
                results['success'] += 1
            else:
                results['failed'] += 1
                results['failed_docs'].append(doc_id)

        return results

    except Exception as e:
        log.error(f"Error reindexing collection {collection_id}: {e}")
        return {
            'total': 0,
            'success': 0,
            'failed': 0,
            'error': str(e)
        }


def get_similar_chunks(
    query: str,
    collection_id: Optional[int] = None,
    doc_type: Optional[str] = None,
    limit: int = 5
) -> List[dict]:
    """
    Find similar chunks using vector search.

    Args:
        query: Search query
        collection_id: Limit to specific collection
        doc_type: Limit to specific document type
        limit: Maximum results

    Returns:
        List of matching chunks with similarity scores
    """
    try:
        import database as db
        from sqlalchemy import text

        # Generate query embedding
        query_embedding = generate_embedding(query)
        if not query_embedding:
            log.error("Failed to generate query embedding")
            return []

        with db.get_db() as session:
            # Build query with optional filters
            filters = []
            params = {
                'embedding': str(query_embedding),
                'limit': limit
            }

            if collection_id:
                filters.append("kd.collection_id = :collection_id")
                params['collection_id'] = collection_id

            if doc_type:
                filters.append("kd.doc_type = :doc_type")
                params['doc_type'] = doc_type

            where_clause = ""
            if filters:
                where_clause = "WHERE " + " AND ".join(filters)

            # pgvector cosine similarity search
            # Note: Use CAST() instead of :: to avoid SQLAlchemy parameter parsing conflicts
            query_sql = text(f"""
                SELECT
                    ke.id,
                    ke.doc_id,
                    ke.chunk_text,
                    ke.chunk_index,
                    kd.title,
                    kd.doc_type,
                    kd.source,
                    1 - (ke.embedding <=> CAST(:embedding AS vector)) as similarity
                FROM knowledge_embeddings ke
                JOIN knowledge_documents kd ON ke.doc_id = kd.doc_id
                {where_clause}
                ORDER BY ke.embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
            """)

            results = session.execute(query_sql, params).fetchall()

            return [
                {
                    'id': row[0],
                    'doc_id': row[1],
                    'content': row[2],
                    'chunk_index': row[3],
                    'title': row[4],
                    'doc_type': row[5],
                    'source': row[6],
                    'similarity': float(row[7]) if row[7] else 0
                }
                for row in results
            ]

    except Exception as e:
        log.error(f"Error in similarity search: {e}")
        return []
