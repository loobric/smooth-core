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


@pytest.mark.contract
def test_unbind_entry(solo_client):
    """Field feedback: a wrong confirm needs an undo. Unbind clears the
    link (audited), leaves entry data untouched, and the entry becomes
    eligible for proposals again.

    Assumptions:
    - POST /api/v1/machines/{id}/tool-table/{tool_number}/unbind
    - 409 when the entry isn't bound; 404 for unknown machine/tool number
    """
    machine = make_machine(solo_client)
    record = make_record(solo_client)
    put_table(solo_client, machine["id"], [{**T3_UNBOUND, "tool_record_id": record["id"]}])

    resp = solo_client.post(f"/api/v1/machines/{machine['id']}/tool-table/3/unbind")
    assert resp.status_code == 200, resp.text
    entry = resp.json()
    assert entry["tool_record_id"] is None
    assert entry["offsets"]["z"] == T3_UNBOUND["offsets"]["z"]  # data untouched

    assert solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/3/unbind"
    ).status_code == 409
    assert solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/99/unbind"
    ).status_code == 404

    logs = solo_client.get("/api/v1/audit-logs").json()["logs"]
    assert any(e["operation"] == "UNBIND" for e in logs)


# -- Explicit bind from the UI (smooth-core#14) --------------------------------

@pytest.mark.contract
def test_bind_unbound_entry_to_record(solo_client):
    """The UI-facing explicit bind: link an unbound entry to a record the
    user owns. Symmetric sibling of /unbind.

    Assumptions:
    - POST /api/v1/machines/{id}/tool-table/{tool_number}/bind {tool_record_id}
    - Entry data untouched; only the link is set; version increments; audited
    - Binding to the record an open proposal suggested closes it as confirmed
    """
    machine = make_machine(solo_client)
    record = make_record(solo_client)
    # unbound push whose diameter+name match the record -> open proposal
    put_table(solo_client, machine["id"], [T3_UNBOUND])
    assert len(solo_client.get("/api/v1/inbox").json()["items"]) == 1

    resp = solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/3/bind",
        json={"tool_record_id": record["id"]},
    )
    assert resp.status_code == 200, resp.text
    entry = resp.json()
    assert entry["tool_record_id"] == record["id"]
    assert entry["offsets"]["z"] == T3_UNBOUND["offsets"]["z"]  # data untouched

    # bound entry surfaces on the record; the open proposal is resolved
    assert solo_client.get("/api/v1/inbox").json()["items"] == []
    fetched = solo_client.get(f"/api/v1/tool-records/{record['id']}").json()
    assert fetched["machines"][0]["tool_number"] == 3

    logs = solo_client.get("/api/v1/audit-logs").json()["logs"]
    assert any(e["operation"] == "BIND" for e in logs)


@pytest.mark.contract
def test_bind_to_different_record_rejects_open_proposal(solo_client):
    """Binding to a record other than the one proposed is an implicit reject
    of that suggestion: the open proposal is closed and won't reappear."""
    machine = make_machine(solo_client)
    proposed = make_record(solo_client, name='1/4" downcut')   # the heuristic match
    other = make_record(solo_client, name="some other tool")
    put_table(solo_client, machine["id"], [T3_UNBOUND])
    assert len(solo_client.get("/api/v1/inbox").json()["items"]) == 1

    resp = solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/3/bind",
        json={"tool_record_id": other["id"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tool_record_id"] == other["id"]
    # the suggestion for `proposed` is gone and not re-proposed on re-sync
    assert solo_client.get("/api/v1/inbox").json()["items"] == []
    put_table(solo_client, machine["id"], [T3_UNBOUND])
    assert solo_client.get("/api/v1/inbox").json()["items"] == []


@pytest.mark.contract
def test_bind_error_cases(solo_client):
    """409 when already bound; 404 for unknown machine/tool number/record."""
    machine = make_machine(solo_client)
    record = make_record(solo_client)
    put_table(solo_client, machine["id"], [T3_UNBOUND])

    ok = solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/3/bind",
        json={"tool_record_id": record["id"]},
    )
    assert ok.status_code == 200
    # already bound
    assert solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/3/bind",
        json={"tool_record_id": record["id"]},
    ).status_code == 409
    # unknown tool number
    assert solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/99/bind",
        json={"tool_record_id": record["id"]},
    ).status_code == 404
    # unknown machine
    assert solo_client.post(
        f"/api/v1/machines/no-such-machine/tool-table/3/bind",
        json={"tool_record_id": record["id"]},
    ).status_code == 404
    # unknown record (unbind first so the entry is bindable)
    solo_client.post(f"/api/v1/machines/{machine['id']}/tool-table/3/unbind")
    assert solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/3/bind",
        json={"tool_record_id": "no-such-record"},
    ).status_code == 404


# -- Create a record from an entry (smooth-core#15) ----------------------------

