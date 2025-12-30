# /home/cwdavis/netstacks/ai/knowledge/platform_docs.py
"""
Platform Documentation Loader
Loads NetStacks documentation into knowledge base.
"""
import os
import logging
from pathlib import Path
from typing import List, Dict

log = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).parent / 'netstacks_docs'
COLLECTION_NAME = 'netstacks-platform'


def get_platform_docs() -> List[Dict]:
    """Load all platform documentation files."""
    docs = []

    if not DOCS_DIR.exists():
        log.warning(f"Platform docs directory not found: {DOCS_DIR}")
        return docs

    for md_file in DOCS_DIR.glob('*.md'):
        try:
            content = md_file.read_text()
            docs.append({
                'filename': md_file.name,
                'title': _extract_title(content),
                'content': content,
                'collection': COLLECTION_NAME,
            })
        except Exception as e:
            log.error(f"Error reading {md_file}: {e}")

    return docs


def _extract_title(content: str) -> str:
    """Extract title from markdown content."""
    for line in content.split('\n'):
        if line.startswith('# '):
            return line[2:].strip()
    return 'Untitled'


def sync_platform_docs_to_knowledge_base():
    """
    Sync platform documentation to the knowledge base.
    Called on startup or manually to update embeddings.
    """
    try:
        import database as db

        docs = get_platform_docs()
        if not docs:
            log.info("No platform docs to sync")
            return

        for doc in docs:
            # Check if doc already exists
            existing = db.get_knowledge_document_by_name(
                doc['filename'],
                collection=COLLECTION_NAME
            )

            if existing:
                # Update if content changed
                if existing.get('content') != doc['content']:
                    db.update_knowledge_document(
                        existing['doc_id'],
                        content=doc['content'],
                        title=doc['title']
                    )
                    log.info(f"Updated platform doc: {doc['filename']}")
            else:
                # Create new
                db.create_knowledge_document(
                    filename=doc['filename'],
                    title=doc['title'],
                    content=doc['content'],
                    collection=COLLECTION_NAME,
                    doc_type='platform_docs'
                )
                log.info(f"Created platform doc: {doc['filename']}")

        log.info(f"Synced {len(docs)} platform docs to knowledge base")

    except Exception as e:
        log.error(f"Error syncing platform docs: {e}", exc_info=True)
