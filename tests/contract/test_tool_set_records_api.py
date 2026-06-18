# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""Contract tests for the sectioned ToolSetRecord facade — the agnostic
collection."""
import pytest
from smooth.contract import ToolSet, UNKNOWN

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
def test_sync_lane_discipline(solo_client):
    sid = solo_client.post(BASE, json={}).json()["internal"]["id"]
    assert solo_client.put(f"{BASE}/{sid}/clients/freecad",
                           json={"client_version": "0.3", "data": {"fctl": {}}}).status_code == 200
    assert solo_client.put(f"{BASE}/{sid}/clients/freecad",
                           json={"client_version": "0.3", "internal": {"id": "x"}}).status_code == 400
