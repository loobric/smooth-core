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

### Tags (Future Feature)

Tags enable flexible access control:

```json
{
  "name": "Mill #3 API Key",
  "scopes": ["read", "write:presets"],
  "tags": ["mill-3", "production", "shop-floor"]
}
```

**Use cases:**
- Restrict keys to specific machines or locations
- Group keys by purpose (backup, monitoring, integration)
- Filter and audit key usage by tag
- Implement custom access policies

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
