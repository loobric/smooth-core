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

CATALOG = {
    "internal": {"id": "catalogid1", "version": 1,
                 "created_at": "t", "updated_at": "t"},
    "canonical": {
        "name": {"value": "1/4in 2FL Endmill", "source": "asserted:manufacturer:kennametal"},
        "manufacturer": {"value": "Kennametal", "source": "asserted:manufacturer:kennametal"},
        "product_code": {"value": "B201", "source": "asserted:manufacturer:kennametal"},
        "geometry": {
            "diameter": {"value": 6.35, "unit": "mm",
                         "source": "asserted:manufacturer:kennametal"},
        },
    },
    "clients": {},
}

INBOX_ITEM = {
    "id": "proposalid000000000000000000000000000",
    "confidence": 0.91,
    "reason": "diameter and description match",
    "entry": {"id": "slotid1", "machine_id": "machineid1", "tool_number": 3},
    "proposed_instance": {"id": "instanceid1", "name": "1/4 downcut",
                          "diameter": 6.35},
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
                 require_auth=False, **kwargs):
        # **kwargs absorbs the per-call config (base_url/api_key/session_cookie)
        # the Client passes through make_request.
        self.calls.append({"method": method, "endpoint": endpoint, "body": body})
        if method == "GET":
            if endpoint.startswith("/machine-records"):
                return {"items": [MACHINE]}
            if endpoint.startswith("/tool-instance-records"):
                return {"items": [INSTANCE]}
            if endpoint == "/tool-set-records":
                return {"items": [TOOLSET]}
            if endpoint.startswith("/tool-set-records/"):
                return TOOLSET                       # GET one set (by id)
            if endpoint.startswith("/tool-table-entry-records"):
                return {"items": [ENTRY]}
            if endpoint.startswith("/tool-catalog-records"):
                return {"items": [CATALOG]}
            if endpoint.startswith("/instance-inbox"):
                return {"items": [INBOX_ITEM]}
            if endpoint == "/auth/me":
                return {"email": "admin@example.com", "role": "admin",
                        "is_admin": True, "id": "userid1"}
            if endpoint == "/version":
                return {"version": "0.1.0", "commit": "abc123def456"}
            if endpoint.startswith("/audit-logs"):
                return {"logs": [{"operation": "BIND", "created_at": "t",
                                  "entity_type": "tool_table_entry_record",
                                  "entity_id": "slotid1"}], "total_count": 1}
        if method == "POST":
            if endpoint.endswith("/confirm"):
                return {"status": "confirmed", "entry_id": "slotid1",
                        "instance_id": "instanceid1"}
            if endpoint.endswith("/reject"):
                return {"status": "rejected"}
            if endpoint.endswith("/bind"):
                # bind mints+binds when no instance_id is given; the response is
                # the slot record with the (possibly newly minted) instance id.
                return {**ENTRY, "canonical": {
                    **ENTRY["canonical"],
                    "bound_instance_id": {"value": "instanceid1",
                                          "source": "asserted:human@web"}}}
            if endpoint.endswith("/create-instance"):
                # the catalog->instance door returns the new (unbound) instance
                return INSTANCE
            if endpoint.endswith("/members"):
                return TOOLSET                       # replace-members door
            if endpoint.endswith("/unbind"):
                return ENTRY
            if endpoint.endswith("/sync"):
                return {"items": [ENTRY], "removed_tool_numbers": []}
            if endpoint.endswith("/assert"):
                if endpoint.startswith("/machine-records"):
                    return MACHINE
                if endpoint.startswith("/tool-instance-records"):
                    return INSTANCE
                return TOOLSET
            if endpoint == "/machine-records":
                return MACHINE
            if endpoint == "/tool-set-records":
                return TOOLSET
            if endpoint == "/tool-instance-records":
                return INSTANCE
            if endpoint == "/tool-catalog-records":
                return CATALOG
            if endpoint == "/tool-table-entry-records":
                return ENTRY
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
# Bind / unbind / create-record: key off the slot's own record id.
# ---------------------------------------------------------------------------

