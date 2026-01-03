# services/ai/app/routes/knowledge.py
"""
Knowledge Base Routes

Provides endpoints for managing knowledge documents and collections for RAG.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from pydantic import BaseModel

from netstacks_core.db import get_session, KnowledgeDocument, KnowledgeCollection
from netstacks_core.auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class DocumentResponse(BaseModel):
    doc_id: str
    title: str
    collection_id: Optional[str] = None
    doc_type: str

    class Config:
        from_attributes = True


class SearchRequest(BaseModel):
    query: str
    collection_id: Optional[str] = None
    limit: int = 10


class CollectionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    doc_type: str = "custom"


class DocumentCreate(BaseModel):
    title: str
    content: str
    collection_id: Optional[str] = None
    doc_type: str = "custom"
    source_url: Optional[str] = None


# ============================================================================
# Collection Endpoints
# ============================================================================

@router.get("/collections", response_model=dict)
async def list_collections(user=Depends(get_current_user)):
    """List all knowledge collections."""
    session = get_session()
    try:
        collections = session.query(KnowledgeCollection).order_by(
            KnowledgeCollection.name
        ).all()

        return {
            "success": True,
            "collections": [
                {
                    "id": c.collection_id,
                    "collection_id": c.collection_id,
                    "name": c.name,
                    "description": c.description,
                    "doc_type": c.doc_type,
                    "is_enabled": c.is_enabled,
                    "document_count": c.document_count or 0,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in collections
            ]
        }
    finally:
        session.close()


@router.post("/collections", response_model=dict)
async def create_collection(
    request: CollectionCreate,
    user=Depends(get_current_user)
):
    """Create a new knowledge collection."""
    session = get_session()
    try:
        # Check if name already exists
        existing = session.query(KnowledgeCollection).filter(
            KnowledgeCollection.name == request.name
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Collection name already exists")

        username = user.get("sub", "unknown") if isinstance(user, dict) else getattr(user, "sub", "unknown")

        collection = KnowledgeCollection(
            collection_id=str(uuid.uuid4()),
            name=request.name,
            description=request.description,
            doc_type=request.doc_type,
            created_by=username,
        )
        session.add(collection)
        session.commit()

        log.info(f"Created collection: {request.name}")

        return {
            "success": True,
            "collection_id": collection.collection_id,
            "message": "Collection created"
        }
    finally:
        session.close()


@router.get("/collections/{collection_id}", response_model=dict)
async def get_collection(collection_id: str, user=Depends(get_current_user)):
    """Get a specific collection."""
    session = get_session()
    try:
        collection = session.query(KnowledgeCollection).filter(
            KnowledgeCollection.collection_id == collection_id
        ).first()

        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        return {
            "success": True,
            "collection": {
                "id": collection.collection_id,
                "collection_id": collection.collection_id,
                "name": collection.name,
                "description": collection.description,
                "doc_type": collection.doc_type,
                "is_enabled": collection.is_enabled,
                "document_count": collection.document_count or 0,
                "created_at": collection.created_at.isoformat() if collection.created_at else None,
            }
        }
    finally:
        session.close()


@router.delete("/collections/{collection_id}", response_model=dict)
async def delete_collection(collection_id: str, user=Depends(get_current_user)):
    """Delete a collection and all its documents."""
    session = get_session()
    try:
        collection = session.query(KnowledgeCollection).filter(
            KnowledgeCollection.collection_id == collection_id
        ).first()

        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        session.delete(collection)
        session.commit()

        log.info(f"Deleted collection: {collection.name}")

        return {"success": True, "message": "Collection deleted"}
    finally:
        session.close()


# ============================================================================
# Document Endpoints
# ============================================================================

@router.get("/documents", response_model=dict)
async def list_documents(
    collection_id: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    user=Depends(get_current_user)
):
    """List knowledge base documents."""
    session = get_session()
    try:
        query = session.query(KnowledgeDocument)
        if collection_id:
            query = query.filter(KnowledgeDocument.collection_id == collection_id)

        docs = query.order_by(KnowledgeDocument.created_at.desc()).limit(limit).all()

        return {
            "success": True,
            "documents": [
                {
                    "id": d.doc_id,
                    "doc_id": d.doc_id,
                    "title": d.title,
                    "collection_id": d.collection_id,
                    "doc_type": d.doc_type,
                    "source_url": d.source_url,
                    "file_type": d.file_type,
                    "is_indexed": d.is_indexed,
                    "chunk_count": d.chunk_count or 0,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in docs
            ]
        }
    finally:
        session.close()


@router.post("/documents", response_model=dict)
async def create_document(
    request: DocumentCreate,
    user=Depends(get_current_user)
):
    """Create a new knowledge document."""
    session = get_session()
    try:
        username = user.get("sub", "unknown") if isinstance(user, dict) else getattr(user, "sub", "unknown")

        doc = KnowledgeDocument(
            doc_id=str(uuid.uuid4()),
            title=request.title,
            content=request.content,
            collection_id=request.collection_id,
            doc_type=request.doc_type,
            source_url=request.source_url,
            created_by=username,
        )
        session.add(doc)

        # Update collection document count
        if request.collection_id:
            collection = session.query(KnowledgeCollection).filter(
                KnowledgeCollection.collection_id == request.collection_id
            ).first()
            if collection:
                collection.document_count = (collection.document_count or 0) + 1

        session.commit()

        log.info(f"Created document: {request.title}")

        return {
            "success": True,
            "doc_id": doc.doc_id,
            "message": "Document created"
        }
    finally:
        session.close()


@router.post("/documents/upload", response_model=dict)
async def upload_document(
    file: UploadFile = File(...),
    collection_id: Optional[str] = None,
    title: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Upload a document file to knowledge base."""
    session = get_session()
    try:
        content = await file.read()
        username = user.get("sub", "unknown") if isinstance(user, dict) else getattr(user, "sub", "unknown")

        # Determine file type
        filename = file.filename or "unknown"
        file_type = filename.split(".")[-1].lower() if "." in filename else "txt"

        doc = KnowledgeDocument(
            doc_id=str(uuid.uuid4()),
            title=title or filename,
            content=content.decode('utf-8', errors='ignore'),
            collection_id=collection_id,
            doc_type="upload",
            file_path=filename,
            file_type=file_type,
            created_by=username,
        )
        session.add(doc)

        # Update collection document count
        if collection_id:
            collection = session.query(KnowledgeCollection).filter(
                KnowledgeCollection.collection_id == collection_id
            ).first()
            if collection:
                collection.document_count = (collection.document_count or 0) + 1

        session.commit()

        log.info(f"Uploaded document: {filename}")

        return {"success": True, "doc_id": doc.doc_id}
    finally:
        session.close()


