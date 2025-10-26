# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Integration tests for ToolInstance bulk API endpoints.

Tests bulk-first design: all operations accept arrays.

Assumptions:
- POST /api/v1/tool-instances - Create (bulk)
- GET /api/v1/tool-instances - List/query with filters
- PUT /api/v1/tool-instances - Update (bulk) with version checking
- DELETE /api/v1/tool-instances - Delete (bulk)
- assembly_id references ToolAssembly
- status: available, in_use, needs_inspection, retired
- Multi-tenant: Users only access their own data
"""
import pytest
from datetime import datetime, UTC


@pytest.mark.integration
def test_bulk_create_tool_instances(client, db_session):
    """Test bulk create of tool instances.
    
    Assumptions:
    - Accepts array of instances
    - assembly_id references parent assembly
    - status defaults to 'available'
    """
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolAssembly
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    # Create assembly first
    assembly = ToolAssembly(
        name="Test Assembly",
        components=[{"item_id": "tool-1", "role": "cutter"}],
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id
    )
    db_session.add(assembly)
    db_session.commit()
    
    instances = [
        {
            "assembly_id": assembly.id,
            "serial_number": "SN-001",
            "status": "available",
            "location": {"building": "A", "shelf": "1"}
        },
        {
            "assembly_id": assembly.id,
            "serial_number": "SN-002",
            "status": "in_use"
        }
    ]
    
    client.cookies.set("session", session_id)
    
    response = client.post(
        "/api/v1/tool-instances",
        json={"items": instances}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success_count"] == 2
    assert len(data["results"]) == 2
    assert data["error_count"] == 0
    
    # Verify assembly_id stored correctly
    assert data["results"][0]["assembly_id"] == assembly.id


@pytest.mark.integration
def test_create_validates_required_fields(client, db_session):
    """Test validation of required fields.
    
    Assumptions:
    - assembly_id is required
    - Returns error for invalid items
    """
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolAssembly
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    # Create assembly
    assembly = ToolAssembly(
        name="Test Assembly",
        components=[{"item_id": "tool-1", "role": "cutter"}],
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id
    )
    db_session.add(assembly)
    db_session.commit()
    
    instances = [
        {
            "assembly_id": assembly.id,
            "serial_number": "SN-001"
        },
        {
            # Missing required 'assembly_id' field
            "serial_number": "SN-002"
        }
    ]
    
    client.cookies.set("session", session_id)
    
    response = client.post(
        "/api/v1/tool-instances",
        json={"items": instances}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success_count"] == 1
    assert data["error_count"] == 1


@pytest.mark.integration
def test_bulk_read_tool_instances(client, db_session):
    """Test bulk read/list of tool instances.
    
    Assumptions:
    - GET returns array of instances
    - Filters by user_id automatically
    """
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolAssembly, ToolInstance
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    # Create assembly
    assembly = ToolAssembly(
        name="Test Assembly",
        components=[{"item_id": "tool-1", "role": "cutter"}],
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id
    )
    db_session.add(assembly)
    db_session.commit()
    
    # Create instances
    for i in range(3):
        instance = ToolInstance(
            assembly_id=assembly.id,
            serial_number=f"SN-{i:03d}",
            status="available",
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id
        )
        db_session.add(instance)
    db_session.commit()
    
    client.cookies.set("session", session_id)
    
    response = client.get("/api/v1/tool-instances")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "items" in data
    assert len(data["items"]) == 3
    assert data["total"] == 3


@pytest.mark.integration
def test_filter_by_status(client, db_session):
    """Test filtering instances by status.
    
    Assumptions:
    - Supports status filter parameter
    """
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolAssembly, ToolInstance
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    # Create assembly
    assembly = ToolAssembly(
        name="Test Assembly",
        components=[{"item_id": "tool-1", "role": "cutter"}],
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id
    )
    db_session.add(assembly)
    db_session.commit()
    
    # Create instances with different statuses
    statuses = ["available", "in_use", "available"]
    for i, status in enumerate(statuses):
        instance = ToolInstance(
            assembly_id=assembly.id,
            serial_number=f"SN-{i:03d}",
            status=status,
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id
        )
        db_session.add(instance)
    db_session.commit()
    
    client.cookies.set("session", session_id)
    
    response = client.get("/api/v1/tool-instances?status=available")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["items"]) == 2
    for item in data["items"]:
        assert item["status"] == "available"


@pytest.mark.integration
def test_bulk_update_tool_instances(client, db_session):
    """Test bulk update with version checking.
    
    Assumptions:
    - Can update status, location, measured_geometry
    - Version field incremented
    """
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolAssembly, ToolInstance
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    # Create assembly
    assembly = ToolAssembly(
        name="Test Assembly",
        components=[{"item_id": "tool-1", "role": "cutter"}],
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id
    )
    db_session.add(assembly)
    db_session.commit()
    
    # Create instances
    instance1 = ToolInstance(
        assembly_id=assembly.id,
        serial_number="SN-001",
        status="available",
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id,
        version=1
    )
    instance2 = ToolInstance(
        assembly_id=assembly.id,
        serial_number="SN-002",
        status="available",
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id,
        version=1
    )
    db_session.add_all([instance1, instance2])
    db_session.commit()
    
    # Update both
    updates = [
        {
            "id": instance1.id,
            "version": 1,
            "status": "in_use"
        },
        {
            "id": instance2.id,
            "version": 1,
            "location": {"building": "B", "shelf": "2"}
        }
    ]
    
    client.cookies.set("session", session_id)
    
    response = client.put(
        "/api/v1/tool-instances",
        json={"items": updates}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success_count"] == 2
    assert data["error_count"] == 0
    
    # Verify updates applied
    assert data["results"][0]["status"] == "in_use"
    assert data["results"][0]["version"] == 2


@pytest.mark.integration
def test_bulk_delete_tool_instances(client, db_session):
    """Test bulk delete of instances."""
    from smooth.auth.user import create_user
    from smooth.api.auth import create_session
    from smooth.database.schema import ToolAssembly, ToolInstance
    
    user = create_user(db_session, "test@example.com", "Password123")
    session_id = create_session(user.id)
    
    # Create assembly
    assembly = ToolAssembly(
        name="Test Assembly",
        components=[{"item_id": "tool-1", "role": "cutter"}],
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id
    )
    db_session.add(assembly)
    db_session.commit()
    
    # Create instances
    instances = []
    for i in range(3):
        instance = ToolInstance(
            assembly_id=assembly.id,
            serial_number=f"SN-{i:03d}",
            status="available",
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id
        )
        instances.append(instance)
        db_session.add(instance)
    db_session.commit()
    
    # Delete first two
    client.cookies.set("session", session_id)
    
    response = client.request(
        "DELETE",
        "/api/v1/tool-instances",
        json={"ids": [instances[0].id, instances[1].id]}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success_count"] == 2
    assert data["error_count"] == 0
