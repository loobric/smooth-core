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

Create is **seeded and atomic** (M2, issue #24): one declared actor plus the
nominal {value, unit} fields, and the server stamps `asserted:<actor>` on each
(the client never writes provenance). Identity floor: name/manufacturer/
product_code are required; spec fields stay honest-sparse.
"""
import pytest

from smooth.contract import ToolCatalogRecord
from smooth.database.schema import AuditLog
from smooth.database.schema import ToolCatalogRecord as Row

BASE = "/api/v1/tool-catalog-records"


def conforms(doc):
    """The server's own output validates against the published contract."""
    ToolCatalogRecord.model_validate(doc)
    return doc


def seed(solo_client, actor="manufacturer:kennametal", **overrides):
    """POST a valid identity-floored create and return the conformant record."""
    body = {
        "actor": actor,
        "name": {"value": "1/4in 2FL Endmill"},
        "manufacturer": {"value": "Kennametal"},
        "product_code": {"value": "B201"},
    }
    body.update(overrides)
    r = solo_client.post(BASE, json=body)
    assert r.status_code == 200, r.text
    return conforms(r.json())


@pytest.mark.contract
def test_seeded_create_stamps_asserted_provenance_on_every_field(solo_client):
    """The acceptance tracer: one declared actor seeds every field, and the
    server — not the client — stamps asserted:<actor> as its source."""
    doc = seed(solo_client, actor="manufacturer:kennametal",
               geometry={"diameter": {"value": 6.35, "unit": "mm"},
                         "flutes": {"value": 2}})
    assert doc["internal"]["version"] == 1 and doc["internal"]["id"]
    src = "asserted:manufacturer:kennametal"
    for path in (("name",), ("manufacturer",), ("product_code",),
                 ("geometry", "diameter"), ("geometry", "flutes")):
        leaf = doc["canonical"]
        for p in path:
            leaf = leaf[p]
        assert leaf["source"] == src, path
    assert doc["canonical"]["geometry"]["diameter"]["value"] == 6.35
    assert doc["canonical"]["geometry"]["diameter"]["unit"] == "mm"


@pytest.mark.contract
@pytest.mark.parametrize("missing", ["name", "manufacturer", "product_code"])
def test_create_requires_the_identity_floor(solo_client, missing):
    """Missing any of name/manufacturer/product_code is rejected — findability,
    not spec completeness."""
    body = {
        "actor": "human@cli",
        "name": {"value": "x"},
        "manufacturer": {"value": "Acme"},
        "product_code": {"value": "P1"},
    }
    del body[missing]
    r = solo_client.post(BASE, json=body)
    assert r.status_code == 400, r.text
    assert missing in r.text


@pytest.mark.contract
def test_identity_floor_rejects_a_null_value(solo_client):
    """A present-but-null identity field is as missing as an absent one."""
    r = solo_client.post(BASE, json={
        "actor": "human@cli", "name": {"value": None},
        "manufacturer": {"value": "Acme"}, "product_code": {"value": "P1"}})
    assert r.status_code == 400, r.text


@pytest.mark.contract
def test_create_accepts_sparse_spec(solo_client):
    """A record with no geometry is honest, not invalid — never fabricate fields
    to pass a gate."""
    doc = seed(solo_client)
    assert doc["canonical"]["geometry"] == {}


@pytest.mark.contract
def test_client_cannot_supply_source(solo_client):
    """Lane discipline: a field that smuggles in its own `source` is rejected —
    provenance is the server's to stamp, never the client's to write."""
    r = solo_client.post(BASE, json={
        "actor": "human@cli",
        "name": {"value": "x", "source": "asserted:somebody-else"},
        "manufacturer": {"value": "Acme"}, "product_code": {"value": "P1"}})
    assert r.status_code == 422, r.text


@pytest.mark.contract
def test_create_is_atomic_and_writes_one_audit_row(solo_client, db_session):
    """All-or-nothing: a malformed seed leaves no half-built record and no audit
    row; a success writes exactly one CREATE row."""
    def created_rows():
        return db_session.query(AuditLog).filter_by(
            entity_type="tool_catalog_record", operation="CREATE").count()
    before = created_rows()

    # Malformed: past pydantic + the identity floor, but an invalid item_type
    # fails canonical validation — rejected before any DB write.
    bad = solo_client.post(BASE, json={
        "actor": "human@cli", "name": {"value": "x"},
        "manufacturer": {"value": "Acme"}, "product_code": {"value": "P1"},
        "item_type": {"value": "not-a-real-type"}})
    assert bad.status_code == 400, bad.text
    assert db_session.query(Row).count() == 0      # no half-built record
    assert created_rows() == before                # no audit row

    seed(solo_client)
    assert created_rows() == before + 1            # exactly one


@pytest.mark.contract
def test_create_can_seed_an_initial_client_section(solo_client):
    doc = seed(solo_client, client="catalog-import", client_version="1.2.0",
               client_item_id="harvey-12345", client_data={"raw": {"page": 42}})
    sec = doc["clients"]["catalog-import"]
    assert sec["client_version"] == "1.2.0" and sec["client_item_id"] == "harvey-12345"
    assert sec["created_at"] and sec["updated_at"]          # server-stamped
    assert "client" not in sec                               # identity is the map key
    assert sec["data"]["raw"]["page"] == 42


@pytest.mark.contract
def test_sync_writes_only_the_client_section(solo_client):
    rid = seed(solo_client)["internal"]["id"]
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
    rid = seed(solo_client)["internal"]["id"]
    body = {"client_version": "1.2.0", "data": {}}
    body[forbidden] = "x" if forbidden == "client" else {"name": "endmill"}
    r = solo_client.put(f"{BASE}/{rid}/clients/catalog-import", json=body)
    assert r.status_code == 400, r.text


@pytest.mark.contract
def test_assert_sets_nominal_fields_with_asserted_provenance(solo_client):
    """A catalog type's nominal spec is a deliberate assertion — there is no
    observe door, because a machine never measures a type. The assert door edits
    a seeded record (here, declaring a published diameter)."""
    rid = seed(solo_client)["internal"]["id"]
    solo_client.post(f"{BASE}/{rid}/assert",
                     json={"path": "geometry.diameter", "value": 6.35, "unit": "mm",
                           "actor": "catalog-import"})
    doc = conforms(solo_client.get(f"{BASE}/{rid}").json())     # round-trips via GET
    dia = doc["canonical"]["geometry"]["diameter"]
    assert dia["value"] == 6.35 and dia["source"] == "asserted:catalog-import"
