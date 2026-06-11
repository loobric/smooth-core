# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Contract tests for the v2 public facade: ToolSet.

ToolSet is a named collection of ToolRecords (UBIQUITOUS_LANGUAGE.md).
The public resource and the internal entity share one name — the 2026-06-11
nomenclature purge removed the client-flavored facade word "Library".

Assumptions:
- Bulk envelope identical to tool-records/machines
- ToolSet shape: id, name, description, tool_record_ids, tags, version,
  created_at, updated_at
- Membership is set wholesale (tool_record_ids replaces) — matches
  file-based clients, where the file IS the membership list
- Member ids are validated against the user's records (per-item error)
- A record may belong to many tool sets; deleting a tool set never
  deletes records
"""
import pytest


def make_records(client, names):
    resp = client.post("/api/v1/tool-records", json={"items": [
        {"name": n, "geometry": {"diameter": 6.35}} for n in names
    ]})
    return resp.json()["items"]


def make_tool_set(client, name="router bits", record_ids=None, **extra):
    resp = client.post("/api/v1/tool-sets", json={"items": [
        {"name": name, "tool_record_ids": record_ids or [], **extra}
    ]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success_count"] == 1, body
    return body["items"][0]


@pytest.mark.contract
def test_tool_set_crud_round_trip(solo_client):
    """Create, fetch, list, update membership, delete."""
    records = make_records(solo_client, ["1/4 downcut", "1/8 upcut"])
    ts = make_tool_set(solo_client, record_ids=[records[0]["id"]],
                       description="shapeoko drawer")
    assert ts["version"] == 1
    assert ts["tool_record_ids"] == [records[0]["id"]]

    fetched = solo_client.get(f"/api/v1/tool-sets/{ts['id']}").json()
    assert fetched["name"] == "router bits"
    assert fetched["description"] == "shapeoko drawer"

    listed = solo_client.get("/api/v1/tool-sets").json()["items"]
    assert any(s["id"] == ts["id"] for s in listed)

    upd = solo_client.patch("/api/v1/tool-sets", json={"items": [
        {"id": ts["id"], "version": 1,
         "tool_record_ids": [r["id"] for r in records]}
    ]})
    assert upd.json()["success_count"] == 1
    assert len(upd.json()["items"][0]["tool_record_ids"]) == 2
    assert upd.json()["items"][0]["version"] == 2

    deleted = solo_client.request("DELETE", "/api/v1/tool-sets",
                                  json={"ids": [ts["id"]]})
    assert deleted.json()["success_count"] == 1
    assert solo_client.get(f"/api/v1/tool-sets/{ts['id']}").status_code == 404
    # records survive their tool set
    assert solo_client.get(f"/api/v1/tool-records/{records[0]['id']}").status_code == 200


@pytest.mark.contract
def test_membership_validates_record_ids(solo_client):
    """Unknown member ids are a per-item error, not a silent drop."""
    record = make_records(solo_client, ["real tool"])[0]
    resp = solo_client.post("/api/v1/tool-sets", json={"items": [
        {"name": "good", "tool_record_ids": [record["id"]]},
        {"name": "bad", "tool_record_ids": ["no-such-record"]},
    ]})
    body = resp.json()
    assert body["success_count"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["index"] == 1
    assert "no-such-record" in body["errors"][0]["message"]


@pytest.mark.contract
def test_record_in_many_tool_sets_and_stale_version(solo_client):
    record = make_records(solo_client, ["shared tool"])[0]
    set_a = make_tool_set(solo_client, "drawer A", [record["id"]])
    set_b = make_tool_set(solo_client, "drawer B", [record["id"]])
    assert set_a["id"] != set_b["id"]

    stale = solo_client.patch("/api/v1/tool-sets", json={"items": [
        {"id": set_a["id"], "version": 99, "name": "x"}
    ]})
    assert stale.json()["success_count"] == 0
    assert "Version conflict" in stale.json()["errors"][0]["message"]


@pytest.mark.contract
def test_name_required_per_item(solo_client):
    resp = solo_client.post("/api/v1/tool-sets", json={"items": [
        {"tool_record_ids": []}, {"name": "ok"}
    ]})
    body = resp.json()
    assert body["success_count"] == 1
    assert body["errors"][0]["index"] == 0


@pytest.mark.contract
def test_openapi_publishes_tool_sets_only(solo_client):
    """/api/v1/tool-sets is the published facade; the retired "libraries"
    routes are gone and the deep routers stay out of the public schema."""
    paths = solo_client.get("/api/v1/openapi.json").json()["paths"]
    assert any(p.startswith("/api/v1/tool-sets") for p in paths)
    assert not [p for p in paths if "libraries" in p or "tool-usage" in p]


@pytest.mark.contract
def test_legacy_library_rows_are_normalized_on_startup(solo_client, db_session):
    """Rows created while the facade was named "Library" carry
    type='library'; startup normalization rewrites them to type='set' so
    they stay visible through the renamed facade."""
    from smooth.database.schema import ToolSet
    from smooth.database.session import normalize_legacy_data

    ts = make_tool_set(solo_client, "pre-rename drawer")
    row = db_session.query(ToolSet).filter(ToolSet.id == ts["id"]).one()
    row.type = "library"  # simulate a row from before the purge
    db_session.commit()
    assert solo_client.get(f"/api/v1/tool-sets/{ts['id']}").status_code == 404

    assert normalize_legacy_data(db_session.get_bind()) == 1
    db_session.expire_all()
    assert solo_client.get(f"/api/v1/tool-sets/{ts['id']}").status_code == 200


@pytest.mark.contract
def test_tool_set_extra_passthrough_round_trips(solo_client):
    """ToolSet.extra holds namespaced client passthrough — e.g. a file-based
    CAM client's per-tool numbers and label, which have no facade
    equivalent."""
    record = make_records(solo_client, ["6mm endmill"])[0]
    doc = {"camclient": {"label": "default", "version": 1,
                         "numbers": {record["id"]: 11}}}
    ts = make_tool_set(solo_client, "default", [record["id"]], extra=doc)
    assert ts["extra"] == doc
    fetched = solo_client.get(f"/api/v1/tool-sets/{ts['id']}").json()
    assert fetched["extra"]["camclient"]["numbers"][record["id"]] == 11
