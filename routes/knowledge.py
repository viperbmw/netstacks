"""
Knowledge Base Routes

HTTP routes for knowledge document management and search.
"""

import logging
import uuid
import os
from flask import Blueprint, render_template, request, jsonify, session
from functools import wraps
from datetime import datetime

import database as db

log = logging.getLogger(__name__)

knowledge_bp = Blueprint('knowledge', __name__, url_prefix='/knowledge')


def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# Knowledge UI Routes
# ============================================================================

@knowledge_bp.route('/')
@login_required
def knowledge_page():
    """Knowledge base management page"""
    return render_template('knowledge.html')


# ============================================================================
# Collection API Routes
# ============================================================================

@knowledge_bp.route('/api/collections', methods=['GET'])
@login_required
def list_collections():
    """List knowledge collections"""
    try:
        from models import KnowledgeCollection, KnowledgeDocument
        from sqlalchemy import func

        with db.get_db() as db_session:
            collections = db_session.query(
                KnowledgeCollection.id,
                KnowledgeCollection.name,
                KnowledgeCollection.description,
                func.count(KnowledgeDocument.doc_id).label('doc_count')
            ).outerjoin(
                KnowledgeDocument,
                KnowledgeCollection.id == KnowledgeDocument.collection_id
            ).group_by(KnowledgeCollection.id).all()

            return jsonify({
                'collections': [
                    {
                        'id': c[0],
                        'name': c[1],
                        'description': c[2],
                        'document_count': c[3],
                    }
                    for c in collections
                ]
            })

    except Exception as e:
        log.error(f"Error listing collections: {e}")
        return jsonify({'error': str(e)}), 500


