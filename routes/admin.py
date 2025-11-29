"""
Admin Routes
User management, authentication configuration
"""
from flask import Blueprint, jsonify, request
import logging

log = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)

# Routes to migrate from app.py:
# - /admin (GET) - Page
# - /users (GET) - Page
# - /authentication (GET) - Page
# - /api/users (GET, POST)
# - /api/users/<username>/password (PUT)
# - /api/users/<username> (DELETE)
# - /api/user/theme (GET, POST)
# - /api/auth/configs (GET)
# - /api/auth/config/<auth_type> (GET, DELETE)
# - /api/auth/config (POST)
# - /api/auth/config/<auth_type>/toggle (POST)
# - /api/auth/test/ldap (POST)
# - /api/auth/test/oidc (POST)
# - /api/auth/local/priority (GET, POST)
