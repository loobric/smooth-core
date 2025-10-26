# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Integration tests for ToolSet versioning API endpoints.

Tests version history, restore, and comparison features.

Assumptions:
- Automatic snapshotting on updates
- User-scoped access control
- Immutable history records
"""
import pytest


@pytest.mark.integration
def test_tool_set_version_history(client, db_session):
    """Test retrieving version history for a ToolSet."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet
    from smooth.versioning import snapshot_tool_set
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    tool_set = ToolSet(
        name="Test Set",
        type="template",
        members=[{"preset_id": "p1"}],
        status="draft",
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id,
        version=1
    )
    db_session.add(tool_set)
    db_session.commit()
    
    snapshot_tool_set(db_session, tool_set, user.id, "Initial version")
    tool_set.version = 2
    snapshot_tool_set(db_session, tool_set, user.id, "Second version")
    db_session.commit()
    
    client.cookies.set("session", session_id)
    response = client.get(f"/api/v1/tool-sets/{tool_set.id}/history")
    
    assert response.status_code == 200
    data = response.json()
    assert data["tool_set_id"] == tool_set.id
    assert len(data["versions"]) == 2
    assert data["versions"][0]["version"] == 2  # Newest first


@pytest.mark.integration
def test_get_specific_version(client, db_session):
    """Test retrieving a specific version snapshot."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet
    from smooth.versioning import snapshot_tool_set
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    tool_set = ToolSet(
        name="Original Name",
        type="template",
        members=[{"preset_id": "p1"}],
        status="draft",
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id,
        version=1
    )
    db_session.add(tool_set)
    db_session.commit()
    
    snapshot_tool_set(db_session, tool_set, user.id)
    db_session.commit()
    
    client.cookies.set("session", session_id)
    response = client.get(f"/api/v1/tool-sets/{tool_set.id}/versions/1")
    
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 1
    assert data["snapshot"]["name"] == "Original Name"


@pytest.mark.integration
def test_restore_to_previous_version(client, db_session):
    """Test restoring a ToolSet to a previous version."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet
    from smooth.versioning import snapshot_tool_set
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    tool_set = ToolSet(
        name="Version 1",
        type="template",
        members=[{"preset_id": "p1"}],
        status="draft",
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id,
        version=1
    )
    db_session.add(tool_set)
    db_session.commit()
    
    snapshot_tool_set(db_session, tool_set, user.id)
    tool_set.name = "Version 2"
    tool_set.version = 2
    snapshot_tool_set(db_session, tool_set, user.id)
    db_session.commit()
    
    client.cookies.set("session", session_id)
    response = client.post(f"/api/v1/tool-sets/{tool_set.id}/restore/1")
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["tool_set"]["name"] == "Version 1"
    assert data["current_version"] == 3  # New version created


@pytest.mark.integration
def test_compare_two_versions(client, db_session):
    """Test comparing two versions of a ToolSet."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet
    from smooth.versioning import snapshot_tool_set
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    tool_set = ToolSet(
        name="Version 1 Name",
        type="template",
        members=[{"preset_id": "p1"}],
        status="draft",
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id,
        version=1
    )
    db_session.add(tool_set)
    db_session.commit()
    
    snapshot_tool_set(db_session, tool_set, user.id)
    tool_set.name = "Version 2 Name"
    tool_set.members = [{"preset_id": "p1"}, {"preset_id": "p2"}]
    tool_set.version = 2
    snapshot_tool_set(db_session, tool_set, user.id)
    db_session.commit()
    
    client.cookies.set("session", session_id)
    response = client.get(f"/api/v1/tool-sets/{tool_set.id}/compare/1/2")
    
    assert response.status_code == 200
    data = response.json()
    assert "differences" in data
    assert "name" in data["differences"]
    assert "members" in data["differences"]
    assert data["total_changes"] == 2


@pytest.mark.integration
def test_update_creates_history(client, db_session):
    """Test that updating a ToolSet automatically creates history."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    tool_set = ToolSet(
        name="Original",
        type="template",
        members=[],
        status="draft",
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id,
        version=1
    )
    db_session.add(tool_set)
    db_session.commit()
    
    client.cookies.set("session", session_id)
    update_response = client.put(
        "/api/v1/tool-sets",
        json={"items": [{"id": tool_set.id, "version": 1, "name": "Updated"}]}
    )
    
    assert update_response.status_code == 200
    
    history_response = client.get(f"/api/v1/tool-sets/{tool_set.id}/history")
    assert history_response.status_code == 200
    history_data = history_response.json()
    assert len(history_data["versions"]) == 1  # Snapshot of v1 before update


@pytest.mark.integration
def test_version_access_control(client, db_session):
    """Test that users can only access their own ToolSet history."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet
    from smooth.versioning import snapshot_tool_set
    
    user1 = create_user(db_session, "user1@example.com", "Password123")
    user2 = create_user(db_session, "user2@example.com", "Password123")
    
    tool_set = ToolSet(
        name="User 1 Set",
        type="template",
        members=[],
        status="draft",
        user_id=user1.id,
        created_by=user1.id,
        updated_by=user1.id,
        version=1
    )
    db_session.add(tool_set)
    db_session.commit()
    
    snapshot_tool_set(db_session, tool_set, user1.id)
    db_session.commit()
    
    # User 2 tries to access User 1's history
    session_id = create_session(user2.id)
    client.cookies.set("session", session_id)
    response = client.get(f"/api/v1/tool-sets/{tool_set.id}/history")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["versions"]) == 0  # No access to other user's data