@router.get("/documents/{doc_id}", response_model=dict)
async def get_document(doc_id: str, user=Depends(get_current_user)):
    """Get document by ID."""
    session = get_session()
    try:
        doc = session.query(KnowledgeDocument).filter(
            KnowledgeDocument.doc_id == doc_id
        ).first()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        return {
            "success": True,
            "document": {
                "id": doc.doc_id,
                "doc_id": doc.doc_id,
                "title": doc.title,
                "content": doc.content,
                "collection_id": doc.collection_id,
                "doc_type": doc.doc_type,
                "source_url": doc.source_url,
                "file_type": doc.file_type,
                "is_indexed": doc.is_indexed,
                "chunk_count": doc.chunk_count or 0,
                "metadata": doc.doc_metadata or {},
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
        }
    finally:
        session.close()


@router.delete("/documents/{doc_id}", response_model=dict)
async def delete_document(doc_id: str, user=Depends(get_current_user)):
    """Delete a document."""
    session = get_session()
    try:
        doc = session.query(KnowledgeDocument).filter(
            KnowledgeDocument.doc_id == doc_id
        ).first()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        collection_id = doc.collection_id

        session.delete(doc)

        # Update collection document count
        if collection_id:
            collection = session.query(KnowledgeCollection).filter(
                KnowledgeCollection.collection_id == collection_id
            ).first()
            if collection and collection.document_count:
                collection.document_count = max(0, collection.document_count - 1)

        session.commit()

        log.info(f"Deleted document: {doc_id}")

        return {"success": True, "message": "Document deleted"}
    finally:
        session.close()


@router.post("/documents/{doc_id}/reindex", response_model=dict)
async def reindex_document(doc_id: str, user=Depends(get_current_user)):
    """Reindex a document (regenerate embeddings)."""
    from app.services.knowledge_indexer import index_document

    result = await index_document(doc_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Indexing failed"))

    return {
        "success": True,
        "message": "Document indexed successfully",
        "doc_id": doc_id,
        "chunk_count": result.get("chunk_count", 0),
        "has_embeddings": result.get("has_embeddings", False),
    }


@router.post("/reindex-all", response_model=dict)
async def reindex_all_documents(user=Depends(get_current_user)):
    """Reindex all unindexed documents."""
    from app.services.knowledge_indexer import index_all_documents

    result = await index_all_documents()

    return {
        "success": True,
        "message": result.get("message"),
        "indexed": result.get("indexed", 0),
        "failed": result.get("failed", 0),
        "errors": result.get("errors"),
    }


# ============================================================================
# Search Endpoints
# ============================================================================

@router.post("/search", response_model=dict)
async def search_documents(
    request: SearchRequest,
    user=Depends(get_current_user)
):
    """Search documents using text matching on indexed chunks."""
    from sqlalchemy import text as sql_text

    session = get_session()
    try:
        # Search in indexed chunks for better results
        if request.collection_id:
            result = session.execute(
                sql_text("""
                    SELECT DISTINCT ON (d.doc_id)
                        d.doc_id,
                        d.title,
                        d.collection_id,
                        d.doc_type,
                        e.chunk_text
                    FROM knowledge_embeddings e
                    JOIN knowledge_documents d ON e.doc_id = d.doc_id
                    WHERE d.collection_id = :collection_id
                      AND (e.chunk_text ILIKE :query OR d.title ILIKE :query)
                    LIMIT :limit
                """),
                {
                    "collection_id": request.collection_id,
                    "query": f"%{request.query}%",
                    "limit": request.limit,
                }
            )
        else:
            result = session.execute(
                sql_text("""
                    SELECT DISTINCT ON (d.doc_id)
                        d.doc_id,
                        d.title,
                        d.collection_id,
                        d.doc_type,
                        e.chunk_text
                    FROM knowledge_embeddings e
                    JOIN knowledge_documents d ON e.doc_id = d.doc_id
                    WHERE e.chunk_text ILIKE :query OR d.title ILIKE :query
                    LIMIT :limit
                """),
                {
                    "query": f"%{request.query}%",
                    "limit": request.limit,
                }
            )

        results = []
        for row in result:
            # Get snippet from matching chunk
            snippet = row.chunk_text[:200] + "..." if len(row.chunk_text) > 200 else row.chunk_text
            results.append({
                "doc_id": row.doc_id,
                "title": row.title,
                "collection_id": row.collection_id,
                "doc_type": row.doc_type,
                "score": 0.8,  # Placeholder score until vector search
                "snippet": snippet,
            })

        return {
            "success": True,
            "query": request.query,
            "results": results
        }
    finally:
        session.close()


# ============================================================================
# Legacy endpoints for backwards compatibility
# ============================================================================

@router.get("/", response_model=dict)
async def list_documents_legacy(
    collection: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    user=Depends(get_current_user)
):
    """List knowledge base documents (legacy endpoint)."""
    return await list_documents(collection_id=collection, limit=limit, user=user)


@router.get("/collections/list")
async def list_collections_legacy(user=Depends(get_current_user)):
    """List available collections (legacy endpoint)."""
    result = await list_collections(user=user)
    # Return just collection names for legacy compatibility
    return {
        "success": True,
        "collections": [c["name"] for c in result.get("collections", [])]
    }
