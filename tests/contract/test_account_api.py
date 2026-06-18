# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""Contract tests for POST /api/v1/account/reset — wipe the caller's tool data,
keep the account and its API keys (REBOOT.md Phase 2.5)."""
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
