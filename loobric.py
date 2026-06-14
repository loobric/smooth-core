#!/usr/bin/env python3
# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only
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
    
    # Prefer API key authentication over session cookie. With neither,
    # send the request anyway and let the server decide: a solo-mode
    # server (SMOOTH_SOLO=1) accepts it; a multi-tenant server returns
    # 401 with a clear message. The client must not pre-judge auth.
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    elif SESSION_COOKIE:
        headers["Cookie"] = f"session={SESSION_COOKIE}"

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


def list_tool_sets():
    """List the user's tool sets (v2 facade: /api/v1/tool-sets)."""
    data = make_request("GET", "/tool-sets", require_auth=True)

    if not data.get("items"):
        print("No tool sets found.")
        return

    print(f"\nTool Sets ({len(data['items'])}):")
    print("=" * 80)
    for tool_set in data["items"]:
        print(f"  ID: {tool_set.get('id')}")
        print(f"  Name: {tool_set.get('name')}")
        if tool_set.get('description'):
            print(f"  Description: {tool_set.get('description')}")
        members = tool_set.get('tool_record_ids', [])
        print(f"  Members: {len(members)} tool record(s)")
        if tool_set.get('updated_at'):
            print(f"  Updated: {tool_set.get('updated_at')}")
        print(f"  Version: {tool_set.get('version')}")
        print("=" * 80)


def list_pending():
    """List inbox items awaiting review (binding proposals).

    The inbox holds what sync could not decide on its own (G2): heuristic
    binding proposals awaiting a human. Resolve with `resolve <id> confirm`
    or `resolve <id> reject`.
    """
    data = make_request("GET", "/inbox", require_auth=True)
    items = data.get("items", [])
    if not items:
        print("Inbox is empty - nothing pending.")
        return

    print(f"\n{len(items)} unrecognized machine tool(s) - best-guess matches below.")
    print()
    print("This is an identity question, NOT a conflict: the machine reported")
    print("tools the server doesn't recognize yet. Confirming or rejecting")
    print("overwrites NOTHING on either side.")
    print()
    print("  confirm = 'same tool': links the machine entry to the record so")
    print("            future changes route between them. Both keep their data.")
    print("  reject  = 'different tools': drops this suggestion permanently.")
    print("            The entry stays unbound and keeps syncing fine.")
    print("  unsure? = reject. A rejected pair can be linked manually later;")
    print("            a wrong confirm is currently hard to undo.")
    print("=" * 78)
    for item in items:
        entry = item.get("entry", {})
        record = item.get("proposed_record", {})
        print(f"  ID: {item.get('id')[:8]}")
        print(f"  Type: {item.get('type')}")
        print(f"  Machine entry: T{entry.get('tool_number')} "
              f"({entry.get('description') or 'no description'})")
        print(f"  Proposed match: {record.get('name')}")
        print(f"  Confidence: {item.get('confidence'):.0%} - {item.get('reason')}")
        print("-" * 78)
    print("Resolve with: loobric.py resolve <id> confirm|reject")


def resolve_pending(item_id: str, action: str):
    """Confirm or reject an inbox item.

    Accepts unique id prefixes (like git short SHAs): anything shorter than
    a full UUID is matched against the open inbox items client-side.

    Args:
        item_id: Inbox item id or unique prefix (from `pending`)
        action: "confirm" (bind entry to proposed record) or "reject"
    """
    if len(item_id) < 36:
        open_items = make_request("GET", "/inbox", require_auth=True).get("items", [])
        matches = [i for i in open_items if i.get("id", "").startswith(item_id)]
        if not matches:
            print(f"Error: no open inbox item starts with '{item_id}'", file=sys.stderr)
            sys.exit(1)
        if len(matches) > 1:
            print(f"Error: '{item_id}' is ambiguous ({len(matches)} matches):", file=sys.stderr)
            for m in matches:
                entry = m.get("entry", {})
                print(f"  {m['id'][:8]}  T{entry.get('tool_number')} "
                      f"-> {m.get('proposed_record', {}).get('name')}", file=sys.stderr)
            sys.exit(1)
        item_id = matches[0]["id"]
    data = make_request("POST", f"/inbox/{item_id}/{action}", require_auth=True)
    entry = data.get("entry", {})
    record = data.get("proposed_record", {})
    if action == "confirm":
        print(f"Linked: T{entry.get('tool_number')} and '{record.get('name')}' are "
              f"now the same tool. No data was changed on either side; future "
              f"changes will route between them.")
    else:
        print(f"Dismissed: T{entry.get('tool_number')} is not '{record.get('name')}'. "
              f"This suggestion won't reappear; the entry stays unbound.")


