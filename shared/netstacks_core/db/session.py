"""
Database Session Management for NetStacks

Provides session factory and database initialization functions.
"""

import os
import logging
from typing import Optional, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine

from .models import (
    Base,
    StepType,
    MenuItem,
    DEFAULT_STEP_TYPES,
    DEFAULT_MENU_ITEMS,
)

log = logging.getLogger(__name__)

# Default database URL - can be overridden via environment variable
DEFAULT_DATABASE_URL = 'postgresql://netstacks:netstacks_secret_change_me@postgres:5432/netstacks'

# Module-level engine cache
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def get_database_url() -> str:
    """Get the database URL from environment or use default."""
    return os.environ.get('DATABASE_URL', DEFAULT_DATABASE_URL)


def get_engine(url: Optional[str] = None) -> Engine:
    """
    Get or create the database engine.

    Args:
        url: Optional database URL. If not provided, uses DATABASE_URL env var.

    Returns:
        SQLAlchemy Engine instance
    """
    global _engine

    if url:
        # Create a new engine for a specific URL
        return create_engine(url, echo=False, pool_pre_ping=True)

    if _engine is None:
        db_url = get_database_url()
        _engine = create_engine(db_url, echo=False, pool_pre_ping=True)
        log.info(f"Created database engine for: {db_url.split('@')[-1]}")

    return _engine


def get_session_factory(engine: Optional[Engine] = None) -> sessionmaker:
    """
    Get or create the session factory.

    Args:
        engine: Optional SQLAlchemy engine. If not provided, uses default engine.

    Returns:
        SQLAlchemy sessionmaker instance
    """
    global _session_factory

    if engine:
        # Create a new session factory for a specific engine
        return sessionmaker(bind=engine, autocommit=False, autoflush=False)

    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False
        )

    return _session_factory


def get_session(engine: Optional[Engine] = None) -> Session:
    """
    Create a new database session.

    Args:
        engine: Optional SQLAlchemy engine. If not provided, uses default engine.

    Returns:
        SQLAlchemy Session instance

    Note:
        The caller is responsible for closing the session.
    """
    factory = get_session_factory(engine)
    return factory()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Yields a session and ensures it's closed after the request.

    Usage:
        @router.get("/items")
        async def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    session = get_session()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope(engine: Optional[Engine] = None) -> Generator[Session, None, None]:
    """
    Provide a transactional scope around a series of operations.

    Usage:
        with session_scope() as session:
            session.query(User).all()

    Args:
        engine: Optional SQLAlchemy engine.

    Yields:
        SQLAlchemy Session instance
    """
    session = get_session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine: Optional[Engine] = None) -> Engine:
    """
    Initialize the database by creating all tables.

    Args:
        engine: Optional SQLAlchemy engine. If not provided, uses default engine.

    Returns:
        The SQLAlchemy Engine used for initialization
    """
    if engine is None:
        engine = get_engine()

    Base.metadata.create_all(engine)
    log.info("Database tables created successfully")

    return engine


def seed_defaults(session: Session) -> None:
    """
    Seed default data into the database.

    Seeds:
    - Default step types for MOPs
    - Default menu items

    Args:
        session: SQLAlchemy Session instance
    """
    # Seed step types
    existing_step_types = session.query(StepType).count()
    if existing_step_types == 0:
        log.info("Seeding default step types...")
        for st in DEFAULT_STEP_TYPES:
            session.add(StepType(**st, enabled=True))
        session.commit()
        log.info(f"Seeded {len(DEFAULT_STEP_TYPES)} step types")

    # Seed menu items
    existing_menu_items = session.query(MenuItem).count()
    if existing_menu_items == 0:
        log.info("Seeding default menu items...")
        for mi in DEFAULT_MENU_ITEMS:
            session.add(MenuItem(**mi))
        session.commit()
        log.info(f"Seeded {len(DEFAULT_MENU_ITEMS)} menu items")


def reset_engine() -> None:
    """
    Reset the module-level engine and session factory.

    Useful for testing or when database configuration changes.
    """
    global _engine, _session_factory

    if _engine:
        _engine.dispose()

    _engine = None
    _session_factory = None
    log.info("Database engine reset")
