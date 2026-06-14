# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Binding engine — heuristic matching of ToolTableEntries to ToolRecords.

This is the server-side identity resolution that closes the sync loop
(decisions D3/G2): when a controller pushes an unbound entry, the server
proposes the best-matching ToolRecord for human review. The engine NEVER
binds anything itself; its only output is BindingProposal rows.

Scoring (documented in the #5 contract; tune with early-adopter feedback):
- diameter agreement (entry.offsets.diameter vs record.geometry.diameter,
  within 1%) contributes 0.55
- name similarity (entry.description vs record.name, difflib ratio)
  contributes up to 0.45
- the single best candidate at >= 0.5 total is proposed; a name alone can
  never trigger a proposal, a diameter alone can

Rules:
- only unbound entries are considered
- at most one OPEN proposal per entry
- a rejected (entry, record) pair is never proposed again
"""
from difflib import SequenceMatcher
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session

from smooth.database.schema import User, ToolItem, ToolTableEntry, BindingProposal
from smooth.audit import create_audit_log

PROPOSAL_THRESHOLD = 0.5
DIAMETER_WEIGHT = 0.55
NAME_WEIGHT = 0.45
DIAMETER_TOLERANCE = 0.01  # relative


def score_candidate(entry: ToolTableEntry, record: ToolItem) -> Tuple[float, str]:
    """Score how plausibly a record is the tool behind a table entry.

    Returns:
        (score, reason): score in [0, 1] and a human-readable explanation.
    """
    score = 0.0
    reasons = []

    entry_dia = (entry.offsets or {}).get("diameter")
    record_dia = (record.geometry or {}).get("diameter")
    if entry_dia and record_dia:
        if abs(entry_dia - record_dia) <= DIAMETER_TOLERANCE * max(entry_dia, record_dia):
            score += DIAMETER_WEIGHT
            reasons.append(f"diameter matches ({record_dia})")

    if entry.description and record.name:
        ratio = SequenceMatcher(
            None, entry.description.lower(), record.name.lower()
        ).ratio()
        if ratio > 0:
            score += NAME_WEIGHT * ratio
            reasons.append(f"name similarity {ratio:.0%}")

    return score, ", ".join(reasons) or "no overlap"


def propose_binding(db: Session, user: User, entry: ToolTableEntry) -> Optional[BindingProposal]:
    """Create the best-match proposal for an unbound entry, if any.

    Assumptions:
    - Caller commits; this only adds to the session
    - Returns None when the entry is bound, already has an open proposal,
      or no candidate reaches the threshold
    """
    if entry.tool_record_id is not None:
        return None

    open_exists = db.query(BindingProposal).filter(
        BindingProposal.entry_id == entry.id,
        BindingProposal.status == "open",
    ).first()
    if open_exists:
        return None

    rejected_record_ids = {
        p.proposed_record_id
        for p in db.query(BindingProposal).filter(
            BindingProposal.entry_id == entry.id,
            BindingProposal.status == "rejected",
        ).all()
    }

    candidates = db.query(ToolItem).filter(ToolItem.user_id == user.id).all()
    best = None  # (score, reason, record)
    for record in candidates:
        if record.id in rejected_record_ids:
            continue
        score, reason = score_candidate(entry, record)
        if score >= PROPOSAL_THRESHOLD and (best is None or score > best[0]):
            best = (score, reason, record)

    if best is None:
        return None

    score, reason, record = best
    proposal = BindingProposal(
        entry_id=entry.id,
        proposed_record_id=record.id,
        confidence=round(score, 3),
        reason=reason,
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(proposal)
    db.flush()
    create_audit_log(
        session=db, user_id=user.id, operation="PROPOSE",
        entity_type="binding_proposal", entity_id=proposal.id,
        changes={"entry_id": entry.id, "proposed_record_id": record.id,
                 "confidence": proposal.confidence},
    )
    return proposal


def close_open_proposal_on_bind(
    db: Session, user: User, entry_id: str, bound_record_id: str
) -> None:
    """Resolve an entry's open proposal when the entry is explicitly bound.

    Explicit binding (UI or client intent) overrides the heuristic
    suggestion, so the open proposal must not linger in the inbox:
    - confirmed when the user bound to the very record proposed
    - rejected otherwise — the user chose a different identity, and that
      (entry, record) pair should not be proposed again (mirrors the inbox
      reject rule)
    Caller commits.
    """
    proposal = db.query(BindingProposal).filter(
        BindingProposal.entry_id == entry_id,
        BindingProposal.status == "open",
    ).first()
    if proposal is None:
        return
    proposal.status = (
        "confirmed" if proposal.proposed_record_id == bound_record_id else "rejected"
    )
    proposal.version += 1
    proposal.updated_by = user.id


def delete_proposals_for_entries(db: Session, entry_ids: List[str]) -> None:
    """Remove proposals referencing entries that are being deleted."""
    if not entry_ids:
        return
    db.query(BindingProposal).filter(
        BindingProposal.entry_id.in_(entry_ids)
    ).delete(synchronize_session=False)
