"""
Device Routes
Device management, Netbox sync, manual devices
"""
from flask import Blueprint, jsonify, request
import logging

log = logging.getLogger(__name__)

devices_bp = Blueprint('devices', __name__)

# Routes to migrate from app.py:
# - /api/devices (GET, POST)
# - /api/devices/clear-cache (POST)
# - /api/manual-devices (GET, POST)
# - /api/manual-devices/<device_name> (PUT, DELETE)
