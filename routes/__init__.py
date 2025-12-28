"""
NetStacks Routes Package
Organizes Flask routes into logical modules
"""
from flask import Blueprint

# Import all route blueprints
from .auth import auth_bp
from .pages import pages_bp
from .devices import devices_bp
from .templates import templates_bp
from .services import services_bp
from .stacks import stacks_bp
from .mop import mop_bp
from .settings import settings_bp
from .admin import admin_bp
from .deploy import deploy_bp
from .api import api_bp
from .agents import agents_bp
from .alerts import alerts_bp
from .knowledge import knowledge_bp
from .approvals import approvals_bp


def register_blueprints(app):
    """Register all blueprints with the Flask app"""
    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(devices_bp)
    app.register_blueprint(templates_bp)
    app.register_blueprint(services_bp)
    app.register_blueprint(stacks_bp)
    app.register_blueprint(mop_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(deploy_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(agents_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(approvals_bp)
