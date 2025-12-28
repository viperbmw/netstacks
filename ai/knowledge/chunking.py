"""
Document Chunking

Strategies for splitting documents into chunks suitable for embedding.
"""

import logging
import re
from enum import Enum
from typing import List, Dict, Any
from dataclasses import dataclass

log = logging.getLogger(__name__)


class ChunkingStrategy(Enum):
    """Chunking strategies for different document types"""
    FIXED_SIZE = "fixed_size"
    SEMANTIC = "semantic"
    MARKDOWN = "markdown"
    CODE = "code"


@dataclass
class Chunk:
    """Represents a document chunk"""
    index: int
    text: str
    token_count: int
    metadata: Dict[str, Any] = None


# Configuration
DEFAULT_CHUNK_SIZE = 500  # Target tokens per chunk
DEFAULT_CHUNK_OVERLAP = 50  # Overlap tokens between chunks
MAX_CHUNK_SIZE = 1000  # Maximum chunk size


def chunk_document(
    content: str,
    doc_type: str = "text",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP
) -> List[Chunk]:
    """
    Split document into chunks based on document type.

    Args:
        content: Document content
        doc_type: Type of document (text, markdown, code, etc.)
        chunk_size: Target tokens per chunk
        overlap: Token overlap between chunks

    Returns:
        List of Chunk objects
    """
    if not content or not content.strip():
        return []

    # Choose strategy based on doc type
    if doc_type in ('markdown', 'md'):
        chunks = _chunk_markdown(content, chunk_size, overlap)
    elif doc_type in ('code', 'python', 'yaml', 'json'):
        chunks = _chunk_code(content, chunk_size, overlap)
    else:
        chunks = _chunk_fixed_size(content, chunk_size, overlap)

    return chunks


def _chunk_fixed_size(
    content: str,
    chunk_size: int,
    overlap: int
) -> List[Chunk]:
    """
    Simple fixed-size chunking with overlap.

    Tries to break at sentence boundaries when possible.
    """
    chunks = []

    # Estimate characters per token
    chars_per_token = 4
    target_chars = chunk_size * chars_per_token
    overlap_chars = overlap * chars_per_token

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', content)

    current_chunk = ""
    chunk_index = 0

    for sentence in sentences:
        # Check if adding sentence exceeds limit
        if len(current_chunk) + len(sentence) > target_chars:
            if current_chunk:
                chunks.append(Chunk(
                    index=chunk_index,
                    text=current_chunk.strip(),
                    token_count=len(current_chunk) // chars_per_token
                ))
                chunk_index += 1

                # Overlap: keep end of previous chunk
                if overlap_chars > 0 and len(current_chunk) > overlap_chars:
                    current_chunk = current_chunk[-overlap_chars:]
                else:
                    current_chunk = ""

        current_chunk += " " + sentence

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(Chunk(
            index=chunk_index,
            text=current_chunk.strip(),
            token_count=len(current_chunk) // chars_per_token
        ))

    return chunks


def _chunk_markdown(
    content: str,
    chunk_size: int,
    overlap: int
) -> List[Chunk]:
    """
    Semantic chunking for markdown documents.

    Preserves heading hierarchy and splits at logical boundaries.
    """
    chunks = []
    chars_per_token = 4
    target_chars = chunk_size * chars_per_token

    # Split by headers
    header_pattern = r'^(#{1,6})\s+(.+)$'
    lines = content.split('\n')

    current_chunk = ""
    current_header = ""
    chunk_index = 0

    for line in lines:
        header_match = re.match(header_pattern, line)

        if header_match:
            # Found a header - might be a good split point
            if len(current_chunk) > target_chars // 2:
                # Save current chunk
                chunks.append(Chunk(
                    index=chunk_index,
                    text=current_chunk.strip(),
                    token_count=len(current_chunk) // chars_per_token,
                    metadata={'header': current_header}
                ))
                chunk_index += 1
                current_chunk = ""

            current_header = header_match.group(2)

        current_chunk += line + "\n"

        # Force split if too large
        if len(current_chunk) > target_chars * 1.5:
            chunks.append(Chunk(
                index=chunk_index,
                text=current_chunk.strip(),
                token_count=len(current_chunk) // chars_per_token,
                metadata={'header': current_header}
            ))
            chunk_index += 1
            current_chunk = ""

    # Last chunk
    if current_chunk.strip():
        chunks.append(Chunk(
            index=chunk_index,
            text=current_chunk.strip(),
            token_count=len(current_chunk) // chars_per_token,
            metadata={'header': current_header}
        ))

    return chunks


def _chunk_code(
    content: str,
    chunk_size: int,
    overlap: int
) -> List[Chunk]:
    """
    Chunking for code files.

    Tries to split at function/class boundaries.
    """
    chunks = []
    chars_per_token = 4
    target_chars = chunk_size * chars_per_token

    # Try to split at function/class definitions
    # This is a simplified approach - real implementation would use AST
    function_pattern = r'^(?:def |class |function |const |let |var )'

    lines = content.split('\n')
    current_chunk = ""
    chunk_index = 0

    for i, line in enumerate(lines):
        is_boundary = bool(re.match(function_pattern, line.strip()))

        if is_boundary and len(current_chunk) > target_chars // 2:
            # Split before this function/class
            chunks.append(Chunk(
                index=chunk_index,
                text=current_chunk.strip(),
                token_count=len(current_chunk) // chars_per_token
            ))
            chunk_index += 1
            current_chunk = ""

        current_chunk += line + "\n"

        # Force split if too large
        if len(current_chunk) > target_chars * 1.5:
            chunks.append(Chunk(
                index=chunk_index,
                text=current_chunk.strip(),
                token_count=len(current_chunk) // chars_per_token
            ))
            chunk_index += 1
            current_chunk = ""

    # Last chunk
    if current_chunk.strip():
        chunks.append(Chunk(
            index=chunk_index,
            text=current_chunk.strip(),
            token_count=len(current_chunk) // chars_per_token
        ))

    return chunks
