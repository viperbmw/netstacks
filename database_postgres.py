"""
PostgreSQL Database Layer for NetStacks
Uses SQLAlchemy for ORM-based database operations
"""
import os
import json
import logging
from datetime import datetime
from contextlib import contextmanager
from typing import Dict, List, Any, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from models import (
    Base, Setting, User, Template, ServiceStack, ServiceInstance,
    Device, DefaultCredential, StackTemplate, APIResource,
    ScheduledStackOperation, AuthConfig, MenuItem, MOP, MOPExecution,
    StepType, TaskHistory, ConfigSnapshot, ConfigBackup, BackupSchedule, DeviceOverride,
    DEFAULT_STEP_TYPES, DEFAULT_MENU_ITEMS
)

log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://netstacks:netstacks_secret_change_me@postgres:5432/netstacks'
)

# Create engine and session factory
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionFactory = sessionmaker(bind=engine)


def init_db():
    """Initialize PostgreSQL database with all tables"""
    Base.metadata.create_all(engine)
    log.info(f"PostgreSQL database initialized at {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")

    # Seed default data
    with get_db() as session:
        _seed_defaults(session)


def _seed_defaults(session: Session):
    """Seed default step types and menu items if tables are empty"""
    # Seed step types
    if session.query(StepType).count() == 0:
        log.info("Seeding default step types")
        for st in DEFAULT_STEP_TYPES:
            session.add(StepType(**st, enabled=True))
        session.commit()

    # Seed menu items
    if session.query(MenuItem).count() == 0:
        log.info("Seeding default menu items")
        for mi in DEFAULT_MENU_ITEMS:
            session.add(MenuItem(**mi))
        session.commit()


@contextmanager
def get_db():
    """Context manager for database sessions"""
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


# =============================================================================
# Settings Operations
# =============================================================================

def get_setting(key: str, default=None):
    """Get a setting value"""
    with get_db() as session:
        setting = session.query(Setting).filter(Setting.key == key).first()
        return setting.value if setting else default


def set_setting(key: str, value: str):
    """Set a setting value"""
    with get_db() as session:
        setting = session.query(Setting).filter(Setting.key == key).first()
        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
        else:
            session.add(Setting(key=key, value=value))


def get_all_settings() -> Dict[str, Any]:
    """Get all settings as dict"""
    with get_db() as session:
        settings = {}
        for setting in session.query(Setting).all():
            value = setting.value
            # Convert verify_ssl to boolean
            if setting.key == 'verify_ssl':
                value = value.lower() in ('true', '1', 'yes') if isinstance(value, str) else bool(value)
            settings[setting.key] = value
        return settings


# =============================================================================
# User Operations
# =============================================================================

def get_user(username: str) -> Optional[Dict]:
    """Get user by username"""
    with get_db() as session:
        user = session.query(User).filter(User.username == username).first()
        if user:
            return {
                'username': user.username,
                'password_hash': user.password_hash,
                'theme': user.theme,
                'auth_source': user.auth_source,
                'created_at': user.created_at.isoformat() if user.created_at else None
            }
        return None


def create_user(username: str, password_hash: str, auth_source: str = 'local'):
    """Create a new user"""
    with get_db() as session:
        session.add(User(username=username, password_hash=password_hash, auth_source=auth_source))


def delete_user(username: str) -> bool:
    """Delete a user"""
    with get_db() as session:
        result = session.query(User).filter(User.username == username).delete()
        return result > 0


def get_all_users() -> List[Dict]:
    """Get all users"""
    with get_db() as session:
        return [
            {'username': u.username, 'created_at': u.created_at.isoformat() if u.created_at else None}
            for u in session.query(User).order_by(User.username).all()
        ]


def set_user_theme(username: str, theme: str) -> bool:
    """Set user's theme preference"""
    with get_db() as session:
        user = session.query(User).filter(User.username == username).first()
        if user:
            user.theme = theme
            return True
        return False


def get_user_theme(username: str) -> str:
    """Get user's theme preference"""
    with get_db() as session:
        user = session.query(User).filter(User.username == username).first()
        return user.theme if user else 'dark'


# =============================================================================
# Template Metadata Operations
# =============================================================================

def get_template_metadata(name: str) -> Optional[Dict]:
    """Get template metadata"""
    with get_db() as session:
        template = session.query(Template).filter(Template.name == name).first()
        if template:
            return {
                'name': template.name,
                'content': template.content,
                'type': template.type,
                'validation_template': template.validation_template,
                'delete_template': template.delete_template,
                'description': template.description,
                'created_at': template.created_at.isoformat() if template.created_at else None,
                'updated_at': template.updated_at.isoformat() if template.updated_at else None
            }
        return None


def get_template_content(name: str) -> Optional[str]:
    """Get template content by name"""
    with get_db() as session:
        template = session.query(Template).filter(Template.name == name).first()
        return template.content if template else None


def save_template(name: str, content: str, metadata: Dict = None):
    """Save template with content and metadata"""
    with get_db() as session:
        template = session.query(Template).filter(Template.name == name).first()
        if template:
            template.content = content
            if metadata:
                template.type = metadata.get('type', template.type)
                template.validation_template = metadata.get('validation_template', template.validation_template)
                template.delete_template = metadata.get('delete_template', template.delete_template)
                template.description = metadata.get('description', template.description)
            template.updated_at = datetime.utcnow()
        else:
            session.add(Template(
                name=name,
                content=content,
                type=metadata.get('type', 'deploy') if metadata else 'deploy',
                validation_template=metadata.get('validation_template') if metadata else None,
                delete_template=metadata.get('delete_template') if metadata else None,
                description=metadata.get('description') if metadata else None
            ))


def save_template_metadata(name: str, metadata: Dict):
    """Save template metadata (content unchanged)"""
    with get_db() as session:
        template = session.query(Template).filter(Template.name == name).first()
        if template:
            template.type = metadata.get('type', 'deploy')
            template.validation_template = metadata.get('validation_template')
            template.delete_template = metadata.get('delete_template')
            template.description = metadata.get('description')
            template.updated_at = datetime.utcnow()
        else:
            session.add(Template(
                name=name,
                type=metadata.get('type', 'deploy'),
                validation_template=metadata.get('validation_template'),
                delete_template=metadata.get('delete_template'),
                description=metadata.get('description')
            ))


def delete_template_metadata(name: str) -> bool:
    """Delete template (including content)"""
    with get_db() as session:
        result = session.query(Template).filter(Template.name == name).delete()
        return result > 0


def get_all_templates() -> List[Dict]:
    """Get all templates with metadata"""
    with get_db() as session:
        return [
            {
                'name': t.name,
                'content': t.content,
                'type': t.type,
                'validation_template': t.validation_template,
                'delete_template': t.delete_template,
                'description': t.description,
                'created_at': t.created_at.isoformat() if t.created_at else None,
                'updated_at': t.updated_at.isoformat() if t.updated_at else None
            }
            for t in session.query(Template).order_by(Template.name).all()
        ]