def test_bind_targets_slot_record_with_instance_id(api):
    loobric.bind_entry("machineid1", 3, "instanceid1")
    post = api.last("POST")
    assert post["endpoint"] == "/tool-table-entry-records/slotid1/bind"
    assert post["body"] == {"instance_id": "instanceid1"}


def test_unbind_targets_slot_record(api):
    loobric.unbind_entry("machineid1", 3)
    assert api.last("POST")["endpoint"] == "/tool-table-entry-records/slotid1/unbind"


def test_create_record_uses_bind(api, capsys):
    loobric.create_record_from_entry("machineid1", 3, name="quarter inch")
    post = api.last("POST")
    assert post["endpoint"] == "/tool-table-entry-records/slotid1/bind"
    assert post["body"] == {"name": "quarter inch"}
    assert "instanceid1"[:8] in capsys.readouterr().out


def test_create_record_without_name_sends_empty_body(api):
    # mint-on-bind needs a JSON body; with no name it is an empty object, not None
    loobric.create_record_from_entry("machineid1", 3)
    assert api.last("POST")["body"] == {}


def test_create_record_entry_form_routes_to_bind_and_binds(api, capsys):
    """The dispatcher's entry branch: MACHINE TOOL_NUMBER -> the bind door, and
    the outcome message names the BOUND result (unchanged from before)."""
    import types
    args = types.SimpleNamespace(machine="machineid1", tool_number=3,
                                 from_catalog=None, name="quarter inch")
    loobric.create_record(args)
    post = api.last("POST")
    assert post["endpoint"] == "/tool-table-entry-records/slotid1/bind"
    assert post["body"] == {"name": "quarter inch"}
    assert "bound it" in capsys.readouterr().out


def test_create_record_catalog_form_routes_to_create_instance_unbound(api, capsys):
    """The dispatcher's catalog branch: --from-catalog -> the create-instance
    door, and the outcome message names the UNBOUND result."""
    import types
    args = types.SimpleNamespace(machine=None, tool_number=None,
                                 from_catalog="catalogid1", name=None)
    loobric.create_record(args)
    post = api.last("POST")
    assert post["endpoint"] == "/tool-catalog-records/catalogid1/create-instance"
    assert post["body"] == {}
    out = capsys.readouterr().out
    assert "unbound" in out                     # names the unbound outcome
    assert "1/4in 2FL Endmill" in out          # catalog name in the message


def test_create_record_catalog_form_passes_name_override(api):
    import types
    args = types.SimpleNamespace(machine=None, tool_number=None,
                                 from_catalog="catalogid1", name="relabel")
    loobric.create_record(args)
    assert api.last("POST")["body"] == {"name": "relabel"}


def test_create_record_catalog_qa_passes_qa_payload_and_cert(api, tmp_path):
    """--qa <file> + --cert flow the geometry-shaped QA payload and the cert
    through to the create-instance endpoint body (the server composes the
    observed:manufacturer@<serial> source — the client never sends a raw source)."""
    qa = tmp_path / "qa.json"
    qa.write_text('{"diameter": {"value": 6.34, "unit": "mm"}}')
    loobric.create_record_from_catalog("catalogid1", qa_path=str(qa),
                                       cert="kennametal@SN12345")
    body = api.last("POST")["body"]
    assert api.last("POST")["endpoint"] == \
        "/tool-catalog-records/catalogid1/create-instance"
    assert body["qa"] == {"diameter": {"value": 6.34, "unit": "mm"}}
    assert body["cert"] == "kennametal@SN12345"
    assert "source" not in str(body)            # client never writes provenance


def test_create_record_qa_without_cert_is_rejected(api, capsys, tmp_path):
    """--cert is required iff --qa: a QA file with no cert exits non-zero."""
    qa = tmp_path / "qa.json"
    qa.write_text('{"diameter": {"value": 6.34, "unit": "mm"}}')
    with pytest.raises(SystemExit):
        loobric.create_record_from_catalog("catalogid1", qa_path=str(qa), cert=None)
    assert "--qa requires --cert" in capsys.readouterr().err
    assert not api.of("POST")                    # rejected before any call


