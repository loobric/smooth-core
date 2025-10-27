# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Integration tests for manufacturer catalog functionality.

Simplified Schema:
- ManufacturerCatalog: Contains tool_ids array, tags, is_published
- ToolItem: Only needs parent_tool_id (nullable) for catalog references
- Same tool can exist in multiple catalogs

Assumptions:
- Users with role="manufacturer" can create catalogs
- Bulk-first API: Use existing /api/v1/tool-items/bulk
- Catalogs are collections of ToolItem IDs
- Users copy catalog tools using parent_tool_id
- Catalogs have tags for searchability
"""
import pytest
from datetime import datetime, UTC


@pytest.mark.integration
def test_grant_manufacturer_role(client, admin_headers):
    """Test granting manufacturer role to existing user.
    
    Assumptions:
    - User self-registers as normal user
    - Admin grants "manufacturer" role via PATCH /users/{id}/roles
    - Can add manufacturer_profile when granting role
    - Only admin can grant roles
    """
    # User self-registers
    user_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "catalog@sandvik.com",
            "password": "secure_password"
        }
    )
    assert user_response.status_code == 201
    user_data = user_response.json()
    assert user_data.get("role") in [None, "user"]  # Default role
    user_id = user_data["id"]
    
    # Admin grants manufacturer role
    response = client.patch(
        f"/api/v1/users/{user_id}/roles",
        headers=admin_headers,
        json={
            "role": "manufacturer",
            "manufacturer_profile": {
                "company_name": "Sandvik Coromant",
                "website": "https://www.sandvik.coromant.com",
                "description": "Leading manufacturer of cutting tools"
            }
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "manufacturer"
    assert data["manufacturer_profile"]["company_name"] == "Sandvik Coromant"
    assert data["is_verified"] == False  # Not yet verified as partner


@pytest.mark.integration
def test_revoke_manufacturer_role(client, admin_headers):
    """Test revoking manufacturer role from user.
    
    Assumptions:
    - Admin can revoke manufacturer role
    - User's catalogs remain but are unpublished
    - manufacturer_profile remains for historical reference
    """
    # Setup: Create user with manufacturer role
    user = client.post(
        "/api/v1/auth/register",
        json={"email": "temp@example.com", "password": "pass"}
    ).json()
    
    client.patch(
        f"/api/v1/users/{user['id']}/roles",
        headers=admin_headers,
        json={
            "role": "manufacturer",
            "manufacturer_profile": {"company_name": "Test Co"}
        }
    )
    
    # Revoke manufacturer role
    response = client.patch(
        f"/api/v1/users/{user['id']}/roles",
        headers=admin_headers,
        json={"role": "user"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "user"
    assert "manufacturer_profile" in data  # Preserved for history


@pytest.mark.integration
def test_non_admin_cannot_grant_roles(client, user_headers):
    """Test that non-admin users cannot grant roles.
    
    Assumptions:
    - Only admin can modify user roles
    - Regular users get 403 Forbidden
    """
    # Create another user
    target_user = client.post(
        "/api/v1/auth/register",
        json={"email": "target@example.com", "password": "pass"}
    ).json()
    
    # Regular user tries to grant manufacturer role
    response = client.patch(
        f"/api/v1/users/{target_user['id']}/roles",
        headers=user_headers,
        json={"role": "manufacturer"}
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_manufacturer_create_catalog_with_tools(client, manufacturer_headers):
    """Test manufacturer creating catalog with tools in single operation.
    
    Assumptions:
    - Manufacturer creates ToolItems first (bulk)
    - Then creates Catalog referencing those tool IDs
    - Or single operation does both atomically
    - Catalog stores tool_ids array
    - is_published defaults to False
    """
    # Step 1: Create tools (uses existing bulk API)
    tools_response = client.post(
        "/api/v1/tool-items/bulk",
        headers=manufacturer_headers,
        json={
            "tools": [
                {
                    "type": "endmill",
                    "product_code": "HT-001",
                    "description": "0.010\" diameter micro end mill",
                    "geometry": {
                        "diameter": {"value": 0.010, "unit": "inch"},
                        "flute_length": {"value": 0.030, "unit": "inch"},
                        "flutes": 2
                    },
                    "material": {"substrate": "carbide"}
                },
                {
                    "type": "endmill",
                    "product_code": "HT-002",
                    "description": "0.020\" diameter micro end mill",
                    "geometry": {
                        "diameter": {"value": 0.020, "unit": "inch"},
                        "flute_length": {"value": 0.060, "unit": "inch"},
                        "flutes": 2
                    },
                    "material": {"substrate": "carbide"}
                }
            ]
        }
    )
    assert tools_response.status_code == 201
    tool_data = tools_response.json()
    assert tool_data["tools_created"] == 2
    
    # Step 2: Create catalog with those tool IDs
    catalog_response = client.post(
        "/api/v1/catalogs",
        headers=manufacturer_headers,
        json={
            "name": "2024 Miniature End Mills",
            "description": "Complete line of miniature cutting tools",
            "catalog_year": 2024,
            "tool_ids": tool_data["tool_ids"],
            "tags": ["endmill", "miniature", "carbide", "milling"]
        }
    )
    assert catalog_response.status_code == 201
    catalog = catalog_response.json()
    assert catalog["name"] == "2024 Miniature End Mills"
    assert catalog["is_published"] == False
    assert len(catalog["tool_ids"]) == 2
    assert catalog["tool_ids"] == tool_data["tool_ids"]
    assert "endmill" in catalog["tags"]


@pytest.mark.integration
def test_manufacturer_add_tools_to_existing_catalog(client, manufacturer_headers):
    """Test manufacturer adding more tools to existing catalog.
    
    Assumptions:
    - Create tools first (bulk)
    - Update catalog's tool_ids array to include new tools
    - Same tools can be in multiple catalogs
    """
    # Create initial catalog with one tool
    tools1 = client.post(
        "/api/v1/tool-items/bulk",
        headers=manufacturer_headers,
        json={"tools": [{"type": "drill", "product_code": "D-001"}]}
    ).json()
    
    catalog = client.post(
        "/api/v1/catalogs",
        headers=manufacturer_headers,
        json={
            "name": "2024 Drills",
            "tool_ids": tools1["tool_ids"],
            "tags": ["drill", "hole-making"]
        }
    ).json()
    
    # Create more tools
    tools2 = client.post(
        "/api/v1/tool-items/bulk",
        headers=manufacturer_headers,
        json={
            "tools": [
                {"type": "drill", "product_code": "D-002"},
                {"type": "drill", "product_code": "D-003"},
                {"type": "drill", "product_code": "D-004"}
            ]
        }
    ).json()
    
    # Add new tools to catalog
    response = client.patch(
        f"/api/v1/catalogs/{catalog['id']}",
        headers=manufacturer_headers,
        json={
            "tool_ids": tools1["tool_ids"] + tools2["tool_ids"]
        }
    )
    assert response.status_code == 200
    updated = response.json()
    assert len(updated["tool_ids"]) == 4


@pytest.mark.integration
def test_user_bulk_copy_catalog_tools(client, user_headers, manufacturer_headers):
    """Test user copying multiple catalog tools to their library (bulk-first).
    
    Assumptions:
    - Manufacturer has published catalog with tools
    - User copies tools (creates new ToolItems with parent_tool_id set)
    - Uses existing /api/v1/tool-items/bulk with parent_tool_id array
    - User owns the copied tools and can modify them
    """
    # Manufacturer: Create catalog tools
    mfr_tools = client.post(
        "/api/v1/tool-items/bulk",
        headers=manufacturer_headers,
        json={
            "tools": [
                {"type": "tap", "product_code": "TAP-M6", "geometry": {"thread_size": "M6x1.0"}},
                {"type": "tap", "product_code": "TAP-M8", "geometry": {"thread_size": "M8x1.25"}},
                {"type": "tap", "product_code": "TAP-M10", "geometry": {"thread_size": "M10x1.5"}}
            ]
        }
    ).json()
    
    catalog = client.post(
        "/api/v1/catalogs",
        headers=manufacturer_headers,
        json={
            "name": "Taps & Threading",
            "tool_ids": mfr_tools["tool_ids"],
            "tags": ["tap", "threading"],
            "is_published": True
        }
    ).json()
    
    # User: Copy first 2 catalog tools to their library
    response = client.post(
        "/api/v1/tool-items/bulk",
        headers=user_headers,
        json={
            "tools": [
                {"parent_tool_id": mfr_tools["tool_ids"][0]},
                {"parent_tool_id": mfr_tools["tool_ids"][1]}
            ]
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["tools_created"] == 2
    
    # Verify copied tools have parent_tool_id set
    for i, tool_id in enumerate(data["tool_ids"]):
        tool = client.get(f"/api/v1/tool-items/{tool_id}", headers=user_headers).json()
        assert tool["parent_tool_id"] == mfr_tools["tool_ids"][i]
        assert tool["type"] == "tap"
        assert tool["user_id"] != mfr_tools["tool_ids"][i]  # Different owner


@pytest.mark.integration
def test_user_bulk_create_custom_tools(client, user_headers):
    """Test user creating multiple custom tools (bulk-first).
    
    Assumptions:
    - Bulk operation for importing user's existing tool library
    - parent_tool_id is None for all (not copied from catalog)
    - User owns all ToolItems
    """
    response = client.post(
        "/api/v1/tool-items/bulk",
        headers=user_headers,
        json={
            "tools": [
                {
                    "type": "endmill",
                    "manufacturer": "Generic",
                    "product_code": "CUSTOM-001",
                    "description": "Custom shop-made cutter",
                    "geometry": {"diameter": {"value": 6.0, "unit": "mm"}}
                },
                {
                    "type": "drill",
                    "manufacturer": "Generic",
                    "product_code": "CUSTOM-002",
                    "description": "Re-ground drill",
                    "geometry": {"diameter": {"value": 5.0, "unit": "mm"}}
                }
            ]
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["tools_created"] == 2
    
    # Verify all are custom (no parent_tool_id)
    for tool_id in data["tool_ids"]:
        tool = client.get(f"/api/v1/tool-items/{tool_id}", headers=user_headers).json()
        assert tool["parent_tool_id"] is None


@pytest.mark.integration
def test_user_bulk_override_catalog_tool_specs(client, user_headers, manufacturer_headers):
    """Test user can bulk update tools copied from catalog (measured dimensions).
    
    Assumptions:
    - User's ToolItems are independent copies
    - Bulk update for efficiency (e.g., after measuring actual tools)
    - parent_tool_id reference maintained
    - Original catalog tools unchanged
    """
    # Manufacturer: Create catalog
    mfr_tools = client.post(
        "/api/v1/tool-items/bulk",
        headers=manufacturer_headers,
        json={
            "tools": [
                {"type": "insert", "product_code": "INS-1", "geometry": {"diameter": {"value": 12.7, "unit": "mm"}}},
                {"type": "insert", "product_code": "INS-2", "geometry": {"diameter": {"value": 15.9, "unit": "mm"}}}
            ]
        }
    ).json()
    
    catalog = client.post(
        "/api/v1/catalogs",
        headers=manufacturer_headers,
        json={
            "name": "Inserts",
            "tool_ids": mfr_tools["tool_ids"],
            "tags": ["insert"],
            "is_published": True
        }
    ).json()
    
    # User: Copy catalog tools
    user_tools = client.post(
        "/api/v1/tool-items/bulk",
        headers=user_headers,
        json={
            "tools": [
                {"parent_tool_id": mfr_tools["tool_ids"][0]},
                {"parent_tool_id": mfr_tools["tool_ids"][1]}
            ]
        }
    ).json()
    
    # User: Bulk update with measured dimensions
    response = client.patch(
        "/api/v1/tool-items/bulk",
        headers=user_headers,
        json={
            "updates": [
                {"id": user_tools["tool_ids"][0], "geometry": {"diameter": {"value": 12.65, "unit": "mm"}}},
                {"id": user_tools["tool_ids"][1], "geometry": {"diameter": {"value": 15.85, "unit": "mm"}}}
            ]
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tools_updated"] == 2
    
    # Verify user tools updated
    tool1 = client.get(f"/api/v1/tool-items/{user_tools['tool_ids'][0]}", headers=user_headers).json()
    assert tool1["geometry"]["diameter"]["value"] == 12.65
    assert tool1["parent_tool_id"] == mfr_tools["tool_ids"][0]  # Reference maintained
    
    # Verify original catalog tools unchanged
    cat_tool1 = client.get(f"/api/v1/tool-items/{mfr_tools['tool_ids'][0]}").json()
    assert cat_tool1["geometry"]["diameter"]["value"] == 12.7


@pytest.mark.integration
def test_catalog_usage_analytics(client, user_headers, manufacturer_headers):
    """Test analytics tracking when users copy catalog tools.
    
    Assumptions:
    - Analytics logged when users copy tools (parent_tool_id set)
    - event_type: copied_from_catalog
    - Manufacturer can query analytics for their catalogs
    - Tracks which catalog tools are most popular
    """
    # Manufacturer: Create catalog
    mfr_tools = client.post(
        "/api/v1/tool-items/bulk",
        headers=manufacturer_headers,
        json={
            "tools": [
                {"type": "insert", "product_code": "GRIP-3"},
                {"type": "insert", "product_code": "GRIP-5"}
            ]
        }
    ).json()
    
    catalog = client.post(
        "/api/v1/catalogs",
        headers=manufacturer_headers,
        json={
            "name": "Grooving Tools",
            "tool_ids": mfr_tools["tool_ids"],
            "tags": ["grooving", "insert"],
            "is_published": True
        }
    ).json()
    
    # User: Copy tools (should log analytics)
    client.post(
        "/api/v1/tool-items/bulk",
        headers=user_headers,
        json={
            "tools": [
                {"parent_tool_id": mfr_tools["tool_ids"][0]},
                {"parent_tool_id": mfr_tools["tool_ids"][1]}
            ]
        }
    )
    
    # Manufacturer: Check analytics
    response = client.get(
        f"/api/v1/catalogs/{catalog['id']}/analytics",
        headers=manufacturer_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_copies"] == 2
    assert len(data["tool_popularity"]) == 2  # Both tools tracked


@pytest.mark.integration
def test_search_catalogs_by_tags(client, manufacturer_headers):
    """Test searching catalogs by tags.
    
    Assumptions:
    - Only is_published=True catalogs visible to public
    - Can filter by tags (e.g., ?tags=lathe,aluminum)
    - Returns manufacturer info with catalogs
    - Tool count included for each catalog
    """
    # Manufacturer: Create catalogs with different tags
    tools1 = client.post(
        "/api/v1/tool-items/bulk",
        headers=manufacturer_headers,
        json={"tools": [{"type": "drill", "product_code": "D-1"}]}
    ).json()
    
    pub_lathe = client.post(
        "/api/v1/catalogs",
        headers=manufacturer_headers,
        json={
            "name": "Lathe Tools for Aluminum",
            "tool_ids": tools1["tool_ids"],
            "tags": ["lathe", "aluminum", "turning"],
            "is_published": True
        }
    ).json()
    
    tools2 = client.post(
        "/api/v1/tool-items/bulk",
        headers=manufacturer_headers,
        json={"tools": [{"type": "endmill", "product_code": "E-1"}]}
    ).json()
    
    pub_mill = client.post(
        "/api/v1/catalogs",
        headers=manufacturer_headers,
        json={
            "name": "Milling Tools",
            "tool_ids": tools2["tool_ids"],
            "tags": ["milling", "endmill", "steel"],
            "is_published": True
        }
    ).json()
    
    tools3 = client.post(
        "/api/v1/tool-items/bulk",
        headers=manufacturer_headers,
        json={"tools": [{"type": "drill", "product_code": "D-2"}]}
    ).json()
    
    draft = client.post(
        "/api/v1/catalogs",
        headers=manufacturer_headers,
        json={
            "name": "Draft Catalog",
            "tool_ids": tools3["tool_ids"],
            "tags": ["lathe"],
            "is_published": False
        }
    ).json()
    
    # Search for lathe + aluminum (no auth required)
    response = client.get("/api/v1/catalogs?tags=lathe,aluminum")
    assert response.status_code == 200
    data = response.json()
    
    catalog_ids = [c["id"] for c in data["catalogs"]]
    assert pub_lathe["id"] in catalog_ids
    assert pub_mill["id"] not in catalog_ids  # Wrong tags
    assert draft["id"] not in catalog_ids  # Not published
    
    # Verify returned catalogs have tags
    for catalog in data["catalogs"]:
        assert catalog["is_published"] == True
        assert "lathe" in catalog["tags"]
        assert "aluminum" in catalog["tags"]
        assert "tool_count" in catalog


@pytest.mark.integration
def test_remove_tools_from_catalog(client, manufacturer_headers):
    """Test manufacturer removing tools from catalog.
    
    Assumptions:
    - Update catalog's tool_ids array to remove tools
    - Tools themselves remain in database (owned by manufacturer)
    - Tools can be added to different catalog later
    - Users who copied tools are unaffected
    """
    # Manufacturer: Create catalog with tools
    tools = client.post(
        "/api/v1/tool-items/bulk",
        headers=manufacturer_headers,
        json={
            "tools": [
                {"type": "drill", "product_code": "OLD-123"},
                {"type": "endmill", "product_code": "OLD-456"},
                {"type": "reamer", "product_code": "OLD-789"}
            ]
        }
    ).json()
    
    catalog = client.post(
        "/api/v1/catalogs",
        headers=manufacturer_headers,
        json={
            "name": "Legacy Tools",
            "tool_ids": tools["tool_ids"],
            "tags": ["legacy"],
            "is_published": True
        }
    ).json()
    
    # Manufacturer: Remove first two tools from catalog
    response = client.patch(
        f"/api/v1/catalogs/{catalog['id']}",
        headers=manufacturer_headers,
        json={
            "tool_ids": [tools["tool_ids"][2]]  # Keep only third tool
        }
    )
    assert response.status_code == 200
    updated = response.json()
    assert len(updated["tool_ids"]) == 1
    assert updated["tool_ids"][0] == tools["tool_ids"][2]
    
    # Verify tools still exist (just not in this catalog)
    tool1 = client.get(f"/api/v1/tool-items/{tools['tool_ids'][0]}", headers=manufacturer_headers).json()
    assert tool1["product_code"] == "OLD-123"


@pytest.mark.integration
def test_verify_manufacturer_partnership(client, admin_headers, manufacturer_headers):
    """Test admin verifying manufacturer user as official partner.
    
    Assumptions:
    - Only admin can set is_verified on manufacturer users
    - Verified manufacturers get special badge/icon in catalog listings
    - Enables analytics access for manufacturer
    - Updates manufacturer_profile metadata
    """
    # Manufacturer: Create account (unverified by default)
    mfr_user = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "partner@guhring.com",
            "password": "secure",
            "role": "manufacturer",
            "manufacturer_profile": {"company_name": "Guhring"}
        }
    ).json()
    
    # Admin: Verify manufacturer partnership
    response = client.patch(
        f"/api/v1/users/{mfr_user['id']}",
        headers=admin_headers,
        json={
            "is_verified": True,
            "manufacturer_profile": {
                "company_name": "Guhring",
                "partnership_tier": "premium",
                "analytics_enabled": True
            }
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_verified"] == True
    assert data["manufacturer_profile"]["analytics_enabled"] == True
    assert data["manufacturer_profile"]["partnership_tier"] == "premium"
