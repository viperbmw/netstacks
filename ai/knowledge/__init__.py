"""
Knowledge Base Module

Provides document chunking, embedding generation, and vector search
for RAG (Retrieval Augmented Generation) capabilities.
"""

from .embeddings import generate_embedding, generate_embeddings_batch
from .chunking import chunk_document, ChunkingStrategy
from .indexer import index_document, reindex_collection

__all__ = [
    'generate_embedding',
    'generate_embeddings_batch',
    'chunk_document',
    'ChunkingStrategy',
    'index_document',
    'reindex_collection',
]
