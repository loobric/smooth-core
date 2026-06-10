# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Contract tests for the v2 public facade: Machine and ToolTableEntry.

These tests define the public contract for smooth-core#4 per the locked v2
decisions (UBIQUITOUS_LANGUAGE.md, RESEARCH_BRIEF.md G2/G3/G4, D4):

- Machine is a first-class entity: identity, controller type, and a
  definition JSON that accepts FreeCAD .fcm content (axes, spindle limits).
- ToolTableEntry is one machine's table row: tool number, pocket, offsets,
  description, per-field provenance, and an `extra` JSON for lossless
  client round-trips (plan principle 6).
- Entries may exist UNBOUND (tool_record_id null) — they are the raw
  material the binding engine (#5) works on. Unbound entries are queryable.
- Explicit binding via the API is allowed (client/user intent); only
  *heuristic* binding requires the inbox (#5). Binding to a record the user
  doesn't own is a per-item error.
- (machine, tool_number) is unique; pushing the same tool_number upserts.
- Bound entries surface on the ToolRecord as `machines[]`.

Assumptions:
- POST/PATCH/DELETE /api/v1/machines          - bulk envelope as tool-records
- GET  /api/v1/machines, /api/v1/machines/{id}
- PUT  /api/v1/machines/{id}/tool-table       - bulk upsert by tool_number
- GET  /api/v1/machines/{id}/tool-table?bound=false
- DELETE /api/v1/machines/{id}/tool-table     - by tool_numbers
"""
import pytest


MILL01 = {
    "name": "mill01",
    "controller_type": "linuxcnc",
    "definition": {
        "axes": ["X", "Y", "Z"],
        "spindle": {"min_rpm": 0, "max_rpm": 24000},
        "units": "mm",
    },
}

T3_UNBOUND = {
    "tool_number": 3,
    "pocket": 3,
    "description": "1/4 downcut",
    "offsets": {"z": -50.012, "z_unit": "mm", "diameter": 6.35, "diameter_unit": "mm"},
    "provenance": {"offsets.z": "machine"},
    "extra": {"linuxcnc": {"raw": "T3 P3 D+6.350000 Z-50.012000 ;1/4 downcut"}},
}


def make_machine(client, machine=MILL01):
    resp = client.post("/api/v1/machines", json={"items": [machine]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success_count"] == 1, body
    return body["items"][0]


def put_table(client, machine_id, entries):
    resp = client.put(f"/api/v1/machines/{machine_id}/tool-table", json={"items": entries})
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_record(client, name="1/4\" downcut", tags=None):
    resp = client.post("/api/v1/tool-records", json={"items": [
        {"name": name, "tags": tags or [], "geometry": {"shape": "endmill", "diameter": 6.35}}
    ]})
    return resp.json()["items"][0]


# -- Machine CRUD --------------------------------------------------------------

@pytest.mark.contract
def test_machine_create_and_fetch_with_fcm_definition(solo_client):
    """Machines carry identity, controller type, and .fcm-shaped definition.

    Assumptions:
    - Response: id, name, controller_type, definition, version, timestamps
    - definition JSON round-trips intact (spindle limits reachable)
    """
    machine = make_machine(solo_client)
    assert machine["id"] and machine["version"] == 1
    fetched = solo_client.get(f"/api/v1/machines/{machine['id']}").json()
    assert fetched["name"] == "mill01"
    assert fetched["controller_type"] == "linuxcnc"
    assert fetched["definition"]["spindle"]["max_rpm"] == 24000

    listed = solo_client.get("/api/v1/machines").json()
    assert any(m["id"] == machine["id"] for m in listed["items"])


@pytest.mark.contract
def test_machine_name_required_and_unique_per_user(solo_client):
    """Partial success: missing name and duplicate name are per-item errors."""
    make_machine(solo_client)
    resp = solo_client.post("/api/v1/machines", json={"items": [
        {"controller_type": "grbl"},          # no name
        {"name": "mill01"},                   # duplicate
        {"name": "router01"},                 # fine
    ]})
    body = resp.json()
    assert body["success_count"] == 1
    assert len(body["errors"]) == 2
    assert {e["index"] for e in body["errors"]} == {0, 1}


@pytest.mark.contract
def test_machine_update_with_version_check_and_delete(solo_client):
    """Machines follow the same optimistic-locking bulk envelope."""
    machine = make_machine(solo_client)
    upd = solo_client.patch("/api/v1/machines", json={"items": [
        {"id": machine["id"], "version": 1,
         "definition": {"spindle": {"min_rpm": 0, "max_rpm": 18000}}}
    ]})
    assert upd.json()["success_count"] == 1
    assert upd.json()["items"][0]["version"] == 2

    stale = solo_client.patch("/api/v1/machines", json={"items": [
        {"id": machine["id"], "version": 1, "controller_type": "x"}
    ]})
    assert stale.json()["success_count"] == 0

    deleted = solo_client.request("DELETE", "/api/v1/machines", json={"ids": [machine["id"]]})
    assert deleted.json()["success_count"] == 1
    assert solo_client.get(f"/api/v1/machines/{machine['id']}").status_code == 404


# -- ToolTableEntry: upsert, unbound, uniqueness -------------------------------

@pytest.mark.contract
def test_tool_table_upsert_creates_unbound_entries(solo_client):
    """Pushing a tool table creates entries; without tool_record_id they are
    unbound and queryable as such.

    Assumptions:
    - Entry response: id, machine_id, tool_number, pocket, description,
      offsets, provenance, extra, tool_record_id (null when unbound),
      version, created_at, updated_at
    """
    machine = make_machine(solo_client)
    body = put_table(solo_client, machine["id"], [T3_UNBOUND])
    assert body["success_count"] == 1
    entry = body["items"][0]
    assert entry["machine_id"] == machine["id"]
    assert entry["tool_number"] == 3
    assert entry["tool_record_id"] is None

    unbound = solo_client.get(
        f"/api/v1/machines/{machine['id']}/tool-table", params={"bound": "false"}
    ).json()["items"]
    assert [e["tool_number"] for e in unbound] == [3]


@pytest.mark.contract
def test_tool_table_upsert_updates_existing_tool_number(solo_client):
    """Same (machine, tool_number) upserts in place: id stable, version bumps,
    no duplicate row."""
    machine = make_machine(solo_client)
    first = put_table(solo_client, machine["id"], [T3_UNBOUND])["items"][0]

    changed = dict(T3_UNBOUND)
    changed["offsets"] = {"z": -50.007, "z_unit": "mm"}
    second = put_table(solo_client, machine["id"], [changed])["items"][0]

    assert second["id"] == first["id"]
    assert second["version"] == first["version"] + 1
    assert second["offsets"]["z"] == -50.007

    table = solo_client.get(f"/api/v1/machines/{machine['id']}/tool-table").json()["items"]
    assert len(table) == 1


@pytest.mark.contract
def test_same_tool_number_on_different_machines_is_independent(solo_client):
    """(machine, tool_number) uniqueness is per machine."""
    m1 = make_machine(solo_client)
    m2 = make_machine(solo_client, {"name": "router01", "controller_type": "grbl"})
    put_table(solo_client, m1["id"], [T3_UNBOUND])
    put_table(solo_client, m2["id"], [T3_UNBOUND])
    t1 = solo_client.get(f"/api/v1/machines/{m1['id']}/tool-table").json()["items"]
    t2 = solo_client.get(f"/api/v1/machines/{m2['id']}/tool-table").json()["items"]
    assert len(t1) == 1 and len(t2) == 1
    assert t1[0]["id"] != t2[0]["id"]


@pytest.mark.contract
def test_provenance_and_extra_round_trip(solo_client):
    """Per-field provenance and the extra JSON survive write/read unchanged
    (lossless round-trip, plan principle 6)."""
    machine = make_machine(solo_client)
    entry = put_table(solo_client, machine["id"], [T3_UNBOUND])["items"][0]
    assert entry["provenance"] == {"offsets.z": "machine"}
    assert entry["extra"]["linuxcnc"]["raw"].startswith("T3 P3")


@pytest.mark.contract
def test_tool_table_delete_by_tool_numbers(solo_client):
    """Entries are removable per machine by tool number."""
    machine = make_machine(solo_client)
    put_table(solo_client, machine["id"], [T3_UNBOUND, {**T3_UNBOUND, "tool_number": 4}])
    resp = solo_client.request(
        "DELETE", f"/api/v1/machines/{machine['id']}/tool-table",
        json={"tool_numbers": [3]},
    )
    assert resp.json()["success_count"] == 1
    remaining = solo_client.get(f"/api/v1/machines/{machine['id']}/tool-table").json()["items"]
    assert [e["tool_number"] for e in remaining] == [4]


@pytest.mark.contract
def test_tool_table_unknown_machine_404(solo_client):
    """Tool-table routes 404 for machines that don't exist."""
    resp = solo_client.get("/api/v1/machines/no-such-machine/tool-table")
    assert resp.status_code == 404


# -- Explicit binding + ToolRecord.machines[] ----------------------------------

@pytest.mark.contract
def test_explicit_binding_surfaces_on_tool_record(solo_client):
    """An entry pushed with tool_record_id is bound (explicit user intent —
    distinct from heuristic proposals, which are #5's inbox territory), and
    the bound entry appears nested on the ToolRecord as machines[]."""
    machine = make_machine(solo_client)
    record = make_record(solo_client)

    bound = dict(T3_UNBOUND)
    bound["tool_record_id"] = record["id"]
    entry = put_table(solo_client, machine["id"], [bound])["items"][0]
    assert entry["tool_record_id"] == record["id"]

    fetched = solo_client.get(f"/api/v1/tool-records/{record['id']}").json()
    assert "machines" in fetched
    assert len(fetched["machines"]) == 1
    assert fetched["machines"][0]["machine_id"] == machine["id"]
    assert fetched["machines"][0]["tool_number"] == 3


@pytest.mark.contract
def test_binding_to_unknown_record_is_per_item_error(solo_client):
    """Binding to a nonexistent ToolRecord fails that item only."""
    machine = make_machine(solo_client)
    bad = dict(T3_UNBOUND)
    bad["tool_record_id"] = "no-such-record"
    good = {**T3_UNBOUND, "tool_number": 5}
    body = put_table(solo_client, machine["id"], [bad, good])
    assert body["success_count"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["index"] == 0


@pytest.mark.contract
def test_deleting_record_cascades_proposals_and_unbinds_entries(solo_client):
    """Deleting a ToolRecord must not leave dangling references (production
    bug: Postgres FK on binding_proposals.proposed_record_id 500'd the bulk
    delete; SQLite doesn't enforce FKs so only behavior can be tested here).

    Assumptions:
    - Proposals referencing the record (any status) are deleted with it
    - Entries bound to it are unbound (tool_record_id -> null), not orphaned
    - The delete succeeds as a normal per-item success
    """
    machine = make_machine(solo_client)
    record = make_record(solo_client)

    # one entry bound explicitly, one unbound entry with an open proposal
    bound = {**T3_UNBOUND, "tool_record_id": record["id"]}
    similar = {**T3_UNBOUND, "tool_number": 5, "description": '1/4" downcut'}
    put_table(solo_client, machine["id"], [bound, similar])
    assert len(solo_client.get("/api/v1/inbox").json()["items"]) == 1

    resp = solo_client.request("DELETE", "/api/v1/tool-records",
                               json={"ids": [record["id"]]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["success_count"] == 1

    entries = solo_client.get(
        f"/api/v1/machines/{machine['id']}/tool-table"
    ).json()["items"]
    assert all(e["tool_record_id"] is None for e in entries)
    assert solo_client.get("/api/v1/inbox").json()["items"] == []