def test_create_record_cert_without_qa_is_rejected(api, capsys):
    """The other direction: a cert with no QA to certify exits non-zero."""
    with pytest.raises(SystemExit):
        loobric.create_record_from_catalog("catalogid1", qa_path=None,
                                           cert="kennametal@SN12345")
    assert "--cert requires --qa" in capsys.readouterr().err
    assert not api.of("POST")


def test_create_record_entry_form_rejects_qa_and_cert(api, capsys):
    """--qa/--cert are catalog-only: the entry form rejects them up front."""
    import types
    qa_args = types.SimpleNamespace(machine="machineid1", tool_number=3,
                                    from_catalog=None, name=None,
                                    qa="qa.json", cert=None)
    with pytest.raises(SystemExit):
        loobric.create_record(qa_args)
    assert "only valid with --from-catalog" in capsys.readouterr().err


def test_create_record_rejects_mixing_entry_and_catalog_forms(api, capsys):
    import types
    args = types.SimpleNamespace(machine="machineid1", tool_number=3,
                                 from_catalog="catalogid1", name=None)
    with pytest.raises(SystemExit):
        loobric.create_record(args)
    assert "cannot be combined" in capsys.readouterr().err


def test_create_record_requires_a_source(api, capsys):
    import types
    args = types.SimpleNamespace(machine=None, tool_number=None,
                                 from_catalog=None, name=None)
    with pytest.raises(SystemExit):
        loobric.create_record(args)
    assert "create-record needs" in capsys.readouterr().err


def test_resolve_slot_errors_when_tool_number_absent(api, capsys):
    with pytest.raises(SystemExit):
        loobric.bind_entry("machineid1", 99, "instanceid1")
    assert "no tool T99" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Tool-set ↔ machine: link-machine.
# ---------------------------------------------------------------------------

def test_link_machine_asserts_machine_id_on_the_set(api, capsys):
    loobric.link_machine("setid1", "machineid1")
    post = api.last("POST")
    assert post["endpoint"] == "/tool-set-records/setid1/assert"
    assert post["body"]["path"] == "machine_id"
    assert post["body"]["value"] == "machineid1"
    assert "linked to machine" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Stand up a machine and push a tool table (the start of the sync loop).
# ---------------------------------------------------------------------------

def test_create_machine_creates_then_asserts_name_and_controller(api, capsys):
    loobric.create_machine("millstone", controller="linuxcnc")
    posts = api.of("POST")
    assert posts[0]["endpoint"] == "/machine-records"            # create first
    asserted = {(c["endpoint"], c["body"]["path"], c["body"]["value"])
                for c in posts if c["endpoint"].endswith("/assert")}
    assert ("/machine-records/machineid1/assert", "name", "millstone") in asserted
    assert ("/machine-records/machineid1/assert", "controller_type", "linuxcnc") in asserted
    assert "Created machine 'millstone'" in capsys.readouterr().out


def test_create_set_creates_then_asserts_name(api):
    loobric.create_set("Drawer A")
    posts = api.of("POST")
    assert posts[0]["endpoint"] == "/tool-set-records"
    assert posts[1]["endpoint"] == "/tool-set-records/setid1/assert"
    assert posts[1]["body"]["path"] == "name"
    assert posts[1]["body"]["value"] == "Drawer A"


def test_push_syncs_slots_with_parsed_fields(api):
    loobric.push_table("machineid1", ["3:1/4 downcut:6.35", "7:chamfer"])
    sync = api.last("POST")
    assert sync["endpoint"] == "/tool-table-entry-records/sync"
    body = sync["body"]
    assert body["machine_id"] == "machineid1"
    assert {s["tool_number"] for s in body["entries"]} == {3, 7}
    s3 = next(s for s in body["entries"] if s["tool_number"] == 3)
    assert s3["description"] == "1/4 downcut"
    assert s3["offsets"]["diameter"] == 6.35
    s7 = next(s for s in body["entries"] if s["tool_number"] == 7)
    assert s7["description"] == "chamfer"
    assert "offsets" not in s7              # no diameter given -> no offsets


def test_push_snapshot_mode_is_explicit(api):
    loobric.push_table("machineid1", ["3"], snapshot=True)
    assert api.last("POST")["body"]["mode"] == "snapshot"


