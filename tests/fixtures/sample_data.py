# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Sample test data generators.

Creates realistic test datasets for tool data, users, and API keys.

Assumptions:
- Used to create backup snapshots for test fixtures
- Generates valid data matching schema constraints
- Supports multiple test scenarios (single user, multi-user, empty)
"""
from datetime import datetime, UTC
from uuid import uuid4


def create_sample_users(count=2):
    """Create sample user data.
    
    Args:
        count: Number of users to create
        
    Returns:
        list: User entity dicts
    """
    users = []
    for i in range(count):
        is_admin = (i == 0)  # First user is admin
        users.append({
            "id": str(uuid4()),
            "email": f"user{i+1}@example.com",
            "password_hash": "$2b$12$SAMPLE_HASH_FOR_TESTING_ONLY",
            "is_active": True,
            "is_admin": is_admin,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "version": 1
        })
    return users


def create_sample_tool_items(user_id, count=5):
    """Create sample tool items for a user.
    
    Args:
        user_id: User ID who owns the tools
        count: Number of tool items to create
        
    Returns:
        list: ToolItem entity dicts
    """
    tool_types = ["cutting_tool", "holder", "insert", "adapter"]
    manufacturers = ["Kennametal", "Sandvik", "Iscar", "Mitsubishi"]
    
    tools = []
    for i in range(count):
        tool_type = tool_types[i % len(tool_types)]
        manufacturer = manufacturers[i % len(manufacturers)]
        
        tools.append({
            "id": str(uuid4()),
            "type": tool_type,
            "manufacturer": manufacturer,
            "product_code": f"{manufacturer.upper()}-{tool_type.upper()}-{i+1:03d}",
            "description": f"Sample {tool_type} #{i+1}",
            "geometry": {
                "diameter": 10.0 + i * 2,
                "length": 50.0 + i * 10,
                "flutes": 4
            } if tool_type == "cutting_tool" else None,
            "material": {
                "grade": "HC",
                "coating": "TiAlN"
            } if tool_type == "cutting_tool" else None,
            "iso_13399_reference": None,
            "user_id": user_id,
            "created_by": user_id,
            "updated_by": user_id,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "version": 1
        })
    
    return tools


def create_sample_api_keys(user_id, count=2):
    """Create sample API keys for a user.
    
    Args:
        user_id: User ID who owns the keys
        count: Number of API keys to create
        
    Returns:
        list: ApiKey entity dicts
    """
    scope_sets = [
        ["read"],
        ["read", "write:items"],
        ["read", "write:items", "write:presets"],
        ["admin:users", "admin:backup"]
    ]
    
    keys = []
    for i in range(count):
        scopes = scope_sets[i % len(scope_sets)]
        
        # Generate unique key hash for each key (using index to make it unique)
        key_hash = f"$2b$12$SAMPLE_KEY_HASH_FOR_TESTING_{i:04d}"
        
        keys.append({
            "id": str(uuid4()),
            "user_id": user_id,
            "name": f"Test Key {i+1}",
            "key_hash": key_hash,
            "scopes": scopes,
            "expires_at": None,
            "is_active": True,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "version": 1
        })
    
    return keys


def create_minimal_backup():
    """Create minimal backup with single user and no tool data.
    
    Returns:
        dict: Backup structure
    """
    users = create_sample_users(count=1)
    
    return {
        "metadata": {
            "version": "0.1.0",
            "timestamp": datetime.now(UTC).isoformat(),
            "backup_type": "admin",
            "counts": {
                "users": 1,
                "api_keys": 0,
                "tool_items": 0,
                "tool_assemblies": 0,
                "tool_instances": 0,
                "tool_presets": 0,
                "tool_usage": 0,
                "tool_sets": 0
            }
        },
        "entities": {
            "users": users,
            "api_keys": [],
            "tool_items": [],
            "tool_assemblies": [],
            "tool_instances": [],
            "tool_presets": [],
            "tool_usage": [],
            "tool_sets": []
        }
    }


def create_single_user_backup():
    """Create backup with single user, API keys, and tool items.
    
    Returns:
        dict: Backup structure
    """
    users = create_sample_users(count=1)
    user_id = users[0]["id"]
    
    api_keys = create_sample_api_keys(user_id, count=2)
    tool_items = create_sample_tool_items(user_id, count=10)
    
    return {
        "metadata": {
            "version": "0.1.0",
            "timestamp": datetime.now(UTC).isoformat(),
            "backup_type": "user",
            "user_id": user_id,
            "counts": {
                "users": 1,
                "api_keys": len(api_keys),
                "tool_items": len(tool_items),
                "tool_assemblies": 0,
                "tool_instances": 0,
                "tool_presets": 0,
                "tool_usage": 0,
                "tool_sets": 0
            }
        },
        "entities": {
            "users": users,
            "api_keys": api_keys,
            "tool_items": tool_items,
            "tool_assemblies": [],
            "tool_instances": [],
            "tool_presets": [],
            "tool_usage": [],
            "tool_sets": []
        }
    }


def create_multi_user_backup():
    """Create backup with multiple users, each with their own data.
    
    Returns:
        dict: Backup structure
    """
    users = create_sample_users(count=3)
    
    all_api_keys = []
    all_tool_items = []
    
    for user in users:
        user_id = user["id"]
        all_api_keys.extend(create_sample_api_keys(user_id, count=2))
        all_tool_items.extend(create_sample_tool_items(user_id, count=5))
    
    return {
        "metadata": {
            "version": "0.1.0",
            "timestamp": datetime.now(UTC).isoformat(),
            "backup_type": "admin",
            "counts": {
                "users": len(users),
                "api_keys": len(all_api_keys),
                "tool_items": len(all_tool_items),
                "tool_assemblies": 0,
                "tool_instances": 0,
                "tool_presets": 0,
                "tool_usage": 0,
                "tool_sets": 0
            }
        },
        "entities": {
            "users": users,
            "api_keys": all_api_keys,
            "tool_items": all_tool_items,
            "tool_assemblies": [],
            "tool_instances": [],
            "tool_presets": [],
            "tool_usage": [],
            "tool_sets": []
        }
    }
