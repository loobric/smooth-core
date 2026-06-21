# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""End-to-end integration tests: drive loobric (the reference client) against the
REAL app in-process.

The mocked unit suite only checks WHICH endpoint loobric calls; it never proves
the server accepts the request or that loobric parses the real response. These
tests run loobric's Client + CLI command functions through the actual
routers/DB/validation, which is what catches response-shape and acceptance bugs
(the audit `logs` shape, empty-`{}` bodies, etc.).

A transport bridge sends loobric's requests through a solo-mode TestClient
(db_session-isolated), faithfully mirroring `make_request`'s success/error
contract. `make_request`'s own raw-HTTP request-building is unit-tested
separately (test_loobric_transport.py).
"""
import importlib.util
import json
import pathlib

import pytest

_LOOBRIC = pathlib.Path(__file__).resolve().parents[2] / "loobric.py"
_spec = importlib.util.spec_from_file_location("loobric", _LOOBRIC)
loobric = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(loobric)


def _bridge(test_client):
    """A loobric transport that calls the in-process app, mirroring make_request:
    parsed JSON on 2xx, the same LoobricError subclasses on error."""
    def transport(method, endpoint, body=None, extra_headers=None, require_auth=False,
                  base_url=None, api_key=None, session_cookie=None,
                  raw_body=None, content_type=None):
        url = "/api/v1/" + endpoint.lstrip("/")
        if raw_body is not None:
            headers = {"Content-Type": content_type} if content_type else {}
            resp = test_client.request(method, url, content=raw_body, headers=headers)
        else:
            resp = test_client.request(method, url, json=body)
        if 200 <= resp.status_code < 300:
            return resp.json() if resp.content else {}
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise loobric._http_error(resp.status_code, detail)
    return transport


@pytest.fixture
def app_client(db_session, monkeypatch):
    monkeypatch.setenv("SMOOTH_SOLO", "1")
    from fastapi.testclient import TestClient
    from smooth.main import create_app
    from smooth.api.auth import get_db
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c


@pytest.fixture
def cli(app_client, monkeypatch):
    """Route loobric's command functions + Client through the in-process app, and
    return a bridged Client for tests that need raw ids."""
    bridge = _bridge(app_client)
    monkeypatch.setattr(loobric, "_client", lambda: loobric.Client(transport=bridge))
    monkeypatch.setattr(loobric, "BASE_URL", "http://app")
    return loobric.Client(transport=bridge)


# --------------------------------------------------------------------------
# The loop, end to end through the CLI command functions.
# --------------------------------------------------------------------------

@pytest.mark.integration
def test_full_loop_through_cli(cli, capsys):
    loobric.create_machine("millstone", controller="linuxcnc")
    loobric.push_table("millstone", ["3:1/4 downcut:6.35", "7:vee:6.0"])
    loobric.show_tool_table("millstone")
    out = capsys.readouterr().out
    assert "T3" in out and "T7" in out and "unbound" in out

    loobric.create_record_from_entry("millstone", 3, name="1/4 downcut")
    loobric.show_tool_table("millstone")
    assert "bound ->" in capsys.readouterr().out

    loobric.list_tools()
    assert "1/4 downcut" in capsys.readouterr().out


@pytest.mark.integration
def test_machines_and_sets(cli, capsys):
    loobric.create_machine("millstone")
    loobric.create_set("Drawer A")
    loobric.link_machine("Drawer A", "millstone")
    loobric.list_machines()
    assert "millstone" in capsys.readouterr().out
    loobric.list_tool_sets()
    assert "Drawer A" in capsys.readouterr().out


@pytest.mark.integration
def test_bind_then_unbind(cli, capsys):
    loobric.create_machine("m1")
    loobric.push_table("m1", ["5:probe:3.0"])
    loobric.create_record_from_entry("m1", 5, name="probe")
    loobric.unbind_entry("m1", 5)
    loobric.show_tool_table("m1")
    assert "unbound" in capsys.readouterr().out


@pytest.mark.integration
def test_inbox_lists_cleanly(cli, capsys):
    loobric.list_pending()
    assert "Inbox is empty" in capsys.readouterr().out


@pytest.mark.integration
def test_audit_after_activity(cli, capsys):
    loobric.create_machine("m1")
    capsys.readouterr()
    loobric.list_audit()
    out = capsys.readouterr().out
    assert "CREATE" in out and "machine_record" in out


@pytest.mark.integration
def test_keys_lifecycle(cli, capsys):
    loobric.create_key("k1", scopes="read")
    capsys.readouterr()
    loobric.list_keys()
    out = capsys.readouterr().out
    assert "k1" in out and "active" in out


@pytest.mark.integration
def test_assert_door(cli, capsys):
    loobric.create_set("S")
    capsys.readouterr()
    sid = cli.list_tool_sets()[0]["internal"]["id"]
    loobric.assert_canonical("tool-set-records", sid, "name", "Renamed")
    assert "Asserted" in capsys.readouterr().out
    assert cli.get_tool_set(sid)["canonical"]["name"]["value"] == "Renamed"


@pytest.mark.integration
def test_observe_door(cli):
    loobric.create_machine("m1")
    mid = cli.list_machines()[0]["internal"]["id"]
    cli.create_entry(mid)
    eid = cli.list_entries(mid)[0]["internal"]["id"]
    cli.observe_field("tool-table-entry-records", eid, "tool_number", 4,
                      client="linuxcnc", machine="m1")
    assert cli.get_entry(eid)["canonical"]["tool_number"]["value"] == 4


@pytest.mark.integration
def test_sync_client_section(cli):
    loobric.create_set("S")
    sid = cli.list_tool_sets()[0]["internal"]["id"]
    cli.sync_client_section("tool-set-records", sid, "freecad", {"fctl": "x"})
    assert cli.get_tool_set(sid)["clients"]["freecad"]["data"] == {"fctl": "x"}


@pytest.mark.integration
def test_set_members(cli):
    loobric.create_set("S")
    sid = cli.list_tool_sets()[0]["internal"]["id"]
    inst = cli.create_tool_record()
    iid = inst["internal"]["id"]
    cli.set_members(sid, [{"tool_record_id": iid, "number": 3}])
    members = cli.get_tool_set(sid)["canonical"]["members"]
    assert any(m["tool_record_id"] == iid for m in members)


@pytest.mark.integration
def test_add_and_remove_from_set_round_trip(cli):
    """add_to_set/remove_from_set against the live members door: add preserves
    existing members and skips duplicates; remove drops only the named tool."""
    loobric.create_set("Drawer")
    sid = cli.list_tool_sets()[0]["internal"]["id"]
    a = cli.create_tool_record()["internal"]["id"]
    b = cli.create_tool_record()["internal"]["id"]

    cli.add_to_set(sid, [a])
    cli.add_to_set(sid, [a, b])                 # `a` already present -> not duplicated
    ids = [m["tool_record_id"] for m in cli.get_tool_set(sid)["canonical"]["members"]]
    assert sorted(ids) == sorted([a, b])
    assert ids.count(a) == 1

    cli.remove_from_set(sid, [a])
    ids = [m["tool_record_id"] for m in cli.get_tool_set(sid)["canonical"]["members"]]
    assert ids == [b]                           # only `a` removed, `b` kept


@pytest.mark.integration
def test_catalog_records(cli):
    rec = cli.create_catalog_record(source="manufacturer:kennametal", fields={
        "name": {"value": "1/4in 2FL Endmill"},
        "manufacturer": {"value": "Kennametal"},
        "product_code": {"value": "B201"},
        "geometry": {"diameter": {"value": 6.35, "unit": "mm"}},
    })
    rid = rec["internal"]["id"]
    # The server stamps provenance — the client never wrote a `source`.
    assert rec["canonical"]["name"]["source"] == "asserted:manufacturer:kennametal"
    assert rec["canonical"]["geometry"]["diameter"]["source"] == \
        "asserted:manufacturer:kennametal"
    assert any(r["internal"]["id"] == rid for r in cli.list_catalog_records())
    assert cli.get_catalog_record(rid)["internal"]["id"] == rid


@pytest.mark.integration
def test_create_catalog_record_via_cli_stdin(cli, capsys, monkeypatch):
    """The acceptance path: JSON on stdin + --source -> a stamped record."""
    import io
    monkeypatch.setattr(loobric.sys, "stdin",
                        io.StringIO('{"name": {"value": "Spot Drill"}, '
                                    '"manufacturer": {"value": "Acme"}, '
                                    '"product_code": {"value": "SD-90"}}'))
    loobric.create_catalog_record(source="manufacturer:acme")
    out = capsys.readouterr().out
    assert "Spot Drill" in out and "asserted:manufacturer:acme" in out
    rec = cli.list_catalog_records()[0]
    assert rec["canonical"]["product_code"]["value"] == "SD-90"
    assert rec["canonical"]["product_code"]["source"] == "asserted:manufacturer:acme"


@pytest.mark.integration
def test_create_catalog_record_identity_floor(cli, monkeypatch):
    """Missing manufacturer/product_code -> the server rejects it (HTTP 400)."""
    import io
    monkeypatch.setattr(loobric.sys, "stdin",
                        io.StringIO('{"name": {"value": "Nameless"}}'))
    with pytest.raises(loobric.HTTPError):
        cli.create_catalog_record(source="human@cli",
                                  fields={"name": {"value": "Nameless"}})


@pytest.mark.integration
def test_catalog_resolver_by_product_code_and_ambiguity(cli, capsys):
    """The resolver accepts id/name/product_code; an ambiguous name prints
    candidates rather than guessing."""
    cli.create_catalog_record(source="manufacturer:acme", fields={
        "name": {"value": "Endmill"}, "manufacturer": {"value": "Acme"},
        "product_code": {"value": "A-100"}})
    cli.create_catalog_record(source="manufacturer:acme", fields={
        "name": {"value": "Endmill"}, "manufacturer": {"value": "Acme"},
        "product_code": {"value": "A-200"}})
    # Unique product_code resolves cleanly.
    loobric.show_catalog_record("A-200")
    out = capsys.readouterr().out
    assert "A-200" in out and "asserted:manufacturer:acme" in out
    # The shared name is ambiguous -> candidates listed, no guess.
    with pytest.raises(SystemExit):
        loobric.show_catalog_record("Endmill")
    err = capsys.readouterr().err
    assert "ambiguous" in err and "A-100" in err and "A-200" in err


@pytest.mark.integration
def test_create_record_from_catalog_makes_an_unbound_linked_instance(cli, capsys):
    """End to end (M2 #26): author a catalog record, then create-record
    --from-catalog -> a new UNBOUND instance that links the catalog type with
    requester-asserted provenance, measured geometry and status unknown."""
    cli.create_catalog_record(source="manufacturer:kennametal", fields={
        "name": {"value": "1/4in 2FL Endmill"},
        "manufacturer": {"value": "Kennametal"},
        "product_code": {"value": "B201"},
        "geometry": {"diameter": {"value": 6.35, "unit": "mm"}},
    })
    capsys.readouterr()

    loobric.create_record_from_catalog("B201")          # resolve by product code
    out = capsys.readouterr().out
    assert "unbound" in out and "1/4in 2FL Endmill" in out

    instances = cli.list_tool_records()
    assert len(instances) == 1
    inst = instances[0]
    link = inst["canonical"]["catalog_type_id"]
    assert link["value"] and link["source"].startswith("asserted:")
    assert inst["canonical"]["geometry"] == {}          # measured geometry unknown
    # Unbound: no machine entry references it.
    assert cli.list_entries() == []


@pytest.mark.integration
def test_create_record_from_catalog_with_qa_stamps_manufacturer_provenance(
        cli, capsys, tmp_path):
    """End to end (M2 #27): create-record --from-catalog --qa qa.json --cert ->
    an UNBOUND instance whose MEASURED geometry carries observed:manufacturer@
    <serial> (the middle rung of the gradient — manufacturer QA, not the shop)."""
    cli.create_catalog_record(source="manufacturer:kennametal", fields={
        "name": {"value": "1/4in 2FL Endmill"},
        "manufacturer": {"value": "Kennametal"},
        "product_code": {"value": "B201"},
        "geometry": {"diameter": {"value": 6.35, "unit": "mm"}},
    })
    capsys.readouterr()
    qa = tmp_path / "qa.json"
    qa.write_text(json.dumps({"diameter": {"value": 6.34, "unit": "mm"},
                              "length": {"value": 50.0, "unit": "mm"}}))

    loobric.create_record_from_catalog("B201", qa_path=str(qa),
                                       cert="kennametal@SN12345")
    out = capsys.readouterr().out
    assert "unbound" in out and "SN12345" in out

    inst = cli.list_tool_records()[0]
    geo = inst["canonical"]["geometry"]
    assert geo["diameter"]["value"] == 6.34
    assert geo["diameter"]["source"] == "observed:manufacturer@SN12345"
    assert geo["length"]["source"] == "observed:manufacturer@SN12345"


@pytest.mark.integration
def test_create_record_from_catalog_qa_requires_cert(cli, capsys, tmp_path):
    """--cert is required iff --qa: the QA file with no cert exits non-zero and
    creates no instance."""
    cli.create_catalog_record(source="manufacturer:acme", fields={
        "name": {"value": "Spot Drill"}, "manufacturer": {"value": "Acme"},
        "product_code": {"value": "SD-90"}})
    capsys.readouterr()
    qa = tmp_path / "qa.json"
    qa.write_text(json.dumps({"diameter": {"value": 3.0, "unit": "mm"}}))
    with pytest.raises(SystemExit):
        loobric.create_record_from_catalog("SD-90", qa_path=str(qa), cert=None)
    assert "--qa requires --cert" in capsys.readouterr().err
    assert cli.list_tool_records() == []


@pytest.mark.integration
def test_create_record_from_catalog_twice_yields_two_instances(cli, capsys):
    """No dedup: each --from-catalog call mints a new, distinct instance."""
    cli.create_catalog_record(source="manufacturer:acme", fields={
        "name": {"value": "Spot Drill"}, "manufacturer": {"value": "Acme"},
        "product_code": {"value": "SD-90"}})
    capsys.readouterr()
    loobric.create_record_from_catalog("SD-90")
    loobric.create_record_from_catalog("SD-90")
    ids = {i["internal"]["id"] for i in cli.list_tool_records()}
    assert len(ids) == 2


@pytest.mark.integration
def test_changes_works_for_v2_records(cli):
    """Change-detection now operates on the v2 sectioned records (R12 fixed);
    the retired legacy entity types are no longer accepted."""
    assert cli.changes_max_version("tool_instance_records")["max_version"] == 0
    cli.create_tool_record()
    cli.create_tool_record()
    assert cli.changes_max_version("tool_instance_records")["max_version"] >= 1
    changed = cli.changes_since_version("tool_instance_records", 0)
    assert changed["count"] == 2
    with pytest.raises(loobric.HTTPError):                  # legacy type -> 400
        cli.changes_max_version("tool_instances")


@pytest.mark.integration
def test_backup_export_runs(cli, capsys):
    loobric.backup_export()
    out = capsys.readouterr().out
    assert "entities" in out or "metadata" in out


@pytest.mark.integration
def test_backup_roundtrip_captures_v2_data(cli, capsys):
    """R9: backup/restore now captures the v2 sectioned records (it used to back
    up only the empty legacy tables). Export -> wipe -> import restores them."""
    loobric.create_machine("millstone", controller="linuxcnc")
    loobric.push_table("millstone", ["3:downcut:6.35"])
    loobric.create_record_from_entry("millstone", 3, name="downcut")
    capsys.readouterr()

    backup = cli.export_backup()
    assert len(backup["entities"]["machine_records"]) == 1
    assert len(backup["entities"]["tool_instance_records"]) == 1
    assert len(backup["entities"]["tool_table_entry_records"]) == 1

    cli.reset_account()
    assert cli.list_machines() == []

    cli.import_backup(json.dumps(backup))
    assert len(cli.list_machines()) == 1
    assert len(cli.list_tool_records()) == 1
    assert len(cli.list_entries()) == 1


@pytest.mark.integration
def test_reset_clears_tool_data(cli, capsys):
    loobric.create_machine("m1")
    capsys.readouterr()
    loobric.reset_account(assume_yes=True)
    capsys.readouterr()
    loobric.list_machines()
    assert "No machines" in capsys.readouterr().out


@pytest.mark.integration
def test_whoami_raises_in_solo(cli):
    # /auth/me is session-based; solo mode has no session -> a clean LoobricError,
    # not a crash. (Documented limitation.)
    with pytest.raises(loobric.LoobricError):
        cli.whoami()
