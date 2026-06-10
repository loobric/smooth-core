# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Contract tests for the v2 public facade: ToolRecord.

These tests define the PUBLIC API contract for smooth-core#3 (facade skeleton).
They are written before the implementation (TDD) and encode the locked v2
decisions (RESEARCH_BRIEF.md G3/D2, UBIQUITOUS_LANGUAGE.md):

- The facade is the ONLY public API. Deep entities (ToolItem, ToolAssembly,
  ToolInstance) never appear in any public response or in the OpenAPI schema.
- ToolRecord is the user's mental object: name + geometry + tags
  (+ machines[] ToolTableEntries, which arrive with smooth-core#4).
- Bulk-first with partial-success semantics, matching the v1 PoC pattern.
- ToolRecord public IDs are stable for the life of the record.
- Optimistic locking via integer `version`.
- Solo mode (SMOOTH_SOLO=1): no registration ceremony; unauthenticated
  requests act as the built-in solo user.
- Every write is audited and visible to change detection.

Assumptions:
- POST   /api/v1/tool-records        - bulk create (array in, per-item results out)
- GET    /api/v1/tool-records        - list with tag filter + pagination
- GET    /api/v1/tool-records/{id}   - fetch one
- PATCH  /api/v1/tool-records        - bulk update with version checking
- DELETE /api/v1/tool-records        - bulk delete by id
- GET    /api/v1/changes/tool-records/since-version - change detection
- GET    /openapi.json               - documents facade resources ONLY
"""
import pytest


# -- helpers -----------------------------------------------------------------

QUARTER_INCH_DOWNCUT = {
    "name": '1/4" downcut endmill',
    "description": "Amana 46202-K spektra",
    "tags": ["router", "wood"],
    "geometry": {
        "shape": "endmill",
        "diameter": 6.35,
        "diameter_unit": "mm",
        "flutes": 2,
        "cutting_length": 19.0,
        "cutting_length_unit": "mm",
    },
}

FIVE_MM_DRILL = {
    "name": "5mm drill HSS",
    "tags": ["mill01"],
    "geometry": {"shape": "drill", "diameter": 5.0, "diameter_unit": "mm"},
}

DEEP_ENTITY_KEYS = {
    "tool_item_id", "tool_assembly_id", "tool_instance_id",
    "assembly_id", "instance_id", "item_id", "holder_id", "cutter_id",
}


def create_records(client, records, **kw):
    """POST a bulk create and return the parsed response."""
    resp = client.post("/api/v1/tool-records", json={"items": records}, **kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


# -- CRUD + bulk semantics ---------------------------------------------------

@pytest.mark.contract
def test_bulk_create_returns_per_item_results(solo_client):
    """Bulk create accepts an array and returns per-item results with ids.

    Assumptions:
    - Response: {"success_count": int, "errors": [...], "items": [...]}
    - Each created item carries: id (UUID string), version=1, created_at,
      updated_at, and echoes name/tags/geometry.
    """
    body = create_records(solo_client, [QUARTER_INCH_DOWNCUT, FIVE_MM_DRILL])
    assert body["success_count"] == 2
    assert body["errors"] == []
    items = body["items"]
    assert len(items) == 2
    for item in items:
        assert item["id"]
        assert item["version"] == 1
        assert item["created_at"] and item["updated_at"]
    assert items[0]["geometry"]["diameter"] == 6.35
    assert items[0]["tags"] == ["router", "wood"]


@pytest.mark.contract
def test_get_single_and_list_with_tag_filter(solo_client):
    """Records are fetchable by id and listable with tag filtering.

    Assumptions:
    - GET /api/v1/tool-records/{id} returns the record
    - GET /api/v1/tool-records?tag=router returns only matching records
    - GET /api/v1/tool-records supports limit/offset pagination
    """
    created = create_records(solo_client, [QUARTER_INCH_DOWNCUT, FIVE_MM_DRILL])["items"]

    one = solo_client.get(f"/api/v1/tool-records/{created[0]['id']}")
    assert one.status_code == 200
    assert one.json()["name"] == QUARTER_INCH_DOWNCUT["name"]

    listed = solo_client.get("/api/v1/tool-records", params={"tag": "router"})
    assert listed.status_code == 200
    names = [r["name"] for r in listed.json()["items"]]
    assert QUARTER_INCH_DOWNCUT["name"] in names
    assert FIVE_MM_DRILL["name"] not in names

    paged = solo_client.get("/api/v1/tool-records", params={"limit": 1, "offset": 0})
    assert len(paged.json()["items"]) == 1


@pytest.mark.contract
def test_bulk_update_with_version_check(solo_client):
    """Updates require the current version; stale versions fail per-item.

    Assumptions:
    - PATCH body: {"items": [{"id": ..., "version": ..., <changed fields>}]}
    - Successful update increments version
    - Stale version yields a per-item error, not a request-level failure
    """
    rec = create_records(solo_client, [QUARTER_INCH_DOWNCUT])["items"][0]

    ok = solo_client.patch("/api/v1/tool-records", json={"items": [
        {"id": rec["id"], "version": 1, "description": "resharpened"}
    ]})
    assert ok.status_code == 200
    assert ok.json()["success_count"] == 1
    assert ok.json()["items"][0]["version"] == 2

    stale = solo_client.patch("/api/v1/tool-records", json={"items": [
        {"id": rec["id"], "version": 1, "description": "should fail"}
    ]})
    assert stale.status_code == 200  # bulk envelope succeeds
    body = stale.json()
    assert body["success_count"] == 0
    assert len(body["errors"]) == 1
    assert body["errors"][0]["id"] == rec["id"]


@pytest.mark.contract
def test_partial_success_in_bulk_create(solo_client):
    """A bad item does not poison the batch.

    Assumptions:
    - Items missing required fields (name) error per-item
    - Valid items in the same request still commit
    """
    body = create_records(solo_client, [FIVE_MM_DRILL, {"tags": ["no-name"]}])
    assert body["success_count"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["index"] == 1


@pytest.mark.contract
def test_bulk_delete(solo_client):
    """Bulk delete removes records; fetching them afterwards is a 404."""
    rec = create_records(solo_client, [FIVE_MM_DRILL])["items"][0]
    resp = solo_client.request(
        "DELETE", "/api/v1/tool-records", json={"ids": [rec["id"]]}
    )
    assert resp.status_code == 200
    assert resp.json()["success_count"] == 1
    assert solo_client.get(f"/api/v1/tool-records/{rec['id']}").status_code == 404


# -- facade opacity (G3) -----------------------------------------------------

@pytest.mark.contract
def test_responses_never_leak_deep_entities(solo_client):
    """No public response exposes deep-schema keys or ids.

    The deep model (ToolItem/Assembly/Instance) is private substrate; its
    existence must be invisible at the API boundary.
    """
    rec = create_records(solo_client, [QUARTER_INCH_DOWNCUT])["items"][0]
    leaked = DEEP_ENTITY_KEYS & set(rec.keys())
    assert not leaked, f"deep entity keys leaked into facade response: {leaked}"

    fetched = solo_client.get(f"/api/v1/tool-records/{rec['id']}").json()
    assert not (DEEP_ENTITY_KEYS & set(fetched.keys()))


@pytest.mark.contract
def test_openapi_documents_facade_only(solo_client):
    """The OpenAPI schema is the published contract: facade paths only.

    Assumptions:
    - The schema is served at /api/v1/openapi.json (existing app config)
    - /api/v1/tool-records present
    - No /api/v1/tool-items, tool-assemblies, tool-instances, or tool-presets
      paths appear in the schema (they are private or removed)
    """
    paths = solo_client.get("/api/v1/openapi.json").json()["paths"]
    assert any(p.startswith("/api/v1/tool-records") for p in paths)
    forbidden = ("tool-items", "tool-assemblies", "tool-instances", "tool-presets")
    exposed = [p for p in paths if any(f in p for f in forbidden)]
    assert not exposed, f"deep-entity routes still public: {exposed}"


@pytest.mark.contract
def test_facade_id_is_stable_across_updates(solo_client):
    """A ToolRecord's public id never changes, regardless of internal
    materialization of deep entities behind it."""
    rec = create_records(solo_client, [QUARTER_INCH_DOWNCUT])["items"][0]
    for n in range(1, 4):
        upd = solo_client.patch("/api/v1/tool-records", json={"items": [
            {"id": rec["id"], "version": n, "description": f"edit {n}"}
        ]})
        assert upd.json()["items"][0]["id"] == rec["id"]


# -- solo mode (G1/D1) -------------------------------------------------------

@pytest.mark.contract
def test_solo_mode_requires_no_registration(solo_client):
    """In solo mode, unauthenticated requests act as the built-in solo user.

    Assumptions:
    - SMOOTH_SOLO=1 boots with a default identity; no register/login/API-key
      ceremony before first use
    - Writes are attributed to the solo user in responses/audit
    """
    body = create_records(solo_client, [FIVE_MM_DRILL])
    assert body["success_count"] == 1


@pytest.mark.contract
def test_multi_tenant_mode_still_requires_auth(client):
    """Outside solo mode the API requires credentials (unchanged from v1).

    Assumptions:
    - Default client fixture has auth ENABLED and no credentials
    - Unauthenticated facade access is 401
    """
    resp = client.get("/api/v1/tool-records")
    assert resp.status_code == 401


# -- audit + change detection ------------------------------------------------

@pytest.mark.contract
def test_writes_are_audited(solo_client):
    """Every facade write produces an audit log entry.

    Assumptions:
    - GET /api/v1/audit-logs returns {"logs": [...]} (existing envelope),
      entries carrying entity_type and operation
    - Facade writes audit as entity_type 'tool_record'
    """
    create_records(solo_client, [FIVE_MM_DRILL])
    entries = solo_client.get("/api/v1/audit-logs").json()["logs"]
    assert any(
        e["entity_type"] == "tool_record" and e["operation"] == "CREATE"
        for e in entries
    )


@pytest.mark.contract
def test_change_detection_sees_facade_writes(solo_client):
    """Clients can sync deltas: new/updated ToolRecords appear in /changes.

    Assumptions:
    - GET /api/v1/changes/tool-records/since-version?since_version=0
      returns records created after that version horizon
    """
    rec = create_records(solo_client, [QUARTER_INCH_DOWNCUT])["items"][0]
    changes = solo_client.get(
        "/api/v1/changes/tool-records/since-version", params={"since_version": 0}
    )
    assert changes.status_code == 200
    ids = [c["id"] for c in changes.json()["items"]]
    assert rec["id"] in ids


@pytest.mark.contract
def test_extra_passthrough_round_trips(solo_client):
    """ToolRecord.extra is opaque client passthrough (plan principle 6).

    The FreeCAD client stores the full .fctb document here — including the
    additive 'presets' key from FreeCAD's F&S work — so a correct round
    trip syncs data the server doesn't model yet. The server must never
    interpret or normalize it.
    """
    doc = {"freecad": {"fctb": {
        "id": "end_mill_6.0mm_2f", "shape": "endmill.fcstd",
        "parameter": {"Diameter": "6.00 mm", "SpindleDirection": "Forward"},
        "presets": [{"name": "alu", "surface_speed": 400}],
        "attribute": {},
    }}}
    created = create_records(solo_client, [
        {**QUARTER_INCH_DOWNCUT, "extra": doc}
    ])["items"][0]
    assert created["extra"] == doc

    fetched = solo_client.get(f"/api/v1/tool-records/{created['id']}").json()
    assert fetched["extra"]["freecad"]["fctb"]["presets"][0]["surface_speed"] == 400

    upd = solo_client.patch("/api/v1/tool-records", json={"items": [
        {"id": created["id"], "version": 1,
         "extra": {"freecad": {"fctb": {"id": "renamed"}}}}
    ]})
    assert upd.json()["items"][0]["extra"]["freecad"]["fctb"]["id"] == "renamed"
