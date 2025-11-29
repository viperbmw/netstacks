"""
Deploy Routes
Configuration deployment, getconfig, setconfig
"""
from flask import Blueprint, jsonify, request
import logging

log = logging.getLogger(__name__)

deploy_bp = Blueprint('deploy', __name__)

# Routes to migrate from app.py:
# - /deploy (GET) - Page
# - /api/deploy/getconfig (POST)
# - /api/deploy/setconfig (POST)
# - /api/deploy/setconfig/dry-run (POST)