@knowledge_bp.route('/api/collections', methods=['POST'])
@login_required
def create_collection():
    """Create a new collection"""
    try:
        from models import KnowledgeCollection

        data = request.get_json()

        with db.get_db() as db_session:
            collection = KnowledgeCollection(
                name=data.get('name'),
                description=data.get('description', ''),
            )
            db_session.add(collection)
            db_session.commit()

            return jsonify({
                'id': collection.id,
                'message': 'Collection created'
            }), 201

    except Exception as e:
        log.error(f"Error creating collection: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Document API Routes
# ============================================================================

@knowledge_bp.route('/api/documents', methods=['GET'])
@login_required
def list_documents():
    """List documents with optional collection filter"""
    try:
        from models import KnowledgeDocument, KnowledgeCollection

        collection_id = request.args.get('collection_id', type=int)
        limit = request.args.get('limit', 100, type=int)

        with db.get_db() as db_session:
            query = db_session.query(
                KnowledgeDocument,
                KnowledgeCollection.name.label('collection_name')
            ).outerjoin(
                KnowledgeCollection,
                KnowledgeDocument.collection_id == KnowledgeCollection.id
            )

            if collection_id:
                query = query.filter(KnowledgeDocument.collection_id == collection_id)

            docs = query.order_by(KnowledgeDocument.created_at.desc()).limit(limit).all()

            return jsonify({
                'documents': [
                    {
                        'doc_id': d[0].doc_id,
                        'title': d[0].title,
                        'doc_type': d[0].doc_type,
                        'source': d[0].source,
                        'collection': d[1],
                        'is_indexed': d[0].is_indexed,
                        'created_at': d[0].created_at.isoformat() if d[0].created_at else None,
                    }
                    for d in docs
                ]
            })

    except Exception as e:
        log.error(f"Error listing documents: {e}")
        return jsonify({'error': str(e)}), 500


@knowledge_bp.route('/api/documents', methods=['POST'])
@login_required
def upload_document():
    """Upload a new document"""
    try:
        from models import KnowledgeDocument

        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            content = data.get('content', '')
            title = data.get('title')
            doc_type = data.get('doc_type', 'text')
            collection_id = data.get('collection_id')
            source = data.get('source', 'manual')
        else:
            # File upload
            if 'file' not in request.files:
                return jsonify({'error': 'No file provided'}), 400

            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400

            title = request.form.get('title', file.filename)
            doc_type = _detect_doc_type(file.filename)
            collection_id = request.form.get('collection_id', type=int)
            source = request.form.get('source', 'upload')

            # Read file content
            content = _read_file_content(file, doc_type)

        doc_id = str(uuid.uuid4())

        with db.get_db() as db_session:
            doc = KnowledgeDocument(
                doc_id=doc_id,
                title=title,
                content=content,
                doc_type=doc_type,
                source=source,
                collection_id=collection_id,
                is_indexed=False,
            )
            db_session.add(doc)
            db_session.commit()

        # Queue for indexing
        _queue_document_indexing(doc_id)

        return jsonify({
            'doc_id': doc_id,
            'message': 'Document uploaded and queued for indexing'
        }), 201

    except Exception as e:
        log.error(f"Error uploading document: {e}")
        return jsonify({'error': str(e)}), 500


@knowledge_bp.route('/api/documents/<doc_id>', methods=['GET'])
@login_required
def get_document(doc_id):
    """Get document details"""
    try:
        from models import KnowledgeDocument, KnowledgeEmbedding

        with db.get_db() as db_session:
            doc = db_session.query(KnowledgeDocument).filter(
                KnowledgeDocument.doc_id == doc_id
            ).first()

            if not doc:
                return jsonify({'error': 'Document not found'}), 404

            # Get chunk count
            chunk_count = db_session.query(KnowledgeEmbedding).filter(
                KnowledgeEmbedding.doc_id == doc_id
            ).count()

            return jsonify({
                'doc_id': doc.doc_id,
                'title': doc.title,
                'content': doc.content,
                'doc_type': doc.doc_type,
                'source': doc.source,
                'collection_id': doc.collection_id,
                'is_indexed': doc.is_indexed,
                'chunk_count': chunk_count,
                'created_at': doc.created_at.isoformat() if doc.created_at else None,
            })

    except Exception as e:
        log.error(f"Error getting document: {e}")
        return jsonify({'error': str(e)}), 500


@knowledge_bp.route('/api/documents/<doc_id>', methods=['DELETE'])
@login_required
def delete_document(doc_id):
    """Delete a document and its embeddings"""
    try:
        from models import KnowledgeDocument, KnowledgeEmbedding

        with db.get_db() as db_session:
            # Delete embeddings first
            db_session.query(KnowledgeEmbedding).filter(
                KnowledgeEmbedding.doc_id == doc_id
            ).delete()

            # Delete document
            db_session.query(KnowledgeDocument).filter(
                KnowledgeDocument.doc_id == doc_id
            ).delete()

            db_session.commit()

            return jsonify({'message': 'Document deleted'})

    except Exception as e:
        log.error(f"Error deleting document: {e}")
        return jsonify({'error': str(e)}), 500


@knowledge_bp.route('/api/documents/index-all', methods=['POST'])
@login_required
def index_all_documents():
    """Index all pending documents"""
    try:
        from models import KnowledgeDocument

        with db.get_db() as db_session:
            pending_docs = db_session.query(KnowledgeDocument).filter(
                KnowledgeDocument.is_indexed == False
            ).all()

            if not pending_docs:
                return jsonify({'message': 'No pending documents to index', 'indexed': 0})

            indexed_count = 0
            for doc in pending_docs:
                try:
                    _index_document_now(doc.doc_id)
                    indexed_count += 1
                except Exception as e:
                    log.error(f"Error indexing {doc.doc_id}: {e}")

            return jsonify({
                'message': f'Indexed {indexed_count} documents',
                'indexed': indexed_count,
                'total_pending': len(pending_docs)
            })

    except Exception as e:
        log.error(f"Error indexing all documents: {e}")
        return jsonify({'error': str(e)}), 500


@knowledge_bp.route('/api/documents/<doc_id>/reindex', methods=['POST'])
@login_required
def reindex_document(doc_id):
    """Re-index a document"""
    try:
        from models import KnowledgeDocument, KnowledgeEmbedding

        with db.get_db() as db_session:
            doc = db_session.query(KnowledgeDocument).filter(
                KnowledgeDocument.doc_id == doc_id
            ).first()

            if not doc:
                return jsonify({'error': 'Document not found'}), 404

            # Delete existing embeddings
            db_session.query(KnowledgeEmbedding).filter(
                KnowledgeEmbedding.doc_id == doc_id
            ).delete()

            doc.is_indexed = False
            db_session.commit()

        # Queue for re-indexing
        _queue_document_indexing(doc_id)

        return jsonify({'message': 'Document queued for re-indexing'})

    except Exception as e:
        log.error(f"Error reindexing document: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Search API Routes
# ============================================================================

@knowledge_bp.route('/api/search', methods=['POST'])
@login_required
def search_knowledge():
    """Search knowledge base using vector similarity"""
    try:
        from ai.tools import KnowledgeSearchTool

        data = request.get_json()
        query = data.get('query', '')
        collection = data.get('collection')
        doc_type = data.get('doc_type')
        limit = data.get('limit', 10)

        if not query:
            return jsonify({'error': 'Query required'}), 400

        tool = KnowledgeSearchTool()
        result = tool.execute(
            query=query,
            collection=collection,
            doc_type=doc_type,
            limit=limit
        )

        if result.success:
            return jsonify(result.data)
        else:
            return jsonify({'error': result.error}), 500

    except Exception as e:
        log.error(f"Error searching knowledge: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Helper Functions
# ============================================================================

def _detect_doc_type(filename):
    """Detect document type from filename"""
    ext = os.path.splitext(filename)[1].lower()
    type_map = {
        '.md': 'markdown',
        '.txt': 'text',
        '.pdf': 'pdf',
        '.html': 'html',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.json': 'json',
    }
    return type_map.get(ext, 'text')


def _read_file_content(file, doc_type):
    """Read content from uploaded file"""
    if doc_type == 'pdf':
        # PDF extraction would require PyPDF2 or similar
        return f"[PDF content extraction not implemented: {file.filename}]"

    # For text-based files, read directly
    content = file.read()
    if isinstance(content, bytes):
        content = content.decode('utf-8', errors='ignore')
    return content


def _queue_document_indexing(doc_id):
    """Queue document for embedding generation"""
    try:
        log.info(f"Indexing document {doc_id}")
        _index_document_now(doc_id)
    except Exception as e:
        log.error(f"Error indexing document: {e}")


def _index_document_now(doc_id):
    """Generate embeddings for a document immediately using pgvector"""
    from models import KnowledgeDocument
    from sqlalchemy import text as sql_text

    with db.get_db() as db_session:
        doc = db_session.query(KnowledgeDocument).filter(
            KnowledgeDocument.doc_id == doc_id
        ).first()

        if not doc:
            log.error(f"Document not found: {doc_id}")
            return

        # Chunk the document
        chunks = _chunk_text(doc.content, chunk_size=1000, overlap=200)
        log.info(f"Document {doc_id} split into {len(chunks)} chunks")

        # Generate embeddings for each chunk
        for i, chunk_text in enumerate(chunks):
            try:
                embedding = _generate_embedding(chunk_text)
                if not embedding:
                    log.error(f"Failed to generate embedding for chunk {i}")
                    return

                # Store embedding using raw SQL for pgvector compatibility
                # Note: Use CAST() syntax instead of :: to avoid SQLAlchemy parameter parsing issues
                db_session.execute(
                    sql_text("""
                        INSERT INTO knowledge_embeddings
                        (doc_id, chunk_index, chunk_text, embedding, created_at)
                        VALUES (:doc_id, :chunk_index, :chunk_text, CAST(:embedding AS vector), NOW())
                    """),
                    {
                        'doc_id': doc_id,
                        'chunk_index': i,
                        'chunk_text': chunk_text,
                        'embedding': str(embedding)
                    }
                )

            except Exception as e:
                log.error(f"Error generating embedding for chunk {i}: {e}")
                return

        # Mark document as indexed
        doc.is_indexed = True
        db_session.commit()
        log.info(f"Document {doc_id} indexed successfully with {len(chunks)} chunks")


def _generate_embedding(text):
    """Generate embedding using OpenAI API"""
    import requests
    from sqlalchemy import text as sql_text

    try:
        with db.get_db() as session:
            result = session.execute(
                sql_text("SELECT api_key FROM llm_providers WHERE name = 'openai' AND is_enabled = true")
            ).fetchone()

            if not result or not result[0]:
                log.error("OpenAI API key not configured")
                return None

            api_key = result[0]
            # Handle space-separated key format (some keys have extra data)
            if ' ' in api_key:
                api_key = api_key.split(' ')[0]
            # Handle encrypted keys
            if api_key.startswith('enc:'):
                try:
                    from credential_encryption import decrypt_value
                    api_key = decrypt_value(api_key)
                except Exception as e:
                    log.error(f"Failed to decrypt API key: {e}")
                    return None

        response = requests.post(
            'https://api.openai.com/v1/embeddings',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'text-embedding-3-small',
                'input': text
            },
            timeout=30
        )

        if response.status_code == 200:
            return response.json()['data'][0]['embedding']
        else:
            log.error(f"OpenAI API error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        log.error(f"OpenAI embedding error: {e}")
        return None


def _chunk_text(text, chunk_size=1000, overlap=200):
    """Split text into overlapping chunks"""
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size

        # Try to break at paragraph or sentence boundary
        if end < text_len:
            # Look for paragraph break
            para_break = text.rfind('\n\n', start, end)
            if para_break > start + chunk_size // 2:
                end = para_break + 2
            else:
                # Look for sentence break
                for sep in ['. ', '.\n', '! ', '? ']:
                    sent_break = text.rfind(sep, start, end)
                    if sent_break > start + chunk_size // 2:
                        end = sent_break + len(sep)
                        break

        chunks.append(text[start:end].strip())
        start = end - overlap

    return [c for c in chunks if c]  # Filter empty chunks
