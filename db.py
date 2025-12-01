"""
Database Layer for NetStacks
Uses PostgreSQL via SQLAlchemy
"""
import logging

log = logging.getLogger(__name__)

log.info("Using PostgreSQL database backend")
from database_postgres import *
