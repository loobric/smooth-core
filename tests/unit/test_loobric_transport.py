# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for make_request's raw HTTP request-building — the transport layer
the in-process integration tests bypass. A fake connection records what would go
on the wire. Covers the bugs class that mocked Client tests can't see: the
empty-`{}` body must be SENT (not dropped as falsy), multipart raw bodies, auth
headers, the /api/v1 prefix, and typed-error raising on non-2xx."""
import importlib.util
import json
import pathlib

import pytest

_LOOBRIC = pathlib.Path(__file__).resolve().parents[2] / "loobric.py"
_spec = importlib.util.spec_from_file_location("loobric", _LOOBRIC)
loobric = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(loobric)


class FakeResponse:
    def __init__(self, status=200, body=b'{"ok": true}', headers=None):
        self.status = status
        self._body = body
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}

    def read(self):
        return self._body

    def getheader(self, name):
        return self._headers.get(name.lower())


class FakeConn:
    def __init__(self):
        self.calls = []
        self.resp = FakeResponse()

    def request(self, method, path, body=None, headers=None):
        self.calls.append({"method": method, "path": path, "body": body, "headers": headers})

    def getresponse(self):
        return self.resp

    def close(self):
        pass


@pytest.fixture
def conn(monkeypatch):
    c = FakeConn()
    monkeypatch.setattr(loobric, "get_connection", lambda base_url=None: c)
    # transport reads/writes module globals; keep them inert for the test
    monkeypatch.setattr(loobric, "API_KEY", None)
    monkeypatch.setattr(loobric, "SESSION_COOKIE", None)
    return c


def test_empty_body_is_sent_as_json_object(conn):
    # the bug that 422'd every create: `if body` dropped {} as falsy
    loobric.make_request("POST", "/x", body={})
    assert conn.calls[-1]["body"] == "{}"


def test_none_body_sends_nothing(conn):
    loobric.make_request("GET", "/x")
    assert conn.calls[-1]["body"] is None


def test_json_body_is_serialized_with_json_content_type(conn):
    loobric.make_request("POST", "/x", body={"a": 1})
    assert json.loads(conn.calls[-1]["body"]) == {"a": 1}
    assert conn.calls[-1]["headers"]["Content-Type"] == "application/json"


def test_raw_multipart_body_overrides_json(conn):
    loobric.make_request("POST", "/backup/import", raw_body=b"--b--",
                         content_type="multipart/form-data; boundary=b")
    call = conn.calls[-1]
    assert call["body"] == b"--b--"
    assert call["headers"]["Content-Type"].startswith("multipart/form-data")


def test_api_key_sets_bearer_header(conn):
    loobric.make_request("GET", "/x", api_key="KEY")
    assert conn.calls[-1]["headers"]["Authorization"] == "Bearer KEY"


def test_path_is_prefixed_with_api_v1(conn):
    loobric.make_request("GET", "/tool-set-records")
    assert conn.calls[-1]["path"] == "/api/v1/tool-set-records"


def test_2xx_returns_parsed_json(conn):
    conn.resp = FakeResponse(status=201, body=b'{"id": "abc"}')
    assert loobric.make_request("POST", "/x", body={}) == {"id": "abc"}


def test_empty_2xx_body_returns_empty_dict(conn):
    conn.resp = FakeResponse(status=204, body=b"")
    assert loobric.make_request("DELETE", "/x") == {}


def test_404_raises_not_found(conn):
    conn.resp = FakeResponse(status=404, body=b'{"detail": "nope"}')
    with pytest.raises(loobric.NotFound):
        loobric.make_request("GET", "/x")


def test_401_raises_auth_required(conn):
    conn.resp = FakeResponse(status=401, body=b'{"detail": "no"}')
    with pytest.raises(loobric.AuthRequired):
        loobric.make_request("GET", "/x")


def test_500_raises_httperror_carrying_status(conn):
    conn.resp = FakeResponse(status=500, body=b"boom")
    with pytest.raises(loobric.HTTPError) as excinfo:
        loobric.make_request("GET", "/x")
    assert excinfo.value.status == 500
