"""
LLM Client Factory

Creates LLM clients based on provider configuration.
"""

import logging
from typing import Optional, List, Dict, Any

from .base import LLMClient
from .anthropic_client import AnthropicClient
from .openrouter_client import OpenRouterClient

log = logging.getLogger(__name__)

# Registry of available providers
PROVIDERS = {
    'anthropic': AnthropicClient,
    'openrouter': OpenRouterClient,
}


def get_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs
) -> LLMClient:
    """
    Get an LLM client instance.

    Args:
        provider: Provider name ('anthropic', 'openrouter'). If None, uses default.
        model: Model ID. If None, uses provider's default.
        api_key: API key. If None, fetches from database.
        **kwargs: Additional provider-specific options.

    Returns:
        Configured LLMClient instance.

    Raises:
        ValueError: If provider not found or not configured.
    """
    # Import here to avoid circular imports
    try:
        import database as db
        from shared.netstacks_core.db.models import LLMProvider
    except ImportError:
        # Fallback for standalone usage
        db = None
        LLMProvider = None

    # If no provider specified, get default from database
    if provider is None and db is not None:
        with db.get_db() as session:
            default_provider = session.query(LLMProvider).filter(
                LLMProvider.is_default == True,
                LLMProvider.is_enabled == True
            ).first()

            if default_provider:
                provider = default_provider.name
                if api_key is None:
                    api_key = _decrypt_api_key(default_provider.api_key)
                if model is None:
                    model = default_provider.default_model
            else:
                raise ValueError("No default LLM provider configured. Please configure an LLM provider in Settings.")

    if provider is None:
        provider = 'anthropic'  # Fallback default

    # Get provider class
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown LLM provider: {provider}. Available: {list(PROVIDERS.keys())}")

    provider_class = PROVIDERS[provider]

    # Get API key from database if not provided
    if api_key is None and db is not None:
        with db.get_db() as session:
            db_provider = session.query(LLMProvider).filter(
                LLMProvider.name == provider
            ).first()

            if db_provider and db_provider.is_enabled:
                api_key = _decrypt_api_key(db_provider.api_key)
                if model is None:
                    model = db_provider.default_model
            else:
                raise ValueError(f"LLM provider '{provider}' not configured or disabled.")

    if api_key is None:
        raise ValueError(f"No API key provided for LLM provider: {provider}")

    # Set default models if not specified
    if model is None:
        default_models = {
            'anthropic': 'claude-sonnet-4-20250514',
            'openrouter': 'anthropic/claude-3.5-sonnet',
        }
        model = default_models.get(provider, 'claude-sonnet-4-20250514')

    log.info(f"Creating LLM client: provider={provider}, model={model}")
    return provider_class(api_key=api_key, model=model, **kwargs)


def get_available_providers() -> List[Dict[str, Any]]:
    """
    Get list of available LLM providers with their status.

    Returns:
        List of provider info dicts with name, display_name, is_enabled, is_default.
    """
    try:
        import database as db
        from shared.netstacks_core.db.models import LLMProvider
    except ImportError:
        # Return static list if database not available
        return [
            {'name': 'anthropic', 'display_name': 'Anthropic Claude', 'is_enabled': False, 'is_default': True},
            {'name': 'openrouter', 'display_name': 'OpenRouter', 'is_enabled': False, 'is_default': False},
        ]

    providers = []
    with db.get_db() as session:
        db_providers = session.query(LLMProvider).all()
        for p in db_providers:
            providers.append({
                'name': p.name,
                'display_name': p.display_name or p.name,
                'is_enabled': p.is_enabled,
                'is_default': p.is_default,
                'default_model': p.default_model,
                'available_models': p.available_models or [],
            })

    return providers


def _decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt API key from database"""
    if not encrypted_key:
        return ""

    # Check if it's encrypted (has enc: prefix)
    if encrypted_key.startswith('enc:'):
        try:
            from credential_encryption import decrypt_value
            return decrypt_value(encrypted_key)
        except ImportError:
            log.warning("Credential encryption not available, using key as-is")
            return encrypted_key[4:]  # Strip enc: prefix
        except Exception as e:
            log.error(f"Failed to decrypt API key: {e}")
            return ""

    # Plain text key (legacy or development)
    return encrypted_key