def get_all_template_metadata() -> Dict[str, Dict]:
    """Get all template metadata as dict keyed by template name"""
    templates = get_all_templates()
    return {t['name']: t for t in templates}


# =============================================================================
# Service Stack Operations
# =============================================================================

def get_service_stack(stack_id: str) -> Optional[Dict]:
    """Get service stack by ID"""
    with get_db() as session:
        stack = session.query(ServiceStack).filter(ServiceStack.stack_id == stack_id).first()
        if not stack:
            return None
        return _stack_to_dict(stack)


def _stack_to_dict(stack: ServiceStack) -> Dict:
    """Convert ServiceStack model to dict"""
    return {
        'stack_id': stack.stack_id,
        'name': stack.name,
        'description': stack.description,
        'services': stack.services or [],
        'shared_variables': stack.shared_variables or {},
        'state': stack.state,
        'has_pending_changes': stack.has_pending_changes,
        'pending_since': stack.pending_since.isoformat() if stack.pending_since else None,
        'deployed_services': stack.deployed_services or [],
        'deployment_errors': stack.deployment_errors or [],
        'created_at': stack.created_at.isoformat() if stack.created_at else None,
        'updated_at': stack.updated_at.isoformat() if stack.updated_at else None,
        'deploy_started_at': stack.deploy_started_at.isoformat() if stack.deploy_started_at else None,
        'deploy_completed_at': stack.deploy_completed_at.isoformat() if stack.deploy_completed_at else None,
        'last_validated': stack.last_validated.isoformat() if stack.last_validated else None,
        'validation_status': stack.validation_status
    }


def save_service_stack(stack_data: Dict):
    """Save or update service stack"""
    with get_db() as session:
        stack = session.query(ServiceStack).filter(
            ServiceStack.stack_id == stack_data['stack_id']
        ).first()

        if stack:
            stack.name = stack_data['name']
            stack.description = stack_data.get('description', '')
            stack.services = stack_data.get('services', [])
            stack.shared_variables = stack_data.get('shared_variables', {})
            stack.state = stack_data.get('state', 'pending')
            stack.has_pending_changes = stack_data.get('has_pending_changes', False)
            stack.pending_since = _parse_datetime(stack_data.get('pending_since'))
            stack.deployed_services = stack_data.get('deployed_services', [])
            stack.deployment_errors = stack_data.get('deployment_errors', [])
            stack.updated_at = datetime.utcnow()
            stack.deploy_started_at = _parse_datetime(stack_data.get('deploy_started_at'))
            stack.deploy_completed_at = _parse_datetime(stack_data.get('deploy_completed_at'))
            stack.last_validated = _parse_datetime(stack_data.get('last_validated'))
            stack.validation_status = stack_data.get('validation_status')
        else:
            session.add(ServiceStack(
                stack_id=stack_data['stack_id'],
                name=stack_data['name'],
                description=stack_data.get('description', ''),
                services=stack_data.get('services', []),
                shared_variables=stack_data.get('shared_variables', {}),
                state=stack_data.get('state', 'pending'),
                has_pending_changes=stack_data.get('has_pending_changes', False),
                deployed_services=stack_data.get('deployed_services', []),
                deployment_errors=stack_data.get('deployment_errors', [])
            ))


def delete_service_stack(stack_id: str) -> bool:
    """Delete service stack"""
    with get_db() as session:
        result = session.query(ServiceStack).filter(ServiceStack.stack_id == stack_id).delete()
        return result > 0


def get_all_service_stacks() -> List[Dict]:
    """Get all service stacks"""
    with get_db() as session:
        stacks = session.query(ServiceStack).order_by(ServiceStack.created_at.desc()).all()
        return [_stack_to_dict(s) for s in stacks]


# =============================================================================
# Service Instance Operations
# =============================================================================

def get_service_instance(service_id: str) -> Optional[Dict]:
    """Get service instance by ID"""
    with get_db() as session:
        instance = session.query(ServiceInstance).filter(
            ServiceInstance.service_id == service_id
        ).first()
        if not instance:
            return None
        return _instance_to_dict(instance)


def _instance_to_dict(instance: ServiceInstance) -> Dict:
    """Convert ServiceInstance model to dict"""
    return {
        'service_id': instance.service_id,
        'name': instance.name,
        'template': instance.template,
        'validation_template': instance.validation_template,
        'delete_template': instance.delete_template,
        'device': instance.device,
        'variables': instance.variables or {},
        'rendered_config': instance.rendered_config,
        'state': instance.state,
        'error': instance.error,
        'task_id': instance.task_id,
        'stack_id': instance.stack_id,
        'stack_order': instance.stack_order,
        'created_at': instance.created_at.isoformat() if instance.created_at else None,
        'deployed_at': instance.deployed_at.isoformat() if instance.deployed_at else None,
        'last_validated': instance.last_validated.isoformat() if instance.last_validated else None,
        'validation_status': instance.validation_status,
        'validation_errors': instance.validation_errors or []
    }


def save_service_instance(service_data: Dict):
    """Save or update service instance"""
    with get_db() as session:
        instance = session.query(ServiceInstance).filter(
            ServiceInstance.service_id == service_data['service_id']
        ).first()

        if instance:
            instance.name = service_data['name']
            instance.template = service_data['template']
            instance.validation_template = service_data.get('validation_template')
            instance.delete_template = service_data.get('delete_template')
            instance.device = service_data['device']
            instance.variables = service_data.get('variables', {})
            instance.rendered_config = service_data.get('rendered_config')
            instance.state = service_data.get('state', 'pending')
            instance.error = service_data.get('error')
            instance.task_id = service_data.get('task_id')
            instance.stack_id = service_data.get('stack_id')
            instance.stack_order = service_data.get('stack_order', 0)
            instance.deployed_at = _parse_datetime(service_data.get('deployed_at'))
            instance.last_validated = _parse_datetime(service_data.get('last_validated'))
            instance.validation_status = service_data.get('validation_status')
            instance.validation_errors = service_data.get('validation_errors', [])
        else:
            session.add(ServiceInstance(
                service_id=service_data['service_id'],
                name=service_data['name'],
                template=service_data['template'],
                validation_template=service_data.get('validation_template'),
                delete_template=service_data.get('delete_template'),
                device=service_data['device'],
                variables=service_data.get('variables', {}),
                rendered_config=service_data.get('rendered_config'),
                state=service_data.get('state', 'pending'),
                error=service_data.get('error'),
                task_id=service_data.get('task_id'),
                stack_id=service_data.get('stack_id'),
                stack_order=service_data.get('stack_order', 0)
            ))


def delete_service_instance(service_id: str) -> bool:
    """Delete service instance"""
    with get_db() as session:
        result = session.query(ServiceInstance).filter(
            ServiceInstance.service_id == service_id
        ).delete()
        return result > 0


def get_all_service_instances() -> List[Dict]:
    """Get all service instances"""
    with get_db() as session:
        instances = session.query(ServiceInstance).order_by(
            ServiceInstance.created_at.desc()
        ).all()
        return [_instance_to_dict(i) for i in instances]


