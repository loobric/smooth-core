# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""The gate: the published surface speaks ONLY the facade vocabulary.

`UBIQUITOUS_LANGUAGE.md` ("Language rule — the gate") and `REBOOT.md` (R2) promise
two things this file enforces in CI so drift cannot recur:

1. The legacy deep-schema routers are LIVE but UNPUBLISHED — they must never
   appear in the published OpenAPI paths. (The glossary long *claimed* this was a
   tested contract; until the 2026-06-18 reboot it was not. Now it is.)
2. The concepts ripped out in the reboot — adopt / coverage / reconcile / mirror —
   never reappear on a public path or in the bundled clients.

If one of these fails, drift reached the contract. Fix the code, not this test.
"""
import pathlib

import pytest

# Legacy deep-schema resources: still mounted (include_in_schema=False) for the
# v2 transition, but excluded from the published schema. See REBOOT.md R6.
LEGACY_DEEP_RESOURCES = {
    "tool-items", "tool-assemblies", "tool-instances", "tool-presets", "tool-usage",
}

# Retired concepts (glossary "Rejected / removed terms"). Matched as a path
# fragment, so they catch both `/.../adopt` endpoints and `/coverage` queries.
RETIRED_PATH_FRAGMENTS = ("/adopt", "/coverage", "/reconcile", "/mirror")

# The facade resources that MUST be published (a positive control so the
# exclusion tests below can't pass vacuously by publishing nothing).
FACADE_RESOURCES = (
    "tool-instance-records", "tool-catalog-records", "tool-table-entry-records",
    "tool-set-records", "machine-records", "instance-inbox",
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _published_paths(solo_client):
    schema = solo_client.get("/api/v1/openapi.json").json()
    return list(schema.get("paths", {}).keys())


@pytest.mark.contract
def test_legacy_deep_routers_excluded_from_published_schema(solo_client):
    leaked = []
    for path in _published_paths(solo_client):
        parts = path.strip("/").split("/")          # ["api", "v1", "<resource>", ...]
        resource = parts[2] if len(parts) >= 3 else ""
        if resource in LEGACY_DEEP_RESOURCES:
            leaked.append(path)
    assert not leaked, "deep-schema routes leaked into the public OpenAPI: %s" % leaked


@pytest.mark.contract
def test_no_retired_concepts_on_public_paths(solo_client):
    offenders = []
    for path in _published_paths(solo_client):
        low = path.lower()
        for frag in RETIRED_PATH_FRAGMENTS:
            if frag in low:
                offenders.append((path, frag))
    assert not offenders, "retired concept on a public path: %s" % offenders


@pytest.mark.contract
def test_facade_resources_are_published(solo_client):
    paths = " ".join(_published_paths(solo_client))
    missing = [r for r in FACADE_RESOURCES if "/api/v1/%s" % r not in paths]
    assert not missing, "facade resource missing from the published schema: %s" % missing


@pytest.mark.contract
def test_bundled_clients_do_not_call_retired_endpoints():
    """The web UI and CLI shipped in this repo must not reference removed endpoints."""
    targets = [REPO_ROOT / "smooth" / "web" / "static" / "index.html",
               REPO_ROOT / "loobric.py"]
    bad = []
    for f in targets:
        text = f.read_text()
        for frag in RETIRED_PATH_FRAGMENTS:
            if frag in text:
                bad.append("%s references %s" % (f.name, frag))
    assert not bad, bad
