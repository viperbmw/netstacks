"""
Settings Routes
Application settings, Netbox configuration, menu customization

Settings routes proxy to auth microservice (auth:8011)
"""

from flask import Blueprint, jsonify, request, render_template
import logging
import json

import database as db
from models import Setting, LLMProvider
from routes.auth import login_required
from services.proxy import proxy_auth_request
from utils.responses import success_response, error_response
from utils.decorators import handle_exceptions, require_json
from utils.exceptions import ValidationError

log = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__)


# ============================================================================
# Settings Pages
# ============================================================================

@settings_bp.route('/settings')
@login_required
def settings_page():
    """Settings page - renders the settings HTML template"""
    return render_template('settings.html')


@settings_bp.route('/settings/ai')
@login_required
def ai_settings_page():
    """AI Settings page - LLM provider configuration"""
    return render_template('ai_settings.html')


# ============================================================================
# Settings API Endpoints - Proxied to Auth Microservice
# ============================================================================

@settings_bp.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    """
    Get current application settings.
    Proxied to auth:8011/api/settings/settings
    """
    return proxy_auth_request('/api/settings/settings')


@settings_bp.route('/api/settings', methods=['POST', 'PUT'])
@login_required
def save_settings():
    """
    Save application settings.
    Proxied to auth:8011/api/settings/settings

    Expected JSON body:
    {
        "netbox_url": "https://netbox.example.com",
        "netbox_token": "token-here",
        "verify_ssl": false,
        "netbox_filters": [],
        "cache_ttl": 300,
        "default_username": "",
        "default_password": "",
        "system_timezone": "UTC"
    }
    """
    return proxy_auth_request('/api/settings/settings')


@settings_bp.route('/api/settings/<category>', methods=['GET'])
@login_required
def get_settings_by_category(category):
    """
    Get settings by category.
    For 'ai' category, returns local AI settings.
    Other categories proxied to auth:8011/api/settings/{category}
    """
    if category == 'ai':
        return get_ai_settings()
    return proxy_auth_request('/api/settings/{category}', category=category)


# ============================================================================
# AI Settings API Endpoints
# ============================================================================

