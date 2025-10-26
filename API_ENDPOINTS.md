# Smooth Core API Endpoints

This document provides a complete reference of all REST API endpoints available in Smooth Core.

For interactive API documentation, start the server and visit:
- **Swagger UI**: http://localhost:8000/api/v1/docs
- **ReDoc**: http://localhost:8000/api/v1/redoc

## Authentication

### User Account Management
- `POST /api/v1/auth/register` - Create user account
- `POST /api/v1/auth/login` - Login with session cookie
- `POST /api/v1/auth/logout` - Logout
- `GET /api/v1/auth/me` - Get current user info

### API Keys
- `POST /api/v1/api-keys` - Create API key with scopes
- `GET /api/v1/api-keys` - List user's API keys
- `DELETE /api/v1/api-keys/{id}` - Revoke API key

## Tool Entities (Bulk-First Design)

All endpoints support bulk operations with arrays. Requests and responses use JSON arrays for efficient batch processing.

### Tool Items
Catalog items (cutting tools, holders, inserts, adapters)

- `POST /api/v1/tool-items` - Create tool items (bulk)
- `GET /api/v1/tool-items` - List/query with pagination
- `PUT /api/v1/tool-items` - Update (bulk, with version checks)
- `DELETE /api/v1/tool-items` - Delete (bulk)

### Tool Assemblies
Tool combinations (holder + cutter)

- `POST /api/v1/tool-assemblies` - Create assemblies (bulk)
- `GET /api/v1/tool-assemblies` - List/query with pagination
- `PUT /api/v1/tool-assemblies` - Update (bulk, with version checks)
- `DELETE /api/v1/tool-assemblies` - Delete (bulk)

### Tool Instances
Physical tool instances with measurements

- `POST /api/v1/tool-instances` - Create instances (bulk)
- `GET /api/v1/tool-instances` - List/query with pagination
- `PUT /api/v1/tool-instances` - Update (bulk, with version checks)
- `DELETE /api/v1/tool-instances` - Delete (bulk)

### Tool Presets
Machine-specific configurations (tool tables, offsets)

- `POST /api/v1/tool-presets` - Create presets (bulk)
- `GET /api/v1/tool-presets` - List/query with pagination (supports `machine_id` filter)
- `PUT /api/v1/tool-presets` - Update (bulk, with version checks)
- `DELETE /api/v1/tool-presets` - Delete (bulk)

### Tool Sets
Tool collections (machine setups, job lists, templates)

- `POST /api/v1/tool-sets` - Create tool sets (bulk)
- `GET /api/v1/tool-sets` - List/query with pagination
- `PUT /api/v1/tool-sets` - Update (bulk, with version checks, automatic versioning)
- `DELETE /api/v1/tool-sets` - Delete (bulk)

### Tool Usage
Runtime tracking (wear, lifecycle, measurements)

- `POST /api/v1/tool-usage` - Create usage records (bulk)
- `GET /api/v1/tool-usage` - List/query with pagination
- `PUT /api/v1/tool-usage` - Update (bulk, with version checks)
- `DELETE /api/v1/tool-usage` - Delete (bulk)

## Change Detection

Efficient synchronization endpoints for clients to detect and fetch changes.

- `GET /api/v1/changes/{entity}/since-version?version={n}&limit={max}` - Version-based sync
- `GET /api/v1/changes/{entity}/since-timestamp?timestamp={iso}&limit={max}` - Time-based sync
- `GET /api/v1/changes/{entity}/max-version` - Get current sync state

**Supported entities:** `tool-items`, `tool-assemblies`, `tool-instances`, `tool-presets`, `tool-sets`, `tool-usage`

**Parameters:**
- `version` - Integer version number to sync from
- `timestamp` - ISO 8601 timestamp (URL encoded)
- `limit` - Maximum results (1-1000, default: 100)

## Backup/Restore

Database backup and restore for disaster recovery and data migration.

- `GET /api/v1/backup/export` - Export database (user or admin)
  - Regular users: Export their own data only
  - Admin users: Export entire database
- `POST /api/v1/backup/import` - Import/restore database
  - Validates backup format and version
  - Atomic operation with rollback on error

**Backup format:** JSON with metadata, versioning fields, and all entity data.

## Audit Logs

Immutable audit trail for compliance and forensics.

- `GET /api/v1/audit-logs?user_id={id}&entity_type={type}&start={iso}&end={iso}` - Query audit trail
  - Regular users: See only their own audit logs
  - Admin users: See all audit logs
  - Supports filtering by user, entity type, and date range

## ToolSet Versioning

Complete version history with snapshots, rollback, and comparison.

- `GET /api/v1/tool-sets/{id}/history` - Version timeline with summaries
- `GET /api/v1/tool-sets/{id}/versions/{version}` - View specific snapshot
- `POST /api/v1/tool-sets/{id}/restore/{version}` - Rollback to previous version
- `GET /api/v1/tool-sets/{id}/compare/{v1}/{v2}` - Compare two versions

**Features:**
- Automatic snapshot on every update
- Immutable history (never deleted)
- Restore creates new version (preserves timeline)
- Version conflicts detected before overwrite

## Bulk Operation Response Format

All bulk endpoints use a consistent response format:

```json
{
  "success_count": 2,
  "error_count": 1,
  "results": [
    {"id": "uuid-1", "version": 1, "status": "created"},
    {"id": "uuid-2", "version": 1, "status": "created"}
  ],
  "errors": [
    {"index": 2, "error": "Validation failed: missing required field"}
  ]
}
```

**Partial success:** Valid items succeed even if some items in the batch fail.

## Authentication Methods

### Session Cookies (Web UI)
- Login via `/api/v1/auth/login`
- Session cookie set (httponly, 24hr lifetime)
- Automatic authentication on subsequent requests

### API Keys (Programmatic Access)
- Create via `/api/v1/api-keys` (requires authenticated session)
- Include in requests: `Authorization: Bearer {api_key}`
- Scoped permissions enforced

## Permission Scopes

API keys support granular permissions:

- `read` - Read any tool data
- `write:items` - Create/update tool items and assemblies
- `write:presets` - Create/update tool presets
- `write:usage` - Record tool usage data
- `write:sets` - Create/update tool sets
- `admin:users` - Manage API keys
- `admin:backup` - Backup/restore operations
- `admin:*` - All admin permissions
- `write:*` - All write permissions

## Multi-Tenancy

All endpoints enforce user-based data isolation:

- Regular users: Access only their own data
- Admin users: Access all data (first user becomes admin)
- Machine-specific API keys: Restricted to specific `machine_id`

## Error Responses

Standard HTTP status codes:

- `200 OK` - Success
- `201 Created` - Resource created
- `400 Bad Request` - Invalid input
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `409 Conflict` - Version conflict
- `500 Internal Server Error` - Server error

Error response format:
```json
{
  "detail": "Error message describing what went wrong"
}
```

## Rate Limiting

Currently not implemented. Future enhancement planned.

## API Versioning

Current version: `v1`

All endpoints are prefixed with `/api/v1/` for stability. Future versions will use `/api/v2/`, etc.
