# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Integration tests for ToolSet bulk API endpoints.

Tests bulk-first design: all operations accept arrays.

Assumptions:
- POST /api/v1/tool-sets - Create (bulk)
- GET /api/v1/tool-sets - List/query with filters
- PUT /api/v1/tool-sets - Update (bulk) with version checking
- DELETE /api/v1/tool-sets - Delete (bulk)
- type: machine_setup, job_specific, template, project
- status: draft, active, archived
- members is JSON array of tool references
- Multi-tenant: Users only access their own data
"""
import pytest
from datetime import datetime, UTC


@pytest.mark.integration
def test_bulk_create_tool_sets(client, db_session):
    """Test bulk create of tool sets.
    
    Assumptions:
    - Accepts array of sets
    - name, type, members required
    - status defaults to 'draft'
    """
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    tool_sets = [
        {
            "name": "Aluminum Milling Set",
            "type": "job_specific",
            "machine_id": "HAAS-VF2",
            "job_id": "JOB-001",
            "members": [
                {"preset_id": "preset-1", "sequence": 1},
                {"preset_id": "preset-2", "sequence": 2}
            ],
            "status": "draft"
        },
        {
            "name": "General Purpose Set",
            "type": "template",
            "members": [
                {"preset_id": "preset-3", "sequence": 1}
            ]
        }
    ]
    
    client.cookies.set("session", session_id)
    
    response = client.post(
        "/api/v1/tool-sets",
        json={"items": tool_sets}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success_count"] == 2
    assert len(data["results"]) == 2
    assert data["error_count"] == 0
    
    # Verify data stored correctly
    assert data["results"][0]["name"] == "Aluminum Milling Set"
    assert data["results"][0]["type"] == "job_specific"
    assert len(data["results"][0]["members"]) == 2


@pytest.mark.integration
def test_create_validates_required_fields(client, db_session):
    """Test validation of required fields.
    
    Assumptions:
    - name, type, members required
    """
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    tool_sets = [
        {
            "name": "Valid Set",
            "type": "template",
            "members": [{"preset_id": "preset-1"}]
        },
        {
            # Missing required 'name'
            "type": "template",
            "members": [{"preset_id": "preset-2"}]
        }
    ]
    
    client.cookies.set("session", session_id)
    
    response = client.post(
        "/api/v1/tool-sets",
        json={"items": tool_sets}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success_count"] == 1
    assert data["error_count"] == 1


@pytest.mark.integration
def test_bulk_read_tool_sets(client, db_session):
    """Test bulk read/list of tool sets."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    # Create tool sets
    for i in range(3):
        tool_set = ToolSet(
            name=f"Tool Set {i}",
            type="template",
            members=[{"preset_id": f"preset-{i}"}],
            status="draft",
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id
        )
        db_session.add(tool_set)
    db_session.commit()
    
    client.cookies.set("session", session_id)
    
    response = client.get("/api/v1/tool-sets")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "items" in data
    assert len(data["items"]) == 3


@pytest.mark.integration
def test_filter_by_type(client, db_session):
    """Test filtering sets by type."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    # Create sets with different types
    types = ["template", "job_specific", "template"]
    for i, set_type in enumerate(types):
        tool_set = ToolSet(
            name=f"Tool Set {i}",
            type=set_type,
            members=[{"preset_id": f"preset-{i}"}],
            status="draft",
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id
        )
        db_session.add(tool_set)
    db_session.commit()
    
    client.cookies.set("session", session_id)
    
    response = client.get("/api/v1/tool-sets?type=template")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["items"]) == 2
    for item in data["items"]:
        assert item["type"] == "template"


@pytest.mark.integration
def test_filter_by_status(client, db_session):
    """Test filtering sets by status."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    # Create sets with different statuses
    statuses = ["draft", "active", "draft"]
    for i, status in enumerate(statuses):
        tool_set = ToolSet(
            name=f"Tool Set {i}",
            type="template",
            members=[{"preset_id": f"preset-{i}"}],
            status=status,
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id
        )
        db_session.add(tool_set)
    db_session.commit()
    
    client.cookies.set("session", session_id)
    
    response = client.get("/api/v1/tool-sets?status=active")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "active"


@pytest.mark.integration
def test_bulk_update_tool_sets(client, db_session):
    """Test bulk update with version checking."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    # Create tool sets
    set1 = ToolSet(
        name="Set 1",
        type="template",
        members=[{"preset_id": "preset-1"}],
        status="draft",
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id,
        version=1
    )
    set2 = ToolSet(
        name="Set 2",
        type="template",
        members=[{"preset_id": "preset-2"}],
        status="draft",
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id,
        version=1
    )
    db_session.add_all([set1, set2])
    db_session.commit()
    
    # Update both
    updates = [
        {
            "id": set1.id,
            "version": 1,
            "status": "active"
        },
        {
            "id": set2.id,
            "version": 1,
            "description": "Updated description"
        }
    ]
    
    client.cookies.set("session", session_id)
    
    response = client.put(
        "/api/v1/tool-sets",
        json={"items": updates}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success_count"] == 2
    assert data["error_count"] == 0


@pytest.mark.integration
def test_get_single_tool_set_success(client, db_session):
    """Test retrieving a single tool set by ID."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet

    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)

    tool_set = ToolSet(
        name="A Set",
        type="template",
        members=[{"preset_id": "p1"}],
        status="draft",
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id
    )
    db_session.add(tool_set)
    db_session.commit()

    client.cookies.set("session", session_id)
    response = client.get(f"/api/v1/tool-sets/{tool_set.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == tool_set.id
    assert data["name"] == "A Set"
    assert data["version"] >= 1


@pytest.mark.integration
def test_get_single_tool_set_not_found_other_user(client, db_session):
    """Test that accessing another user's tool set returns 404."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet

    owner = create_user(db_session, "owner@example.com", "Password123")
    other = create_user(db_session, "other@example.com", "Password123")
    session_id = create_session(other.id)

    tool_set = ToolSet(
        name="Owner Set",
        type="template",
        members=[{"preset_id": "p1"}],
        status="draft",
        user_id=owner.id,
        created_by=owner.id,
        updated_by=owner.id
    )
    db_session.add(tool_set)
    db_session.commit()

    client.cookies.set("session", session_id)
    response = client.get(f"/api/v1/tool-sets/{tool_set.id}")
    assert response.status_code == 404


@pytest.mark.integration
def test_bulk_delete_tool_sets(client, db_session):
    """Test bulk delete of tool sets."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolSet
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    # Create tool sets
    tool_sets = []
    for i in range(3):
        tool_set = ToolSet(
            name=f"Tool Set {i}",
            type="template",
            members=[{"preset_id": f"preset-{i}"}],
            status="draft",
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id
        )
        tool_sets.append(tool_set)
        db_session.add(tool_set)
    db_session.commit()
    
    # Delete first two
    client.cookies.set("session", session_id)
    
    response = client.request(
        "DELETE",
        "/api/v1/tool-sets",
        json={"ids": [tool_sets[0].id, tool_sets[1].id]}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success_count"] == 2
    assert data["error_count"] == 0
