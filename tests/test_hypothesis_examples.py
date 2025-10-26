# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Property-based testing examples using Hypothesis.

Demonstrates hypothesis strategies for tool data entities.

Assumptions:
- Hypothesis is used for bulk operations testing
- Strategies generate valid entity data
- Tests verify properties hold for all generated inputs
"""
import pytest
from hypothesis import given, strategies as st
from datetime import datetime


# Custom strategies for tool data
@st.composite
def tool_item_strategy(draw):
    """Generate valid ToolItem data."""
    # Create alphabet for manufacturer names (letters, digits, spaces)
    manufacturer_chars = st.characters(whitelist_categories=("L", "N")) | st.just(" ")
    
    # Create alphabet for product codes (uppercase letters, digits, hyphens)
    product_code_chars = st.characters(whitelist_categories=("Lu", "Nd")) | st.just("-")
    
    return {
        "type": draw(st.sampled_from(["cutting_tool", "holder", "insert", "adapter"])),
        "manufacturer": draw(st.text(alphabet=manufacturer_chars, min_size=1, max_size=100)),
        "product_code": draw(st.text(alphabet=product_code_chars, min_size=1, max_size=100)),
        "description": draw(st.text(min_size=0, max_size=500)),
    }


@st.composite
def tool_geometry_strategy(draw):
    """Generate valid tool geometry data."""
    return {
        "diameter": draw(st.floats(min_value=0.1, max_value=100.0)),
        "length": draw(st.floats(min_value=1.0, max_value=500.0)),
        "flutes": draw(st.integers(min_value=1, max_value=12)),
    }


@st.composite
def api_key_scopes_strategy(draw):
    """Generate valid API key scope combinations."""
    available_scopes = [
        "read",
        "write:items",
        "write:presets",
        "write:usage",
        "write:sets",
        "admin:users",
        "admin:backup"
    ]
    return draw(st.lists(
        st.sampled_from(available_scopes),
        min_size=1,
        max_size=len(available_scopes),
        unique=True
    ))


@pytest.mark.unit
@pytest.mark.hypothesis
@given(tool_data=tool_item_strategy())
def test_tool_item_data_properties(tool_data):
    """Test that generated tool item data has valid properties.
    
    Assumptions:
    - All required fields present
    - Type is one of valid values
    - Strings are non-empty where required
    """
    assert "type" in tool_data
    assert tool_data["type"] in ["cutting_tool", "holder", "insert", "adapter"]
    assert "manufacturer" in tool_data
    assert len(tool_data["manufacturer"]) > 0
    assert "product_code" in tool_data
    assert len(tool_data["product_code"]) > 0


@pytest.mark.unit
@pytest.mark.hypothesis
@given(geometry=tool_geometry_strategy())
def test_tool_geometry_properties(geometry):
    """Test that generated geometry has valid properties.
    
    Assumptions:
    - Diameter and length are positive
    - Flutes count is reasonable
    """
    assert geometry["diameter"] > 0
    assert geometry["length"] > 0
    assert 1 <= geometry["flutes"] <= 12


@pytest.mark.unit
@pytest.mark.hypothesis
@given(scopes=api_key_scopes_strategy())
def test_api_key_scopes_properties(scopes):
    """Test that generated API key scopes are valid.
    
    Assumptions:
    - At least one scope
    - All scopes are from valid set
    - No duplicate scopes
    """
    assert len(scopes) >= 1
    assert len(scopes) == len(set(scopes))  # No duplicates
    
    valid_scopes = [
        "read", "write:items", "write:presets",
        "write:usage", "write:sets", "admin:users", "admin:backup"
    ]
    for scope in scopes:
        assert scope in valid_scopes


@pytest.mark.unit
@pytest.mark.hypothesis
@given(
    items=st.lists(tool_item_strategy(), min_size=1, max_size=100)
)
def test_bulk_tool_items_structure(items):
    """Test properties of bulk tool item lists.
    
    Assumptions:
    - List contains at least one item
    - All items have required fields
    - Useful for testing bulk operations
    """
    assert len(items) >= 1
    assert len(items) <= 100
    
    for item in items:
        assert "type" in item
        assert "manufacturer" in item
        assert "product_code" in item
