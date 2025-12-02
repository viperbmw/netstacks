"""
API Routes
General API endpoints, task status, workers, API resources
"""
from flask import Blueprint, jsonify, request
import logging

log = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

# Routes to migrate from app.py:
# - /api-docs (GET) - Page
# - /api/task/<task_id> (GET)
# - /api/task/<task_id>/result (GET)
# - /api/workers (GET)
# - /api/api-resources (GET, POST)
# - /api/api-resources/<resource_id> (GET, PUT, DELETE)
# - /api/proxy-api-call (POST)