@pytest.mark.contract
def test_create_record_from_entry_closes_the_dead_end(solo_client):
    """A never-before-seen tool synced from a controller has no matching
    record and so no proposal; this promotes the entry into a ToolRecord and
    binds it in one step, so the unbound row is never a dead-end.

    Assumptions:
    - POST /api/v1/machines/{id}/tool-table/{tool_number}/create-record
    - The new record is owned by the caller and visible on the Tools tab
    - The entry becomes bound to it; CREATE (tool_record) + BIND are audited
    """
    machine = make_machine(solo_client)
    novel = {
        "tool_number": 7,
        "description": "7mm spot drill",
        "offsets": {"diameter": 7.0, "diameter_unit": "mm", "z": -41.0},
        "extra": {"linuxcnc": {"raw": "T7 ..."}},
    }
    put_table(solo_client, machine["id"], [novel])
    # nothing to match -> no proposal, the dead-end this endpoint fixes
    assert solo_client.get("/api/v1/inbox").json()["items"] == []
    before = len(solo_client.get("/api/v1/tool-records").json()["items"])

    resp = solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/7/create-record"
    )
    assert resp.status_code == 200, resp.text
    entry = resp.json()
    assert entry["tool_record_id"] is not None

    records = solo_client.get("/api/v1/tool-records").json()["items"]
    assert len(records) == before + 1
    new_record = next(r for r in records if r["id"] == entry["tool_record_id"])
    assert new_record["name"] == "7mm spot drill"
    assert new_record["geometry"]["diameter"] == 7.0      # diameter mapped through
    assert new_record["machines"][0]["tool_number"] == 7  # bound round-trips

    logs = solo_client.get("/api/v1/audit-logs").json()["logs"]
    ops = {(e["operation"], e["entity_type"]) for e in logs}
    assert ("CREATE", "tool_record") in ops
    assert ("BIND", "tool_table_entry") in ops


@pytest.mark.contract
def test_create_record_with_custom_name(solo_client):
    """The user may name the record instead of inheriting the description."""
    machine = make_machine(solo_client)
    put_table(solo_client, machine["id"], [{**T3_UNBOUND, "tool_number": 8}])
    resp = solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/8/create-record",
        json={"name": "Chamfer 90deg"},
    )
    assert resp.status_code == 200, resp.text
    rec_id = resp.json()["tool_record_id"]
    record = solo_client.get(f"/api/v1/tool-records/{rec_id}").json()
    assert record["name"] == "Chamfer 90deg"


@pytest.mark.contract
def test_create_record_error_cases(solo_client):
    """409 if the entry is already bound; 404 unknown machine/tool number."""
    machine = make_machine(solo_client)
    put_table(solo_client, machine["id"], [{**T3_UNBOUND, "tool_number": 9}])
    first = solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/9/create-record"
    )
    assert first.status_code == 200
    # entry now bound -> can't create another record from it
    assert solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/9/create-record"
    ).status_code == 409
    assert solo_client.post(
        f"/api/v1/machines/{machine['id']}/tool-table/99/create-record"
    ).status_code == 404
    assert solo_client.post(
        f"/api/v1/machines/no-such-machine/tool-table/9/create-record"
    ).status_code == 404


# -- Snapshot reconciliation (the operator deleted a tool locally) -------------
#
# A full-table push is an OBSERVATION: the controller is authoritative over
# what its table contains. mode="snapshot" declares "these items are my
# complete table", so an entry the operator deleted from tool.tbl must be
# reconciled away on the next sync — never left as a phantom. The tool's
# RECORD identity survives; only the machine's observation of the slot dies.


def put_snapshot(client, machine_id, entries, force=False):
    resp = client.put(
        f"/api/v1/machines/{machine_id}/tool-table",
        json={"items": entries, "mode": "snapshot", "force": force},
    )
    return resp


@pytest.mark.contract
def test_merge_mode_is_the_default_and_never_deletes(solo_client):
    """The default push touches only the tool_numbers it carries — a partial
    caller must never lose unmentioned entries."""
    machine = make_machine(solo_client)
    put_table(solo_client, machine["id"], [
        {**T3_UNBOUND, "tool_number": 1},
        {**T3_UNBOUND, "tool_number": 2},
    ])
    # A merge push of only T1 leaves T2 untouched.
    body = put_table(solo_client, machine["id"], [{**T3_UNBOUND, "tool_number": 1}])
    assert body.get("removed_tool_numbers", []) == []
    nums = {e["tool_number"] for e in
            solo_client.get(f"/api/v1/machines/{machine['id']}/tool-table").json()["items"]}
    assert nums == {1, 2}