@settings_bp.route('/api/settings/ai', methods=['GET'])
@login_required
def get_ai_settings():
    """Get AI-specific settings"""
    try:
        with db.get_db() as db_session:
            # Get AI settings from Settings table
            settings = {}
            ai_keys = [
                'ai_default_provider',
                'ai_default_model',
                'ai_default_temperature',
                'ai_default_max_tokens',
                'ai_approval_timeout_minutes'
            ]

            for key in ai_keys:
                setting = db_session.query(Setting).filter(
                    Setting.key == key
                ).first()
                if setting:
                    # Remove 'ai_' prefix for response
                    clean_key = key.replace('ai_', '')
                    try:
                        settings[clean_key] = json.loads(setting.value)
                    except (json.JSONDecodeError, TypeError):
                        settings[clean_key] = setting.value

            return jsonify({'settings': settings})

    except Exception as e:
        log.error(f"Error getting AI settings: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/settings/ai', methods=['POST'])
@login_required
def save_ai_settings():
    """Save AI-specific settings"""
    try:
        data = request.get_json()

        with db.get_db() as db_session:
            settings_map = {
                'default_provider': 'ai_default_provider',
                'default_model': 'ai_default_model',
                'default_temperature': 'ai_default_temperature',
                'default_max_tokens': 'ai_default_max_tokens',
                'approval_timeout_minutes': 'ai_approval_timeout_minutes'
            }

            for key, db_key in settings_map.items():
                if key in data:
                    value = json.dumps(data[key]) if not isinstance(data[key], str) else data[key]

                    setting = db_session.query(Setting).filter(
                        Setting.key == db_key
                    ).first()

                    if setting:
                        setting.value = value
                    else:
                        setting = Setting(key=db_key, value=value)
                        db_session.add(setting)

            db_session.commit()

        return jsonify({'message': 'AI settings saved successfully'})

    except Exception as e:
        log.error(f"Error saving AI settings: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/llm/providers', methods=['GET'])
@login_required
def list_llm_providers():
    """List all configured LLM providers"""
    try:
        with db.get_db() as db_session:
            providers = db_session.query(LLMProvider).all()

            return jsonify({
                'providers': [
                    {
                        'id': p.id,
                        'name': p.name,
                        'display_name': p.display_name,
                        'base_url': p.base_url,
                        'default_model': p.default_model,
                        'available_models': p.available_models or [],
                        'is_enabled': p.is_enabled,
                        'is_default': p.is_default,
                        'created_at': p.created_at.isoformat() if p.created_at else None,
                    }
                    for p in providers
                ]
            })

    except Exception as e:
        log.error(f"Error listing LLM providers: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/llm/providers', methods=['POST'])
@login_required
def configure_llm_provider():
    """Add or update an LLM provider"""
    try:
        data = request.get_json()
        name = data.get('name')

        if not name:
            return jsonify({'error': 'Provider name is required'}), 400

        with db.get_db() as db_session:
            # Check if provider exists
            provider = db_session.query(LLMProvider).filter(
                LLMProvider.name == name
            ).first()

            if provider:
                # Update existing
                if data.get('api_key'):
                    # In production, encrypt the API key
                    provider.api_key = data['api_key']
                if 'display_name' in data:
                    provider.display_name = data['display_name']
                if 'base_url' in data:
                    provider.base_url = data['base_url']
                if 'default_model' in data:
                    provider.default_model = data['default_model']
                if 'available_models' in data:
                    provider.available_models = data['available_models']
                if 'is_enabled' in data:
                    provider.is_enabled = data['is_enabled']
                if 'is_default' in data:
                    if data['is_default']:
                        # Unset other defaults first
                        db_session.query(LLMProvider).update({'is_default': False})
                    provider.is_default = data['is_default']
            else:
                # Create new - API key required
                if not data.get('api_key'):
                    return jsonify({'error': 'API key is required for new providers'}), 400

                # Unset other defaults if this is default
                if data.get('is_default'):
                    db_session.query(LLMProvider).update({'is_default': False})

                provider = LLMProvider(
                    name=name,
                    display_name=data.get('display_name'),
                    api_key=data['api_key'],  # In production, encrypt this
                    base_url=data.get('base_url'),
                    default_model=data.get('default_model'),
                    available_models=data.get('available_models', []),
                    is_enabled=data.get('is_enabled', True),
                    is_default=data.get('is_default', False),
                )
                db_session.add(provider)

            db_session.commit()

        return jsonify({'message': 'Provider configured successfully'})

    except Exception as e:
        log.error(f"Error configuring LLM provider: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/llm/providers/<name>', methods=['DELETE'])
@login_required
def delete_llm_provider(name):
    """Delete an LLM provider"""
    try:
        with db.get_db() as db_session:
            provider = db_session.query(LLMProvider).filter(
                LLMProvider.name == name
            ).first()

            if not provider:
                return jsonify({'error': 'Provider not found'}), 404

            db_session.delete(provider)
            db_session.commit()

        return jsonify({'message': 'Provider deleted successfully'})

    except Exception as e:
        log.error(f"Error deleting LLM provider: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/llm/test', methods=['POST'])
@login_required
def test_llm_connection():
    """Test connection to an LLM provider"""
    try:
        data = request.get_json()
        provider = data.get('provider')
        api_key = data.get('api_key')

        if not provider or not api_key:
            return jsonify({'error': 'Provider and API key are required'}), 400

        # Test the connection based on provider
        import requests

        if provider == 'anthropic':
            response = requests.get(
                'https://api.anthropic.com/v1/models',
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01'
                },
                timeout=10
            )
            if response.status_code == 200:
                return jsonify({'success': True, 'message': 'Connection successful'})
            else:
                return jsonify({'error': f'API returned status {response.status_code}'}), 400

        elif provider == 'openai':
            response = requests.get(
                'https://api.openai.com/v1/models',
                headers={'Authorization': f'Bearer {api_key}'},
                timeout=10
            )
            if response.status_code == 200:
                return jsonify({'success': True, 'message': 'Connection successful'})
            else:
                return jsonify({'error': f'API returned status {response.status_code}'}), 400

        elif provider == 'openrouter':
            base_url = data.get('base_url', 'https://openrouter.ai/api/v1')
            response = requests.get(
                f'{base_url}/models',
                headers={'Authorization': f'Bearer {api_key}'},
                timeout=10
            )
            if response.status_code == 200:
                return jsonify({'success': True, 'message': 'Connection successful'})
            else:
                return jsonify({'error': f'API returned status {response.status_code}'}), 400

        else:
            return jsonify({'error': f'Unknown provider: {provider}'}), 400

    except requests.exceptions.Timeout:
        return jsonify({'error': 'Connection timed out'}), 400
    except requests.exceptions.ConnectionError as e:
        return jsonify({'error': f'Connection failed: {str(e)}'}), 400
    except Exception as e:
        log.error(f"Error testing LLM connection: {e}")
        return jsonify({'error': str(e)}), 500
