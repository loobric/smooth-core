# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Integration tests for tag-based access control on tool sets.

Tests tag enforcement across CRUD operations for tool sets.

Assumptions:
- API keys can have tags that restrict access to resources
- Resources (tool sets) can have tags
- Access granted if any API key tag matches any resource tag
- Empty API key tags = no restrictions (access all resources with proper scopes)
- Empty resource tags = accessible to all keys with proper scopes
- Admin scope (admin:*) bypasses tag checks
- Session auth bypasses tag checks (user owns all their resources)
"""
import pytest
from smooth.database.schema import ToolSet


@pytest.mark.integration
def test_create_tool_set_with_api_key_tags(client, db_session):
    """Test creating tool sets with API key that has tags.
    
    Assumptions:
    - API key with tags can only create resources with those tags
    - Creating resource with unauthorized tags returns error
    - Creating resource with subset of key tags succeeds
    """
    from smooth.auth.user import create_user
    from smooth.auth.apikey import create_api_key
    
    user = create_user(db_session, "test@example.com", "Password123")
    db_session.commit()
    
    # Create API key with tags
    api_key_plain = create_api_key(
        db_session,
        user_id=user.id,
        name="Mill-3 Key",
        scopes=["read", "write:sets"],
        tags=["mill-3", "production"]
    )
    
    # Test 1: Create tool set with allowed tags
    response = client.post(
        "/api/v1/tool-sets",
        headers={"Authorization": f"Bearer {api_key_plain}"},
        json={
            "items": [{
                "name": "Mill-3 Tool Set",
                "type": "machine_setup",
                "members": [{"tool_id": "tool-1"}],
                "tags": ["mill-3"]
            }]
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success_count"] == 1
    assert data["results"][0]["tags"] == ["mill-3"]
    
    # Test 2: Create tool set with unauthorized tag fails
    response = client.post(
        "/api/v1/tool-sets",
        headers={"Authorization": f"Bearer {api_key_plain}"},
        json={
            "items": [{
                "name": "Lathe Tool Set",
                "type": "machine_setup",
                "members": [{"tool_id": "tool-2"}],
                "tags": ["lathe-1"]
            }]
        }
    )
    
    assert response.status_code == 200  # Partial success response
    data = response.json()
    assert data["success_count"] == 0
    assert data["error_count"] == 1
    assert "not authorized" in data["errors"][0]["message"].lower()


@pytest.mark.integration
def test_list_tool_sets_filtered_by_api_key_tags(client, db_session):
    """Test listing tool sets is filtered by API key tags.
    
    Assumptions:
    - API key with tags only sees resources with matching tags
    - API key without tags sees all resources (with proper scopes)
    - Returns only tool sets where at least one tag matches
    """
    from smooth.auth.user import create_user
    from smooth.auth.apikey import create_api_key
    
    user = create_user(db_session, "test@example.com", "Password123")
    db_session.commit()
    
    # Create tool sets with different tags
    tool_sets = [
        ToolSet(
            name="Mill-3 Set",
            type="machine_setup",
            members=[{"tool_id": "tool-1"}],
            tags=["mill-3", "production"],
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id
        ),
        ToolSet(
            name="Lathe-1 Set",
            type="machine_setup",
            members=[{"tool_id": "tool-2"}],
            tags=["lathe-1"],
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id
        ),
        ToolSet(
            name="Production Set",
            type="template",
            members=[{"tool_id": "tool-3"}],
            tags=["production"],
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id
        ),
    ]
    for ts in tool_sets:
        db_session.add(ts)
    db_session.commit()
    
    # Create API key with mill-3 tag
    api_key_plain = create_api_key(
        db_session,
        user_id=user.id,
        name="Mill-3 Key",
        scopes=["read"],
        tags=["mill-3"]
    )
    
    # List tool sets with tagged API key
    response = client.get(
        "/api/v1/tool-sets",
        headers={"Authorization": f"Bearer {api_key_plain}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should only see tool sets with mill-3 tag
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Mill-3 Set"


@pytest.mark.integration
def test_get_tool_set_with_tag_access(client, db_session):
    """Test getting single tool set with tag-based access control.
    
    Assumptions:
    - API key with matching tags can access tool set
    - API key without matching tags gets 403
    - Resource owner can always access (session auth)
    """
    from smooth.auth.user import create_user
    from smooth.auth.apikey import create_api_key
    
    user = create_user(db_session, "test@example.com", "Password123")
    db_session.commit()
    
    # Create tool set with tags
    tool_set = ToolSet(
        name="Mill-3 Set",
        type="machine_setup",
        members=[{"tool_id": "tool-1"}],
        tags=["mill-3", "production"],
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id
    )
    db_session.add(tool_set)
    db_session.commit()
    
    # Test 1: API key with matching tag can access
    api_key_mill_plain = create_api_key(
        db_session,
        user_id=user.id,
        name="Mill-3 Key",
        scopes=["read"],
        tags=["mill-3"]
    )
    
    response = client.get(
        f"/api/v1/tool-sets/{tool_set.id}",
        headers={"Authorization": f"Bearer {api_key_mill_plain}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == tool_set.id
    
    # Test 2: API key without matching tag gets denied
    api_key_lathe_plain = create_api_key(
        db_session,
        user_id=user.id,
        name="Lathe-1 Key",
        scopes=["read"],
        tags=["lathe-1"]
    )
    
    response = client.get(
        f"/api/v1/tool-sets/{tool_set.id}",
        headers={"Authorization": f"Bearer {api_key_lathe_plain}"}
    )
    
    assert response.status_code == 403


@pytest.mark.integration
def test_update_tool_set_with_tag_enforcement(client, db_session):
    """Test updating tool sets with tag-based access control.
    
    Assumptions:
    - API key must have access to existing tool set tags
    - API key must have access to new tags being applied
    - Cannot change tags to unauthorized values
    """
    from smooth.auth.user import create_user
    from smooth.auth.apikey import create_api_key
    
    user = create_user(db_session, "test@example.com", "Password123")
    db_session.commit()
    
    # Create tool set with tags
    tool_set = ToolSet(
        name="Mill-3 Set",
        type="machine_setup",
        members=[{"tool_id": "tool-1"}],
        tags=["mill-3"],
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id,
        version=1
    )
    db_session.add(tool_set)
    db_session.commit()
    
    # Create API key with mill-3 tag
    api_key_plain = create_api_key(
        db_session,
        user_id=user.id,
        name="Mill-3 Key",
        scopes=["read", "write:sets"],
        tags=["mill-3", "production"]
    )
    
    # Test 1: Update with allowed tags succeeds
    response = client.put(
        "/api/v1/tool-sets",
        headers={"Authorization": f"Bearer {api_key_plain}"},
        json={
            "items": [{
                "id": tool_set.id,
                "version": 1,
                "description": "Updated description",
                "tags": ["mill-3", "production"]
            }]
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success_count"] == 1
    assert data["results"][0]["tags"] == ["mill-3", "production"]
    
    # Test 2: Update with unauthorized tags fails
    db_session.refresh(tool_set)
    response = client.put(
        "/api/v1/tool-sets",
        headers={"Authorization": f"Bearer {api_key_plain}"},
        json={
            "items": [{
                "id": tool_set.id,
                "version": 2,
                "tags": ["lathe-1"]
            }]
        }
    )
    
    assert response.status_code == 200  # Partial success
    data = response.json()
    assert data["success_count"] == 0
    assert data["error_count"] == 1
    assert "not authorized" in data["errors"][0]["message"].lower()


@pytest.mark.integration
def test_delete_tool_set_with_tag_enforcement(client, db_session):
    """Test deleting tool sets with tag-based access control.
    
    Assumptions:
    - API key must have access to tool set tags to delete
    - API key without matching tags cannot delete
    """
    from smooth.auth.user import create_user
    from smooth.auth.apikey import create_api_key
    
    user = create_user(db_session, "test@example.com", "Password123")
    db_session.commit()
    
    # Create tool sets with different tags
    set_mill = ToolSet(
        name="Mill-3 Set",
        type="machine_setup",
        members=[{"tool_id": "tool-1"}],
        tags=["mill-3"],
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id
    )
    set_lathe = ToolSet(
        name="Lathe-1 Set",
        type="machine_setup",
        members=[{"tool_id": "tool-2"}],
        tags=["lathe-1"],
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id
    )
    db_session.add_all([set_mill, set_lathe])
    db_session.commit()
    
    # Create API key with mill-3 tag
    api_key_plain = create_api_key(
        db_session,
        user_id=user.id,
        name="Mill-3 Key",
        scopes=["read", "write:sets", "delete:sets"],
        tags=["mill-3"]
    )
    
    # Test 1: Delete tool set with matching tag succeeds
    response = client.request(
        "DELETE",
        "/api/v1/tool-sets",
        headers={"Authorization": f"Bearer {api_key_plain}"},
        json={"ids": [set_mill.id]}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success_count"] == 1
    
    # Test 2: Delete tool set without matching tag fails
    response = client.request(
        "DELETE",
        "/api/v1/tool-sets",
        headers={"Authorization": f"Bearer {api_key_plain}"},
        json={"ids": [set_lathe.id]}
    )
    
    assert response.status_code == 200  # Partial success
    data = response.json()
    assert data["success_count"] == 0
    assert data["error_count"] == 1
    assert "not authorized" in data["errors"][0]["message"].lower()


@pytest.mark.integration
def test_session_auth_bypasses_tag_checks_tool_sets(client, db_session):
    """Test that session authentication bypasses tag checks for tool sets.
    
    Assumptions:
    - Users own all their resources
    - Session auth doesn't use tag filtering
    - Can create/update resources with any tags
    """
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    db_session.commit()
    
    # Create tool set with any tags via session auth
    response = client.post(
        "/api/v1/tool-sets",
        cookies={"session": session_id},
        json={
            "items": [{
                "name": "My Tool Set",
                "type": "template",
                "members": [{"tool_id": "tool-1"}],
                "tags": ["mill-3", "lathe-1", "production", "custom-tag"]
            }]
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success_count"] == 1
    assert len(data["results"][0]["tags"]) == 4