def _match_id(items: List[Dict[str, Any]], prefix: str, label: str) -> Dict[str, Any]:
    """Resolve a possibly-abbreviated id against a list (git short-SHA style).

    An exact match wins outright; otherwise a unique prefix match is used.
    Exits with a helpful message on no/ambiguous match.
    """
    exact = [i for i in items if i.get("id") == prefix]
    if exact:
        return exact[0]
    matches = [i for i in items if str(i.get("id", "")).startswith(prefix)]
    if not matches:
        print(f"Error: no {label} matches '{prefix}'", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"Error: '{prefix}' is ambiguous ({len(matches)} {label}s):", file=sys.stderr)
        for m in matches:
            print(f"  {str(m.get('id'))[:8]}  {m.get('name', '')}", file=sys.stderr)
        sys.exit(1)
    return matches[0]


def _resolve_machine(prefix: str) -> Dict[str, Any]:
    items = make_request("GET", "/machines", require_auth=True).get("items", [])
    return _match_id(items, prefix, "machine")


def _resolve_record(prefix: str) -> Dict[str, Any]:
    items = make_request("GET", "/tool-records", require_auth=True).get("items", [])
    return _match_id(items, prefix, "tool record")


def _confirm(message: str, assume_yes: bool) -> bool:
    """Guard a destructive action. --yes skips; non-interactive requires it."""
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print(f"{message}\nRefusing to proceed without confirmation; re-run with --yes.",
              file=sys.stderr)
        sys.exit(1)
    return input(f"{message} [y/N]: ").strip().lower() in ("y", "yes")


def list_machines():
    """List the user's machines (id, name, controller)."""
    items = make_request("GET", "/machines", require_auth=True).get("items", [])
    if not items:
        print("No machines found.")
        return
    print(f"\nMachines ({len(items)}):")
    print("=" * 78)
    for m in items:
        print(f"  ID: {m.get('id')}")
        print(f"  Name: {m.get('name')}")
        if m.get("controller_type"):
            print(f"  Controller: {m.get('controller_type')}")
        print("=" * 78)


def list_tools():
    """List the user's tool records (the public facade)."""
    items = make_request("GET", "/tool-records", require_auth=True).get("items", [])
    if not items:
        print("No tool records found.")
        return
    print(f"\nTool Records ({len(items)}):")
    print("=" * 78)
    for t in items:
        print(f"  ID: {t.get('id')}")
        print(f"  Name: {t.get('name')}")
        g = t.get("geometry") or {}
        bits = []
        if g.get("shape"):
            bits.append(str(g["shape"]))
        if g.get("diameter"):
            bits.append(f"⌀{g['diameter']}{g.get('diameter_unit', '')}")
        if bits:
            print(f"  Geometry: {' · '.join(bits)}")
        bound = t.get("machines", [])
        if bound:
            plural = "entries" if len(bound) != 1 else "entry"
            print(f"  Bound: {len(bound)} machine {plural}")
        print("=" * 78)


def show_tool_table(machine_id: str):
    """List a machine's tool-table entries and their bind state."""
    machine = _resolve_machine(machine_id)
    items = make_request(
        "GET", f"/machines/{machine['id']}/tool-table", require_auth=True
    ).get("items", [])
    if not items:
        print(f"{machine['name']}: empty tool table.")
        return
    plural = "entries" if len(items) != 1 else "entry"
    print(f"\n{machine['name']} tool table ({len(items)} {plural}):")
    print("=" * 78)
    for e in items:
        rec_id = e.get("tool_record_id")
        state = f"bound -> {str(rec_id)[:8]}" if rec_id else "unbound"
        dia = (e.get("offsets") or {}).get("diameter")
        line = f"  T{e.get('tool_number')}: {e.get('description') or '—'}"
        if dia:
            line += f"  ⌀{dia}"
        print(f"{line}  [{state}]")
    print("=" * 78)


def delete_machine(machine_id: str, assume_yes: bool = False):
    """Delete a machine and its tool-table entries (tool records untouched)."""
    machine = _resolve_machine(machine_id)
    if not _confirm(
        f"Delete machine '{machine['name']}' and its tool-table entries?", assume_yes
    ):
        print("Aborted.")
        return
    r = make_request("DELETE", "/machines", body={"ids": [machine["id"]]}, require_auth=True)
    if r.get("errors"):
        print(f"Error: {r['errors'][0].get('message')}", file=sys.stderr)
        sys.exit(1)
    print(f"✓ Deleted machine '{machine['name']}'. Tool records were not affected.")