# =============================================================================
# Device Operations (unified - replaces manual_devices)
# =============================================================================

def get_manual_device(device_name: str) -> Optional[Dict]:
    """Get device by name (compatibility with old API)"""
    with get_db() as session:
        device = session.query(Device).filter(Device.name == device_name).first()
        if not device:
            return None
        return {
            'device_name': device.name,
            'device_type': device.device_type,
            'host': device.host,
            'port': device.port,
            'username': device.username,
            'password': device.password,
            'enable_password': device.enable_password,
            'description': device.description,
            'manufacturer': device.manufacturer,
            'model': device.model,
            'site': device.site,
            'tags': device.tags or [],
            'source': device.source,
            'created_at': device.created_at.isoformat() if device.created_at else None,
            'updated_at': device.updated_at.isoformat() if device.updated_at else None
        }


def save_manual_device(device_data: Dict):
    """Save or update device"""
    with get_db() as session:
        device_name = device_data.get('device_name') or device_data.get('name')
        device = session.query(Device).filter(Device.name == device_name).first()

        if device:
            device.device_type = device_data['device_type']
            device.host = device_data['host']
            device.port = device_data.get('port', 22)
            device.username = device_data.get('username')
            device.password = device_data.get('password')
            device.enable_password = device_data.get('enable_password')
            device.description = device_data.get('description', '')
            device.manufacturer = device_data.get('manufacturer', '')
            device.model = device_data.get('model', '')
            device.site = device_data.get('site', '')
            device.tags = device_data.get('tags', [])
            device.updated_at = datetime.utcnow()
        else:
            session.add(Device(
                name=device_name,
                device_type=device_data['device_type'],
                host=device_data['host'],
                port=device_data.get('port', 22),
                username=device_data.get('username'),
                password=device_data.get('password'),
                enable_password=device_data.get('enable_password'),
                description=device_data.get('description', ''),
                manufacturer=device_data.get('manufacturer', ''),
                model=device_data.get('model', ''),
                site=device_data.get('site', ''),
                tags=device_data.get('tags', []),
                source='manual'
            ))


def delete_manual_device(device_name: str) -> bool:
    """Delete device"""
    with get_db() as session:
        result = session.query(Device).filter(Device.name == device_name).delete()
        return result > 0


def get_all_manual_devices() -> List[Dict]:
    """Get all devices"""
    with get_db() as session:
        devices = session.query(Device).order_by(Device.name).all()
        return [
            {
                'device_name': d.name,
                'device_type': d.device_type,
                'host': d.host,
                'port': d.port,
                'username': d.username,
                'password': d.password,
                'enable_password': d.enable_password,
                'description': d.description,
                'manufacturer': d.manufacturer,
                'model': d.model,
                'site': d.site,
                'tags': d.tags or [],
                'source': d.source,
                'created_at': d.created_at.isoformat() if d.created_at else None,
                'updated_at': d.updated_at.isoformat() if d.updated_at else None
            }
            for d in devices
        ]


# =============================================================================
# Auth Config Operations
# =============================================================================

def save_auth_config(auth_type: str, config_data: Dict, is_enabled: bool = True, priority: int = 0):
    """Save or update authentication configuration"""
    with get_db() as session:
        config = session.query(AuthConfig).filter(AuthConfig.auth_type == auth_type).first()
        if config:
            config.config_data = config_data
            config.is_enabled = is_enabled
            config.priority = priority
            config.updated_at = datetime.utcnow()
        else:
            session.add(AuthConfig(
                auth_type=auth_type,
                config_data=config_data,
                is_enabled=is_enabled,
                priority=priority
            ))


def get_auth_config(auth_type: str) -> Optional[Dict]:
    """Get authentication configuration by type"""
    with get_db() as session:
        config = session.query(AuthConfig).filter(AuthConfig.auth_type == auth_type).first()
        if config:
            return {
                'config_id': config.config_id,
                'auth_type': config.auth_type,
                'config_data': config.config_data or {},
                'is_enabled': config.is_enabled,
                'priority': config.priority,
                'created_at': config.created_at.isoformat() if config.created_at else None,
                'updated_at': config.updated_at.isoformat() if config.updated_at else None
            }
        return None


def get_all_auth_configs() -> List[Dict]:
    """Get all authentication configurations"""
    with get_db() as session:
        configs = session.query(AuthConfig).order_by(AuthConfig.priority).all()
        return [
            {
                'config_id': c.config_id,
                'auth_type': c.auth_type,
                'config_data': c.config_data or {},
                'is_enabled': c.is_enabled,
                'priority': c.priority
            }
            for c in configs
        ]


def get_enabled_auth_configs() -> List[Dict]:
    """Get all enabled authentication configurations"""
    with get_db() as session:
        configs = session.query(AuthConfig).filter(
            AuthConfig.is_enabled == True
        ).order_by(AuthConfig.priority).all()
        return [
            {
                'config_id': c.config_id,
                'auth_type': c.auth_type,
                'config_data': c.config_data or {},
                'is_enabled': c.is_enabled,
                'priority': c.priority
            }
            for c in configs
        ]


def delete_auth_config(auth_type: str) -> bool:
    """Delete an authentication configuration"""
    with get_db() as session:
        result = session.query(AuthConfig).filter(AuthConfig.auth_type == auth_type).delete()
        return result > 0


def toggle_auth_config(auth_type: str, enabled: bool) -> bool:
    """Enable or disable an authentication method"""
    with get_db() as session:
        config = session.query(AuthConfig).filter(AuthConfig.auth_type == auth_type).first()
        if config:
            config.is_enabled = enabled
            config.updated_at = datetime.utcnow()
            return True
        return False


# =============================================================================
# Menu Items Operations
# =============================================================================

def get_menu_items() -> List[Dict]:
    """Get all menu items"""
    with get_db() as session:
        items = session.query(MenuItem).order_by(MenuItem.order_index).all()
        return [
            {
                'item_id': m.item_id,
                'label': m.label,
                'icon': m.icon,
                'url': m.url,
                'order_index': m.order_index,
                'visible': m.visible
            }
            for m in items
        ]


def update_menu_order(menu_items: List[Dict]) -> bool:
    """Update menu items order"""
    with get_db() as session:
        for item in menu_items:
            menu = session.query(MenuItem).filter(MenuItem.item_id == item['item_id']).first()
            if menu:
                menu.order_index = item['order_index']
                menu.visible = item.get('visible', True)
                menu.updated_at = datetime.utcnow()
        return True


def update_menu_item(item_id: str, label: str = None, icon: str = None, visible: bool = None) -> bool:
    """Update a menu item"""
    with get_db() as session:
        menu = session.query(MenuItem).filter(MenuItem.item_id == item_id).first()
        if menu:
            if label is not None:
                menu.label = label
            if icon is not None:
                menu.icon = icon
            if visible is not None:
                menu.visible = visible
            menu.updated_at = datetime.utcnow()
            return True
        return False


