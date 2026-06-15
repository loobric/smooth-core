# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Contract tests for the sectioned ToolCatalogRecord facade.

Mirrors the ToolInstanceRecord tracer: responses are the three-section shape and
validate against smooth.contract; a client writes only its own section; routine
sync cannot touch internal/canonical. The one difference: a catalog TYPE carries
nominal, asserted data — there is no observe door, because a machine never
measures a type. See docs/TOOL_SCHEMA.md §7.1.
"""
import pytest

from smooth.contract import ToolCatalogRecord, UNKNOWN

BASE = "/api/v1/tool-catalog-records"


def conforms(doc):
    """The server's own output validates against the published contract."""
    ToolCatalogRecord.model_validate(doc)
    return doc


@pytest.mark.contract
def test_create_returns_a_conformant_all_unknown_record(solo_client):
    """A freshly minted catalog type asserts nothing — its name is honestly
    unknown, never a fabricated default."""
    r = solo_client.post(BASE, json={})
    assert r.status_code == 200, r.text
    doc = conforms(r.json())
    assert doc["internal"]["version"] == 1 and doc["internal"]["id"]
    assert doc["canonical"]["name"]["source"] == UNKNOWN
    assert doc["canonical"]["name"]["value"] is None
    assert doc["clients"] == {}


@pytest.mark.contract
def test_create_can_seed_an_initial_client_section(solo_client):
    r = solo_client.post(BASE, json={"client": "catalog-import", "client_version": "1.2.0",
                                     "client_item_id": "harvey-12345",
                                     "data": {"raw": {"page": 42}}})
    doc = conforms(r.json())
    sec = doc["clients"]["catalog-import"]
    assert sec["client_version"] == "1.2.0" and sec["client_item_id"] == "harvey-12345"
    assert sec["created_at"] and sec["updated_at"]          # server-stamped
    assert "client" not in sec                               # identity is the map key
    assert sec["data"]["raw"]["page"] == 42


@pytest.mark.contract
def test_sync_writes_only_the_client_section(solo_client):
    rid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    r = solo_client.put(f"{BASE}/{rid}/clients/catalog-import",
                        json={"client_version": "1.2.0", "client_item_id": "harvey-12345",
                              "data": {"any": [1, 2]}})
    assert r.status_code == 200, r.text
    doc = conforms(r.json())
    assert doc["clients"]["catalog-import"]["data"] == {"any": [1, 2]}
    assert doc["internal"]["version"] == 2                   # bumped


@pytest.mark.contract
@pytest.mark.parametrize("forbidden", ["internal", "canonical", "client"])
def test_sync_cannot_touch_internal_or_canonical(solo_client, forbidden):
    """The load-bearing safety property, enforced at the API: a sync write that
    reaches for internal/canonical (or re-sends the redundant `client` key) is a
    loud 400, not a silent strip."""
    rid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    body = {"client_version": "1.2.0", "data": {}}
    body[forbidden] = "x" if forbidden == "client" else {"name": "endmill"}
    r = solo_client.put(f"{BASE}/{rid}/clients/catalog-import", json=body)
    assert r.status_code == 400, r.text


@pytest.mark.contract
def test_assert_sets_nominal_fields_with_asserted_provenance(solo_client):
    """A catalog type's identity and nominal spec are deliberate assertions —
    there is no observe door, because a machine never measures a type."""
    rid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    solo_client.post(f"{BASE}/{rid}/assert",
                     json={"path": "name", "value": "1/4in 2FL Endmill",
                           "actor": "catalog-import"})
    solo_client.post(f"{BASE}/{rid}/assert",
                     json={"path": "manufacturer", "value": "Harvey Tool",
                           "actor": "catalog-import"})
    doc = conforms(solo_client.get(f"{BASE}/{rid}").json())     # round-trips via GET
    name = doc["canonical"]["name"]
    assert name["value"] == "1/4in 2FL Endmill" and name["source"] == "asserted:catalog-import"
    mfr = doc["canonical"]["manufacturer"]
    assert mfr["value"] == "Harvey Tool" and mfr["source"] == "asserted:catalog-import"
