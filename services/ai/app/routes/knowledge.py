# services/ai/app/routes/knowledge.py
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from typing import List, Optional
from pydantic import BaseModel

from netstacks_core.db import get_session, KnowledgeDocument
from netstacks_core.auth import get_current_user

router = APIRouter()


class DocumentResponse(BaseModel):
    doc_id: str
    title: str
    filename: str
    collection: str

    class Config:
        from_attributes = True


class SearchRequest(BaseModel):
    query: str
    collection: Optional[str] = None
    limit: int = 10


@router.get("/", response_model=dict)
async def list_documents(
    collection: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    user=Depends(get_current_user)
):
    """List knowledge base documents."""
    session = get_session()
    try:
        query = session.query(KnowledgeDocument)
        if collection:
            query = query.filter(KnowledgeDocument.collection == collection)

        docs = query.order_by(KnowledgeDocument.created_at.desc()).limit(limit).all()
        return {
            "success": True,
            "documents": [
                {
                    "doc_id": d.doc_id,
                    "title": d.title,
                    "filename": d.filename,
                    "collection": d.collection,
                    "doc_type": d.doc_type,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in docs
            ]
        }
    finally:
        session.close()


@router.post("/", response_model=dict)
async def upload_document(
    file: UploadFile = File(...),
    collection: str = "default",
    title: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Upload a document to knowledge base."""
    session = get_session()
    try:
        import uuid
        content = await file.read()

        doc = KnowledgeDocument(
            doc_id=str(uuid.uuid4()),
            title=title or file.filename,
            filename=file.filename,
            content=content.decode('utf-8', errors='ignore'),
            collection=collection,
            doc_type="upload",
        )
        session.add(doc)
        session.commit()
        return {"success": True, "doc_id": doc.doc_id}
    finally:
        session.close()


@router.get("/{doc_id}", response_model=dict)
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
                "doc_id": doc.doc_id,
                "title": doc.title,
                "filename": doc.filename,
                "collection": doc.collection,
                "doc_type": doc.doc_type,
                "content": doc.content,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
        }
    finally:
        session.close()


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, user=Depends(get_current_user)):
    """Delete a document."""
    session = get_session()
    try:
        doc = session.query(KnowledgeDocument).filter(
            KnowledgeDocument.doc_id == doc_id
        ).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        session.delete(doc)
        session.commit()
        return {"success": True, "message": "Document deleted"}
    finally:
        session.close()


@router.post("/search", response_model=dict)
async def search_documents(
    request: SearchRequest,
    user=Depends(get_current_user)
):
    """Search documents using vector similarity."""
    session = get_session()
    try:
        # TODO: Implement actual vector search with pgvector
        # For now, do a simple text search
        query = session.query(KnowledgeDocument)
        if request.collection:
            query = query.filter(KnowledgeDocument.collection == request.collection)

        # Simple text matching for now
        query = query.filter(
            KnowledgeDocument.content.ilike(f"%{request.query}%")
        )

        docs = query.limit(request.limit).all()
        return {
            "success": True,
            "results": [
                {
                    "doc_id": d.doc_id,
                    "title": d.title,
                    "filename": d.filename,
                    "collection": d.collection,
                    "score": 0.5,  # Placeholder score
                }
                for d in docs
            ]
        }
    finally:
        session.close()


@router.get("/collections/list")
async def list_collections(user=Depends(get_current_user)):
    """List available collections."""
    session = get_session()
    try:
        from sqlalchemy import distinct
        collections = session.query(distinct(KnowledgeDocument.collection)).all()
        return {
            "success": True,
            "collections": [c[0] for c in collections if c[0]]
        }
    finally:
        session.close()
