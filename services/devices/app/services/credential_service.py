"""
Credential Service

Business logic for default credential management.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from netstacks_core.db import DefaultCredential

from app.schemas.credentials import CredentialCreate, CredentialUpdate

log = logging.getLogger(__name__)


class CredentialService:
    """Service for managing default credentials."""

    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> List[Dict]:
        """Get all credentials (passwords masked)."""
        credentials = self.session.query(DefaultCredential).order_by(
            DefaultCredential.is_default.desc(),
            DefaultCredential.name
        ).all()

        return [self._to_dict(c) for c in credentials]

    def get(self, credential_id: int) -> Optional[Dict]:
        """Get a single credential by ID (password masked)."""
        credential = self.session.query(DefaultCredential).filter(
            DefaultCredential.id == credential_id
        ).first()

        if credential:
            return self._to_dict(credential)
        return None

    def get_default(self) -> Optional[Dict]:
        """Get the default credential set."""
        credential = self.session.query(DefaultCredential).filter(
            DefaultCredential.is_default == True
        ).first()

        if credential:
            return self._to_dict(credential, mask_password=False)
        return None

    def create(self, credential: CredentialCreate) -> Dict:
        """Create a new credential."""
        # If this is the default, unset any existing defaults
        if credential.is_default:
            self._clear_defaults()

        db_credential = DefaultCredential(
            name=credential.name,
            username=credential.username,
            password=credential.password,
            enable_password=credential.enable_password,
            is_default=credential.is_default,
        )
        self.session.add(db_credential)
        self.session.commit()

        log.info(f"Credential '{credential.name}' created")
        return self._to_dict(db_credential)

    def update(self, credential_id: int, credential: CredentialUpdate) -> Dict:
        """Update a credential."""
        db_credential = self.session.query(DefaultCredential).filter(
            DefaultCredential.id == credential_id
        ).first()

        if not db_credential:
            raise ValueError("Credential not found")

        # Handle default flag
        if credential.is_default:
            self._clear_defaults()

        # Update only provided fields
        update_data = credential.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(db_credential, field) and value is not None:
                setattr(db_credential, field, value)

        self.session.commit()

        log.info(f"Credential ID {credential_id} updated")
        return self._to_dict(db_credential)

    def delete(self, credential_id: int) -> bool:
        """Delete a credential."""
        db_credential = self.session.query(DefaultCredential).filter(
            DefaultCredential.id == credential_id
        ).first()

        if not db_credential:
            return False

        self.session.delete(db_credential)
        self.session.commit()

        log.info(f"Credential ID {credential_id} deleted")
        return True

    def set_default(self, credential_id: int) -> bool:
        """Set a credential as the default."""
        db_credential = self.session.query(DefaultCredential).filter(
            DefaultCredential.id == credential_id
        ).first()

        if not db_credential:
            return False

        # Clear existing defaults
        self._clear_defaults()

        # Set this one as default
        db_credential.is_default = True
        self.session.commit()

        log.info(f"Credential ID {credential_id} set as default")
        return True

    def _clear_defaults(self):
        """Clear all default flags."""
        self.session.query(DefaultCredential).filter(
            DefaultCredential.is_default == True
        ).update({'is_default': False})

    def _to_dict(self, credential: DefaultCredential, mask_password: bool = True) -> Dict:
        """Convert credential model to dict."""
        return {
            'id': credential.id,
            'name': credential.name,
            'username': credential.username,
            'password': '****' if mask_password else credential.password,
            'enable_password': '****' if (mask_password and credential.enable_password) else credential.enable_password,
            'is_default': credential.is_default,
            'created_at': credential.created_at.isoformat() if credential.created_at else None,
        }
