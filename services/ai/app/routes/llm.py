# services/ai/app/routes/llm.py
"""
LLM provider management routes.

Provides endpoints for managing LLM provider configurations.
"""

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from netstacks_core.db import get_session, LLMProvider
from netstacks_core.auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter()


class LLMProviderCreate(BaseModel):
    name: str = Field(..., description="Provider name (e.g., anthropic, openrouter)")
    display_name: Optional[str] = None
    api_key: str = Field(..., description="API key (stored encrypted)")
    api_base_url: Optional[str] = Field(None, description="Custom API base URL")
    default_model: Optional[str] = Field(None, description="Default model for this provider")
    available_models: Optional[List[Dict[str, str]]] = None
    is_enabled: bool = True
    is_default: bool = False
    config: Optional[Dict[str, Any]] = None


class LLMProviderUpdate(BaseModel):
    display_name: Optional[str] = None
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    default_model: Optional[str] = None
    available_models: Optional[List[Dict[str, str]]] = None
    is_enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


class LLMTestRequest(BaseModel):
    name: str
    model: Optional[str] = None
    prompt: str = "Hello, this is a test."


@router.get("/", response_model=dict)
async def list_providers(user=Depends(get_current_user)):
    """List all configured LLM providers."""
    session = get_session()
    try:
        providers = session.query(LLMProvider).all()

        return {
            "success": True,
            "providers": [
                {
                    "id": p.id,
                    "name": p.name,
                    "display_name": p.display_name or p.name,
                    "api_base_url": p.api_base_url,
                    "default_model": p.default_model,
                    "available_models": p.available_models or [],
                    "is_enabled": p.is_enabled,
                    "is_default": p.is_default,
                    "has_api_key": bool(p.api_key),
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in providers
            ]
        }
    finally:
        session.close()


@router.get("/{name}", response_model=dict)
async def get_provider(name: str, user=Depends(get_current_user)):
    """Get provider details by name."""
    session = get_session()
    try:
        provider = session.query(LLMProvider).filter(
            LLMProvider.name == name
        ).first()

        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        return {
            "success": True,
            "provider": {
                "id": provider.id,
                "name": provider.name,
                "display_name": provider.display_name or provider.name,
                "api_base_url": provider.api_base_url,
                "default_model": provider.default_model,
                "available_models": provider.available_models or [],
                "is_enabled": provider.is_enabled,
                "is_default": provider.is_default,
                "config": provider.config or {},
                "has_api_key": bool(provider.api_key),
                "created_at": provider.created_at.isoformat() if provider.created_at else None,
                "updated_at": provider.updated_at.isoformat() if provider.updated_at else None,
            }
        }
    finally:
        session.close()


@router.post("/", response_model=dict)
async def create_provider(request: LLMProviderCreate, user=Depends(get_current_user)):
    """Create or update an LLM provider configuration."""
    session = get_session()
    try:
        # Check if provider already exists
        existing = session.query(LLMProvider).filter(
            LLMProvider.name == request.name
        ).first()

        if existing:
            # Update existing provider
            existing.display_name = request.display_name or existing.display_name
            if request.api_key:
                existing.api_key = request.api_key  # TODO: Encrypt
            existing.api_base_url = request.api_base_url or existing.api_base_url
            existing.default_model = request.default_model or existing.default_model
            if request.available_models:
                existing.available_models = request.available_models
            existing.is_enabled = request.is_enabled
            existing.is_default = request.is_default
            if request.config:
                existing.config = request.config
            session.commit()

            log.info(f"Updated LLM provider: {request.name}")
            return {
                "success": True,
                "message": "Provider updated",
                "id": existing.id
            }
        else:
            # Create new provider
            provider = LLMProvider(
                name=request.name,
                display_name=request.display_name,
                api_key=request.api_key,  # TODO: Encrypt
                api_base_url=request.api_base_url,
                default_model=request.default_model,
                available_models=request.available_models or [],
                is_enabled=request.is_enabled,
                is_default=request.is_default,
                config=request.config or {},
            )
            session.add(provider)
            session.commit()

            log.info(f"Created LLM provider: {request.name}")
            return {
                "success": True,
                "message": "Provider created",
                "id": provider.id
            }
    finally:
        session.close()


@router.put("/{name}", response_model=dict)
async def update_provider(
    name: str,
    request: LLMProviderUpdate,
    user=Depends(get_current_user)
):
    """Update an LLM provider configuration."""
    session = get_session()
    try:
        provider = session.query(LLMProvider).filter(
            LLMProvider.name == name
        ).first()

        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        if request.display_name is not None:
            provider.display_name = request.display_name
        if request.api_key is not None:
            provider.api_key = request.api_key  # TODO: Encrypt
        if request.api_base_url is not None:
            provider.api_base_url = request.api_base_url
        if request.default_model is not None:
            provider.default_model = request.default_model
        if request.available_models is not None:
            provider.available_models = request.available_models
        if request.is_enabled is not None:
            provider.is_enabled = request.is_enabled
        if request.is_default is not None:
            provider.is_default = request.is_default
        if request.config is not None:
            provider.config = request.config

        session.commit()

        log.info(f"Updated LLM provider: {name}")
        return {"success": True, "message": "Provider updated"}
    finally:
        session.close()


@router.delete("/{name}", response_model=dict)
async def delete_provider(name: str, user=Depends(get_current_user)):
    """Delete an LLM provider configuration."""
    session = get_session()
    try:
        provider = session.query(LLMProvider).filter(
            LLMProvider.name == name
        ).first()

        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        session.delete(provider)
        session.commit()

        log.info(f"Deleted LLM provider: {name}")
        return {"success": True, "message": "Provider deleted"}
    finally:
        session.close()


@router.post("/test", response_model=dict)
async def test_provider(request: LLMTestRequest, user=Depends(get_current_user)):
    """Test connection to an LLM provider."""
    session = get_session()
    try:
        provider = session.query(LLMProvider).filter(
            LLMProvider.name == request.name
        ).first()

        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        if not provider.api_key:
            raise HTTPException(status_code=400, detail="No API key configured")

        # TODO: Implement actual LLM test call
        # For now, return a placeholder response
        log.info(f"Testing LLM provider: {request.name}")

        return {
            "success": True,
            "message": "Provider connection test not yet implemented",
            "provider": request.name,
            "model": request.model or provider.default_model
        }
    finally:
        session.close()


@router.get("/models/{name}", response_model=dict)
async def get_provider_models(name: str, user=Depends(get_current_user)):
    """Get available models for a provider."""
    session = get_session()
    try:
        provider = session.query(LLMProvider).filter(
            LLMProvider.name == name
        ).first()

        if provider and provider.available_models:
            return {
                "success": True,
                "provider": name,
                "models": provider.available_models
            }

        # Return default models for known providers
        default_models = {
            "anthropic": [
                {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
                {"id": "claude-opus-4-20250514", "name": "Claude Opus 4"},
                {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
            ],
            "openrouter": [
                {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet"},
                {"id": "anthropic/claude-3-opus", "name": "Claude 3 Opus"},
                {"id": "openai/gpt-4-turbo", "name": "GPT-4 Turbo"},
            ],
            "openai": [
                {"id": "gpt-4o", "name": "GPT-4o"},
                {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
                {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
            ],
            "ollama": [
                {"id": "llama3.2", "name": "Llama 3.2"},
                {"id": "mistral", "name": "Mistral"},
                {"id": "codellama", "name": "Code Llama"},
            ],
        }

        return {
            "success": True,
            "provider": name,
            "models": default_models.get(name, [])
        }
    finally:
        session.close()