# =============================================================================
# MOP Operations
# =============================================================================

def create_mop(mop_id: str, name: str, description: str = "", devices: List = None) -> bool:
    """Create a new MOP"""
    with get_db() as session:
        session.add(MOP(
            mop_id=mop_id,
            name=name,
            description=description,
            devices=devices or []
        ))
        return True


def get_all_mops() -> List[Dict]:
    """Get all MOPs"""
    with get_db() as session:
        mops = session.query(MOP).order_by(MOP.updated_at.desc()).all()
        return [
            {
                'mop_id': m.mop_id,
                'name': m.name,
                'description': m.description,
                'devices': m.devices or [],
                'created_at': m.created_at.isoformat() if m.created_at else None,
                'updated_at': m.updated_at.isoformat() if m.updated_at else None
            }
            for m in mops
        ]


def get_mop(mop_id: str) -> Optional[Dict]:
    """Get a specific MOP by ID"""
    with get_db() as session:
        mop = session.query(MOP).filter(MOP.mop_id == mop_id).first()
        if mop:
            return {
                'mop_id': mop.mop_id,
                'name': mop.name,
                'description': mop.description,
                'devices': mop.devices or [],
                'yaml_content': mop.yaml_content,
                'created_at': mop.created_at.isoformat() if mop.created_at else None,
                'updated_at': mop.updated_at.isoformat() if mop.updated_at else None
            }
        return None


def update_mop(mop_id: str, name: str = None, description: str = None, devices: List = None) -> bool:
    """Update a MOP"""
    with get_db() as session:
        mop = session.query(MOP).filter(MOP.mop_id == mop_id).first()
        if mop:
            if name is not None:
                mop.name = name
            if description is not None:
                mop.description = description
            if devices is not None:
                mop.devices = devices
            mop.updated_at = datetime.utcnow()
            return True
        return False


def delete_mop(mop_id: str) -> bool:
    """Delete a MOP"""
    with get_db() as session:
        result = session.query(MOP).filter(MOP.mop_id == mop_id).delete()
        return result > 0


# =============================================================================
# Step Types Operations
# =============================================================================

def get_all_step_types() -> List[Dict]:
    """Get all enabled step types"""
    with get_db() as session:
        types = session.query(StepType).filter(StepType.enabled == True).order_by(
            StepType.is_builtin.desc(), StepType.category, StepType.name
        ).all()
        return [
            {
                'step_type_id': t.step_type_id,
                'name': t.name,
                'description': t.description,
                'category': t.category,
                'icon': t.icon,
                'enabled': t.enabled,
                'is_builtin': t.is_builtin,
                'action_type': t.action_type,
                'config': t.config or {},
                'parameters_schema': t.parameters_schema or {}
            }
            for t in types
        ]


def get_step_type(step_type_id: str) -> Optional[Dict]:
    """Get a specific step type"""
    with get_db() as session:
        t = session.query(StepType).filter(StepType.step_type_id == step_type_id).first()
        if t:
            return {
                'step_type_id': t.step_type_id,
                'name': t.name,
                'description': t.description,
                'category': t.category,
                'icon': t.icon,
                'enabled': t.enabled,
                'is_builtin': t.is_builtin,
                'action_type': t.action_type,
                'config': t.config or {},
                'parameters_schema': t.parameters_schema or {}
            }
        return None


def get_all_step_types_full() -> List[Dict]:
    """Get all step types (including disabled) with full details"""
    with get_db() as session:
        types = session.query(StepType).order_by(
            StepType.is_builtin.desc(), StepType.category, StepType.name
        ).all()
        return [
            {
                'step_type_id': t.step_type_id,
                'name': t.name,
                'description': t.description,
                'category': t.category,
                'icon': t.icon,
                'enabled': t.enabled,
                'is_builtin': t.is_builtin,
                'action_type': t.action_type,
                'config': t.config or {},
                'parameters_schema': t.parameters_schema or {}
            }
            for t in types
        ]


def save_step_type(data: Dict) -> str:
    """Save or update a step type"""
    with get_db() as session:
        step_type_id = data.get('step_type_id')

        if step_type_id:
            # Update existing
            t = session.query(StepType).filter(StepType.step_type_id == step_type_id).first()
            if t:
                t.name = data.get('name', t.name)
                t.description = data.get('description', t.description)
                t.category = data.get('category', t.category)
                t.icon = data.get('icon', t.icon)
                t.enabled = data.get('enabled', t.enabled)
                t.action_type = data.get('action_type', t.action_type)
                t.config = data.get('config', t.config)
                t.parameters_schema = data.get('parameters_schema', t.parameters_schema)
                session.commit()
                return step_type_id

        # Create new
        import uuid
        new_id = data.get('step_type_id') or str(uuid.uuid4())[:8]
        t = StepType(
            step_type_id=new_id,
            name=data['name'],
            description=data.get('description', ''),
            category=data.get('category', 'Custom'),
            icon=data.get('icon', 'cog'),
            enabled=data.get('enabled', True),
            is_builtin=data.get('is_builtin', False),
            action_type=data.get('action_type', 'get_config'),
            config=data.get('config', {}),
            parameters_schema=data.get('parameters_schema', {})
        )
        session.add(t)
        session.commit()
        return new_id


def delete_step_type(step_type_id: str) -> bool:
    """Delete a step type (only custom types can be deleted)"""
    with get_db() as session:
        t = session.query(StepType).filter(StepType.step_type_id == step_type_id).first()
        if t:
            if t.is_builtin:
                raise ValueError("Cannot delete built-in step types")
            session.delete(t)
            session.commit()
            return True
        return False


def toggle_step_type(step_type_id: str, enabled: bool) -> bool:
    """Enable or disable a step type"""
    with get_db() as session:
        t = session.query(StepType).filter(StepType.step_type_id == step_type_id).first()
        if t:
            t.enabled = enabled
            session.commit()
            return True
        return False


# =============================================================================
# Stack Templates Operations
# =============================================================================

def get_stack_template(template_id: str) -> Optional[Dict]:
    """Get a stack template by ID"""
    with get_db() as session:
        t = session.query(StackTemplate).filter(StackTemplate.template_id == template_id).first()
        if t:
            return {
                'template_id': t.template_id,
                'name': t.name,
                'description': t.description,
                'services': t.services or [],
                'required_variables': t.required_variables or [],
                'api_variables': t.api_variables or {},
                'per_device_variables': t.per_device_variables or [],
                'tags': t.tags or [],
                'created_at': t.created_at.isoformat() if t.created_at else None,
                'updated_at': t.updated_at.isoformat() if t.updated_at else None,
                'created_by': t.created_by
            }
        return None


