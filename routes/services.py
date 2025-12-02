"""
Service Routes
Service instances, deployment, validation
"""
from flask import Blueprint, jsonify, request
import logging

log = logging.getLogger(__name__)

services_bp = Blueprint('services', __name__)

# Routes to migrate from app.py:
# - /services (GET) - Page
# - /api/services/templates (GET)
# - /api/services/templates/<template_name>/schema (GET)
# - /api/services/instances (GET)
# - /api/services/instances/<service_id> (GET)
# - /api/services/instances/create (POST)
# - /api/services/instances/<service_id>/healthcheck (POST)
# - /api/services/instances/<service_id>/redeploy (POST)
# - /api/services/instances/<service_id>/delete (POST)
# - /api/services/instances/<service_id>/check_status (POST)
# - /api/services/instances/<service_id>/validate (POST)
# - /api/services/instances/sync-states (POST)
