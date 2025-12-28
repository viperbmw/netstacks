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
# AI Feature Pages (Placeholders)
# ============================================================================

@pages_bp.route('/agents')
@login_required
def agents():
    """AI Agents management page."""
    return render_template('ai_placeholder.html',
        page_title='AI Agents',
        page_icon='robot',
        page_description='Configure and manage AI-powered automation agents'
    )


@pages_bp.route('/incidents')
@login_required
def incidents():
    """Incidents and alerts page."""
    return render_template('ai_placeholder.html',
        page_title='Incidents',
        page_icon='exclamation-triangle',
        page_description='View and manage network incidents and alerts'
    )


@pages_bp.route('/knowledge')
@login_required
def knowledge():
    """Knowledge base page."""
    return render_template('ai_placeholder.html',
        page_title='Knowledge Base',
        page_icon='book-open',
        page_description='Documentation and runbooks for AI agents'
    )


@pages_bp.route('/tools')
@login_required
def tools():
    """AI Tools management page."""
    return render_template('ai_placeholder.html',
        page_title='Tools',
        page_icon='wrench',
        page_description='Configure tools available to AI agents'
    )
