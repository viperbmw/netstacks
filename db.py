"""
Database Abstraction Layer for NetStacks
Switches between SQLite and PostgreSQL based on USE_POSTGRES environment variable
"""
import os
import logging

log = logging.getLogger(__name__)

USE_POSTGRES = os.environ.get('USE_POSTGRES', 'false').lower() in ('true', '1', 'yes')

if USE_POSTGRES:
    log.info("Using PostgreSQL database backend")
    from database_postgres import *
else:
    log.info("Using SQLite database backend")
    from database import *
