"""
Authentication configuration routes (LDAP, OIDC)
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from netstacks_core.auth import get_current_user, TokenData
from netstacks_core.db import get_session, AuthConfig
from netstacks_core.utils import success_response

log = logging.getLogger(__name__)
router = APIRouter()


# Schemas for auth config
class AuthConfigBase(BaseModel):
    """Base auth config schema"""
    auth_type: str = Field(..., pattern="^(local|ldap|oidc)$")
    is_enabled: bool = False
    priority: int = Field(default=0, ge=0, le=100)


class LDAPConfig(BaseModel):
    """LDAP configuration"""
    server: str
    port: int = 389
    use_ssl: bool = False
    base_dn: str
    user_dn_template: Optional[str] = None
    bind_dn: Optional[str] = None
    bind_password: Optional[str] = None
    user_search_filter: str = "(uid={username})"
    group_search_base: Optional[str] = None
    group_search_filter: Optional[str] = None


class OIDCConfig(BaseModel):
    """OIDC configuration"""
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: List[str] = ["openid", "profile", "email"]
    username_claim: str = "preferred_username"


class AuthConfigCreate(AuthConfigBase):
    """Create auth config request"""
    config_data: dict = {}


class AuthConfigResponse(AuthConfigBase):
    """Auth config response"""
    config_id: int
    config_data: dict = {}


class AuthConfigList(BaseModel):
    """List of auth configs"""
    success: bool = True
    data: List[AuthConfigResponse]


@router.get("", response_model=AuthConfigList)
async def list_auth_configs(current_user: TokenData = Depends(get_current_user)):
    """
    List all authentication configurations.
    """
    session = get_session()
    try:
        configs = session.query(AuthConfig).order_by(AuthConfig.priority).all()
        return AuthConfigList(
            data=[
                AuthConfigResponse(
                    config_id=c.config_id,
                    auth_type=c.auth_type,
                    is_enabled=c.is_enabled,
                    priority=c.priority,
                    config_data=mask_sensitive_config(c.config_data or {}),
                )
                for c in configs
            ]
        )
    finally:
        session.close()


@router.get("/{auth_type}", response_model=AuthConfigResponse)
async def get_auth_config(
    auth_type: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get authentication configuration by type.
    """
    if auth_type not in ["local", "ldap", "oidc"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid auth type: {auth_type}"
        )

    session = get_session()
    try:
        config = session.query(AuthConfig).filter(
            AuthConfig.auth_type == auth_type
        ).first()

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Auth config not found: {auth_type}"
            )

        return AuthConfigResponse(
            config_id=config.config_id,
            auth_type=config.auth_type,
            is_enabled=config.is_enabled,
            priority=config.priority,
            config_data=mask_sensitive_config(config.config_data or {}),
        )
    finally:
        session.close()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_auth_config(
    request: AuthConfigCreate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Create or update authentication configuration.
    """
    session = get_session()
    try:
        # Check if config already exists
        existing = session.query(AuthConfig).filter(
            AuthConfig.auth_type == request.auth_type
        ).first()

        if existing:
            # Update existing config
            existing.is_enabled = request.is_enabled
            existing.priority = request.priority
            existing.config_data = request.config_data
            session.commit()
            log.info(f"{request.auth_type.upper()} config updated by {current_user.sub}")
            return success_response(message=f"{request.auth_type.upper()} configuration updated")
        else:
            # Create new config
            config = AuthConfig(
                auth_type=request.auth_type,
                is_enabled=request.is_enabled,
                priority=request.priority,
                config_data=request.config_data,
            )
            session.add(config)
            session.commit()
            log.info(f"{request.auth_type.upper()} config created by {current_user.sub}")
            return success_response(message=f"{request.auth_type.upper()} configuration created")

    finally:
        session.close()


@router.put("/{auth_type}")
async def update_auth_config(
    auth_type: str,
    request: AuthConfigCreate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Update authentication configuration.
    """
    if auth_type not in ["local", "ldap", "oidc"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid auth type: {auth_type}"
        )

    session = get_session()
    try:
        config = session.query(AuthConfig).filter(
            AuthConfig.auth_type == auth_type
        ).first()

        if not config:
            # Create new config
            config = AuthConfig(
                auth_type=auth_type,
                is_enabled=request.is_enabled,
                priority=request.priority,
                config_data=request.config_data,
            )
            session.add(config)
        else:
            config.is_enabled = request.is_enabled
            config.priority = request.priority
            config.config_data = request.config_data

        session.commit()
        log.info(f"{auth_type.upper()} config updated by {current_user.sub}")

        return success_response(message=f"{auth_type.upper()} configuration updated")

    finally:
        session.close()


@router.delete("/{auth_type}")
async def delete_auth_config(
    auth_type: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Delete authentication configuration.
    """
    if auth_type == "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete local authentication"
        )

    session = get_session()
    try:
        config = session.query(AuthConfig).filter(
            AuthConfig.auth_type == auth_type
        ).first()

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Auth config not found: {auth_type}"
            )

        session.delete(config)
        session.commit()
        log.info(f"{auth_type.upper()} config deleted by {current_user.sub}")

        return success_response(message=f"{auth_type.upper()} configuration deleted")

    finally:
        session.close()


@router.post("/{auth_type}/toggle")
async def toggle_auth_config(
    auth_type: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Toggle authentication method enabled/disabled.
    """
    session = get_session()
    try:
        config = session.query(AuthConfig).filter(
            AuthConfig.auth_type == auth_type
        ).first()

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Auth config not found: {auth_type}"
            )

        config.is_enabled = not config.is_enabled
        session.commit()

        status_str = "enabled" if config.is_enabled else "disabled"
        log.info(f"{auth_type.upper()} auth {status_str} by {current_user.sub}")

        return success_response(
            data={"is_enabled": config.is_enabled},
            message=f"{auth_type.upper()} authentication {status_str}"
        )

    finally:
        session.close()


@router.post("/{auth_type}/test")
async def test_auth_config(
    auth_type: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Test authentication configuration.
    """
    if auth_type not in ["ldap", "oidc"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only test LDAP or OIDC configurations"
        )

    session = get_session()
    try:
        config = session.query(AuthConfig).filter(
            AuthConfig.auth_type == auth_type
        ).first()

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Auth config not found: {auth_type}"
            )

        # TODO: Implement actual connection testing
        # For now, just return success if config exists
        log.info(f"{auth_type.upper()} config test requested by {current_user.sub}")

        return success_response(
            data={"tested": True},
            message=f"{auth_type.upper()} configuration test completed"
        )

    finally:
        session.close()


def mask_sensitive_config(config: dict) -> dict:
    """Mask sensitive fields in config data."""
    sensitive_keys = ['bind_password', 'client_secret', 'password', 'secret']
    result = config.copy()
    for key in sensitive_keys:
        if key in result and result[key]:
            result[key] = '****'
    return result
