"""
NetStacks Auth Service - FastAPI Application

Provides authentication, user management, and system settings APIs.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from netstacks_core.db import init_db, get_session, seed_defaults, User
from netstacks_core.auth import hash_password

from app.config import get_settings
from app.routes import auth, users, settings, config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

settings_config = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    log.info(f"Starting {settings_config.SERVICE_NAME} service on port {settings_config.SERVICE_PORT}")

    # Initialize database
    try:
        init_db()
        log.info("Database initialized")

        # Seed defaults and create admin user if needed
        session = get_session()
        try:
            seed_defaults(session)

            # Create default admin user if not exists
            admin = session.query(User).filter(User.username == 'admin').first()
            if not admin:
                admin = User(
                    username='admin',
                    password_hash=hash_password('admin'),
                    auth_source='local'
                )
                session.add(admin)
                session.commit()
                log.info("Created default admin user (username: admin, password: admin)")
        finally:
            session.close()

    except Exception as e:
        log.error(f"Database initialization failed: {e}")
        raise

    yield

    # Shutdown
    log.info("Shutting down auth service")


# Create FastAPI application
app = FastAPI(
    title="NetStacks Auth Service",
    description="Authentication, user management, and system settings API",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
origins = settings_config.CORS_ORIGINS.split(',') if settings_config.CORS_ORIGINS != '*' else ['*']
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/auth/users", tags=["Users"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])  # Alias for frontend compatibility
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(config.router, prefix="/api/auth/config", tags=["Auth Config"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": settings_config.SERVICE_NAME}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "NetStacks Auth Service",
        "version": "1.0.0",
        "endpoints": [
            "/api/auth",
            "/api/auth/users",
            "/api/settings",
            "/api/auth/config",
        ]
    }
