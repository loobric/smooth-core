# Authentication

Smooth uses simple authentication to protect your tool data while keeping it easy to integrate with machines and applications.

## Two Ways to Authenticate

### 1. User Accounts (Web UI)
- Email and password login
- Session-based
- For managing tools, data, and creating API keys

### 2. API Keys (Machine/client Access)
- For CNC machines, scripts, and applications
- Created by users through the web UI
- Can be scoped and tagged for specific purposes

## API Keys

### Creating API Keys

1. Log in to Smooth web UI
2. Navigate to Settings → API Keys
3. Click "Create New Key"
4. Set:
   - **Name**: Descriptive name (e.g., "Mill #3", "Backup Script")
   - **Scopes**: What the key can do (read, write:items, write:presets, etc.)
   - **Tags**: Optional labels to narrow what a token can act on.
   - **Expiration**: Optional expiration date

5. Copy the key immediately—it won't be shown again

### Using API Keys

Include the key in the `Authorization` header:

```bash
curl -H "Authorization: Bearer sk_abc123..." \
  https://api.loobric.com/api/v1/tools
```

### Scopes

Control what each key can access:

- `read` - View all data
- `write:items` - Create/update tool items
- `write:presets` - Create/update presets
- `write:assemblies` - Create/update assemblies
- `admin:users` - Manage users (admin only)
- `admin:backup` - Backup/restore operations

### Tags

Tags enable flexible, fine-grained access control for API keys:

```json
{
  "name": "Mill #3 API Key",
  "scopes": ["read", "write:assemblies"],
  "tags": ["mill-3", "production", "shop-floor"]
}
```

**How Tags Work:**

API keys with tags can only access resources that have matching tags. Access is granted if **any** tag on the API key matches **any** tag on the resource.

- **Empty API key tags**: No tag restrictions (can access all resources with proper scopes)
- **Empty resource tags**: Accessible to all API keys with proper scopes
- **Session authentication**: Bypasses tag checks (users own all their resources)
- **Admin scope** (`admin:*`): Bypasses all tag checks

**Examples:**

Create a resource with tags:
```bash
curl -H "Authorization: Bearer sk_mill3..." \
  -X POST https://api.loobric.com/api/v1/tool-assemblies \
  -d '{
    "items": [{
      "name": "Mill #3 Assembly",
      "components": [...],
      "tags": ["mill-3", "production"]
    }]
  }'
```

List resources (automatically filtered by tags):
```bash
# API key with ["mill-3"] tag only sees assemblies tagged with "mill-3"
curl -H "Authorization: Bearer sk_mill3..." \
  https://api.loobric.com/api/v1/tool-assemblies
```

**Use Cases:**
- **Machine-specific keys**: Restrict keys to specific machines (e.g., "mill-3", "lathe-1")
- **Location-based access**: Limit keys by location (e.g., "shop-floor", "office")
- **Purpose grouping**: Organize by function (e.g., "backup", "monitoring", "integration")
- **Environment isolation**: Separate production and development (e.g., "production", "staging")

**Tag Enforcement:**

Currently implemented for:
- Tool assemblies (create, read, update, delete, list)
- Tool sets (create, read, update, delete, list)

Coming soon:
- Tool items
- Tool instances
- Tool presets

## Security

### Passwords
- Hashed with bcrypt (never stored in plaintext)
- Minimum 8 characters recommended

### API Keys
- Cryptographically secure (32-byte tokens)
- Hashed in database (like passwords)
- Shown only once at creation
- Can be revoked anytime

### Sessions
- HTTP-only cookies (not accessible to JavaScript)
- Secure flag in production (HTTPS only)
- Automatic expiration

## Disabling Authentication

For testing or single-user deployments:

```bash
export AUTH_ENABLED=false
```

**Warning:** Only use in trusted environments. All API endpoints become publicly accessible.

## Multi-Tenancy

All data is isolated by user account:
- Each user sees only their own tools, presets, and assemblies
- API keys inherit the user's data access
- Queries automatically filtered by `user_id`

## Troubleshooting

**"Invalid API key"**
- Key may be expired, revoked, or mistyped
- Check key is active in Settings → API Keys

**"Insufficient permissions"**
- Key lacks required scope for the operation
- Create new key with appropriate scopes

**"Session expired"**
- Log in again through web UI
- Sessions expire after 24 hours of inactivity