# ---------------------------------------------------------------------------
# Tool-set membership: add/remove are read-modify-write over the replace-only
# members door (GET the set, recompute, POST the full list).
# ---------------------------------------------------------------------------

def test_client_add_to_set_appends_and_dedupes(api):
    loobric.Client().add_to_set("setid1", ["instanceid1", "newtool99"])
    post = api.last("POST")
    assert post["endpoint"] == "/tool-set-records/setid1/members"
    ids = [m["tool_record_id"] for m in post["body"]["members"]]
    assert ids.count("instanceid1") == 1     # already a member -> not duplicated
    assert "newtool99" in ids                # the genuinely new one is appended
    assert post["body"]["actor"]             # the server stamps provenance from it


def test_client_add_to_set_preserves_existing_member_numbers(api):
    loobric.Client().add_to_set("setid1", ["newtool99"])
    members = api.last("POST")["body"]["members"]
    kept = next(m for m in members if m["tool_record_id"] == "instanceid1")
    assert kept["number"] == 3               # TOOLSET's existing asserted number, preserved
    added = next(m for m in members if m["tool_record_id"] == "newtool99")
    assert added["number"] is None           # a fresh member's number is unknown


def test_client_remove_from_set_drops_only_the_named_tool(api):
    loobric.Client().remove_from_set("setid1", ["instanceid1"])
    post = api.last("POST")
    assert post["endpoint"] == "/tool-set-records/setid1/members"
    ids = [m["tool_record_id"] for m in post["body"]["members"]]
    assert "instanceid1" not in ids


def test_add_to_set_cli_resolves_set_and_tools(api, capsys):
    loobric.add_to_set("setid1", ["instanceid1"])
    post = api.last("POST")
    assert post["endpoint"] == "/tool-set-records/setid1/members"
    assert any(m["tool_record_id"] == "instanceid1" for m in post["body"]["members"])
    assert "Added" in capsys.readouterr().out


def test_remove_from_set_cli_resolves_set_and_tools(api, capsys):
    loobric.remove_from_set("setid1", ["instanceid1"])
    post = api.last("POST")
    assert post["endpoint"] == "/tool-set-records/setid1/members"
    assert "Removed" in capsys.readouterr().out


def test_show_tool_set_lists_members_with_numbers(api, capsys):
    loobric.show_tool_set("setid1")
    out = capsys.readouterr().out
    assert "Tool Set" in out
    assert "Members: 1" in out
    assert "1/4 downcut" in out          # member tool name resolved from its id
    assert "T3" in out                   # the member's number


# ---------------------------------------------------------------------------
# Catalog records (M2): seeded create + browse + provenance.
# ---------------------------------------------------------------------------

def test_create_catalog_record_posts_actor_and_fields(api, capsys, monkeypatch):
    """--source becomes the `actor`; the JSON/flags carry values+units; the body
    never carries a `source` (the server stamps it)."""
    import io
    monkeypatch.setattr(loobric.sys, "stdin",
                        io.StringIO('{"name": {"value": "Endmill"}, '
                                    '"manufacturer": {"value": "Kennametal"}}'))
    loobric.create_catalog_record(source="manufacturer:kennametal",
                                  product_code="B201", diameter=6.35)
    post = api.last("POST")
    assert post["endpoint"] == "/tool-catalog-records"
    body = post["body"]
    assert body["actor"] == "manufacturer:kennametal"
    assert body["name"] == {"value": "Endmill"}
    assert body["product_code"] == {"value": "B201"}            # convenience flag
    assert body["geometry"]["diameter"] == {"value": 6.35, "unit": "mm"}
    assert "source" not in body                                  # never client-written
    assert "asserted:manufacturer:kennametal" in capsys.readouterr().out