@pytest.mark.contract
def test_snapshot_reconciles_away_a_locally_deleted_tool(solo_client):
    """18 reported, operator deletes one, client re-pushes the remaining 17 as
    a snapshot: the missing entry is removed; the rest are intact."""
    machine = make_machine(solo_client)
    full = [{**T3_UNBOUND, "tool_number": n} for n in range(1, 19)]
    put_snapshot(solo_client, machine["id"], full)
    assert len(solo_client.get(
        f"/api/v1/machines/{machine['id']}/tool-table").json()["items"]) == 18

    remaining = [e for e in full if e["tool_number"] != 7]  # operator deleted T7
    resp = put_snapshot(solo_client, machine["id"], remaining)
    assert resp.status_code == 200, resp.text
    assert resp.json()["removed_tool_numbers"] == [7]
    nums = {e["tool_number"] for e in
            solo_client.get(f"/api/v1/machines/{machine['id']}/tool-table").json()["items"]}
    assert 7 not in nums and len(nums) == 17


@pytest.mark.contract
def test_snapshot_removal_keeps_the_bound_record_alive(solo_client):
    """Deleting a slot is not scrapping the tool: a bound entry's ToolRecord
    survives the reconciliation; only the entry (the observation) is gone."""
    machine = make_machine(solo_client)
    record = make_record(solo_client)
    put_snapshot(solo_client, machine["id"], [
        {**T3_UNBOUND, "tool_number": 1},
        {**T3_UNBOUND, "tool_number": 2, "tool_record_id": record["id"]},
    ])
    # Snapshot now omits T2 (its bound slot was deleted locally).
    resp = put_snapshot(solo_client, machine["id"], [{**T3_UNBOUND, "tool_number": 1}])
    assert resp.json()["removed_tool_numbers"] == [2]
    # The record still exists and simply lost its machine location.
    rec = solo_client.get(f"/api/v1/tool-records/{record['id']}")
    assert rec.status_code == 200
    assert all(m["tool_number"] != 2 for m in rec.json().get("machines", []))


@pytest.mark.contract
def test_snapshot_withdraws_open_proposal_for_removed_entry(solo_client):
    """An unbound entry pending in the inbox that vanishes from the snapshot
    is no longer a question to answer — its proposal is withdrawn."""
    machine = make_machine(solo_client)
    make_record(solo_client)  # gives the binding engine a match to propose
    put_snapshot(solo_client, machine["id"], [
        {**T3_UNBOUND, "tool_number": 1},
        {**T3_UNBOUND, "tool_number": 2},
    ])
    assert len(solo_client.get("/api/v1/inbox").json()["items"]) >= 1
    # Drop every reported tool except T1; the inbox question for T2 is moot.
    put_snapshot(solo_client, machine["id"], [{**T3_UNBOUND, "tool_number": 1}])
    open_entries = {i["entry"]["tool_number"]
                    for i in solo_client.get("/api/v1/inbox").json()["items"]}
    assert 2 not in open_entries


@pytest.mark.contract
def test_snapshot_refuses_mass_wipe_without_force(solo_client):
    """A snapshot that would remove more than half the table — or an empty one
    — is treated as a likely partial read and refused with 409."""
    machine = make_machine(solo_client)
    put_snapshot(solo_client, machine["id"],
                 [{**T3_UNBOUND, "tool_number": n} for n in range(1, 5)])  # 4 entries

    # Empty snapshot: refused.
    assert put_snapshot(solo_client, machine["id"], []).status_code == 409
    # Removing 3 of 4 (>half): refused, and nothing was deleted.
    assert put_snapshot(solo_client, machine["id"],
                        [{**T3_UNBOUND, "tool_number": 1}]).status_code == 409
    assert len(solo_client.get(
        f"/api/v1/machines/{machine['id']}/tool-table").json()["items"]) == 4


@pytest.mark.contract
def test_force_overrides_the_mass_wipe_guard(solo_client):
    """force=true is the operator vouching the deletions are real."""
    machine = make_machine(solo_client)
    put_snapshot(solo_client, machine["id"],
                 [{**T3_UNBOUND, "tool_number": n} for n in range(1, 5)])
    resp = put_snapshot(solo_client, machine["id"],
                        [{**T3_UNBOUND, "tool_number": 1}], force=True)
    assert resp.status_code == 200
    assert sorted(resp.json()["removed_tool_numbers"]) == [2, 3, 4]
    assert len(solo_client.get(
        f"/api/v1/machines/{machine['id']}/tool-table").json()["items"]) == 1


@pytest.mark.contract
def test_snapshot_reconcile_is_audited(solo_client):
    """A reconciled deletion leaves an audit trail distinct from a human one."""
    machine = make_machine(solo_client)
    put_snapshot(solo_client, machine["id"], [
        {**T3_UNBOUND, "tool_number": 1},
        {**T3_UNBOUND, "tool_number": 2},
    ])
    put_snapshot(solo_client, machine["id"], [{**T3_UNBOUND, "tool_number": 1}])
    logs = solo_client.get("/api/v1/audit-logs").json()["logs"]
    reconciled = [l for l in logs
                  if l["entity_type"] == "tool_table_entry" and l["operation"] == "DELETE"]
    assert reconciled, "expected a DELETE audit entry for the reconciled slot"
