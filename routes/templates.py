"""
Template Routes
Jinja2 template management, rendering, variables
"""
from flask import Blueprint, jsonify, request
import logging

log = logging.getLogger(__name__)

templates_bp = Blueprint('templates', __name__)

# Routes to migrate from app.py:
# - /templates (GET) - Page
# - /api/templates (GET, POST, DELETE)
# - /api/templates/<template_name> (GET)
# - /api/templates/<template_name>/metadata (PUT)
# - /api/templates/<template_name>/variables (GET)
# - /api/templates/render (POST)
