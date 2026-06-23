# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""Integration-test fixtures.

Re-export the contract suite's `solo_client` (TestClient against an app booted
in solo mode) so the server-driven roundtrip integration test can drive the same
real API the clients use, without standing up a second harness.
"""
from tests.contract.conftest import solo_client  # noqa: F401