def delete_tool(record_id: str, assume_yes: bool = False):
    """Delete a tool record; entries bound to it are unbound, not orphaned."""
    rec = _resolve_record(record_id)
    if not _confirm(
        f"Delete tool record '{rec['name']}'? Bound machine entries will be unbound "
        f"(their data stays on the machine).", assume_yes
    ):
        print("Aborted.")
        return
    r = make_request("DELETE", "/tool-records", body={"ids": [rec["id"]]}, require_auth=True)
    if r.get("errors"):
        print(f"Error: {r['errors'][0].get('message')}", file=sys.stderr)
        sys.exit(1)
    print(f"✓ Deleted tool record '{rec['name']}'. Any bound entries were unbound; "
          f"their data stays on the machine.")


def delete_entry(machine_id: str, tool_number: int, assume_yes: bool = False):
    """Remove a machine-reported tool-table entry by tool number."""
    machine = _resolve_machine(machine_id)
    if not _confirm(
        f"Remove T{tool_number} from '{machine['name']}'?", assume_yes
    ):
        print("Aborted.")
        return
    r = make_request(
        "DELETE", f"/machines/{machine['id']}/tool-table",
        body={"tool_numbers": [tool_number]}, require_auth=True,
    )
    if r.get("errors"):
        print(f"Error: {r['errors'][0].get('message')}", file=sys.stderr)
        sys.exit(1)
    print(f"✓ Removed T{tool_number} from '{machine['name']}'. "
          f"If the controller pushes it again, it returns.")


def bind_entry(machine_id: str, tool_number: int, record_id: str):
    """Link an unbound entry to an owned tool record (overwrites nothing)."""
    machine = _resolve_machine(machine_id)
    rec = _resolve_record(record_id)
    make_request(
        "POST", f"/machines/{machine['id']}/tool-table/{tool_number}/bind",
        body={"tool_record_id": rec["id"]}, require_auth=True,
    )
    print(f"✓ Linked T{tool_number} @ {machine['name']} -> '{rec['name']}'. "
          f"Nothing was overwritten on either side.")


def unbind_entry(machine_id: str, tool_number: int):
    """Unbind an entry; it keeps its data and becomes eligible for suggestions."""
    machine = _resolve_machine(machine_id)
    make_request(
        "POST", f"/machines/{machine['id']}/tool-table/{tool_number}/unbind",
        require_auth=True,
    )
    print(f"✓ Unbound T{tool_number} @ {machine['name']}. The entry keeps its data.")


def create_record_from_entry(machine_id: str, tool_number: int, name: str = None):
    """Create a tool record from an entry and bind it in one step."""
    machine = _resolve_machine(machine_id)
    body = {"name": name} if name else None
    entry = make_request(
        "POST", f"/machines/{machine['id']}/tool-table/{tool_number}/create-record",
        body=body, require_auth=True,
    )
    rec_id = str(entry.get("tool_record_id") or "")[:8]
    print(f"✓ Created a record from T{tool_number} @ {machine['name']} and linked it "
          f"(record {rec_id}).")


