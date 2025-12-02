"""
MOP (Method of Procedures) Routes
MOP management, execution, step types
"""
from flask import Blueprint, jsonify, request
import logging

log = logging.getLogger(__name__)

mop_bp = Blueprint('mop', __name__)

# Routes to migrate from app.py:
# - /mop (GET) - Page
# - /api/mops (GET, POST)
# - /api/mops/<mop_id> (GET, PUT, DELETE)
# - /api/mops/<mop_id>/execute (POST)
# - /api/mops/<mop_id>/executions (GET)
# - /api/mop-executions/<execution_id> (GET)
# - /api/mop-executions/running (GET)
# - /api/step-types-introspect (GET)
# - /api/custom-step-types (GET, POST)
# - /api/custom-step-types/<step_type_id> (GET, PUT, DELETE)
