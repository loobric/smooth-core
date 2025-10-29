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

## Running Tests
```bash
# Run tests with coverage
pytest --cov=smooth tests/

# Run specific test file
pytest tests/unit/test_module.py

# Run with detailed output
pytest -v
```

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

### Manufacturer Support
- [X] Write tests for manufacturer accounts
- [\] Implement manufacturer accounts
- [X] Write tests for manufacturer tools
- [\] Implement manufacturer tool import

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