def ping():
    """Check server health/connectivity."""
    conn = get_connection()
    path = "/api/health"
    headers = {
        "Accept": "application/json",
    }
    
    try:
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        status = response.status
        content = response.read().decode("utf-8")
        
        if 200 <= status < 300:
            data = json.loads(content) if content.strip() else {}
            print("✓ Server is healthy")
            print(f"  Status: {data.get('status', 'ok')}")
            if data.get('version'):
                print(f"  Version: {data.get('version')}")
            print(f"  URL: {BASE_URL}")
        else:
            print(f"✗ Server returned HTTP {status}")
            print(f"  URL: {BASE_URL}")
            sys.exit(1)
    except Exception as e:
        print(f"✗ Server unreachable at {BASE_URL}")
        print(f"  Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


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

  # Inspect and manage machines, tool records, and reported entries
  loobric.py list-machines
  loobric.py list-tools
  loobric.py tool-table <machine>          # ids accept unique prefixes
  loobric.py bind <machine> 3 <record>     # link entry T3 to a record
  loobric.py create-record <machine> 3 --name "1/4 downcut"
  loobric.py unbind <machine> 3
  loobric.py delete-entry <machine> 3 --yes
  loobric.py delete-tool <record> --yes
  loobric.py delete-machine <machine> --yes

  # Check server health
  loobric.py ping
  
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
        description="List the user's tool sets (named collections of ToolRecords)."
    )
    list_tool_sets_parser.set_defaults(func=lambda args: list_tool_sets())

    # === pending / resolve (v2 inbox) ===
    pending_parser = subparsers.add_parser(
        "pending", help="List inbox items awaiting review (binding proposals)"
    )
    pending_parser.set_defaults(func=lambda _: list_pending())

    resolve_parser = subparsers.add_parser(
        "resolve", help="Confirm or reject an inbox item"
    )
    resolve_parser.add_argument("item_id", help="Inbox item id or unique prefix (see 'pending')")
    resolve_parser.add_argument("action", choices=["confirm", "reject"])
    resolve_parser.set_defaults(func=lambda args: resolve_pending(
        args.item_id, args.action
    ))

    # === machines / tool records / entries (v2 management) ===
    list_machines_parser = subparsers.add_parser(
        "list-machines", help="List machines (id, name, controller)"
    )
    list_machines_parser.set_defaults(func=lambda _: list_machines())

    list_tools_parser = subparsers.add_parser(
        "list-tools", help="List tool records (the public facade)"
    )
    list_tools_parser.set_defaults(func=lambda _: list_tools())

    tool_table_parser = subparsers.add_parser(
        "tool-table", help="Show a machine's tool-table entries and bind state"
    )
    tool_table_parser.add_argument("machine", help="Machine id or unique prefix")
    tool_table_parser.set_defaults(func=lambda args: show_tool_table(args.machine))

    delete_machine_parser = subparsers.add_parser(
        "delete-machine",
        help="Delete a machine and its tool-table entries (records untouched)",
    )
    delete_machine_parser.add_argument("machine", help="Machine id or unique prefix")
    delete_machine_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip the confirmation prompt"
    )
    delete_machine_parser.set_defaults(func=lambda args: delete_machine(args.machine, args.yes))

    delete_tool_parser = subparsers.add_parser(
        "delete-tool",
        help="Delete a tool record (bound entries are unbound, not orphaned)",
    )
    delete_tool_parser.add_argument("record", help="Tool record id or unique prefix")
    delete_tool_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip the confirmation prompt"
    )
    delete_tool_parser.set_defaults(func=lambda args: delete_tool(args.record, args.yes))

    delete_entry_parser = subparsers.add_parser(
        "delete-entry", help="Remove a machine-reported tool-table entry"
    )
    delete_entry_parser.add_argument("machine", help="Machine id or unique prefix")
    delete_entry_parser.add_argument("tool_number", type=int, help="Tool number (e.g. 3)")
    delete_entry_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip the confirmation prompt"
    )
    delete_entry_parser.set_defaults(
        func=lambda args: delete_entry(args.machine, args.tool_number, args.yes)
    )

    bind_parser = subparsers.add_parser(
        "bind", help="Link an unbound entry to a tool record"
    )
    bind_parser.add_argument("machine", help="Machine id or unique prefix")
    bind_parser.add_argument("tool_number", type=int, help="Tool number (e.g. 3)")
    bind_parser.add_argument("record", help="Tool record id or unique prefix")
    bind_parser.set_defaults(
        func=lambda args: bind_entry(args.machine, args.tool_number, args.record)
    )

    unbind_parser = subparsers.add_parser(
        "unbind", help="Unbind an entry (it keeps its data)"
    )
    unbind_parser.add_argument("machine", help="Machine id or unique prefix")
    unbind_parser.add_argument("tool_number", type=int, help="Tool number (e.g. 3)")
    unbind_parser.set_defaults(
        func=lambda args: unbind_entry(args.machine, args.tool_number)
    )

    create_record_parser = subparsers.add_parser(
        "create-record",
        help="Create a tool record from an entry and bind it in one step",
    )
    create_record_parser.add_argument("machine", help="Machine id or unique prefix")
    create_record_parser.add_argument("tool_number", type=int, help="Tool number (e.g. 3)")
    create_record_parser.add_argument(
        "--name", help="Name for the new record (defaults to the entry description)"
    )
    create_record_parser.set_defaults(
        func=lambda args: create_record_from_entry(args.machine, args.tool_number, args.name)
    )

    # === ping ===
    ping_parser = subparsers.add_parser(
        "ping",
        help="Check server health",
        description="Check if the server is reachable and healthy."
    )
    ping_parser.set_defaults(func=lambda _: ping())

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