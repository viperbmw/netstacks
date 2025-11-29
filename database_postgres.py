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
    StepType, TaskHistory, DEFAULT_STEP_TYPES, DEFAULT_MENU_ITEMS
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
            session.add(StepType(**st, enabled=True, is_custom=False))
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
            StepType.is_custom, StepType.name
        ).all()
        return [
            {
                'step_type_id': t.step_type_id,
                'name': t.name,
                'description': t.description,
                'category': t.category,
                'parameters_schema': t.parameters_schema or {},
                'handler_function': t.handler_function,
                'icon': t.icon,
                'enabled': t.enabled,
                'is_custom': t.is_custom
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
                'parameters_schema': t.parameters_schema or {},
                'handler_function': t.handler_function,
                'icon': t.icon,
                'enabled': t.enabled,
                'is_custom': t.is_custom
            }
        return None


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
