# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Main FastAPI application entry point.

This module creates and configures the FastAPI application.

Assumptions:
- FastAPI instance should include OpenAPI documentation
- Authentication middleware is optional based on settings
- API versioning is handled via path prefix
"""
import os
from pathlib import Path
from fastapi import FastAPI
from smooth.config import settings
from smooth.api.auth import router as auth_router
from smooth.api.backup_api import router as backup_router
from smooth.api.users import router as users_router
from smooth.api.catalogs import router as catalogs_router
from smooth.api.tool_items import router as tool_items_router
from smooth.api.tool_assemblies import router as tool_assemblies_router
from smooth.api.tool_instances import router as tool_instances_router
from smooth.api.tool_presets import router as tool_presets_router
from smooth.api.tool_usage import router as tool_usage_router
from smooth.api.tool_sets import router as tool_sets_router
from smooth.api.audit_log_api import router as audit_log_router
from smooth.api.changes_api import router as changes_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.
    
    Returns:
        FastAPI: Configured FastAPI application instance
        
    Assumptions:
    - OpenAPI docs are enabled by default
    - Title and version are set for documentation
    - CORS is not configured yet (will be added later if needed)
    - Database schema is initialized on startup
    """
    # Initialize database schema
    from smooth.database.session import init_db
    init_db()
    
    # Print database configuration on startup
    db_url = settings.database_url
    if db_url.startswith("sqlite:///"):
        # Extract the path from sqlite:///path
        db_path = db_url.replace("sqlite:///", "")
        # Resolve to absolute path
        if db_path.startswith("./"):
            db_path = db_path[2:]
        abs_path = Path(db_path).resolve()
        print(f"Database: {abs_path}")
        print(f"Database exists: {abs_path.exists()}")
    else:
        print(f"Database: {db_url}")
    
    app = FastAPI(
        title="Smooth Tool Data Exchange",
        description="Vendor-neutral tool data synchronization system",
        version="0.1.0",
        docs_url=f"/api/{settings.api_version}/docs",
        redoc_url=f"/api/{settings.api_version}/redoc",
        openapi_url=f"/api/{settings.api_version}/openapi.json",
    )
    
    # Health check endpoint (before mounting static files and routers)
    @app.get("/api/health")
    async def health_check():
        """API health check endpoint.
        
        Returns:
            dict: Service status information
        """
        return {
            "service": "smooth",
            "version": "0.1.0",
            "status": "running"
        }
    
    # Include routers
    app.include_router(auth_router)
    app.include_router(backup_router)
    app.include_router(users_router)
    app.include_router(catalogs_router)
    app.include_router(tool_items_router)
    app.include_router(tool_assemblies_router)
    app.include_router(tool_instances_router)
    app.include_router(tool_presets_router)
    app.include_router(tool_usage_router)
    app.include_router(tool_sets_router)
    app.include_router(audit_log_router)
    app.include_router(changes_router)
    
    return app


app = create_app()
