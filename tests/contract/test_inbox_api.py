# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Contract tests for the binding engine + Inbox (smooth-core#5).

The binding engine is the heart of the product (decisions D3/G2): when a
controller pushes unbound ToolTableEntries, the SERVER proposes bindings to
matching ToolRecords. Proposals are pending-review state — a human confirms
or rejects them in the Inbox; nothing heuristic is ever applied silently.

Heuristic (documented contract, tunable later):
- diameter agreement between entry.offsets.diameter and
  record.geometry.diameter (within 1%) scores 0.55
- name similarity between entry.description and record.name scores up to
  0.45 (difflib ratio)
- a proposal is created for the single best-scoring record at >= 0.5 —
  so a name alone can never trigger a proposal, a diameter alone can

Assumptions:
- Proposals are generated during tool-table upsert for unbound entries
- At most ONE open proposal per entry; re-pushing does not duplicate
- GET  /api/v1/inbox                    -> {"items": [...]} open items only
- POST /api/v1/inbox/{id}/confirm       -> binds entry, closes proposal
- POST /api/v1/inbox/{id}/reject        -> closes proposal; the same
  (entry, record) pair is never proposed again
- Acting on a resolved proposal is 409
- propose/confirm/reject are audited
"""
import pytest


MILL = {"name": "mill01", "controller_type": "linuxcnc"}

DOWNCUT_RECORD = {
    "name": '1/4" downcut',
    "geometry": {"shape": "endmill", "diameter": 6.35, "diameter_unit": "mm"},
}

T3_DOWNCUT = {
    "tool_number": 3,
    "description": "1/4 downcut",
    "offsets": {"z": -48.25, "z_unit": "mm", "diameter": 6.35, "diameter_unit": "mm"},
}


def setup_machine_and_record(client, record=DOWNCUT_RECORD):
    machine = client.post("/api/v1/machines", json={"items": [MILL]}).json()["items"][0]
    rec = client.post("/api/v1/tool-records", json={"items": [record]}).json()["items"][0]
    return machine, rec


def push(client, machine_id, entries):
    resp = client.put(f"/api/v1/machines/{machine_id}/tool-table", json={"items": entries})
    assert resp.status_code == 200, resp.text
    return resp.json()


def inbox(client):
    resp = client.get("/api/v1/inbox")
    assert resp.status_code == 200
    return resp.json()["items"]


@pytest.mark.contract
def test_unbound_push_generates_proposal(solo_client):
    """A matching record yields exactly one open proposal with the entry,
    the proposed record, a confidence, and a human-readable reason."""
    machine, record = setup_machine_and_record(solo_client)
    push(solo_client, machine["id"], [T3_DOWNCUT])

    items = inbox(solo_client)
    assert len(items) == 1
    proposal = items[0]
    assert proposal["type"] == "binding_proposal"
    assert proposal["entry"]["tool_number"] == 3
    assert proposal["entry"]["machine_id"] == machine["id"]
    assert proposal["proposed_record"]["id"] == record["id"]
    assert proposal["confidence"] >= 0.5
    assert proposal["reason"]


@pytest.mark.contract
def test_no_auto_bind_ever(solo_client):
    """Even a perfect match leaves the entry unbound until a human confirms."""
    machine, _ = setup_machine_and_record(solo_client)
    push(solo_client, machine["id"], [T3_DOWNCUT])
    entries = solo_client.get(
        f"/api/v1/machines/{machine['id']}/tool-table"
    ).json()["items"]
    assert entries[0]["tool_record_id"] is None


@pytest.mark.contract
def test_at_most_one_open_proposal_per_entry(solo_client):
    """Re-pushing the same table does not stack duplicate proposals."""
    machine, _ = setup_machine_and_record(solo_client)
    push(solo_client, machine["id"], [T3_DOWNCUT])
    push(solo_client, machine["id"], [T3_DOWNCUT])
    push(solo_client, machine["id"], [T3_DOWNCUT])
    assert len(inbox(solo_client)) == 1


@pytest.mark.contract
def test_confirm_binds_and_persists_across_syncs(solo_client):
    """Confirming binds the entry, empties the inbox, surfaces the entry on
    the ToolRecord, and survives subsequent pushes without new proposals."""
    machine, record = setup_machine_and_record(solo_client)
    push(solo_client, machine["id"], [T3_DOWNCUT])
    proposal = inbox(solo_client)[0]

    resp = solo_client.post(f"/api/v1/inbox/{proposal['id']}/confirm")
    assert resp.status_code == 200

    entries = solo_client.get(
        f"/api/v1/machines/{machine['id']}/tool-table"
    ).json()["items"]
    assert entries[0]["tool_record_id"] == record["id"]
    assert inbox(solo_client) == []

    fetched = solo_client.get(f"/api/v1/tool-records/{record['id']}").json()
    assert fetched["machines"][0]["tool_number"] == 3

    # the controller pushes again (a fresh touch-off): binding sticks
    changed = dict(T3_DOWNCUT)
    changed["offsets"] = {"z": -48.10, "z_unit": "mm", "diameter": 6.35, "diameter_unit": "mm"}
    push(solo_client, machine["id"], [changed])
    entries = solo_client.get(
        f"/api/v1/machines/{machine['id']}/tool-table"
    ).json()["items"]
    assert entries[0]["tool_record_id"] == record["id"]
    assert inbox(solo_client) == []


@pytest.mark.contract
def test_reject_closes_and_never_reproposes_same_pair(solo_client):
    """Rejection is remembered: the same (entry, record) pair is not
    proposed again on the next sync."""
    machine, _ = setup_machine_and_record(solo_client)
    push(solo_client, machine["id"], [T3_DOWNCUT])
    proposal = inbox(solo_client)[0]

    resp = solo_client.post(f"/api/v1/inbox/{proposal['id']}/reject")
    assert resp.status_code == 200
    assert inbox(solo_client) == []

    push(solo_client, machine["id"], [T3_DOWNCUT])
    assert inbox(solo_client) == []


@pytest.mark.contract
def test_no_plausible_match_means_no_proposal(solo_client):
    """A record with no diameter and a dissimilar name never reaches the
    proposal threshold — silence is correct, not a fallback proposal."""
    machine, _ = setup_machine_and_record(
        solo_client, {"name": "engraving laser", "geometry": {"shape": "custom"}}
    )
    push(solo_client, machine["id"], [T3_DOWNCUT])
    assert inbox(solo_client) == []


@pytest.mark.contract
def test_best_match_wins_single_proposal(solo_client):
    """With several candidates, exactly one proposal targets the best one."""
    machine = solo_client.post("/api/v1/machines", json={"items": [MILL]}).json()["items"][0]
    records = solo_client.post("/api/v1/tool-records", json={"items": [
        {"name": "6.35mm rougher", "geometry": {"diameter": 6.35}},
        DOWNCUT_RECORD,  # same diameter, much better name match
        {"name": "5mm drill", "geometry": {"diameter": 5.0}},
    ]}).json()["items"]

    push(solo_client, machine["id"], [T3_DOWNCUT])
    items = inbox(solo_client)
    assert len(items) == 1
    assert items[0]["proposed_record"]["id"] == records[1]["id"]


@pytest.mark.contract
def test_resolved_proposal_cannot_be_acted_on_again(solo_client):
    """Confirm/reject on an already-resolved proposal is a 409."""
    machine, _ = setup_machine_and_record(solo_client)
    push(solo_client, machine["id"], [T3_DOWNCUT])
    proposal = inbox(solo_client)[0]
    solo_client.post(f"/api/v1/inbox/{proposal['id']}/confirm")

    assert solo_client.post(f"/api/v1/inbox/{proposal['id']}/confirm").status_code == 409
    assert solo_client.post(f"/api/v1/inbox/{proposal['id']}/reject").status_code == 409


@pytest.mark.contract
def test_unknown_proposal_404(solo_client):
    assert solo_client.post("/api/v1/inbox/nope/confirm").status_code == 404


@pytest.mark.contract
def test_propose_confirm_reject_are_audited(solo_client):
    """The full lifecycle leaves an audit trail."""
    machine, _ = setup_machine_and_record(solo_client)
    push(solo_client, machine["id"], [T3_DOWNCUT])
    proposal = inbox(solo_client)[0]
    solo_client.post(f"/api/v1/inbox/{proposal['id']}/confirm")

    entries = solo_client.get("/api/v1/audit-logs").json()["logs"]
    ops = {(e["entity_type"], e["operation"]) for e in entries}
    assert ("binding_proposal", "PROPOSE") in ops
    assert ("binding_proposal", "CONFIRM") in ops


@pytest.mark.contract
def test_inbox_items_include_machine_name(solo_client):
    """Field feedback: T-numbers are ambiguous across machines. Items carry
    the machine's display name alongside the entry."""
    machine, _ = setup_machine_and_record(solo_client)
    push(solo_client, machine["id"], [T3_DOWNCUT])
    item = inbox(solo_client)[0]
    assert item["machine_name"] == "mill01"


@pytest.mark.contract
def test_web_inbox_is_served(solo_client):
    """The web inbox ships with core: / redirects to /ui/, which serves the
    single-file app. Auth is enforced by the APIs the page calls, so the
    page itself is public."""
    root = solo_client.get("/", follow_redirects=False)
    assert root.status_code in (302, 307)
    assert root.headers["location"] == "/ui/"

    page = solo_client.get("/ui/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    # Assert on durable app identifiers, not user-facing copy (which evolves).
    assert "Smooth web inbox" in page.text   # file header comment
    assert "<title>Smooth</title>" in page.text
