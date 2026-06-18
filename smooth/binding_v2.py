# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Binding engine for the sectioned schema — proposes which instance an unbound
entry holds, for human review (docs/TOOL_SCHEMA.md; successor to binding.py).

The entry OBSERVED a tool in it (a diameter); the engine proposes the best-
matching existing instance. It never installs anything — its only output is
EntryProposal rows. A diameter agreement (within 1%) is, as before, sufficient
to propose; name matching is left for when entries carry an observed description.
"""
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from smooth.database.schema import (
    User, ToolInstanceRecord as InstanceRow, ToolTableEntryRecord as EntryRow,
    EntryProposal,
)
from smooth.audit import create_audit_log

PROPOSAL_THRESHOLD = 0.5
DIAMETER_WEIGHT = 0.55
DIAMETER_TOLERANCE = 0.01  # relative


def _diameter(canonical: dict, *path: str):
    node = canonical or {}
    for p in path:
        node = (node or {}).get(p) or {}
    return node.get("value")


def score(entry: EntryRow, instance: InstanceRow) -> Tuple[float, str]:
    """How plausibly `instance` is the tool observed in `entry`."""
    entry_dia = _diameter(entry.canonical, "offsets", "diameter")
    inst_dia = _diameter(instance.canonical, "geometry", "diameter")
    if entry_dia and inst_dia and \
            abs(entry_dia - inst_dia) <= DIAMETER_TOLERANCE * max(entry_dia, inst_dia):
        return DIAMETER_WEIGHT, "diameter matches (%s)" % inst_dia
    return 0.0, "no overlap"


def propose_for_entry(db: Session, user: User, entry: EntryRow) -> Optional[EntryProposal]:
    """Create the best-match open proposal for an unbound entry, if any. Caller
    commits. Returns None when the entry is bound, already has an open proposal,
    or nothing clears the threshold."""
    if entry.bound_instance_id is not None:
        return None
    if db.query(EntryProposal).filter(
            EntryProposal.entry_id == entry.id, EntryProposal.status == "open").first():
        return None
    rejected = {p.proposed_instance_id for p in db.query(EntryProposal).filter(
        EntryProposal.entry_id == entry.id, EntryProposal.status == "rejected").all()}

    best = None  # (score, reason, instance)
    for inst in db.query(InstanceRow).filter(InstanceRow.user_id == user.id).all():
        if inst.id in rejected:
            continue
        s, reason = score(entry, inst)
        if s >= PROPOSAL_THRESHOLD and (best is None or s > best[0]):
            best = (s, reason, inst)
    if best is None:
        return None

    s, reason, inst = best
    proposal = EntryProposal(
        entry_id=entry.id, proposed_instance_id=inst.id,
        confidence=round(s, 3), reason=reason, status="open",
        user_id=user.id, created_by=user.id, updated_by=user.id)
    db.add(proposal)
    db.flush()
    create_audit_log(session=db, user_id=user.id, operation="PROPOSE",
                     entity_type="entry_proposal", entity_id=proposal.id,
                     changes={"entry_id": entry.id, "instance_id": inst.id,
                              "confidence": proposal.confidence})
    return proposal


def close_open_proposal_on_bind(db: Session, user: User, entry_id: str,
                                bound_instance_id: str) -> None:
    """When a entry is bound explicitly, resolve its open proposal: confirmed if
    it named the bound instance, else rejected (the human chose a different
    tool; don't propose that pair again). Caller commits."""
    proposal = db.query(EntryProposal).filter(
        EntryProposal.entry_id == entry_id, EntryProposal.status == "open").first()
    if proposal is None:
        return
    proposal.status = ("confirmed" if proposal.proposed_instance_id == bound_instance_id
                       else "rejected")
    proposal.version += 1
    proposal.updated_by = user.id
