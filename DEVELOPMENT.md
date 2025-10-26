# Smooth Core Development

This document contains development information specific to **smooth-core** - the application-agnostic REST API and database.

> **See also**: [../DEVELOPMENT.md](../DEVELOPMENT.md) for cross-project development principles, AI prompts, and coding standards that apply to all Smooth repositories.

## Project Overview

Smooth Core provides:
- RESTful API with bulk-first design
- SQLAlchemy-based database schema
- User authentication and authorization
- API key management with scoped permissions
- Audit logging for all data changes
- Backup/restore functionality
- Change detection and synchronization
- Version tracking for all entities

## Development Plan

This plan follows the infrastructure priorities outlined in the top-level DEVELOPMENT.md, organized into phases following TDD principles.

### Phase 1: Logging Infrastructure ✅ COMPLETE
- [x] Configure structlog with JSON formatting
- [x] Set up context binding (user_id, request_id)
- [x] Implement log level configuration
- [x] Create logging utilities for application, audit, and security logs
- [x] Write tests for logging functions

**Completed:** 10/10 tests passing, 93% coverage. Files created:
- `smooth/logging_config.py` - structlog configuration with JSON/console output
- `smooth/logging_utils.py` - Application, audit, and security log utilities
- `tests/unit/test_logging.py` - Comprehensive unit tests

### Phase 2: Database Schema ✅ COMPLETE
- [x] Design SQLAlchemy models for all entities
- [x] Add versioning fields (created_at, updated_at, version)
- [x] Add user attribution fields (user_id, created_by, updated_by)
- [x] Implement database migrations with Alembic (deferred - using init_db() for development)
- [x] Write tests for schema validation

**Completed:** 19/19 tests passing, 95% coverage.

### Phase 3: Authentication & Authorization ✅ COMPLETE

#### Phase 3a: User Account System ✅ COMPLETE
- [x] Write tests for user registration and login
- [x] Implement user model (email, password hash)
- [x] Implement password hashing (bcrypt/argon2)
- [x] Implement session management for web UI
- [x] Add user CRUD endpoints

**Completed:** 19/19 unit tests + 11/11 integration tests passing.

#### Phase 3b: API Key System ✅ COMPLETE
- [x] Write tests for API key creation with scopes
- [x] Implement API key model (linked to user, scopes, machine_id, expiration)
- [x] Implement API key hashing
- [x] Implement API key validation middleware
- [x] Add API key management endpoints
- [x] Test scope-based permission checks
- [x] Test machine-specific key restrictions

**Completed:** 15/15 unit tests + 8/8 integration tests passing.

### Phase 4: Web Front-End (Basic) ✅ COMPLETE
- [x] Design page templates (Jinja2)
- [x] Implement user registration page
- [x] Implement login page with session management
- [x] Create authenticated user dashboard
- [x] Build API key management UI
- [x] Add logout functionality
- [x] Style with minimal CSS
- [x] Test session security

### Phase 5: Backup & Restore ✅ COMPLETE
- [x] Write tests for backup operations
- [x] Implement full database export (JSON format)
- [x] Implement data validation on restore
- [x] Implement atomic restore operations
- [x] Test backup/restore with versioned data
- [x] Add backup/restore endpoints to web UI

**Completed:** 20/20 unit tests passing with multi-tenant support.

### Phase 6: Test Framework Enhancement ✅ COMPLETE
- [x] Create pytest fixtures using backup/restore
- [x] Set up test database isolation
- [x] Configure auth disabled mode for tests
- [x] Add property-based testing setup (hypothesis)
- [x] Create sample test datasets

**Completed:** 9/9 tests passing (5 fixture tests + 4 hypothesis tests).

### Phase 7: Core CRUD Operations

#### Phase 7a: ToolItem API ✅ COMPLETE
- [x] Write tests for bulk create (array input)
- [x] Write tests for bulk read/query
- [x] Write tests for bulk update with version conflicts
- [x] Write tests for bulk delete
- [x] Implement ToolItem endpoints with bulk-first design
- [x] Test partial success scenarios

**Completed:** 13/13 integration tests passing.

#### Phase 7b: Additional Entity APIs ✅ COMPLETE
- [x] ToolAssembly CRUD with tests
- [x] ToolInstance CRUD with tests
- [x] ToolPreset CRUD with tests
- [x] ToolUsage CRUD with tests
- [x] ToolSet CRUD with tests

**Completed:** All 5 entity APIs with 37 integration tests passing.

#### Phase 7c: Audit Logging Integration ✅ COMPLETE
- [x] Log all data modifications with user context
- [x] Test audit log entries for all operations
- [x] Implement audit log immutability

**Completed:** Audit logging infrastructure with 8 unit tests passing.

