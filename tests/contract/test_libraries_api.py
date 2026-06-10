# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Contract tests for the v2 public facade: Library (smooth-freecad#5 prereq).

Library is the facade word for a named collection of ToolRecords
(UBIQUITOUS_LANGUAGE.md): it maps FreeCAD's Tool Library / .fctl concept.
Internally backed by ToolSet (type="library") — invisible at the boundary.

Assumptions:
- Bulk envelope identical to tool-records/machines
- Library shape: id, name, description, tool_record_ids, tags, version,
  created_at, updated_at
- Membership is set wholesale (tool_record_ids replaces) — matches .fctl
  semantics, where the file IS the membership list
- Member ids are validated against the user's records (per-item error)
- A record may belong to many libraries; deleting a library never deletes
  records
"""
import pytest


def make_records(client, names):
    resp = client.post("/api/v1/tool-records", json={"items": [
        {"name": n, "geometry": {"diameter": 6.35}} for n in names
    ]})
    return resp.json()["items"]


def make_library(client, name="router bits", record_ids=None, **extra):
    resp = client.post("/api/v1/libraries", json={"items": [
        {"name": name, "tool_record_ids": record_ids or [], **extra}
    ]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success_count"] == 1, body
    return body["items"][0]


@pytest.mark.contract
def test_library_crud_round_trip(solo_client):
    """Create, fetch, list, update membership, delete."""
    records = make_records(solo_client, ["1/4 downcut", "1/8 upcut"])
    lib = make_library(solo_client, record_ids=[records[0]["id"]],
                       description="shapeoko drawer")
    assert lib["version"] == 1
    assert lib["tool_record_ids"] == [records[0]["id"]]

    fetched = solo_client.get(f"/api/v1/libraries/{lib['id']}").json()
    assert fetched["name"] == "router bits"
    assert fetched["description"] == "shapeoko drawer"

    listed = solo_client.get("/api/v1/libraries").json()["items"]
    assert any(l["id"] == lib["id"] for l in listed)

    upd = solo_client.patch("/api/v1/libraries", json={"items": [
        {"id": lib["id"], "version": 1,
         "tool_record_ids": [r["id"] for r in records]}
    ]})
    assert upd.json()["success_count"] == 1
    assert len(upd.json()["items"][0]["tool_record_ids"]) == 2
    assert upd.json()["items"][0]["version"] == 2

    deleted = solo_client.request("DELETE", "/api/v1/libraries",
                                  json={"ids": [lib["id"]]})
    assert deleted.json()["success_count"] == 1
    assert solo_client.get(f"/api/v1/libraries/{lib['id']}").status_code == 404
    # records survive their library
    assert solo_client.get(f"/api/v1/tool-records/{records[0]['id']}").status_code == 200


@pytest.mark.contract
def test_membership_validates_record_ids(solo_client):
    """Unknown member ids are a per-item error, not a silent drop."""
    record = make_records(solo_client, ["real tool"])[0]
    resp = solo_client.post("/api/v1/libraries", json={"items": [
        {"name": "good", "tool_record_ids": [record["id"]]},
        {"name": "bad", "tool_record_ids": ["no-such-record"]},
    ]})
    body = resp.json()
    assert body["success_count"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["index"] == 1
    assert "no-such-record" in body["errors"][0]["message"]


@pytest.mark.contract
def test_record_in_many_libraries_and_stale_version(solo_client):
    record = make_records(solo_client, ["shared tool"])[0]
    lib_a = make_library(solo_client, "drawer A", [record["id"]])
    lib_b = make_library(solo_client, "drawer B", [record["id"]])
    assert lib_a["id"] != lib_b["id"]

    stale = solo_client.patch("/api/v1/libraries", json={"items": [
        {"id": lib_a["id"], "version": 99, "name": "x"}
    ]})
    assert stale.json()["success_count"] == 0
    assert "Version conflict" in stale.json()["errors"][0]["message"]


@pytest.mark.contract
def test_name_required_per_item(solo_client):
    resp = solo_client.post("/api/v1/libraries", json={"items": [
        {"tool_record_ids": []}, {"name": "ok"}
    ]})
    body = resp.json()
    assert body["success_count"] == 1
    assert body["errors"][0]["index"] == 0


@pytest.mark.contract
def test_openapi_includes_libraries_and_hides_tool_sets(solo_client):
    """Libraries are the published concept; the internal tool-sets routes
    (their backing implementation) leave the public schema with this change."""
    paths = solo_client.get("/api/v1/openapi.json").json()["paths"]
    assert any(p.startswith("/api/v1/libraries") for p in paths)
    assert not [p for p in paths if "tool-sets" in p or "tool-usage" in p]
