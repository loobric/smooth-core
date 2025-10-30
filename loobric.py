#!/usr/bin/env python3
# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0
"""
Loobric CLI Utility - Manage authentication and API keys for Smooth Core

Usage:
    # Interactive login (saves session)
    loobric.py --login
    loobric.py --logout
    
    # Session-based auth (after login)
    loobric.py list-keys
    loobric.py create-key <name> [options]
    
    # API key auth (one-off commands)
    loobric.py --api-key <key> list-keys
    loobric.py --api-key <key> --base-url https://api.loobric.com list-tool-sets

Environment Variables:
    LOOBRIC_BASE_URL - Default base URL (can be overridden with --base-url)

Authentication Priority:
    1. --api-key flag (if provided)
    2. Saved session cookie (from login)
    3. No auth (will fail for protected endpoints)
"""

import argparse
import getpass
import http.client
import json
import os
import sys
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, List

# Global session state
SESSION_COOKIE: Optional[str] = None
API_KEY: Optional[str] = None
BASE_URL: str = ""  # Will be set from CLI or environment

# Session file location
SESSION_DIR = Path.home() / ".loobric"
SESSION_FILE = SESSION_DIR / "session.json"


def load_session():
    """Load session cookie and base URL from file if it exists.
    
    Returns:
        dict: Session data including base_url, session_cookie, and email (if available)
    """
    global SESSION_COOKIE, BASE_URL
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, 'r') as f:
                data = json.load(f)
                # If BASE_URL is not set, use the one from session
                if not BASE_URL and data.get('base_url'):
                    BASE_URL = data.get('base_url')
                # Load session cookie if base URLs match
                if data.get('base_url') == BASE_URL:
                    SESSION_COOKIE = data.get('session_cookie')
                return data
        except (json.JSONDecodeError, IOError) as e:
            # Ignore errors loading session file
            pass
    return {}


def save_session(email: str = None):
    """Save session cookie and base URL to file.
    
    Args:
        email: Optional email to save with session
    """
    if SESSION_COOKIE:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        try:
            session_data = {
                'base_url': BASE_URL,
                'session_cookie': SESSION_COOKIE
            }
            if email:
                session_data['email'] = email
            
            with open(SESSION_FILE, 'w') as f:
                json.dump(session_data, f)
            # Set restrictive permissions (owner read/write only)
            SESSION_FILE.chmod(0o600)
        except IOError as e:
            print(f"Warning: Could not save session: {e}", file=sys.stderr)


def clear_session():
    """Clear saved session file."""
    if SESSION_FILE.exists():
        try:
            SESSION_FILE.unlink()
        except IOError as e:
            print(f"Warning: Could not clear session file: {e}", file=sys.stderr)


def get_connection():
    """Create HTTP/HTTPS connection based on BASE_URL scheme."""
    parsed = urllib.parse.urlparse(BASE_URL)
    if parsed.scheme == "https":
        return http.client.HTTPSConnection(parsed.netloc)
    elif parsed.scheme == "http":
        return http.client.HTTPConnection(parsed.netloc)
    else:
        print(f"Error: Unsupported scheme in base URL: {parsed.scheme}", file=sys.stderr)
        sys.exit(1)


