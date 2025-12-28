"""
Page Routes
Main dashboard and general page routes
"""
from flask import Blueprint, render_template, redirect, url_for
import logging

from routes.auth import login_required

log = logging.getLogger(__name__)

pages_bp = Blueprint('pages', __name__)


# ============================================================================
# Main Pages
# ============================================================================

@pages_bp.route('/')
@login_required
def index():
    """Main dashboard."""
    return render_template('index.html')


@pages_bp.route('/deploy')
@login_required
def deploy():
    """Config deployment page."""
    return render_template('deploy.html')


@pages_bp.route('/monitor')
@login_required
def monitor():
    """Job monitoring page."""
    return render_template('monitor.html')


@pages_bp.route('/workers')
@login_required
def workers():
    """Workers list page."""
    return render_template('workers.html')


@pages_bp.route('/snapshots')
@login_required
def snapshots():
    """Config snapshots page - manage network configuration snapshots and device backups."""
    return render_template('config_backups.html')


@pages_bp.route('/config-backups')
@login_required
def config_backups():
    """Redirect old config-backups URL to snapshots."""
    return redirect(url_for('pages.snapshots'))


@pages_bp.route('/platform')
@login_required
def platform():
    """Platform health monitoring page."""
    return render_template('platform.html')


# ============================================================================
# AI Feature Pages - Redirect to proper blueprints
# ============================================================================

@pages_bp.route('/agents')
@login_required
def agents():
    """Redirect to agents blueprint."""
    return redirect(url_for('agents.agents_page'))


@pages_bp.route('/incidents')
@login_required
def incidents():
    """Redirect to incidents page."""
    return redirect(url_for('alerts.incidents_page'))


@pages_bp.route('/knowledge')
@login_required
def knowledge():
    """Redirect to knowledge blueprint."""
    return redirect(url_for('knowledge.knowledge_page'))


@pages_bp.route('/tools')
@login_required
def tools():
    """AI Tools management page."""
    return render_template('tools.html')


@pages_bp.route('/alerts')
@login_required
def alerts():
    """Redirect to alerts blueprint."""
    return redirect(url_for('alerts.alerts_page'))


@pages_bp.route('/approvals')
@login_required
def approvals():
    """Redirect to approvals blueprint."""
    return redirect(url_for('approvals.approvals_page'))
