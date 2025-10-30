# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Database session management.

This module provides database session management utilities including
the get_db dependency for FastAPI and session factory.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from smooth.config import settings

# Create database engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

def get_db() -> Session:
    """Dependency for getting database session.
    
    Yields:
        Session: Database session
        
    Example:
        @router.get("/items/{item_id}")
        def read_item(item_id: int, db: Session = Depends(get_db)):
            return db.query(Item).filter(Item.id == item_id).first()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db() -> None:
    """Initialize database tables if they don't exist.
    
    This should be called during application startup to ensure all
    database tables are created. Uses SQLAlchemy's create_all() which
    only creates tables that don't already exist - it will not overwrite
    or modify existing tables.
    
    Assumptions:
    - Safe to call multiple times
    - Does not drop or modify existing tables
    - Does not affect existing data
    """
    from smooth.database.schema import Base  # Import here to avoid circular imports
    from sqlalchemy import inspect
    
    # Check if tables already exist
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    if existing_tables:
        print(f"Database has {len(existing_tables)} existing tables - skipping initialization")
    else:
        print("Initializing fresh database schema...")
        Base.metadata.create_all(bind=engine)
        print("Database schema created")
