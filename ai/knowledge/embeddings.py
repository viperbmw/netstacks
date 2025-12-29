"""
Embedding Generation

Uses OpenAI's text-embedding-3-small model for generating embeddings.
"""

import logging
import requests
from typing import List, Optional

log = logging.getLogger(__name__)

# Embedding model configuration
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
MAX_TOKENS_PER_REQUEST = 8000  # Conservative limit for batch requests


def get_openai_api_key() -> Optional[str]:
    """Get OpenAI API key from database or environment"""
    import os

    # Try environment first
    api_key = os.environ.get('OPENAI_API_KEY')
    if api_key:
        return api_key

    # Try database
    try:
        import database as db
        from models import SystemSetting

        with db.get_db() as session:
            setting = session.query(SystemSetting).filter(
                SystemSetting.key == 'openai_api_key'
            ).first()

            if setting and setting.value:
                value = setting.value
                if value.startswith('enc:'):
                    from credential_encryption import decrypt_value
                    return decrypt_value(value)
                return value

    except Exception as e:
        log.warning(f"Could not get OpenAI key from database: {e}")

    return None


def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate embedding for a single text.

    Args:
        text: Text to embed

    Returns:
        List of floats (embedding vector) or None on error
    """
    api_key = get_openai_api_key()
    if not api_key:
        log.error("OpenAI API key not configured")
        return None

    try:
        response = requests.post(
            'https://api.openai.com/v1/embeddings',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': EMBEDDING_MODEL,
                'input': text
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            return data['data'][0]['embedding']
        else:
            log.error(f"OpenAI API error: {response.status_code} - {response.text}")
            return None

    except requests.exceptions.Timeout:
        log.error("OpenAI API timeout")
        return None
    except Exception as e:
        log.error(f"Error generating embedding: {e}")
        return None


def generate_embeddings_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts in batch.

    More efficient than individual calls for multiple documents.

    Args:
        texts: List of texts to embed

    Returns:
        List of embedding vectors (None for failed items)
    """
    if not texts:
        return []

    api_key = get_openai_api_key()
    if not api_key:
        log.error("OpenAI API key not configured")
        return [None] * len(texts)

    try:
        # OpenAI API accepts batch input
        response = requests.post(
            'https://api.openai.com/v1/embeddings',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': EMBEDDING_MODEL,
                'input': texts
            },
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            # Sort by index to ensure correct order
            embeddings_data = sorted(data['data'], key=lambda x: x['index'])
            return [item['embedding'] for item in embeddings_data]
        else:
            log.error(f"OpenAI API batch error: {response.status_code} - {response.text}")
            return [None] * len(texts)

    except Exception as e:
        log.error(f"Error generating batch embeddings: {e}")
        return [None] * len(texts)


def count_tokens(text: str) -> int:
    """
    Estimate token count for a text.

    Uses a simple approximation. For accurate counting,
    use tiktoken library.
    """
    # Rough estimate: ~4 characters per token for English
    return len(text) // 4
