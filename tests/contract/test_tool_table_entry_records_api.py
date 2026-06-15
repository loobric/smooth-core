# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""Contract tests for the sectioned ToolTableEntryRecord facade — the machine
slot, with the install-once invariant (bind / 409 / move)."""
import pytest
from smooth.contract import ToolTableEntry, Provenance, UNKNOWN

BASE = "/api/v1/tool-table-entry-records"


def conforms(doc):
    ToolTableEntry.model_validate(doc)
    return doc


@pytest.mark.contract
def test_create_carries_machine_in_internal_and_unknown_canonical(solo_client):
    doc = conforms(solo_client.post(BASE, json={"machine_id": "m-mill"}).json())
    assert doc["internal"]["machine_id"] == "m-mill"
    assert doc["canonical"]["tool_number"]["source"] == UNKNOWN
    assert doc["canonical"]["bound_instance_id"]["source"] == UNKNOWN


@pytest.mark.contract
def test_observe_slot_number_and_offset(solo_client):
    rid = solo_client.post(BASE, json={"machine_id": "m-mill"}).json()["internal"]["id"]
    solo_client.post(f"{BASE}/{rid}/observe",
                     json={"path": "tool_number", "value": 5, "client": "linuxcnc", "machine": "millstone"})
    doc = conforms(solo_client.post(f"{BASE}/{rid}/observe",
                   json={"path": "offsets.diameter", "value": 6.35, "unit": "mm",
                         "client": "linuxcnc", "machine": "millstone"}).json())
    assert doc["canonical"]["tool_number"]["value"] == 5
    assert doc["canonical"]["tool_number"]["source"] == "observed:linuxcnc@millstone"
    assert doc["canonical"]["offsets"]["diameter"]["value"] == 6.35


@pytest.mark.contract
def test_bind_then_install_once_409_then_move(solo_client):
    a = solo_client.post(BASE, json={"machine_id": "m-mill"}).json()["internal"]["id"]
    b = solo_client.post(BASE, json={"machine_id": "m-lathe"}).json()["internal"]["id"]  # different machine
    # install instance into slot A
    r = solo_client.post(f"{BASE}/{a}/bind", json={"instance_id": "inst-X", "actor": "human@inbox"})
    assert r.status_code == 200, r.text
    assert conforms(r.json())["canonical"]["bound_instance_id"]["value"] == "inst-X"
    # cannot install the same physical tool in a second slot
    r = solo_client.post(f"{BASE}/{b}/bind", json={"instance_id": "inst-X", "actor": "human@inbox"})
    assert r.status_code == 409, r.text
    # move relocates it: A is vacated, B holds it
    r = solo_client.post(f"{BASE}/{b}/bind", json={"instance_id": "inst-X", "actor": "human@inbox", "move": True})
    assert r.status_code == 200, r.text
    assert solo_client.get(f"{BASE}/{a}").json()["canonical"]["bound_instance_id"]["value"] is None
    assert solo_client.get(f"{BASE}/{b}").json()["canonical"]["bound_instance_id"]["value"] == "inst-X"


@pytest.mark.contract
def test_unbind_clears_the_binding(solo_client):
    a = solo_client.post(BASE, json={"machine_id": "m-mill"}).json()["internal"]["id"]
    solo_client.post(f"{BASE}/{a}/bind", json={"instance_id": "inst-Y", "actor": "human@inbox"})
    doc = conforms(solo_client.post(f"{BASE}/{a}/unbind").json())
    assert doc["canonical"]["bound_instance_id"]["value"] is None
    assert doc["canonical"]["bound_instance_id"]["source"] == UNKNOWN


@pytest.mark.contract
def test_sync_lane_discipline(solo_client):
    rid = solo_client.post(BASE, json={"machine_id": "m-mill"}).json()["internal"]["id"]
    ok = solo_client.put(f"{BASE}/{rid}/clients/linuxcnc",
                         json={"client_version": "0.2", "data": {"raw": "T5 ..."}})
    assert ok.status_code == 200
    bad = solo_client.put(f"{BASE}/{rid}/clients/linuxcnc",
                          json={"client_version": "0.2", "canonical": {"x": 1}})
    assert bad.status_code == 400


@pytest.mark.contract
def test_a_machine_cannot_observe_the_binding(solo_client):
    rid = solo_client.post(BASE, json={"machine_id": "m-mill"}).json()["internal"]["id"]
    r = solo_client.post(f"{BASE}/{rid}/observe",
                         json={"path": "bound_instance_id", "value": "inst-Z",
                               "client": "linuxcnc", "machine": "millstone"})
    assert r.status_code == 400   # binding is a human assertion, not a machine observation
