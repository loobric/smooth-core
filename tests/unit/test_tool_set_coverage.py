# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for the pure coverage diff (smooth.api.tool_set_records.compute_coverage).

The function is the read-only generalization of `reconcile`'s join: it never
touches a database, so every status can be exercised from plain dicts.
"""
from smooth.api.tool_set_records import compute_coverage
from smooth.contract import Provenance, UNKNOWN


def _member(instance, number=None, actor="freecad"):
    field = ({"value": number, "source": Provenance.asserted(actor)}
             if number is not None else {"value": None, "source": UNKNOWN})
    return {"tool_record_id": instance, "number": field}


def _slot(slot_id, tool_number, bound_instance_id):
    return {"id": slot_id, "tool_number": tool_number,
            "bound_instance_id": bound_instance_id}


def _status(coverage, instance):
    for m in coverage["members"]:
        if m["tool_record_id"] == instance:
            return m["status"]
    raise AssertionError("no member %r" % instance)


def test_in_sync_when_bound_and_numbers_agree():
    canonical = {"members": [_member("inst-A", 5)]}
    entries = [_slot("s1", 5, "inst-A")]
    cov = compute_coverage(canonical, entries)
    assert _status(cov, "inst-A") == "in_sync"
    assert cov["summary"]["in_sync"] == 1


def test_in_sync_when_set_number_unknown():
    # No asserted set number yet -> bound is enough; reconcile would adopt 5.
    canonical = {"members": [_member("inst-A")]}
    entries = [_slot("s1", 5, "inst-A")]
    cov = compute_coverage(canonical, entries)
    assert _status(cov, "inst-A") == "in_sync"


def test_absent_on_machine_is_the_promised_but_not_yet_real_tool():
    canonical = {"members": [_member("inst-A", 5), _member("inst-C", 9)]}
    entries = [_slot("s1", 5, "inst-A")]            # nothing holds inst-C
    cov = compute_coverage(canonical, entries)
    assert _status(cov, "inst-C") == "absent_on_machine"
    assert cov["summary"]["absent_on_machine"] == 1


def test_number_mismatch_when_bound_but_set_claims_a_different_number():
    canonical = {"members": [_member("inst-A", 9)]}  # set says T9
    entries = [_slot("s1", 5, "inst-A")]             # machine has it at T5
    cov = compute_coverage(canonical, entries)
    row = cov["members"][0]
    assert row["status"] == "number_mismatch"
    assert row["set_number"] == 9 and row["machine_tool_number"] == 5


def test_machine_only_and_unbound_slot_are_reported_from_the_table_side():
    canonical = {"members": [_member("inst-A", 5)]}
    entries = [
        _slot("s1", 5, "inst-A"),     # accounted for by the set
        _slot("s2", 7, "inst-X"),     # bound to a tool the set doesn't know
        _slot("s3", 8, None),         # empty pocket
    ]
    cov = compute_coverage(canonical, entries)
    by_id = {s["slot_id"]: s["status"] for s in cov["slots"]}
    assert by_id == {"s2": "machine_only", "s3": "unbound_slot"}
    assert cov["summary"]["machine_only"] == 1
    assert cov["summary"]["unbound_slot"] == 1
    # the in-sync slot is accounted for, not echoed as leftover
    assert "s1" not in by_id


def test_number_collision_flags_two_members_claiming_one_number():
    canonical = {"members": [_member("inst-A", 5), _member("inst-B", 5)]}
    entries = [_slot("s1", 5, "inst-A")]
    cov = compute_coverage(canonical, entries)
    flagged = {m["tool_record_id"]: m for m in cov["members"]}
    assert flagged["inst-A"]["collides"] and flagged["inst-B"]["collides"]
    assert flagged["inst-A"]["collides_with"] == ["inst-B"]
    assert cov["summary"]["number_collision"] == 2


def test_empty_machine_makes_every_member_absent():
    canonical = {"members": [_member("inst-A", 1), _member("inst-B", 2)]}
    cov = compute_coverage(canonical, entries=[])
    assert cov["summary"]["absent_on_machine"] == 2
    assert cov["summary"]["total_slots"] == 0
    assert cov["slots"] == []


def test_mutates_nothing():
    canonical = {"members": [_member("inst-A", 5)]}
    entries = [_slot("s1", 5, "inst-A")]
    import copy
    before = copy.deepcopy(canonical)
    compute_coverage(canonical, entries)
    assert canonical == before