def get_all_stack_templates() -> List[Dict]:
    """Get all stack templates"""
    with get_db() as session:
        templates = session.query(StackTemplate).order_by(StackTemplate.name).all()
        return [
            {
                'template_id': t.template_id,
                'name': t.name,
                'description': t.description,
                'services': t.services or [],
                'required_variables': t.required_variables or [],
                'api_variables': t.api_variables or {},
                'per_device_variables': t.per_device_variables or [],
                'tags': t.tags or [],
                'created_at': t.created_at.isoformat() if t.created_at else None,
                'updated_at': t.updated_at.isoformat() if t.updated_at else None,
                'created_by': t.created_by
            }
            for t in templates
        ]


def save_stack_template(template_data: Dict) -> str:
    """Save a stack template"""
    import uuid
    with get_db() as session:
        template_id = template_data.get('template_id') or str(uuid.uuid4())

        template = session.query(StackTemplate).filter(
            StackTemplate.template_id == template_id
        ).first()

        if template:
            template.name = template_data['name']
            template.description = template_data.get('description', '')
            template.services = template_data['services']
            template.required_variables = template_data.get('required_variables', [])
            template.api_variables = template_data.get('api_variables', {})
            template.per_device_variables = template_data.get('per_device_variables', [])
            template.tags = template_data.get('tags', [])
            template.updated_at = datetime.utcnow()
        else:
            session.add(StackTemplate(
                template_id=template_id,
                name=template_data['name'],
                description=template_data.get('description', ''),
                services=template_data['services'],
                required_variables=template_data.get('required_variables', []),
                api_variables=template_data.get('api_variables', {}),
                per_device_variables=template_data.get('per_device_variables', []),
                tags=template_data.get('tags', []),
                created_by=template_data.get('created_by', '')
            ))

        return template_id


def delete_stack_template(template_id: str) -> bool:
    """Delete a stack template"""
    with get_db() as session:
        result = session.query(StackTemplate).filter(
            StackTemplate.template_id == template_id
        ).delete()
        return result > 0


# =============================================================================
# Scheduled Operations
# =============================================================================

def create_scheduled_operation(schedule_id: str, stack_id: str, operation_type: str,
                               schedule_type: str, scheduled_time: str,
                               day_of_week: int = None, day_of_month: int = None,
                               created_by: str = None, config_data: str = None) -> str:
    """Create a new scheduled operation"""
    with get_db() as session:
        session.add(ScheduledStackOperation(
            schedule_id=schedule_id,
            stack_id=stack_id,
            operation_type=operation_type,
            schedule_type=schedule_type,
            scheduled_time=scheduled_time,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            config_data=json.loads(config_data) if config_data else None,
            created_by=created_by
        ))
        return schedule_id


def get_scheduled_operations(stack_id: str = None) -> List[Dict]:
    """Get scheduled operations"""
    with get_db() as session:
        query = session.query(ScheduledStackOperation).order_by(ScheduledStackOperation.next_run)
        if stack_id:
            query = query.filter(ScheduledStackOperation.stack_id == stack_id)

        return [
            {
                'schedule_id': s.schedule_id,
                'stack_id': s.stack_id,
                'operation_type': s.operation_type,
                'schedule_type': s.schedule_type,
                'scheduled_time': s.scheduled_time,
                'day_of_week': s.day_of_week,
                'day_of_month': s.day_of_month,
                'config_data': s.config_data,
                'enabled': s.enabled,
                'last_run': s.last_run.isoformat() if s.last_run else None,
                'next_run': s.next_run.isoformat() if s.next_run else None,
                'run_count': s.run_count,
                'created_at': s.created_at.isoformat() if s.created_at else None,
                'created_by': s.created_by
            }
            for s in query.all()
        ]


def get_scheduled_operation(schedule_id: str) -> Optional[Dict]:
    """Get a specific scheduled operation"""
    with get_db() as session:
        s = session.query(ScheduledStackOperation).filter(
            ScheduledStackOperation.schedule_id == schedule_id
        ).first()
        if s:
            return {
                'schedule_id': s.schedule_id,
                'stack_id': s.stack_id,
                'operation_type': s.operation_type,
                'schedule_type': s.schedule_type,
                'scheduled_time': s.scheduled_time,
                'day_of_week': s.day_of_week,
                'day_of_month': s.day_of_month,
                'config_data': s.config_data,
                'enabled': s.enabled,
                'last_run': s.last_run.isoformat() if s.last_run else None,
                'next_run': s.next_run.isoformat() if s.next_run else None,
                'run_count': s.run_count,
                'created_at': s.created_at.isoformat() if s.created_at else None,
                'created_by': s.created_by
            }
        return None


def delete_scheduled_operation(schedule_id: str) -> bool:
    """Delete a scheduled operation"""
    with get_db() as session:
        result = session.query(ScheduledStackOperation).filter(
            ScheduledStackOperation.schedule_id == schedule_id
        ).delete()
        return result > 0


def update_scheduled_operation(schedule_id: str, **kwargs) -> bool:
    """Update a scheduled operation"""
    with get_db() as session:
        op = session.query(ScheduledStackOperation).filter(
            ScheduledStackOperation.schedule_id == schedule_id
        ).first()
        if op:
            for key, value in kwargs.items():
                if hasattr(op, key):
                    setattr(op, key, value)
            return True
        return False


def get_pending_scheduled_operations() -> List[Dict]:
    """Get all enabled scheduled operations that are due to run"""
    with get_db() as session:
        now = datetime.utcnow()
        ops = session.query(ScheduledStackOperation).filter(
            ScheduledStackOperation.enabled == True,
            (ScheduledStackOperation.next_run == None) | (ScheduledStackOperation.next_run <= now)
        ).order_by(ScheduledStackOperation.next_run).all()

        return [
            {
                'schedule_id': s.schedule_id,
                'stack_id': s.stack_id,
                'operation_type': s.operation_type,
                'schedule_type': s.schedule_type,
                'scheduled_time': s.scheduled_time,
                'config_data': s.config_data,
                'enabled': s.enabled
            }
            for s in ops
        ]


# =============================================================================
# API Resources Operations
# =============================================================================

def create_api_resource(resource_id: str, name: str, description: str, base_url: str,
                        auth_type: str, auth_token: str, auth_username: str,
                        auth_password: str, custom_headers: Dict, created_by: str) -> str:
    """Create a new API resource"""
    with get_db() as session:
        session.add(APIResource(
            resource_id=resource_id,
            name=name,
            description=description,
            base_url=base_url,
            auth_type=auth_type,
            auth_token=auth_token,
            auth_username=auth_username,
            auth_password=auth_password,
            custom_headers=custom_headers,
            created_by=created_by
        ))
        return resource_id


def get_api_resource(resource_id: str) -> Optional[Dict]:
    """Get a specific API resource"""
    with get_db() as session:
        r = session.query(APIResource).filter(APIResource.resource_id == resource_id).first()
        if r:
            return {
                'resource_id': r.resource_id,
                'name': r.name,
                'description': r.description,
                'base_url': r.base_url,
                'auth_type': r.auth_type,
                'auth_token': r.auth_token,
                'auth_username': r.auth_username,
                'auth_password': r.auth_password,
                'custom_headers': r.custom_headers,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'updated_at': r.updated_at.isoformat() if r.updated_at else None,
                'created_by': r.created_by
            }
        return None


