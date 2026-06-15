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


@pytest.mark.contract
def test_sync_lane_discipline(solo_client):
    sid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    assert solo_client.put(f"{BASE}/{sid}/clients/freecad",
                           json={"client_version": "0.3", "data": {"fctl": {}}}).status_code == 200
    assert solo_client.put(f"{BASE}/{sid}/clients/freecad",
                           json={"client_version": "0.3", "internal": {"id": "x"}}).status_code == 400
