# Deployment

## Run Locally

```bash
git clone https://github.com/loobric/smooth-core.git
cd smooth-core
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
uvicorn smooth.main:app --reload
```

## Self-Hosted
TBD

## Environment Variables

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
## Database

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

**Backup:**
```bash
# PostgreSQL dump
pg_dump -U smooth smooth > backup.sql

# With docker
docker exec postgres pg_dump -U smooth smooth > backup.sql
```

## Docker

### Sample Docker Compose:

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