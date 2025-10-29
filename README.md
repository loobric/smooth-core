# Smooth Core

> Application-agnostic REST API and database for tool data synchronization across CAM systems, CNC machines, and tool rooms.

## What is Smooth Core?

Smooth Core is the central REST API and database system that provides:
- **RESTful API** with bulk-first design for efficient data operations
- **SQLAlchemy-based database** supporting SQLite (development) and PostgreSQL (production)
- **Authentication & authorization** with user accounts and scoped API keys and Tag-Based Access Control
- **Audit logging** for compliance and traceability
- **Change detection** for efficient client synchronization
- **Backup/restore** for disaster recovery
- **Version tracking** for all entities with optimistic locking

### Standards Alignment

Smooth Core's data model is informed by industry standards while remaining pragmatic for real-world synchronization:

- **ISO 13399** - Tool data representation standard
  - Schema inspired by ISO 13399's separation of catalog items, assemblies, and instances
  - Maintains compatibility layer for enterprise integrations
  - Pragmatic JSON schema for everyday CAM/CNC workflows

- **STEP-NC (ISO 10303-238)** - Process and geometry modeling
  - Tool geometry representation compatible with STEP-NC concepts
  - Supports future integration with STEP-NC controllers

- **MTConnect (ANSI/MTC1.4)** - Machine monitoring and data exchange
  - Complementary focus: Smooth manages tool libraries, MTConnect handles machine telemetry
  - Change detection API supports MTConnect-style event-driven architectures

**Design Philosophy:** Standards-informed, not standards-constrained. Smooth fills the gap between CAM tool libraries and CNC tool tables that existing standards don't fully address.

## Quick Start

```bash
# Install UV (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone https://github.com/loobric/smooth-core.git
cd smooth-core

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Run tests
pytest

# Start server
uvicorn smooth.main:app --reload

# Visit API documentation
# http://localhost:8000/api/v1/docs (Swagger UI)
# http://localhost:8000/api/v1/redoc (ReDoc)
```

## API Endpoints

Smooth Core provides a comprehensive REST API with bulk-first design:

- **Authentication** - User registration, login, API key management
- **Tool Entities** - CRUD operations for all 6 tool entity types (bulk operations)
- **Change Detection** - Efficient synchronization endpoints
- **Backup/Restore** - Database export/import
- **Audit Logs** - Query audit trail
- **Versioning** - ToolSet version history and rollback

**Complete API Reference:** See [API_ENDPOINTS.md](./API_ENDPOINTS.md)

**Interactive Documentation:**
- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc

## Data Model

```
User
├── ToolItem (catalog items)
├── ToolAssembly (holder + cutter combinations)
├── ToolInstance (physical tools with measurements)
├── ToolPreset (machine-specific setups)
├── ToolUsage (runtime tracking)
├── ToolSet (tool collections)
├── APIKey (scoped access tokens)
└── AuditLog (immutable change history)
```

**Multi-tenant by default:** All data is user-scoped with automatic isolation.

## Authentication

### Two-Tier Model

**Tier 1: User Accounts** (human access)
- Email/password authentication
- Session-based (httponly cookies, 24hr lifetime)
- Web UI and CLI access
- Full data ownership

**Tier 2: API Keys** (machine/application access)
- Created by users for programmatic access
- Scoped permissions (read, write:items, write:presets, admin:*, etc.)
- Optional machine-specific restrictions
- Revocable, named, with expiration
- Tags can be assigned to API keys and resources to refine access policy

### Permission Scopes
- `read` - Read any tool data
- `write:items` - Create/update tool items and assemblies
- `write:presets` - Create/update tool presets
- `write:usage` - Record tool usage data
- `write:sets` - Create/update tool sets
- `admin:users` - Manage API keys
- `admin:backup` - Backup/restore operations
- `admin:*` - All admin permissions
- `write:*` - All write permissions

### Development Mode
Set `AUTH_ENABLED=false` to disable authentication for single-user development.

## Configuration

Environment variables (see `.env.example`):
```bash
# Database
DATABASE_URL=sqlite:///./smooth.db  # or postgresql://...

# Authentication
AUTH_ENABLED=true
SECRET_KEY=your-secret-key-here

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=smooth --cov-report=html

# Run specific test suite
pytest tests/unit/
pytest tests/integration/
pytest tests/property/

# Run specific test file
pytest tests/unit/test_schema.py

# Verbose output
pytest -v
```

**Test coverage:** 90%+ across core modules

## Database Configuration

