# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""Contract tests for the sectioned binding engine + instance inbox: propose an
instance for an unbound slot, confirm (install) / reject (remember), and adopt a
brand-new instance from a slot. Diameter agreement drives the proposal."""
import pytest

INST = "/api/v1/tool-instance-records"
ENTRY = "/api/v1/tool-table-entry-records"
INBOX = "/api/v1/instance-inbox"


def _instance(client, diameter):
    rid = client.post(INST, json={}).json()["internal"]["id"]
    client.post(f"{INST}/{rid}/observe", json={"path": "geometry.diameter",
                "value": diameter, "unit": "mm", "client": "linuxcnc", "machine": "millstone"})
    return rid


def _slot(client, diameter, tool_number=1, machine="m-mill"):
    sid = client.post(ENTRY, json={"machine_id": machine}).json()["internal"]["id"]
    client.post(f"{ENTRY}/{sid}/observe", json={"path": "tool_number", "value": tool_number,
                "client": "linuxcnc", "machine": "millstone"})
    client.post(f"{ENTRY}/{sid}/observe", json={"path": "offsets.diameter", "value": diameter,
                "unit": "mm", "client": "linuxcnc", "machine": "millstone"})
    return sid


@pytest.mark.contract
def test_diameter_match_is_proposed(solo_client):
    inst = _instance(solo_client, 6.35)
    slot = _slot(solo_client, 6.35)
    items = solo_client.get(INBOX).json()["items"]
    assert len(items) == 1
    p = items[0]
    assert p["slot"]["id"] == slot and p["proposed_instance"]["id"] == inst
    assert p["confidence"] >= 0.5


@pytest.mark.contract
def test_no_match_no_proposal(solo_client):
    _instance(solo_client, 12.0)
    _slot(solo_client, 6.35)         # diameters disagree
    assert solo_client.get(INBOX).json()["items"] == []


@pytest.mark.contract
def test_confirm_installs_and_empties_inbox(solo_client):
    inst = _instance(solo_client, 6.35)
    slot = _slot(solo_client, 6.35)
    pid = solo_client.get(INBOX).json()["items"][0]["id"]
    r = solo_client.post(f"{INBOX}/{pid}/confirm")
    assert r.status_code == 200, r.text
    # slot now holds the instance; inbox empty; acting again is 409
    assert solo_client.get(f"{ENTRY}/{slot}").json()["canonical"]["bound_instance_id"]["value"] == inst
    assert solo_client.get(INBOX).json()["items"] == []
    assert solo_client.post(f"{INBOX}/{pid}/confirm").status_code == 409


@pytest.mark.contract
def test_reject_is_remembered(solo_client):
    _instance(solo_client, 6.35)
    _slot(solo_client, 6.35)
    pid = solo_client.get(INBOX).json()["items"][0]["id"]
    assert solo_client.post(f"{INBOX}/{pid}/reject").status_code == 200
    # the same (slot, instance) pair is not proposed again
    assert solo_client.get(INBOX).json()["items"] == []


@pytest.mark.contract
def test_adopt_mints_an_instance_from_the_slot(solo_client):
    """The 'new tool' path: a slot with no matching instance adopts a fresh one,
    seeded with the slot's MEASURED diameter (provenance carried through)."""
    slot = _slot(solo_client, 6.35)
    r = solo_client.post(f"{ENTRY}/{slot}/adopt", json={"actor": "human@inbox"})
    assert r.status_code == 200, r.text
    inst_id = r.json()["instance_id"]
    assert r.json()["slot"]["canonical"]["bound_instance_id"]["value"] == inst_id
    inst = solo_client.get(f"{INST}/{inst_id}").json()
    dia = inst["canonical"]["geometry"]["diameter"]
    assert dia["value"] == 6.35 and dia["source"] == "observed:linuxcnc@millstone"
    assert inst["canonical"]["name"]["source"] == "unknown"   # honest; user asserts later