def make_request(
    method: str,
    endpoint: str,
    body: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    require_auth: bool = False
) -> Dict[str, Any]:
    """Make authenticated HTTP request to Loobric API.
    
    Args:
        method: HTTP method (GET, POST, DELETE, etc.)
        endpoint: API endpoint path
        body: Optional request body (will be JSON encoded)
        extra_headers: Optional additional headers
        require_auth: If True, fail if no authentication is available
    
    Returns:
        Parsed JSON response
    """
    global SESSION_COOKIE, API_KEY

    conn = get_connection()
    path = urllib.parse.urljoin("/api/v1/", endpoint.lstrip("/"))
    headers = extra_headers or {}
    headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    
    # Prefer API key authentication over session cookie
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    elif SESSION_COOKIE:
        headers["Cookie"] = f"session={SESSION_COOKIE}"
    elif require_auth:
        print("Error: Not authenticated. Run 'login' first or set LOOBRIC_API_KEY.", file=sys.stderr)
        sys.exit(1)

    body_str = json.dumps(body) if body else None

    try:
        conn.request(method, path, body=body_str, headers=headers)
        response = conn.getresponse()
        status = response.status
        content = response.read().decode("utf-8")

        # Extract session cookie from Set-Cookie header (for login)
        set_cookie = response.getheader("set-cookie") or response.getheader("Set-Cookie")
        if set_cookie:
            # Parse: "session=VALUE; HttpOnly; ..." -> extract VALUE
            for part in set_cookie.split(";"):
                part = part.strip()
                if part.startswith("session="):
                    SESSION_COOKIE = part.split("=", 1)[1]
                    break

        if 200 <= status < 300:
            return json.loads(content) if content.strip() else {}
        else:
            try:
                error_data = json.loads(content)
                error_msg = error_data.get("detail", content)
            except json.JSONDecodeError:
                error_msg = content
            print(f"Error: HTTP {status}: {error_msg}", file=sys.stderr)
            sys.exit(1)
    except http.client.HTTPException as e:
        print(f"HTTP request failed: {e}", file=sys.stderr)
        sys.exit(1)
    except ConnectionError as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        print(f"Check that the server is running at {BASE_URL}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


def register(email: str = None, password: str = None):
    """Register a new user account.
    
    First user registration is open. Subsequent registrations require admin auth.
    
    Args:
        email: User email address (will prompt if not provided)
        password: User password (will prompt if not provided)
    """
    # Prompt for email if not provided
    if not email:
        email = input("Email: ").strip()
        if not email:
            print("Error: Email is required", file=sys.stderr)
            sys.exit(1)
    
    # Prompt for password if not provided
    if not password:
        password = getpass.getpass("Password: ")
        if not password:
            print("Error: Password is required", file=sys.stderr)
            sys.exit(1)
        # Confirm password
        password_confirm = getpass.getpass("Confirm Password: ")
        if password != password_confirm:
            print("Error: Passwords do not match", file=sys.stderr)
            sys.exit(1)
    
    payload = {"email": email, "password": password}
    data = make_request("POST", "/auth/register", body=payload)
    print("✓ Registration successful!")
    print(f"  User: {data.get('email', 'Unknown')}")
    if data.get('id'):
        print(f"  User ID: {data.get('id')}")
    print("\nYou can now login with:")
    print(f"  ./loobric.py login {email}")


def login(email: str = None, password: str = None, base_url: str = None):
    """Authenticate and capture session cookie.
    
    Args:
        email: User email address (will prompt if not provided)
        password: User password (will prompt if not provided)
        base_url: Base URL (will prompt if not provided and not in session)
    """
    global SESSION_COOKIE, BASE_URL
    
    # Prompt for base URL if not provided
    if base_url:
        BASE_URL = base_url.rstrip("/")
    elif not BASE_URL:
        url_input = input("Base URL [http://127.0.0.1:8000]: ").strip()
        if not url_input:
            url_input = "http://127.0.0.1:8000"
        BASE_URL = url_input.rstrip("/")
    
    # Prompt for email if not provided
    if not email:
        email = input("Email: ").strip()
        if not email:
            print("Error: Email is required", file=sys.stderr)
            sys.exit(1)
    
    # Prompt for password if not provided
    if not password:
        password = getpass.getpass("Password: ")
        if not password:
            print("Error: Password is required", file=sys.stderr)
            sys.exit(1)
    
    payload = {"email": email, "password": password}
    data = make_request("POST", "/auth/login", body=payload)
    print("✓ Login successful!")
    print(f"  User: {data.get('email', 'Unknown')}")
    if data.get('id'):
        print(f"  User ID: {data.get('id')}")
    if not SESSION_COOKIE:
        print("⚠ Warning: No session cookie received. Authentication may have failed.", file=sys.stderr)
    else:
        save_session(email=email)
        print(f"  Session saved to {SESSION_FILE}")
        print(f"  Base URL: {BASE_URL}")


def create_key(
    name: str,
    scopes: Optional[str] = None,
    tags: Optional[str] = None,
    expires_at: Optional[str] = None
):
    """Create a new API key.
    
    Args:
        name: Descriptive name for the API key
        scopes: Space-separated list of scopes (e.g., 'read write:items')
        tags: Space-separated list of tags (e.g., 'production mill-3')
        expires_at: ISO 8601 datetime string for expiration
    """
    payload = {"name": name}
    if scopes:
        payload["scopes"] = scopes.strip().split()
    if tags:
        payload["tags"] = tags.strip().split()
    if expires_at:
        payload["expires_at"] = expires_at

    data = make_request("POST", "/auth/keys", body=payload, require_auth=True)

    # Output the plain API key first (for easy copying/piping)
    print(data.get('key'))
    
    # Then output details to stderr so they don't interfere with key capture
    print("\n✓ API key created successfully!", file=sys.stderr)
    print(f"  ID: {data.get('id')}", file=sys.stderr)
    print(f"  Name: {data.get('name')}", file=sys.stderr)
    print(f"  Scopes: {', '.join(data.get('scopes', []))}", file=sys.stderr)
    if data.get("tags"):
        print(f"  Tags: {', '.join(data.get('tags', []))}", file=sys.stderr)
    if data.get("expires_at"):
        print(f"  Expires: {data.get('expires_at')}", file=sys.stderr)
    print("\n⚠ Warning: Save the key now — it won't be shown again!", file=sys.stderr)
    print("\nTo use this key, set the environment variable:", file=sys.stderr)
    print(f"  export LOOBRIC_API_KEY={data.get('key')}", file=sys.stderr)


def list_keys():
    """List all API keys for the authenticated user."""
    data = make_request("GET", "/auth/keys", require_auth=True)
    
    if not data:
        print("No API keys found.")
        return
    
    print("\nAPI Keys:")
    print("-" * 80)
    for key in data:
        print(f"  ID: {key.get('id')}")
        print(f"  Name: {key.get('name')}")
        print(f"  Scopes: {', '.join(key.get('scopes', []))}")
        if key.get('tags'):
            print(f"  Tags: {', '.join(key.get('tags', []))}")
        if key.get('created_at'):
            print(f"  Created: {key.get('created_at')}")
        if key.get('expires_at'):
            print(f"  Expires: {key.get('expires_at')}")
        if key.get('last_used_at'):
            print(f"  Last Used: {key.get('last_used_at')}")
        print("-" * 80)


def revoke_key(key_id: str):
    """Revoke (delete) an API key.
    
    Args:
        key_id: The ID of the key to revoke
    """
    make_request("DELETE", f"/auth/keys/{key_id}", require_auth=True)
    print(f"✓ API key {key_id} revoked successfully.")


def list_tool_sets(
    type_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """List tool sets with optional filters.
    
    Args:
        type_filter: Filter by type (e.g., 'machine_setup', 'job_specific', 'template', 'project')
        status_filter: Filter by status (e.g., 'draft', 'active', 'archived')
        limit: Maximum number of results to return
        offset: Number of results to skip
    """
    params = {"limit": limit, "offset": offset}
    if type_filter:
        params["type"] = type_filter
    if status_filter:
        params["status"] = status_filter
    
    # Build query string
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    endpoint = f"/tool-sets?{query_string}"
    
    data = make_request("GET", endpoint, require_auth=True)
    
    if not data.get("items"):
        print("No tool sets found.")
        return
    
    print(f"\nTool Sets (showing {len(data['items'])} of {data['total']} total):")
    print("=" * 80)
    for tool_set in data["items"]:
        print(f"  ID: {tool_set.get('id')}")
        print(f"  Name: {tool_set.get('name')}")
        if tool_set.get('description'):
            print(f"  Description: {tool_set.get('description')}")
        print(f"  Type: {tool_set.get('type')}")
        print(f"  Status: {tool_set.get('status')}")
        if tool_set.get('machine_id'):
            print(f"  Machine ID: {tool_set.get('machine_id')}")
        if tool_set.get('job_id'):
            print(f"  Job ID: {tool_set.get('job_id')}")
        members = tool_set.get('members', [])
        print(f"  Members: {len(members)} tool(s)")
        if tool_set.get('created_at'):
            print(f"  Created: {tool_set.get('created_at')}")
        if tool_set.get('updated_at'):
            print(f"  Updated: {tool_set.get('updated_at')}")
        print(f"  Version: {tool_set.get('version')}")
        print("=" * 80)
    
    # Show pagination info
    if data['total'] > len(data['items']):
        remaining = data['total'] - (offset + len(data['items']))
        if remaining > 0:
            print(f"\n{remaining} more tool set(s) available. Use --offset {offset + limit} to see more.")


def logout():
    """End session."""
    global SESSION_COOKIE
    if not SESSION_COOKIE:
        print("No active session to logout.")
        return

    make_request("POST", "/auth/logout")
    SESSION_COOKIE = None
    clear_session()
    print("✓ Logged out successfully.")
    print(f"  Session cleared from {SESSION_FILE}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Loobric API Key Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # First time setup - register a user on fresh database
  loobric.py --base-url http://127.0.0.1:8000 register admin@example.com
  
  # Interactive login (prompts for URL, email, password)
  loobric.py --login
  
  # Login with specific URL and email
  loobric.py --base-url http://127.0.0.1:8000 login user@example.com
  
  # After login, base URL is saved - just run commands
  loobric.py list-keys
  loobric.py create-key "My Key" --scopes "read write:items"
  
  # Create a key with tags and expiration
  loobric.py create-key "Backup Script" \\
    --scopes "read" --tags "backup production" --expires-at "2025-12-31T23:59:59Z"
  
  # Revoke an API key
  loobric.py revoke-key <key_id>
  
  # Logout
  loobric.py logout

Environment Variables:
  LOOBRIC_BASE_URL - Default base URL (can override with --base-url)
  LOOBRIC_API_KEY  - API key for authentication (alternative to login)
"""
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Interactive login (prompts for URL, email, password)"
    )
    parser.add_argument(
        "--logout",
        action="store_true",
        help="End current session (clears session cookie)"
    )
    parser.add_argument(
        "--api-key",
        help="API key for authentication (overrides session cookie and $LOOBRIC_API_KEY)"
    )
    parser.add_argument(
        "--base-url", "-b",
        default=os.environ.get("LOOBRIC_BASE_URL"),
        help="Base API URL (default: $LOOBRIC_BASE_URL or saved session)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    subparsers = parser.add_subparsers(dest="command", required=False)

    # === register ===
    register_parser = subparsers.add_parser(
        "register",
        help="Register a new user account",
        description="Create a new user account. Use this for the first user on a fresh database."
    )
    register_parser.add_argument("email", nargs="?", help="User email address (will prompt if not provided)")
    register_parser.add_argument(
        "--password", "-p",
        help="Password (will be prompted if not provided)"
    )
    register_parser.set_defaults(func=lambda args: register(
        email=args.email,
        password=args.password
    ))

    # === login ===
    login_parser = subparsers.add_parser(
        "login",
        help="Authenticate with email/password",
        description="Authenticate with email and password to create a session."
    )
    login_parser.add_argument("email", nargs="?", help="User email address (will prompt if not provided)")
    login_parser.add_argument(
        "--password", "-p",
        help="Password (will be prompted if not provided)"
    )
    login_parser.add_argument(
        "--url",
        help="Base URL (will be prompted if not provided)"
    )
    login_parser.set_defaults(func=lambda args: login(
        email=args.email,
        password=args.password,
        base_url=args.url or args.base_url
    ))

    # === create-key ===
    create_parser = subparsers.add_parser("create-key", help="Generate a new API key")
    create_parser.add_argument("name", help="Name for the API key (e.g., 'My App')")
    create_parser.add_argument("--scopes", help="Space-separated scopes, e.g., 'read write'")
    create_parser.add_argument("--tags", help="Space-separated tags, e.g., 'production mill-3'")
    create_parser.add_argument("--expires-at", help="ISO datetime, e.g., 2025-12-31T23:59:59Z")
    create_parser.set_defaults(func=lambda args: create_key(
        args.name, args.scopes, args.tags, args.expires_at
    ))

    # === list-keys ===
    list_parser = subparsers.add_parser("list-keys", help="List all API keys")
    list_parser.set_defaults(func=lambda _: list_keys())

    # === revoke-key ===
    revoke_parser = subparsers.add_parser("revoke-key", help="Revoke an API key")
    revoke_parser.add_argument("key_id", help="ID of the key to revoke")
    revoke_parser.set_defaults(func=lambda args: revoke_key(args.key_id))

    # === list-tool-sets ===
    list_tool_sets_parser = subparsers.add_parser(
        "list-tool-sets",
        help="List tool sets",
        description="List tool sets with optional filters for type and status."
    )
    list_tool_sets_parser.add_argument(
        "--type",
        help="Filter by type (machine_setup, job_specific, template, project)"
    )
    list_tool_sets_parser.add_argument(
        "--status",
        help="Filter by status (draft, active, archived)"
    )
    list_tool_sets_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of results (default: 100)"
    )
    list_tool_sets_parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Number of results to skip (default: 0)"
    )
    list_tool_sets_parser.set_defaults(func=lambda args: list_tool_sets(
        type_filter=args.type,
        status_filter=args.status,
        limit=args.limit,
        offset=args.offset
    ))

    # === logout ===
    logout_parser = subparsers.add_parser(
        "logout",
        help="End current session",
        description="End the current session (clears session cookie)."
    )
    logout_parser.set_defaults(func=lambda _: logout())

    # Parse args
    args = parser.parse_args()
    
    # Set global state
    global BASE_URL, API_KEY
    
    # Handle --login shortcut
    if args.login:
        login()
        return
    
    # Handle --logout shortcut
    if args.logout:
        # Load session to get BASE_URL for logout request
        API_KEY = os.environ.get("LOOBRIC_API_KEY")
        if not API_KEY:
            session_data = load_session()
        logout()
        return
    
    # Set BASE_URL from args or environment first (before loading session)
    if args.base_url:
        BASE_URL = args.base_url.rstrip("/")
    
    # Load session first (for session-based auth)
    session_data = load_session()
    
    # Set API key only if explicitly provided via --api-key flag
    # Environment variable is NOT used automatically to avoid conflicts with session auth
    if args.api_key:
        API_KEY = args.api_key
    
    # Validate BASE_URL is set
    if not BASE_URL:
        print("Error: Base URL required. Use --base-url, set LOOBRIC_BASE_URL, or run 'loobric.py --login' first", file=sys.stderr)
        sys.exit(1)
    
    if args.verbose:
        print(f"Base URL: {BASE_URL}", file=sys.stderr)
        if API_KEY:
            print(f"Using API key from --api-key flag", file=sys.stderr)
        elif SESSION_COOKIE:
            print(f"Using saved session from {SESSION_FILE}", file=sys.stderr)
        else:
            print(f"No authentication (login required for protected endpoints)", file=sys.stderr)

    # Run command if one was provided
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()