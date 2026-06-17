# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Regression suite for the loobric.py CLI.

This suite exists because the v2 cutover (the flat ToolRecord/machines facade
was retired in favour of the sectioned *-records API, docs/TOOL_SCHEMA.md) left
the CLI pointed at dead endpoints for an entire release. Every test here mocks
``loobric.make_request`` and asserts the *contract the CLI depends on*:

  - the HTTP method + path each command hits (so a path regressing to the
    retired flat facade fails loudly), and
  - that the CLI parses the three-section response shape
    ({internal, canonical, clients}) rather than the old flat top-level fields.

``test_no_command_touches_the_retired_flat_facade`` is the drift-class guard:
it drives every management command and asserts no call lands on a v1 path.
"""
import importlib.util
import pathlib

import pytest

# Load loobric.py (a top-level script, not a package module) by path so the
# suite is immune to the repo's mixed test-package layout.
_LOOBRIC_PATH = pathlib.Path(__file__).resolve().parents[2] / "loobric.py"
_spec = importlib.util.spec_from_file_location("loobric", _LOOBRIC_PATH)
loobric = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(loobric)


# ---------------------------------------------------------------------------
# Canned v2 sectioned records (the shape the live routers actually emit).
# ---------------------------------------------------------------------------

MACHINE = {
    "internal": {"id": "machineid1", "version": 1,
                 "created_at": "t", "updated_at": "t"},
    "canonical": {
        "name": {"value": "Haas Mini", "source": "asserted:cfg"},
        "controller_type": {"value": "linuxcnc", "source": "asserted:cfg"},
    },
    "clients": {},
}

INSTANCE = {
    "internal": {"id": "instanceid1", "version": 3,
                 "created_at": "t", "updated_at": "t"},
    "canonical": {
        "name": {"value": "1/4 downcut", "source": "asserted:human@web"},
        "catalog_type_id": {"value": None, "source": "unknown"},
        "geometry": {
            "diameter": {"value": 6.35, "unit": "mm",
                         "source": "observed:linuxcnc@haas"},
            "shape": {"value": "endmill", "source": "asserted:human@web"},
        },
    },
    "clients": {},
}

ENTRY = {
    "internal": {"id": "slotid1", "machine_id": "machineid1", "version": 2,
                 "created_at": "t", "updated_at": "t"},
    "canonical": {
        "tool_number": {"value": 3, "source": "observed:linuxcnc@haas"},
        "bound_instance_id": {"value": None, "source": "unknown"},
        "description": {"value": "quarter inch", "source": "observed:linuxcnc@haas"},
        "offsets": {"diameter": {"value": 6.35, "source": "observed:linuxcnc@haas"}},
    },
    "clients": {},
}

TOOLSET = {
    "internal": {"id": "setid1", "version": 5,
                 "created_at": "t", "updated_at": "t"},
    "canonical": {
        "name": {"value": "Drawer A", "source": "asserted:human@web"},
        "machine_id": {"value": None, "source": "unknown"},
        "members": [{"tool_record_id": "instanceid1",
                     "number": {"value": 3, "source": "asserted:human@web"}}],
    },
    "clients": {},
}

INBOX_ITEM = {
    "id": "proposalid000000000000000000000000000",
    "confidence": 0.91,
    "reason": "diameter and description match",
    "slot": {"id": "slotid1", "machine_id": "machineid1", "tool_number": 3},
    "proposed_instance": {"id": "instanceid1", "name": "1/4 downcut",
                          "diameter": 6.35},
}

COVERAGE = {
    "set_id": "setid1",
    "machine_id": "machineid1",
    "applicable": True,
    "members": [
        {"tool_record_id": "instanceid1", "set_number": 3,
         "machine_tool_number": 3, "slot_id": "slotid1", "status": "in_sync",
         "collides": False, "collides_with": []},
        {"tool_record_id": "instanceid9", "set_number": 9,
         "machine_tool_number": None, "slot_id": None,
         "status": "absent_on_machine", "collides": False, "collides_with": []},
    ],
    "slots": [
        {"slot_id": "slotid7", "tool_number": 7, "bound_instance_id": "instanceX",
         "status": "machine_only"},
    ],
    "summary": {"total_members": 2, "total_slots": 2, "in_sync": 1,
                "number_mismatch": 0, "absent_on_machine": 1,
                "number_collision": 0, "machine_only": 1, "unbound_slot": 0},
}

# Paths from the retired flat facade. Any call whose path begins with one of
# these (after the leading slash) is the exact drift class this suite guards.
RETIRED_PREFIXES = ("/tool-records", "/machines", "/tool-sets", "/inbox")


class Recorder:
    """A stand-in for ``loobric.make_request`` that records every call and
    returns realistic sectioned data routed by method + endpoint."""

    def __init__(self):
        self.calls = []

    def __call__(self, method, endpoint, body=None, extra_headers=None,
                 require_auth=False):
        self.calls.append({"method": method, "endpoint": endpoint, "body": body})
        if method == "GET":
            if endpoint.startswith("/machine-records"):
                return {"items": [MACHINE]}
            if endpoint.startswith("/tool-instance-records"):
                return {"items": [INSTANCE]}
            if endpoint.endswith("/coverage"):
                return COVERAGE
            if endpoint.startswith("/tool-set-records"):
                return {"items": [TOOLSET]}
            if endpoint.startswith("/tool-table-entry-records"):
                return {"items": [ENTRY]}
            if endpoint.startswith("/instance-inbox"):
                return {"items": [INBOX_ITEM]}
        if method == "POST":
            if endpoint.endswith("/confirm"):
                return {"status": "confirmed", "slot_id": "slotid1",
                        "instance_id": "instanceid1"}
            if endpoint.endswith("/reject"):
                return {"status": "rejected"}
            if endpoint.endswith("/bind"):
                return {"internal": ENTRY["internal"]}
            if endpoint.endswith("/unbind"):
                return ENTRY
            if endpoint.endswith("/adopt"):
                return {"instance_id": "instanceid1", "slot": ENTRY}
            if endpoint.endswith("/assert"):
                return TOOLSET
            if endpoint.endswith("/reconcile"):
                return {**TOOLSET, "unreconciled": ["instanceid9"]}
        if method == "DELETE":
            return {"deleted": endpoint.rsplit("/", 1)[-1]}
        return {}

    def of(self, method):
        return [c for c in self.calls if c["method"] == method]

    def last(self, method):
        matches = self.of(method)
        assert matches, f"expected at least one {method} call, got {self.calls}"
        return matches[-1]


@pytest.fixture
def api(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(loobric, "make_request", rec)
    return rec


# ---------------------------------------------------------------------------
# Listing commands: correct endpoint + sectioned parsing.
# ---------------------------------------------------------------------------

def test_list_machines_hits_v2_and_parses_sections(api, capsys):
    loobric.list_machines()
    assert api.last("GET")["endpoint"] == "/machine-records"
    out = capsys.readouterr().out
    assert "machineid1" in out          # internal.id, not a flat top-level id
    assert "Haas Mini" in out           # canonical.name.value
    assert "linuxcnc" in out            # canonical.controller_type.value


def test_list_tools_hits_v2_and_parses_geometry(api, capsys):
    loobric.list_tools()
    assert api.last("GET")["endpoint"] == "/tool-instance-records"
    out = capsys.readouterr().out
    assert "instanceid1" in out
    assert "1/4 downcut" in out         # canonical.name.value
    assert "endmill" in out             # canonical.geometry.shape.value
    assert "6.35mm" in out              # canonical.geometry.diameter value + unit


def test_list_tool_sets_hits_v2_and_counts_members(api, capsys):
    loobric.list_tool_sets()
    assert api.last("GET")["endpoint"] == "/tool-set-records"
    out = capsys.readouterr().out
    assert "Drawer A" in out
    assert "1 tool record" in out       # canonical.members length


def test_inbox_parses_slot_and_proposed_instance(api, capsys):
    loobric.list_pending()
    assert api.last("GET")["endpoint"] == "/instance-inbox"
    out = capsys.readouterr().out
    assert "T3" in out                  # slot.tool_number
    assert "1/4 downcut" in out         # proposed_instance.name


def test_show_tool_table_queries_by_machine_id(api, capsys):
    loobric.show_tool_table("machineid1")
    get_paths = [c["endpoint"] for c in api.of("GET")]
    assert "/machine-records" in get_paths
    assert "/tool-table-entry-records?machine_id=machineid1" in get_paths
    out = capsys.readouterr().out
    assert "T3" in out                  # canonical.tool_number.value
    assert "unbound" in out             # canonical.bound_instance_id.value is None


# ---------------------------------------------------------------------------
# Inbox resolution.
# ---------------------------------------------------------------------------

def test_resolve_confirm_posts_to_instance_inbox(api, capsys):
    loobric.resolve_pending("proposal", "confirm")
    post = api.last("POST")
    assert post["endpoint"] == "/instance-inbox/%s/confirm" % INBOX_ITEM["id"]
    out = capsys.readouterr().out
    assert "Linked" in out and "1/4 downcut" in out


def test_resolve_reject_posts_to_instance_inbox(api):
    loobric.resolve_pending("proposal", "reject")
    assert api.last("POST")["endpoint"].endswith("/reject")


# ---------------------------------------------------------------------------
# Delete commands: path-based, single id, no body.
# ---------------------------------------------------------------------------

def test_delete_machine_is_path_based_no_body(api):
    loobric.delete_machine("machineid1", assume_yes=True)
    d = api.last("DELETE")
    assert d["endpoint"] == "/machine-records/machineid1"
    assert d["body"] is None


def test_delete_tool_is_path_based_no_body(api):
    loobric.delete_tool("instanceid1", assume_yes=True)
    d = api.last("DELETE")
    assert d["endpoint"] == "/tool-instance-records/instanceid1"
    assert d["body"] is None


def test_delete_entry_resolves_slot_then_deletes_by_record_id(api):
    loobric.delete_entry("machineid1", 3, assume_yes=True)
    d = api.last("DELETE")
    assert d["endpoint"] == "/tool-table-entry-records/slotid1"
    assert d["body"] is None


# ---------------------------------------------------------------------------
# Bind / unbind / adopt: key off the slot's own record id.
# ---------------------------------------------------------------------------

def test_bind_targets_slot_record_with_instance_id(api):
    loobric.bind_entry("machineid1", 3, "instanceid1")
    post = api.last("POST")
    assert post["endpoint"] == "/tool-table-entry-records/slotid1/bind"
    assert post["body"] == {"instance_id": "instanceid1"}


def test_unbind_targets_slot_record(api):
    loobric.unbind_entry("machineid1", 3)
    assert api.last("POST")["endpoint"] == "/tool-table-entry-records/slotid1/unbind"


def test_create_record_uses_adopt(api, capsys):
    loobric.create_record_from_entry("machineid1", 3, name="quarter inch")
    post = api.last("POST")
    assert post["endpoint"] == "/tool-table-entry-records/slotid1/adopt"
    assert post["body"] == {"name": "quarter inch"}
    assert "instanceid1"[:8] in capsys.readouterr().out


def test_create_record_without_name_sends_no_body(api):
    loobric.create_record_from_entry("machineid1", 3)
    assert api.last("POST")["body"] is None


def test_resolve_slot_errors_when_tool_number_absent(api, capsys):
    with pytest.raises(SystemExit):
        loobric.bind_entry("machineid1", 99, "instanceid1")
    assert "no tool T99" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Tool-set ↔ machine: link-machine / reconcile / coverage.
# ---------------------------------------------------------------------------

def test_link_machine_asserts_machine_id_on_the_set(api, capsys):
    loobric.link_machine("setid1", "machineid1")
    post = api.last("POST")
    assert post["endpoint"] == "/tool-set-records/setid1/assert"
    assert post["body"]["path"] == "machine_id"
    assert post["body"]["value"] == "machineid1"
    assert "mirrors machine" in capsys.readouterr().out


def test_reconcile_posts_and_reports_unreconciled(api, capsys):
    loobric.reconcile_set("setid1")
    assert api.last("POST")["endpoint"] == "/tool-set-records/setid1/reconcile"
    out = capsys.readouterr().out
    assert "reconciled" in out
    assert "instanceid9"[:8] in out          # the member with no machine slot


def test_coverage_hits_endpoint_and_surfaces_absent_tools(api, capsys):
    loobric.show_coverage("setid1")
    assert api.last("GET")["endpoint"] == "/tool-set-records/setid1/coverage"
    out = capsys.readouterr().out
    assert "in sync" in out                  # the in_sync member
    assert "NOT ON MACHINE" in out           # the absent_on_machine member
    assert "not yet set up on the machine" in out   # the call-to-action summary


def test_coverage_explains_when_set_is_unlinked(api, capsys, monkeypatch):
    def rec(method, endpoint, body=None, extra_headers=None, require_auth=False):
        if endpoint.endswith("/coverage"):
            return {"set_id": "setid1", "machine_id": None, "applicable": False,
                    "reason": "set is not linked to a machine (machine_id unknown)"}
        return {"items": [TOOLSET]}
    monkeypatch.setattr(loobric, "make_request", rec)
    loobric.show_coverage("setid1")
    assert "not linked to a machine" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Drift-class guard: the test that would have caught the v2 cutover miss.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("invoke", [
    lambda: loobric.list_machines(),
    lambda: loobric.list_tools(),
    lambda: loobric.list_tool_sets(),
    lambda: loobric.list_pending(),
    lambda: loobric.show_tool_table("machineid1"),
    lambda: loobric.resolve_pending("proposal", "confirm"),
    lambda: loobric.delete_machine("machineid1", assume_yes=True),
    lambda: loobric.delete_tool("instanceid1", assume_yes=True),
    lambda: loobric.delete_entry("machineid1", 3, assume_yes=True),
    lambda: loobric.bind_entry("machineid1", 3, "instanceid1"),
    lambda: loobric.unbind_entry("machineid1", 3),
    lambda: loobric.create_record_from_entry("machineid1", 3, name="x"),
    lambda: loobric.link_machine("setid1", "machineid1"),
    lambda: loobric.reconcile_set("setid1"),
    lambda: loobric.show_coverage("setid1"),
])
def test_no_command_touches_the_retired_flat_facade(api, invoke):
    invoke()
    for call in api.calls:
        path = call["endpoint"].split("?", 1)[0]
        for retired in RETIRED_PREFIXES:
            assert not path.startswith(retired), (
                "%s %s hits the retired flat facade %r — the exact v2-cutover "
                "drift this suite guards against"
                % (call["method"], call["endpoint"], retired))
