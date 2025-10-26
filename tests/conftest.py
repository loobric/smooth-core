# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Pytest configuration and shared fixtures.

This module provides test fixtures that are shared across the test suite.

Assumptions:
- Tests run with authentication disabled by default
- Each test gets a fresh TestClient instance
- Database fixtures use in-memory SQLite
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from smooth.main import create_app
from smooth.database.schema import Base


@pytest.fixture
def app():
    """Create a FastAPI application instance for testing.
    
    Returns:
        FastAPI: Application instance with test configuration
        
    Assumptions:
    - Auth is disabled for testing
    - Uses in-memory or test database (when implemented)
    """
    return create_app()


@pytest.fixture
def client(db_session):
    """Create test client sharing the same database session.
    
    Args:
        db_session: Shared database session fixture
        
    Returns:
        TestClient: FastAPI test client
        
    Assumptions:
    - Shares database session with tests
    - Overrides get_db dependency to use shared session
    """
    from smooth.main import create_app
    from smooth.api.auth import get_db
    
    app = create_app()
    
    # Override get_db to return the shared session
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # Don't close, let the fixture handle it
    
    app.dependency_overrides[get_db] = override_get_db
    
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def minimal_backup():
    """Minimal backup fixture with single admin user.
    
    Returns:
        dict: Backup with one user, no tool data
        
    Assumptions:
    - Used for testing basic functionality
    - Single admin user for testing
    """
    from tests.fixtures.sample_data import create_minimal_backup
    return create_minimal_backup()


@pytest.fixture
def single_user_backup():
    """Single user backup fixture with tool data.
    
    Returns:
        dict: Backup with one user, API keys, and tool items
        
    Assumptions:
    - Used for testing user-level operations
    - Includes realistic tool data
    """
    from tests.fixtures.sample_data import create_single_user_backup
    return create_single_user_backup()


@pytest.fixture
def multi_user_backup():
    """Multi-user backup fixture with tool data.
    
    Returns:
        dict: Backup with multiple users, each with their own data
        
    Assumptions:
    - Used for testing multi-tenant isolation
    - Each user has their own tool items and API keys
    """
    from tests.fixtures.sample_data import create_multi_user_backup
    return create_multi_user_backup()


@pytest.fixture
def db_with_sample_data(db_session):
    """Database session pre-loaded with sample data.
    
    Args:
        db_session: Base database session fixture
        
    Returns:
        Session: Database session with sample data loaded
        
    Assumptions:
    - Uses backup/restore to load data
    - Includes single user with tool items
    - Useful for integration tests
    """
    from smooth.backup import restore_backup
    from tests.fixtures.sample_data import create_single_user_backup
    
    backup = create_single_user_backup()
    restore_backup(db_session, backup)
    
    return db_session


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing.
    
    Returns:
        Session: SQLAlchemy session
        
    Assumptions:
    - Uses in-memory SQLite for fast tests
    - StaticPool keeps connection alive across threads
    - check_same_thread=False allows TestClient to use same connection
    - Schema is created fresh for each test
    - Session is closed after test
    """
    from sqlalchemy.pool import StaticPool
    
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    
    session = Session(engine)
    yield session
    session.close()
