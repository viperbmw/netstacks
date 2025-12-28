"""
Credentials Routes

Default credential management for device connections.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from netstacks_core.db import get_db
from netstacks_core.auth import get_current_user
from netstacks_core.utils.responses import success_response

from app.schemas.credentials import (
    CredentialCreate,
    CredentialUpdate,
    CredentialResponse,
    CredentialListResponse,
)
from app.services.credential_service import CredentialService

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=CredentialListResponse)
async def list_credentials(
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get all default credentials (passwords masked)."""
    service = CredentialService(session)
    credentials = service.get_all()
    return success_response(data={
        "credentials": credentials,
        "count": len(credentials),
    })


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(
    credential_id: int,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get a single credential by ID (password masked)."""
    service = CredentialService(session)
    credential = service.get(credential_id)
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    return success_response(data={"credential": credential})


@router.post("", response_model=CredentialResponse)
async def create_credential(
    credential: CredentialCreate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new default credential."""
    service = CredentialService(session)
    created = service.create(credential)
    log.info(f"Credential '{credential.name}' created by {current_user.sub}")
    return success_response(
        data={"credential": created},
        message=f"Credential '{credential.name}' created successfully"
    )


@router.put("/{credential_id}", response_model=CredentialResponse)
async def update_credential(
    credential_id: int,
    credential: CredentialUpdate,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update a credential."""
    service = CredentialService(session)

    existing = service.get(credential_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Credential not found")

    updated = service.update(credential_id, credential)
    log.info(f"Credential ID {credential_id} updated by {current_user.sub}")
    return success_response(
        data={"credential": updated},
        message="Credential updated successfully"
    )


@router.delete("/{credential_id}")
async def delete_credential(
    credential_id: int,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete a credential."""
    service = CredentialService(session)

    existing = service.get(credential_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Credential not found")

    service.delete(credential_id)
    log.info(f"Credential ID {credential_id} deleted by {current_user.sub}")
    return success_response(message="Credential deleted successfully")


@router.post("/{credential_id}/default")
async def set_default_credential(
    credential_id: int,
    session: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Set a credential as the default."""
    service = CredentialService(session)

    existing = service.get(credential_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Credential not found")

    service.set_default(credential_id)
    log.info(f"Credential ID {credential_id} set as default by {current_user.sub}")
    return success_response(message="Credential set as default")
