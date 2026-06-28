# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""Contract tests for the account endpoints:
- POST /api/v1/account/reset — wipe the caller's tool data, keep the account and
  its API keys (REBOOT.md Phase 2.5).
- POST /api/v1/account/seed-demo — populate a fresh account with the demo so a
  first-time visitor has something to explore."""
import pytest

API = "/api/v1"


@pytest.mark.contract
def test_reset_wipes_tool_data(solo_client):
    solo_client.post(f"{API}/machine-records", json={})
    solo_client.post(f"{API}/tool-set-records", json={})
    assert solo_client.get(f"{API}/machine-records").json()["items"]
    assert solo_client.get(f"{API}/tool-set-records").json()["items"]

    r = solo_client.post(f"{API}/account/reset")
    assert r.status_code == 200
    assert r.json()["reset"] is True

    assert solo_client.get(f"{API}/machine-records").json()["items"] == []
    assert solo_client.get(f"{API}/tool-set-records").json()["items"] == []


@pytest.mark.contract
def test_reset_keeps_api_keys(solo_client):
    solo_client.post(f"{API}/auth/keys", json={"name": "keep me", "scopes": ["read"]})
    before = solo_client.get(f"{API}/auth/keys").json()
    solo_client.post(f"{API}/account/reset")
    after = solo_client.get(f"{API}/auth/keys").json()
    assert len(after) == len(before) and before, "reset must not delete API keys"


@pytest.mark.contract
def test_seed_demo_populates_empty_account(solo_client):
    r = solo_client.post(f"{API}/account/seed-demo")
    assert r.status_code == 200
    body = r.json()
    assert body["seeded"] is True
    created = body["created"]
    assert created["machines"] == 1
    assert created["tool_catalogs"] == 8
    assert created["tool_instances"] == 2
    assert created["tool_sets"] == 1
    assert created["tool_table_entries"] == 2
    assert created["binding_proposals"] >= 0  # the server may propose bindings

    # The data is really there and readable through the normal collections.
    assert len(solo_client.get(f"{API}/tool-catalog-records").json()["items"]) == 8
    assert len(solo_client.get(f"{API}/tool-instance-records").json()["items"]) == 2
    sets = solo_client.get(f"{API}/tool-set-records").json()["items"]
    assert len(sets) == 1
    machines = solo_client.get(f"{API}/machine-records").json()["items"]
    assert len(machines) == 1
    mid = machines[0]["internal"]["id"]
    entries = solo_client.get(
        f"{API}/tool-table-entry-records?machine_id={mid}").json()["items"]
    assert len(entries) == 2


@pytest.mark.contract
def test_seed_demo_refuses_non_empty_account(solo_client):
    # Any tool data at all blocks the seed — load it on a clean slate.
    solo_client.post(f"{API}/machine-records", json={})
    r = solo_client.post(f"{API}/account/seed-demo")
    assert r.status_code == 409


@pytest.mark.contract
def test_seed_demo_then_reset_then_seed_again(solo_client):
    assert solo_client.post(f"{API}/account/seed-demo").status_code == 200
    # Reset clears the demo so the account can be reused (or seeded again).
    assert solo_client.post(f"{API}/account/reset").status_code == 200
    assert solo_client.get(f"{API}/tool-catalog-records").json()["items"] == []
    # A second seed succeeds on the now-empty account.
    again = solo_client.post(f"{API}/account/seed-demo")
    assert again.status_code == 200
    assert len(solo_client.get(f"{API}/tool-catalog-records").json()["items"]) == 8
