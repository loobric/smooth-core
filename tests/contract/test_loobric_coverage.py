# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""Drift gate: loobric.py (THE reference Python client) can reach EVERY published
facade route. If the server publishes a route loobric cannot call, this test
fails — full client coverage is enforced in CI, not aspirational (REBOOT.md
Phase 2.5; memory `loobric-reference-client`).

Coverage is detected statically: every endpoint string loobric passes to
`_call(...)` / `make_request(...)` is matched against the OpenAPI paths.
Path parameters are wildcards, so loobric's generic doors — `assert_field`,
`observe_field`, `sync_client_section` use `/{resource}/{id}/...` — legitimately
cover the per-resource published routes.
"""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
LOOBRIC = REPO / "loobric.py"

# Published routes loobric reaches by a path NOT built from a _call/make_request
# string literal. Keep this tiny and justified (no silent caps).
ALLOWLIST = {
    ("GET", ("api", "health")),     # the `ping` command issues a raw health check
}


def _segments(path: str):
    path = path.split("?", 1)[0]
    path = re.sub(r"\{[^}]+\}", "{}", path)        # every path param -> wildcard
    if not path.startswith("/api/"):
        path = "/api/v1/" + path.lstrip("/")
    return tuple(path.strip("/").split("/"))


def _match(published, covered) -> bool:
    """A published route is covered if some loobric route has the same method and
    a segment-by-segment match, where `{}` on either side is a wildcard."""
    pm, ps = published
    for cm, cs in covered:
        if cm == pm and len(cs) == len(ps) and all(
                a == b or a == "{}" or b == "{}" for a, b in zip(ps, cs)):
            return True
    return False


def _published_routes():
    from smooth.main import create_app
    app = create_app()
    out = set()
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            if method.lower() in ("get", "post", "put", "patch", "delete"):
                out.add((method.upper(), _segments(path)))
    return out


def _loobric_routes():
    src = LOOBRIC.read_text()
    out = set(ALLOWLIST)
    for method, endpoint in re.findall(
            r'(?:_call|_send|make_request)\(\s*["\'](\w+)["\']\s*,\s*f?["\']([^"\']+)["\']', src):
        out.add((method.upper(), _segments(endpoint)))
    return out


@pytest.mark.contract
def test_loobric_covers_every_published_route():
    published = _published_routes()
    covered = _loobric_routes()
    missing = sorted((m, "/" + "/".join(s)) for m, s in published if not _match((m, s), covered))
    assert not missing, (
        "loobric (the reference client) cannot reach %d published route(s):\n  %s"
        % (len(missing), "\n  ".join(f"{m} {p}" for m, p in missing))
    )
