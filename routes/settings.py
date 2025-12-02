"""
Settings Routes
Application settings, Netbox configuration
"""
from flask import Blueprint, jsonify, request
import logging

log = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__)

# Routes to migrate from app.py:
# - /settings (GET) - Page
# - /api/settings (GET, POST)
# - /api/menu-items (GET, POST)