def get_all_api_resources() -> List[Dict]:
    """Get all API resources"""
    with get_db() as session:
        resources = session.query(APIResource).order_by(APIResource.name).all()
        return [
            {
                'resource_id': r.resource_id,
                'name': r.name,
                'description': r.description,
                'base_url': r.base_url,
                'auth_type': r.auth_type,
                'auth_token': r.auth_token,
                'auth_username': r.auth_username,
                'auth_password': r.auth_password,
                'custom_headers': r.custom_headers
            }
            for r in resources
        ]


def update_api_resource(resource_id: str, name: str, description: str, base_url: str,
                        auth_type: str, auth_token: str, auth_username: str,
                        auth_password: str, custom_headers: Dict) -> bool:
    """Update an API resource"""
    with get_db() as session:
        r = session.query(APIResource).filter(APIResource.resource_id == resource_id).first()
        if r:
            r.name = name
            r.description = description
            r.base_url = base_url
            r.auth_type = auth_type
            r.auth_token = auth_token
            r.auth_username = auth_username
            r.auth_password = auth_password
            r.custom_headers = custom_headers
            r.updated_at = datetime.utcnow()
            return True
        return False


def delete_api_resource(resource_id: str) -> bool:
    """Delete an API resource"""
    with get_db() as session:
        result = session.query(APIResource).filter(APIResource.resource_id == resource_id).delete()
        return result > 0


# =============================================================================
# Helper Functions
# =============================================================================