#### Phase 7d: Web UI for CRUD Operations ✅ COMPLETE
- [x] ToolItem management interface
- [x] ToolAssembly builder with component selection
- [x] ToolInstance tracker with status management
- [x] ToolPreset manager for machine setups
- [x] ToolSet builder for collections
- [x] Bulk operation support in UI
- [x] Pagination and filtering
- [x] Form validation with server feedback

### Phase 8: LinuxCNC Format Translator ✅ COMPLETE
- [x] Write tests for LinuxCNC parser
- [x] Implement LinuxCNC tool table parser
- [x] Implement LinuxCNC tool table generator
- [x] Test round-trip conversion
- [x] Create import/export API endpoints

**Note:** LinuxCNC translator moved to smooth-linuxcnc repository (client-side conversion).

### Phase 9: Authorization Layer ✅ COMPLETE
- [x] Implement function-level permission checks
- [x] Test read permission enforcement
- [x] Test write permission enforcement by scope
- [x] Test data isolation between users
- [x] Add detailed logging for authorization decisions

**Completed:** Full authorization layer with scope-based permissions.

### Phase 10: Change Detection API ✅ COMPLETE
- [x] Write tests for "changes since version X" queries
- [x] Write tests for timestamp-based queries
- [x] Implement change detection endpoints
- [x] Filter changes by user permissions
- [x] Optimize queries with database indexes

**Completed:** Full change detection system with 9 unit + 13 integration tests.

### Phase 11: Format Translators

#### Phase 11a: FreeCAD Format ✅ COMPLETE
- [x] Collect real FreeCAD tool library sample files
- [x] Write tests for FreeCAD parser
- [x] Test round-trip conversion
- [x] Implement export (Smooth → FreeCAD)

**Note:** FreeCAD translators moved to smooth-freecad repository (client-side conversion).

#### Phase 11b: ToolSet Versioning System ✅ COMPLETE
- [x] Create ToolSetHistory schema table
- [x] Implement snapshot function for version capture
- [x] Add automatic snapshotting on updates
- [x] Create API endpoints for history management
- [x] Build web UI for version history and restore
- [x] Write comprehensive unit and integration tests

**Completed:** Level 2 versioning with snapshot-based history, rollback, and comparison features.

#### Phase 11c: Future Format Translators
- [ ] Haas tool table translator with tests
- [ ] Mazak tool table translator with tests
- [ ] Mastercam tool library translator with tests
- [ ] Fusion 360 tool library translator with tests

### Phase 12: Notification System
- [ ] Write tests for MQTT message publishing
- [ ] Write tests for WebSocket connections
- [ ] Implement MQTT broker integration
- [ ] Implement WebSocket server
- [ ] Add auth context to notifications
- [ ] Test subscription filtering by user/machine

### Phase 13: Log Query API
- [ ] Write tests for log search and filtering
- [ ] Implement log query endpoints
- [ ] Add log filtering by user, entity, date range
- [ ] Implement audit log export for compliance
- [ ] Test log retention policies

## Project Structure

```
smooth-core/
├── smooth/                 # Main application package
│   ├── __init__.py
│   ├── main.py            # FastAPI application entry point
│   ├── config.py          # Configuration management
│   ├── database/          # Database schema and operations
│   │   ├── schema.py      # SQLAlchemy table definitions
│   │   └── ...
│   ├── api/               # API endpoints
│   │   ├── tool_items.py
│   │   ├── tool_assemblies.py
│   │   └── ...
│   ├── auth/              # Authentication/authorization
│   │   ├── password.py
│   │   ├── user.py
│   │   ├── apikey.py
│   │   └── authorization.py
│   ├── backup.py          # Backup/restore functions
│   ├── audit.py           # Audit logging
│   ├── change_detection.py
│   └── versioning.py
├── tests/                 # Test suite
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   ├── property/         # Property-based tests
│   ├── fixtures/         # Test data and snapshots
│   └── conftest.py       # Pytest configuration
├── requirements.txt      # Production dependencies
├── requirements-dev.txt  # Development dependencies
├── pytest.ini           # Pytest configuration
├── .env.example         # Environment variables template
├── README.md            # User documentation
└── DEVELOPMENT.md       # This file
```

## Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_schema.py

# Run with coverage
pytest --cov=smooth --cov-report=html

# Run integration tests only
pytest tests/integration/

# Run property-based tests
pytest tests/property/
```

## Database Migrations

Currently using `init_db()` for development. Alembic migrations planned for production:

```bash
# Initialize Alembic (future)
alembic init alembic

# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## API Documentation

Start the server and visit:
- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc

## Configuration

Environment variables (see `.env.example`):
- `DATABASE_URL` - Database connection string
- `AUTH_ENABLED` - Enable/disable authentication (default: true)
- `SECRET_KEY` - Session encryption key
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)

## Dependencies

Core dependencies:
- FastAPI - Web framework
- SQLAlchemy - ORM
- structlog - Structured logging
- bcrypt - Password hashing
- pytest - Testing framework
- hypothesis - Property-based testing
