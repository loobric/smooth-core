# Manufacturer Catalog System

## Overview

Manufacturers can publish catalogs of their products. Users copy tools from catalogs into their accounts, creating independent ToolItems that reference the original via `parent_tool_id`.

## Key Concepts

- **Manufacturer Role**: Admin-created accounts that can publish catalogs
- **Catalog**: Collection of ToolItem IDs with tags for searchability
- **parent_tool_id**: Links copied tools to their catalog source
- **Published Flag**: Only published catalogs visible to public
- **Analytics**: Track tool copy counts via `parent_tool_id` references

## Workflows

### Manufacturer Onboarding
1. Admin creates user account with `role: "manufacturer"`
2. Admin grants manufacturer role via PATCH `/api/v1/users/{id}/roles`
3. Admin optionally verifies partnership via PATCH `/api/v1/users/{id}`

### Publishing Catalog
1. Manufacturer creates ToolItems (bulk endpoint)
2. Manufacturer creates catalog with those tool IDs
3. Manufacturer sets `is_published: true` to make public

### User Copying Tools
1. User searches catalogs by tags
2. User creates ToolItems with `parent_tool_id` set to catalog tool
3. User modifies their copies independently
4. Original catalog tools unchanged

## Data Model Extensions

### User
- `role`: "manufacturer" (in addition to "user", "admin")
- `manufacturer_profile`: JSON with company info
- `is_verified`: Partnership verification flag

### ManufacturerCatalog (new table)
- `tool_ids`: Array of ToolItem IDs
- `tags`: Searchable tags
- `is_published`: Visibility control

### ToolItem
- `parent_tool_id`: Optional FK to source catalog tool

## Implementation Notes

- SQLAlchemy JSON fields require `flag_modified()` when updating
- Tag filtering done in Python for SQLite compatibility
- Bulk endpoints support alternate request/response formats for compatibility
- Version checking optional in PATCH `/api/v1/tool-items/bulk`

## Testing

```bash
pytest tests/integration/test_manufacturer_catalog.py -xvs
```