def test_create_catalog_record_surfaces_the_409_reuse_funnel(capsys, monkeypatch):
    """A natural-key collision (HTTP 409) reaches the user as the server's funnel
    message — naming the existing record and inviting reuse — not a stack trace."""
    import io
    funnel = ("Kennametal B201 already exists as abc123 — create an instance "
              "from it, or edit that record.")

    def boom(*a, **k):
        raise loobric.HTTPError(409, funnel)

    monkeypatch.setattr(loobric, "make_request", boom)
    monkeypatch.setattr(loobric.sys, "stdin", io.StringIO(""))
    with pytest.raises(SystemExit):
        loobric._run(loobric.create_catalog_record,
                     source="manufacturer:kennametal", name="x",
                     manufacturer="Kennametal", product_code="B201")
    err = capsys.readouterr().err
    assert "already exists as abc123" in err
    assert "create an instance from it" in err


def test_list_catalog_records_hits_endpoint_and_shows_identity(api, capsys):
    loobric.list_catalog_records()
    assert api.last("GET")["endpoint"] == "/tool-catalog-records"
    out = capsys.readouterr().out
    assert "catalogid1" in out and "Kennametal" in out and "B201" in out


def test_show_catalog_record_resolves_and_shows_provenance(api, capsys):
    loobric.show_catalog_record("catalogid1")
    out = capsys.readouterr().out
    assert "1/4in 2FL Endmill" in out
    # every field is shown with its source badge
    assert "asserted:manufacturer:kennametal" in out
    assert "diameter" in out


def test_show_catalog_record_resolves_by_product_code(api, capsys):
    loobric.show_catalog_record("B201")
    assert "1/4in 2FL Endmill" in capsys.readouterr().out


def test_audit_reads_logs_list(api, capsys):
    # the /audit-logs response nests rows under "logs" (not "items")
    loobric.list_audit()
    assert api.last("GET")["endpoint"] == "/audit-logs"
    assert "BIND" in capsys.readouterr().out


def test_reset_hits_account_reset(api, capsys):
    loobric.reset_account(assume_yes=True)
    assert api.last("POST")["endpoint"] == "/account/reset"
    assert "reset" in capsys.readouterr().out.lower()


def test_list_keys_shows_revoked_state(monkeypatch, capsys):
    # Regression for the dogfood finding: a revoked key must not read as active.
    monkeypatch.setattr(loobric, "make_request", lambda *a, **k: [
        {"id": "k1", "name": "old", "scopes": [], "is_active": False}])
    loobric.list_keys()
    assert "REVOKED" in capsys.readouterr().out


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
    lambda: loobric.create_record_from_catalog("catalogid1"),
    lambda: loobric.link_machine("setid1", "machineid1"),
    lambda: loobric.create_machine("millstone", controller="linuxcnc"),
    lambda: loobric.create_set("Drawer A"),
    lambda: loobric.add_to_set("setid1", ["instanceid1"]),
    lambda: loobric.remove_from_set("setid1", ["instanceid1"]),
    lambda: loobric.show_tool_set("setid1"),
    lambda: loobric.push_table("machineid1", ["3:1/4 downcut:6.35"]),
    lambda: loobric.list_catalog_records(),
    lambda: loobric.show_catalog_record("catalogid1"),
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


# ---------------------------------------------------------------------------
# whoami: account identity + the server's build stamp (the "is this server
# running my code?" check). New server -> version+commit; old server -> the
# missing /version endpoint is itself reported as an older build.
# ---------------------------------------------------------------------------

def test_whoami_shows_server_account_and_build(api, capsys, monkeypatch):
    monkeypatch.setattr(loobric, "BASE_URL", "http://nas:8000")
    loobric.whoami()
    out = capsys.readouterr().out
    assert "Server: http://nas:8000" in out      # which server we're talking to
    assert "admin@example.com" in out
    assert "Build:  0.1.0 (abc123def456)" in out  # what code it's running
    assert any(c["endpoint"] == "/version" for c in api.of("GET"))


def test_whoami_reports_old_server_without_version_endpoint(monkeypatch, capsys):
    def fake(method, endpoint, **kwargs):
        if endpoint == "/version":
            raise loobric.NotFound(404, "Not Found")
        if endpoint == "/auth/me":
            return {"email": "a@b", "role": "user", "is_admin": False, "id": "x"}
        return {}
    monkeypatch.setattr(loobric, "make_request", fake)
    loobric.whoami()
    out = capsys.readouterr().out
    assert "older server" in out
