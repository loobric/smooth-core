# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""Contract tests for the sectioned ToolSetRecord facade — the agnostic
collection, with machine-bound number reconciliation."""
import pytest
from smooth.contract import ToolSet, Provenance, UNKNOWN

BASE = "/api/v1/tool-set-records"
ENTRY = "/api/v1/tool-table-entry-records"


def conforms(doc):
    ToolSet.model_validate(doc)
    return doc


@pytest.mark.contract
def test_create_and_assert_name_and_link(solo_client):
    rid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    doc = conforms(solo_client.post(f"{BASE}/{rid}/assert",
                   json={"path": "name", "value": "millstone tools", "actor": "freecad"}).json())
    assert doc["canonical"]["name"]["value"] == "millstone tools"
    assert doc["canonical"]["machine_id"]["source"] == UNKNOWN   # general set until linked


@pytest.mark.contract
def test_members_asserted_then_reconciled_from_the_machine(solo_client):
    machine = "m-millstone"
    # two occupied slots on the machine, with observed numbers
    def slot(tool_number, instance):
        eid = solo_client.post(ENTRY, json={"machine_id": machine}).json()["internal"]["id"]
        solo_client.post(f"{ENTRY}/{eid}/observe",
                         json={"path": "tool_number", "value": tool_number,
                               "client": "linuxcnc", "machine": "millstone"})
        solo_client.post(f"{ENTRY}/{eid}/bind",
                         json={"instance_id": instance, "actor": "human@inbox"})
    slot(5, "inst-A")
    slot(7, "inst-B")

    sid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    solo_client.post(f"{BASE}/{sid}/assert", json={"path": "machine_id", "value": machine, "actor": "human"})
    # membership includes one tool not on the machine (inst-C)
    solo_client.post(f"{BASE}/{sid}/members", json={"actor": "freecad", "members": [
        {"tool_record_id": "inst-A"}, {"tool_record_id": "inst-B"}, {"tool_record_id": "inst-C"}]})

    r = solo_client.post(f"{BASE}/{sid}/reconcile")
    assert r.status_code == 200, r.text
    doc = r.json()
    conforms({k: v for k, v in doc.items() if k != "unreconciled"})
    nums = {m["tool_record_id"]: m["number"] for m in doc["canonical"]["members"]}
    assert nums["inst-A"]["value"] == 5 and Provenance.kind(nums["inst-A"]["source"]) == "observed"
    assert nums["inst-B"]["value"] == 7
    assert nums["inst-C"]["value"] is None              # no slot -> stays unknown
    assert doc["unreconciled"] == ["inst-C"]


@pytest.mark.contract
def test_reconcile_requires_a_machine_link(solo_client):
    sid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    assert solo_client.post(f"{BASE}/{sid}/reconcile").status_code == 400


def _occupy(solo_client, machine, tool_number, instance):
    """Create a machine slot at `tool_number` holding `instance`."""
    eid = solo_client.post(ENTRY, json={"machine_id": machine}).json()["internal"]["id"]
    solo_client.post(f"{ENTRY}/{eid}/observe",
                     json={"path": "tool_number", "value": tool_number,
                           "client": "linuxcnc", "machine": machine})
    solo_client.post(f"{ENTRY}/{eid}/bind",
                     json={"instance_id": instance, "actor": "human@inbox"})
    return eid


@pytest.mark.contract
def test_coverage_matrix_for_a_machine_linked_set(solo_client):
    machine = "m-cov"
    _occupy(solo_client, machine, 5, "inst-A")        # will be in_sync with the set
    _occupy(solo_client, machine, 7, "inst-X")        # bound, but not in the set
    eid = solo_client.post(ENTRY, json={"machine_id": machine}).json()["internal"]["id"]
    solo_client.post(f"{ENTRY}/{eid}/observe",        # an empty pocket
                     json={"path": "tool_number", "value": 8,
                           "client": "linuxcnc", "machine": machine})

    sid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    solo_client.post(f"{BASE}/{sid}/assert",
                     json={"path": "machine_id", "value": machine, "actor": "human"})
    solo_client.post(f"{BASE}/{sid}/members", json={"actor": "freecad", "members": [
        {"tool_record_id": "inst-A", "number": 5},
        {"tool_record_id": "inst-C", "number": 9}]})   # promised, not on the machine

    r = solo_client.get(f"{BASE}/{sid}/coverage")
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["applicable"] is True and doc["machine_id"] == machine

    status = {m["tool_record_id"]: m["status"] for m in doc["members"]}
    assert status["inst-A"] == "in_sync"
    assert status["inst-C"] == "absent_on_machine"     # the tool not yet set up

    slots = {s["slot_id"]: s["status"] for s in doc["slots"]}
    assert set(slots.values()) == {"machine_only", "unbound_slot"}

    s = doc["summary"]
    assert s["in_sync"] == 1 and s["absent_on_machine"] == 1
    assert s["machine_only"] == 1 and s["unbound_slot"] == 1


@pytest.mark.contract
def test_coverage_reports_number_mismatch(solo_client):
    machine = "m-mismatch"
    _occupy(solo_client, machine, 5, "inst-A")
    sid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    solo_client.post(f"{BASE}/{sid}/assert",
                     json={"path": "machine_id", "value": machine, "actor": "human"})
    solo_client.post(f"{BASE}/{sid}/members", json={"actor": "freecad", "members": [
        {"tool_record_id": "inst-A", "number": 9}]})   # set says T9, machine says T5

    doc = solo_client.get(f"{BASE}/{sid}/coverage").json()
    row = doc["members"][0]
    assert row["status"] == "number_mismatch"
    assert row["set_number"] == 9 and row["machine_tool_number"] == 5


@pytest.mark.contract
def test_coverage_is_read_only(solo_client):
    """Calling coverage must not renumber members the way reconcile does."""
    machine = "m-readonly"
    _occupy(solo_client, machine, 5, "inst-A")
    sid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    solo_client.post(f"{BASE}/{sid}/assert",
                     json={"path": "machine_id", "value": machine, "actor": "human"})
    solo_client.post(f"{BASE}/{sid}/members", json={"actor": "freecad",
                     "members": [{"tool_record_id": "inst-A"}]})  # number unknown
    before = solo_client.get(f"{BASE}/{sid}").json()

    solo_client.get(f"{BASE}/{sid}/coverage")

    after = solo_client.get(f"{BASE}/{sid}").json()
    assert after["internal"]["version"] == before["internal"]["version"]
    assert after["canonical"]["members"][0]["number"]["value"] is None


@pytest.mark.contract
def test_coverage_not_applicable_without_machine_link(solo_client):
    sid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    r = solo_client.get(f"{BASE}/{sid}/coverage")
    assert r.status_code == 200
    doc = r.json()
    assert doc["applicable"] is False and doc["machine_id"] is None


@pytest.mark.contract
def test_sync_lane_discipline(solo_client):
    sid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    assert solo_client.put(f"{BASE}/{sid}/clients/freecad",
                           json={"client_version": "0.3", "data": {"fctl": {}}}).status_code == 200
    assert solo_client.put(f"{BASE}/{sid}/clients/freecad",
                           json={"client_version": "0.3", "internal": {"id": "x"}}).status_code == 400