def _parse_datetime(value) -> Optional[datetime]:
    """Parse datetime from various formats"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    return None


# Stub functions for compatibility (these may not be fully used)
def create_mop_step(*args, **kwargs):
    """Stub - MOP steps are now in YAML"""
    pass

def get_mop_steps(*args, **kwargs):
    """Stub - MOP steps are now in YAML"""
    return []

def get_mop_step(*args, **kwargs):
    """Stub"""
    return None

def update_mop_step(*args, **kwargs):
    """Stub"""
    return False

def delete_mop_step(*args, **kwargs):
    """Stub"""
    return False

def delete_all_mop_steps(*args, **kwargs):
    """Stub"""
    return 0

def create_mop_execution(*args, **kwargs):
    """Stub"""
    return True

def get_mop_execution(*args, **kwargs):
    """Stub"""
    return None

def get_mop_executions(*args, **kwargs):
    """Stub"""
    return []

def update_mop_execution(*args, **kwargs):
    """Stub"""
    return False

def create_custom_step_type(*args, **kwargs):
    """Stub"""
    return None

def update_custom_step_type(*args, **kwargs):
    """Stub"""
    return False

def delete_custom_step_type(*args, **kwargs):
    """Stub"""
    return False

def create_stack_template(*args, **kwargs):
    """Stub - use save_stack_template"""
    pass

def update_stack_template(*args, **kwargs):
    """Stub - use save_stack_template"""
    pass


# ============================================================
# CONFIG BACKUP FUNCTIONS
# ============================================================

def save_config_backup(data: Dict) -> str:
    """Save a config backup to the database"""
    import uuid
    import hashlib

    with get_db() as session:
        backup_id = data.get('backup_id') or str(uuid.uuid4())[:12]
        config_content = data.get('config_content', '')

        # Calculate hash for change detection
        config_hash = hashlib.sha256(config_content.encode()).hexdigest()

        backup = ConfigBackup(
            backup_id=backup_id,
            device_name=data['device_name'],
            device_ip=data.get('device_ip'),
            platform=data.get('platform'),
            config_content=config_content,
            config_format=data.get('config_format', 'native'),
            config_hash=config_hash,
            backup_type=data.get('backup_type', 'scheduled'),
            status=data.get('status', 'success'),
            error_message=data.get('error_message'),
            file_size=len(config_content),
            snapshot_id=data.get('snapshot_id'),
            created_by=data.get('created_by', 'scheduler')
        )
        session.add(backup)
        session.commit()
        return backup_id


def get_config_backup(backup_id: str) -> Optional[Dict]:
    """Get a specific config backup"""
    with get_db() as session:
        backup = session.query(ConfigBackup).filter(
            ConfigBackup.backup_id == backup_id
        ).first()

        if backup:
            return {
                'backup_id': backup.backup_id,
                'device_name': backup.device_name,
                'device_ip': backup.device_ip,
                'platform': backup.platform,
                'config_content': backup.config_content,
                'config_format': backup.config_format,
                'config_hash': backup.config_hash,
                'backup_type': backup.backup_type,
                'status': backup.status,
                'error_message': backup.error_message,
                'file_size': backup.file_size,
                'snapshot_id': backup.snapshot_id,
                'created_at': backup.created_at.isoformat() if backup.created_at else None,
                'created_by': backup.created_by
            }
        return None


def get_latest_backup_for_device(device_name: str) -> Optional[Dict]:
    """Get the most recent successful backup for a device"""
    with get_db() as session:
        backup = session.query(ConfigBackup).filter(
            ConfigBackup.device_name == device_name,
            ConfigBackup.status == 'success'
        ).order_by(ConfigBackup.created_at.desc()).first()

        if backup:
            return {
                'backup_id': backup.backup_id,
                'device_name': backup.device_name,
                'device_ip': backup.device_ip,
                'platform': backup.platform,
                'config_content': backup.config_content,
                'config_format': backup.config_format,
                'config_hash': backup.config_hash,
                'backup_type': backup.backup_type,
                'status': backup.status,
                'file_size': backup.file_size,
                'created_at': backup.created_at.isoformat() if backup.created_at else None,
                'created_by': backup.created_by
            }
        return None


def get_config_backups(device_name: str = None, limit: int = 100, offset: int = 0, snapshot_id: str = None) -> List[Dict]:
    """Get config backups, optionally filtered by device or snapshot"""
    with get_db() as session:
        query = session.query(ConfigBackup)

        if device_name:
            query = query.filter(ConfigBackup.device_name == device_name)

        if snapshot_id:
            query = query.filter(ConfigBackup.snapshot_id == snapshot_id)

        query = query.order_by(ConfigBackup.created_at.desc())
        query = query.offset(offset).limit(limit)

        backups = query.all()
        return [
            {
                'backup_id': b.backup_id,
                'device_name': b.device_name,
                'device_ip': b.device_ip,
                'platform': b.platform,
                'config_format': b.config_format,
                'config_hash': b.config_hash,
                'backup_type': b.backup_type,
                'status': b.status,
                'error_message': b.error_message,
                'file_size': b.file_size,
                'snapshot_id': b.snapshot_id,
                'created_at': b.created_at.isoformat() if b.created_at else None,
                'created_by': b.created_by
            }
            for b in backups
        ]


def get_backup_summary() -> Dict:
    """Get summary statistics for backups"""
    with get_db() as session:
        from sqlalchemy import func

        total_backups = session.query(func.count(ConfigBackup.backup_id)).scalar() or 0
        unique_devices = session.query(func.count(func.distinct(ConfigBackup.device_name))).scalar() or 0
        successful = session.query(func.count(ConfigBackup.backup_id)).filter(
            ConfigBackup.status == 'success'
        ).scalar() or 0
        failed = session.query(func.count(ConfigBackup.backup_id)).filter(
            ConfigBackup.status == 'failed'
        ).scalar() or 0

        # Get last backup time
        last_backup = session.query(func.max(ConfigBackup.created_at)).scalar()

        return {
            'total_backups': total_backups,
            'unique_devices': unique_devices,
            'successful': successful,
            'failed': failed,
            'last_backup': last_backup.isoformat() if last_backup else None
        }


def delete_config_backup(backup_id: str) -> bool:
    """Delete a specific backup"""
    with get_db() as session:
        backup = session.query(ConfigBackup).filter(
            ConfigBackup.backup_id == backup_id
        ).first()
        if backup:
            session.delete(backup)
            session.commit()
            return True
        return False


def delete_old_backups(retention_days: int) -> int:
    """Delete backups older than retention_days, keeping at least one per device"""
    from datetime import timedelta

    with get_db() as session:
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        # Get all devices
        devices = session.query(ConfigBackup.device_name).distinct().all()
        deleted_count = 0

        for (device_name,) in devices:
            # Get all backups for this device older than cutoff
            old_backups = session.query(ConfigBackup).filter(
                ConfigBackup.device_name == device_name,
                ConfigBackup.created_at < cutoff_date
            ).order_by(ConfigBackup.created_at.desc()).all()

            # Keep at least one backup per device
            # Delete all but skip if it's the only backup for this device
            total_backups = session.query(ConfigBackup).filter(
                ConfigBackup.device_name == device_name
            ).count()

            for backup in old_backups:
                if total_backups > 1:
                    session.delete(backup)
                    deleted_count += 1
                    total_backups -= 1

        session.commit()
        return deleted_count


# ============================================================
# BACKUP SCHEDULE FUNCTIONS
# ============================================================

def get_backup_schedule() -> Dict:
    """Get the backup schedule configuration"""
    with get_db() as session:
        schedule = session.query(BackupSchedule).filter(
            BackupSchedule.schedule_id == 'default'
        ).first()

        if schedule:
            return {
                'schedule_id': schedule.schedule_id,
                'enabled': schedule.enabled,
                'interval_hours': schedule.interval_hours,
                'last_run': schedule.last_run.isoformat() if schedule.last_run else None,
                'next_run': schedule.next_run.isoformat() if schedule.next_run else None,
                'retention_days': schedule.retention_days,
                'include_filters': schedule.include_filters or [],
                'exclude_patterns': schedule.exclude_patterns or [],
                'juniper_set_format': schedule.juniper_set_format,
                'created_at': schedule.created_at.isoformat() if schedule.created_at else None,
                'updated_at': schedule.updated_at.isoformat() if schedule.updated_at else None
            }

        # Return defaults if no schedule exists
        return {
            'schedule_id': 'default',
            'enabled': False,
            'interval_hours': 24,
            'last_run': None,
            'next_run': None,
            'retention_days': 30,
            'include_filters': [],
            'exclude_patterns': [],
            'juniper_set_format': True
        }


def save_backup_schedule(data: Dict) -> bool:
    """Save or update the backup schedule configuration"""
    with get_db() as session:
        schedule = session.query(BackupSchedule).filter(
            BackupSchedule.schedule_id == 'default'
        ).first()

        if schedule:
            # Update existing
            schedule.enabled = data.get('enabled', schedule.enabled)
            schedule.interval_hours = data.get('interval_hours', schedule.interval_hours)
            schedule.retention_days = data.get('retention_days', schedule.retention_days)
            schedule.include_filters = data.get('include_filters', schedule.include_filters)
            schedule.exclude_patterns = data.get('exclude_patterns', schedule.exclude_patterns)
            schedule.juniper_set_format = data.get('juniper_set_format', schedule.juniper_set_format)
            if 'last_run' in data:
                schedule.last_run = data['last_run']
            if 'next_run' in data:
                schedule.next_run = data['next_run']
        else:
            # Create new
            schedule = BackupSchedule(
                schedule_id='default',
                enabled=data.get('enabled', False),
                interval_hours=data.get('interval_hours', 24),
                retention_days=data.get('retention_days', 30),
                include_filters=data.get('include_filters', []),
                exclude_patterns=data.get('exclude_patterns', []),
                juniper_set_format=data.get('juniper_set_format', True)
            )
            session.add(schedule)

        session.commit()
        return True


def update_backup_schedule_run_times(last_run: datetime, next_run: datetime) -> bool:
    """Update the last_run and next_run times for the backup schedule"""
    with get_db() as session:
        schedule = session.query(BackupSchedule).filter(
            BackupSchedule.schedule_id == 'default'
        ).first()

        if schedule:
            schedule.last_run = last_run
            schedule.next_run = next_run
            session.commit()
            return True
        return False


def get_devices_needing_backup() -> List[str]:
    """Get list of device names that have no backup or backup older than interval"""
    schedule = get_backup_schedule()
    if not schedule or not schedule.get('enabled'):
        return []

    from datetime import timedelta

    with get_db() as session:
        # Get devices from cache
        devices = session.query(Device).all()
        device_names = [d.name for d in devices]

        # For each device, check if backup is needed
        interval_hours = schedule.get('interval_hours', 24)
        cutoff = datetime.utcnow() - timedelta(hours=interval_hours)

        devices_needing_backup = []
        for name in device_names:
            # Check exclude patterns
            excluded = False
            for pattern in schedule.get('exclude_patterns', []):
                import fnmatch
                if fnmatch.fnmatch(name.lower(), pattern.lower()):
                    excluded = True
                    break

            if excluded:
                continue

            # Check if has recent backup
            recent = session.query(ConfigBackup).filter(
                ConfigBackup.device_name == name,
                ConfigBackup.status == 'success',
                ConfigBackup.created_at > cutoff
            ).first()

            if not recent:
                devices_needing_backup.append(name)

        return devices_needing_backup


# ============================================================================
# Device Override Functions
# ============================================================================

def get_device_override(device_name: str) -> Optional[Dict]:
    """Get device-specific overrides for a device"""
    with get_db() as session:
        override = session.query(DeviceOverride).filter(
            DeviceOverride.device_name == device_name
        ).first()

        if not override:
            return None

        return {
            'device_name': override.device_name,
            'device_type': override.device_type,
            'host': override.host,
            'port': override.port,
            'username': override.username,
            'password': override.password,
            'secret': override.secret,
            'timeout': override.timeout,
            'conn_timeout': override.conn_timeout,
            'auth_timeout': override.auth_timeout,
            'banner_timeout': override.banner_timeout,
            'notes': override.notes,
            'disabled': override.disabled,
            'created_at': override.created_at.isoformat() if override.created_at else None,
            'updated_at': override.updated_at.isoformat() if override.updated_at else None
        }


def save_device_override(data: Dict) -> bool:
    """Save or update device-specific overrides"""
    device_name = data.get('device_name')
    if not device_name:
        return False

    with get_db() as session:
        override = session.query(DeviceOverride).filter(
            DeviceOverride.device_name == device_name
        ).first()

        if not override:
            override = DeviceOverride(device_name=device_name)
            session.add(override)

        # Update fields (only if provided, None means use default)
        if 'device_type' in data:
            override.device_type = data['device_type'] or None
        if 'host' in data:
            override.host = data['host'] or None
        if 'port' in data:
            override.port = int(data['port']) if data['port'] else None
        if 'username' in data:
            override.username = data['username'] or None
        if 'password' in data:
            override.password = data['password'] or None
        if 'secret' in data:
            override.secret = data['secret'] or None
        if 'timeout' in data:
            override.timeout = int(data['timeout']) if data['timeout'] else None
        if 'conn_timeout' in data:
            override.conn_timeout = int(data['conn_timeout']) if data['conn_timeout'] else None
        if 'auth_timeout' in data:
            override.auth_timeout = int(data['auth_timeout']) if data['auth_timeout'] else None
        if 'banner_timeout' in data:
            override.banner_timeout = int(data['banner_timeout']) if data['banner_timeout'] else None
        if 'notes' in data:
            override.notes = data['notes'] or None
        if 'disabled' in data:
            override.disabled = bool(data['disabled'])

        override.updated_at = datetime.utcnow()
        session.commit()
        return True


def delete_device_override(device_name: str) -> bool:
    """Delete device-specific overrides"""
    with get_db() as session:
        result = session.query(DeviceOverride).filter(
            DeviceOverride.device_name == device_name
        ).delete()
        session.commit()
        return result > 0


def get_all_device_overrides() -> List[Dict]:
    """Get all device overrides"""
    with get_db() as session:
        overrides = session.query(DeviceOverride).all()
        return [
            {
                'device_name': o.device_name,
                'device_type': o.device_type,
                'host': o.host,
                'port': o.port,
                'username': o.username,
                'has_password': bool(o.password),
                'has_secret': bool(o.secret),
                'timeout': o.timeout,
                'notes': o.notes,
                'disabled': o.disabled,
                'updated_at': o.updated_at.isoformat() if o.updated_at else None
            }
            for o in overrides
        ]


# ============================================================
# CONFIG SNAPSHOT FUNCTIONS
# ============================================================

def create_config_snapshot(data: Dict) -> str:
    """Create a new config snapshot"""
    import uuid

    with get_db() as session:
        snapshot_id = data.get('snapshot_id') or str(uuid.uuid4())

        snapshot = ConfigSnapshot(
            snapshot_id=snapshot_id,
            name=data.get('name'),
            description=data.get('description'),
            snapshot_type=data.get('snapshot_type', 'manual'),
            status='in_progress',
            total_devices=data.get('total_devices', 0),
            success_count=0,
            failed_count=0,
            created_by=data.get('created_by')
        )
        session.add(snapshot)
        session.commit()
        return snapshot_id


def get_config_snapshot(snapshot_id: str) -> Optional[Dict]:
    """Get a specific config snapshot with its backups"""
    with get_db() as session:
        snapshot = session.query(ConfigSnapshot).filter(
            ConfigSnapshot.snapshot_id == snapshot_id
        ).first()

        if not snapshot:
            return None

        return {
            'snapshot_id': snapshot.snapshot_id,
            'name': snapshot.name,
            'description': snapshot.description,
            'snapshot_type': snapshot.snapshot_type,
            'status': snapshot.status,
            'total_devices': snapshot.total_devices,
            'success_count': snapshot.success_count,
            'failed_count': snapshot.failed_count,
            'created_at': snapshot.created_at.isoformat() if snapshot.created_at else None,
            'completed_at': snapshot.completed_at.isoformat() if snapshot.completed_at else None,
            'created_by': snapshot.created_by
        }


def get_config_snapshots(limit: int = 50, offset: int = 0) -> List[Dict]:
    """Get all config snapshots"""
    with get_db() as session:
        snapshots = session.query(ConfigSnapshot).order_by(
            ConfigSnapshot.created_at.desc()
        ).offset(offset).limit(limit).all()

        return [
            {
                'snapshot_id': s.snapshot_id,
                'name': s.name,
                'description': s.description,
                'snapshot_type': s.snapshot_type,
                'status': s.status,
                'total_devices': s.total_devices,
                'success_count': s.success_count,
                'failed_count': s.failed_count,
                'created_at': s.created_at.isoformat() if s.created_at else None,
                'completed_at': s.completed_at.isoformat() if s.completed_at else None,
                'created_by': s.created_by
            }
            for s in snapshots
        ]


def update_config_snapshot(snapshot_id: str, data: Dict) -> bool:
    """Update a config snapshot"""
    with get_db() as session:
        snapshot = session.query(ConfigSnapshot).filter(
            ConfigSnapshot.snapshot_id == snapshot_id
        ).first()

        if not snapshot:
            return False

        if 'name' in data:
            snapshot.name = data['name']
        if 'description' in data:
            snapshot.description = data['description']
        if 'status' in data:
            snapshot.status = data['status']
        if 'success_count' in data:
            snapshot.success_count = data['success_count']
        if 'failed_count' in data:
            snapshot.failed_count = data['failed_count']
        if 'completed_at' in data:
            snapshot.completed_at = _parse_datetime(data['completed_at'])

        session.commit()
        return True


def increment_snapshot_counts(snapshot_id: str, success: bool = True) -> bool:
    """Increment success or failed count for a snapshot"""
    with get_db() as session:
        snapshot = session.query(ConfigSnapshot).filter(
            ConfigSnapshot.snapshot_id == snapshot_id
        ).first()

        if not snapshot:
            return False

        if success:
            snapshot.success_count = (snapshot.success_count or 0) + 1
        else:
            snapshot.failed_count = (snapshot.failed_count or 0) + 1

        # Check if snapshot is complete
        total_done = (snapshot.success_count or 0) + (snapshot.failed_count or 0)
        if total_done >= snapshot.total_devices:
            snapshot.completed_at = datetime.utcnow()
            if snapshot.failed_count == 0:
                snapshot.status = 'complete'
            elif snapshot.success_count == 0:
                snapshot.status = 'failed'
            else:
                snapshot.status = 'partial'

        session.commit()
        return True


def delete_config_snapshot(snapshot_id: str) -> bool:
    """Delete a config snapshot and all its backups"""
    with get_db() as session:
        snapshot = session.query(ConfigSnapshot).filter(
            ConfigSnapshot.snapshot_id == snapshot_id
        ).first()

        if not snapshot:
            return False

        session.delete(snapshot)
        session.commit()
        return True


def get_snapshot_backups(snapshot_id: str) -> List[Dict]:
    """Get all backups for a specific snapshot"""
    return get_config_backups(snapshot_id=snapshot_id, limit=1000)