Smooth Core supports multiple database backends via SQLAlchemy. Choose based on your deployment needs:

### SQLite (Recommended for Self-Hosting)

**Best for:**
- Single-instance deployments
- Personal or small team use
- Tool libraries under 10,000 items
- Simple backup requirements
- Quick setup with minimal infrastructure

**Configuration:**
```bash
# In .env file
DATABASE_URL=sqlite:///./data/smooth.db
```

**Advantages:**
- ✅ Zero setup - works out of the box
- ✅ Single file database (easy backups)
- ✅ No separate database server needed
- ✅ Excellent performance for typical use cases
- ✅ Reliable and mature

**Backup:**
```bash
# Simple file copy
cp ./data/smooth.db ./backups/smooth_$(date +%Y%m%d).db
```

### PostgreSQL (Optional for Scale)

**Best for:**
- High-concurrency environments (50+ concurrent users)
- Very large tool libraries (10,000+ items)
- Multi-server deployments
- Advanced database features (replication, clustering)
- Enterprise compliance requirements

**Configuration:**
```bash
# In .env file
DATABASE_URL=postgresql://username:password@host:5432/database

# With docker-compose
POSTGRES_DB=smooth
POSTGRES_USER=smooth
POSTGRES_PASSWORD=your-secure-password
DATABASE_URL=postgresql://smooth:your-secure-password@db:5432/smooth
```

**Docker Compose Example:**
```yaml
services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: smooth
      POSTGRES_USER: smooth
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      
  smooth-core:
    environment:
      DATABASE_URL: postgresql://smooth:${POSTGRES_PASSWORD}@db:5432/smooth
    depends_on:
      - db
```

**Backup:**
```bash
# PostgreSQL dump
pg_dump -U smooth smooth > backup.sql

# With docker
docker exec postgres pg_dump -U smooth smooth > backup.sql
```

### MySQL/MariaDB (Alternative)

MySQL and MariaDB are also supported via SQLAlchemy:
```bash
DATABASE_URL=mysql+pymysql://user:password@host/database
```

### Migration Path

You can start with SQLite and migrate to PostgreSQL later:

```bash
# 1. Export data from SQLite
python -m smooth.cli backup --output backup.json

# 2. Update DATABASE_URL to PostgreSQL
DATABASE_URL=postgresql://...

# 3. Restore data to PostgreSQL
python -m smooth.cli restore --input backup.json
```

**Note:** Alembic migrations for schema changes are planned for future releases.

## Client Integration

Smooth Core is designed to be consumed by client applications:

- **smooth-freecad** - FreeCAD CAM workbench integration
- **smooth-linuxcnc** - LinuxCNC controller integration
- **smooth-web** - Browser-based management interface

Clients communicate via REST API only - no direct code dependencies.

## Deployment

### Small Shop / Development
```bash
# SQLite, single machine
uvicorn smooth.main:app --host 0.0.0.0 --port 8000
```

### Production
```bash
# With PostgreSQL, multiple workers
gunicorn smooth.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

**Recommended:**
- Reverse proxy (nginx/caddy)
- HTTPS with Let's Encrypt
- Database backups (automated)
- Log aggregation (ELK, Grafana Loki)

## Architecture Principles

Smooth Core follows five infrastructure principles:

1. **Backup/Restore First** - All data serializable, atomic operations
2. **Versioning Built-In** - Every entity tracks version for sync and conflict detection
3. **Test-Driven Development** - Tests before implementation
4. **Auth Built-In** - Multi-tenant by default, optional disable
5. **Structured Logging** - JSON logs with full context

See [DEVELOPMENT.md](./DEVELOPMENT.md) for detailed development information.

## Documentation

- **[DEVELOPMENT.md](./DEVELOPMENT.md)** - Development guide, project structure, testing
- **API Docs** - http://localhost:8000/api/v1/docs (when server running)
- **Top-level [README](../README.md)** - Multi-repo overview
- **Top-level [DEVELOPMENT](../DEVELOPMENT.md)** - Cross-project principles

## Contributing

Contributions welcome! Please:
1. Follow TDD (tests before implementation)
2. Maintain 90%+ test coverage
3. Follow functional programming style
4. Update docstrings and documentation
5. Pass all existing tests

See [DEVELOPMENT.md](./DEVELOPMENT.md) and [../DEVELOPMENT.md](../DEVELOPMENT.md) for coding standards.

## License

[License information to be added]

## Support

- GitHub Issues: [Link to issues]
- Documentation: [Link to docs]
- Community: [Link to forum/chat]
