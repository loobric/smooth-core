# Smooth Core Development Guide

## Development Documentation
1. **[Development Guide](DEVELOPMENT.md)** - This document 
2. **[Design Philosophy](DESIGN_PHILOSOPHY.md)** - Core principles and architecture
3. **[Authentication](AUTHENTICATION.md)** - Authentication and authorization
4. **[Architecture](ARCHITECTURE.md)** - System architecture and components
5. **[Data Model](DATA_MODEL.md)** - Database schema and relationships

## Development Setup

### Prerequisites
- Python 3.9+
- SQLite (development) / PostgreSQL (production)
- UV (recommended) or pip

## Quick Start for running locally

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/your-username/smooth-core.git
   cd smooth-core
   ```

2. Set up the development environment:
   ```bash
   uv venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   uv pip install -e ".[dev]"
   ```

3. Run tests:
   ```bash
   pytest

4. Start the development server:
   ```bash
   uvicorn smooth.main:app --reload
   ```

## Repo Organization

```
smooth-core/
├── smooth/               # Main package
│   ├── api/             # API endpoints and routers
│   ├── auth/            # Authentication & authorization
│   ├── database/        # Database models and sessions
│   ├── models/          # Data models and schemas
│   ├── notifications/   # Notification system
│   └── static/          # Static files and templates
├── tests/               # Test suite
│   ├── fixtures/        # Test fixtures
│   ├── integration/     # Integration tests
│   ├── property/        # Property-based tests
│   └── unit/            # Unit tests
├── migrations/          # Database migrations
└── docs/                # Documentation
```

## Testing

### Running Tests
```bash
# Run tests with coverage
pytest --cov=smooth tests/

# Run specific test file
pytest tests/unit/test_module.py

# Run with detailed output
pytest -v
```

### Authentication in Tests

**Important:** Authentication is **enabled by default** (`AUTH_ENABLED=true`). This ensures tests run in a production-like environment and catch authentication/authorization bugs.

#### Disabling Authentication for Specific Tests

Only disable authentication when absolutely necessary (e.g., testing unauthenticated endpoints). Use a pytest fixture:

```python
@pytest.fixture
def disable_auth(monkeypatch):
    """Disable authentication for tests that need it."""
    monkeypatch.setenv("AUTH_ENABLED", "false")

def test_unauthenticated_endpoint(client, disable_auth):
    """Test that works without authentication."""
    response = client.get("/api/health")
    assert response.status_code == 200
```

#### Best Practices

- **Default to auth enabled**: Write tests that properly authenticate users
- **Explicit opt-out**: Only disable auth when testing specific unauthenticated flows
- **Use fixtures**: Create reusable fixtures for common auth scenarios (admin user, normal user, etc.)
- **Test auth failures**: Verify that endpoints properly reject unauthenticated/unauthorized requests

## Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```


## Testing API Endpoints

1. Start the development server:
   ```bash
   uvicorn smooth.main:app --reload
   ```

2. Access interactive documentation:
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

### Planned Future Work

### Authentication & Authorization
**Completed:**
- ✅ User registration and login endpoints
- ✅ Session-based authentication with cookies
- ✅ API key creation and management
- ✅ First user automatically becomes admin
- ✅ Admin-only user registration (after first user)
- ✅ User-scoped API key listing (users only see their own keys)
- ✅ CLI tool for user and API key management
- ✅ Authentication enabled by default (production-like)
- ✅ Test fixtures for disabling auth when needed

**Remaining Work:**
- [ ] Password reset/recovery flow
- [ ] Email verification
- [ ] Multi-factor authentication (MFA)
- [ ] User role management (beyond admin/user)
- [ ] API key expiration enforcement
- [ ] Rate limiting per user/API key

### Manufacturer Support
- [X] Write tests for manufacturer accounts
- [ ] Implement manufacturer accounts
- [X] Write tests for manufacturer tools
- [ ] Implement manufacturer tool import

### Tag-based API key control

**Current State:**
- ✅ Database schema: `ApiKey.tags` and resource `tags` columns added (migration: `add_tags_columns.py`)
- ✅ Core functions: `check_tag_access()`, `require_tag_access()`, `check_tag_scope_access()` in `auth/authorization.py`
- ✅ API key creation: Tags can be set via `/api/v1/auth/keys` endpoint
- ✅ API key validation: `validate_api_key()` returns tags tuple
- ✅ Request state: Tags stored in `request.state.api_key_tags`, `is_api_key_auth` flag distinguishes session vs API key auth
- ✅ Dependencies: `require_tag_access()` factory creates tag-aware endpoint guards
- ✅ Tool assemblies: Full tag enforcement (create, read, update, delete, list)
- ✅ Integration tests: Comprehensive test coverage in `test_tag_enforcement.py`
- ✅ Documentation: AUTHENTICATION.md updated with tag usage patterns and examples
- ✅ Admin bypass: `admin:*` scope bypasses all tag checks
- ✅ Session auth: Bypasses tag checks (users own all their resources)

**Completed:**
- ✅ Tool sets: Full tag enforcement (create, read, update, delete, list)
- ✅ Integration tests: `test_tool_sets_tag_enforcement.py`

**Remaining Work:**
- [ ] Add tag enforcement to tool_items endpoints
- [ ] Add tag enforcement to tool_instances endpoints
- [ ] Add tag enforcement to tool_presets endpoints
- [ ] Add `resource_tags_getter` implementations for remaining resource types

### Notification System
- [ ] Write tests for MQTT message publishing
- [ ] Write tests for WebSocket connections
- [ ] Implement MQTT broker integration
- [ ] Implement WebSocket server
- [ ] Add auth context to notifications
- [ ] Test subscription filtering by user/machine

### Log Query API
- [ ] Write tests for log search and filtering
- [ ] Implement log query endpoints
- [ ] Add log filtering by user, entity, date range
- [ ] Implement audit log export for compliance
- [ ] Test log retention policies