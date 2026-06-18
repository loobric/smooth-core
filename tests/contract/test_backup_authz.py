# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""Regression: full-database backup/restore is admin-only.

Before the 2026-06-18 reboot (REBOOT.md Phase 2) the `/backup/export` and
`/backup/import` endpoints took no `user` dependency at all — anyone could dump
or overwrite the entire database unauthenticated. These tests lock the gate shut.

(A cross-user API-key revoke test belongs here too, but needs the multi-user
fixture isolation fixed first — see REBOOT.md R8.)
"""
import io

import pytest


@pytest.mark.integration
def test_backup_export_requires_auth(client):
    """Multi-user mode, no credentials → rejected (was an open full-DB dump)."""
    r = client.get("/api/v1/backup/export")
    assert r.status_code in (401, 403)


@pytest.mark.integration
def test_backup_import_requires_auth(client):
    """Multi-user mode, no credentials → rejected (was an open full-DB restore)."""
    r = client.post(
        "/api/v1/backup/import",
        files={"file": ("backup.json", io.BytesIO(b"{}"), "application/json")},
    )
    assert r.status_code in (401, 403)


@pytest.mark.contract
def test_backup_export_allowed_for_solo_admin(solo_client):
    """The solo user is the first user → admin, so solo backup still works with
    no auth ceremony (the admin gate must not break the primary path)."""
    r = solo_client.get("/api/v1/backup/export")
    assert r.status_code == 200
