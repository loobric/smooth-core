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
    """Initialize database tables.
    
    This should be called during application startup to ensure all
    database tables are created.
    """
    from smooth.database.schema import Base  # Import here to avoid circular imports
    Base.metadata.create_all(bind=engine)
