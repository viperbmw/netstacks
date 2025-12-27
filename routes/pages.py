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
