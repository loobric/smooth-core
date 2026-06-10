# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Inbox API — pending-review state awaiting a human (smooth-core#5).

The inbox holds items sync cannot decide on its own (decision G2): today
binding proposals; frozen conflicts join with #7. Sync never blocks or
prompts — items accumulate here and the user resolves them from the web
inbox or the CLI, whenever they're next at a browser or terminal.

Assumptions:
- GET /api/v1/inbox lists OPEN items only, newest first
- Items carry a `type` discriminator ("binding_proposal"; "conflict" later)
- POST /{id}/confirm binds the entry to the proposed record (sticky) and
  closes the proposal; POST /{id}/reject closes it and the pair is never
  re-proposed
- Acting on a resolved proposal is 409; unknown ids are 404
- Confirm/reject are audited
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, get_authenticated_user
from smooth.api.machines import ToolTableEntryResponse, entry_to_response
from smooth.database.schema import User, ToolItem, ToolTableEntry, BindingProposal, Machine
from smooth.audit import create_audit_log


router = APIRouter(prefix="/api/v1/inbox", tags=["inbox"])


class ProposedRecordSummary(BaseModel):
    """Just enough of the ToolRecord to judge the proposal."""
    id: str
    name: str
    geometry: Optional[dict]


class InboxItem(BaseModel):
    """One item awaiting review."""
    id: str
    type: str
    confidence: float
    reason: str
    created_at: str
    machine_name: str
    entry: ToolTableEntryResponse
    proposed_record: ProposedRecordSummary


class InboxResponse(BaseModel):
    items: List[InboxItem]


def _proposal_to_item(db: Session, proposal: BindingProposal) -> Optional[InboxItem]:
    entry = db.query(ToolTableEntry).filter(
        ToolTableEntry.id == proposal.entry_id
    ).first()
    record = db.query(ToolItem).filter(
        ToolItem.id == proposal.proposed_record_id
    ).first()
    if entry is None or record is None:
        return None
    machine = db.query(Machine).filter(Machine.id == entry.machine_id).first()
    return InboxItem(
        id=proposal.id,
        type="binding_proposal",
        confidence=proposal.confidence,
        reason=proposal.reason,
        created_at=proposal.created_at.isoformat(),
        machine_name=machine.name if machine else "?",
        entry=entry_to_response(entry),
        proposed_record=ProposedRecordSummary(
            id=record.id,
            name=record.name or record.description or "",
            geometry=record.geometry,
        ),
    )


def _owned_proposal(db: Session, user: User, proposal_id: str) -> BindingProposal:
    proposal = db.query(BindingProposal).filter(
        BindingProposal.id == proposal_id
    ).first()
    if proposal is None or (proposal.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="Inbox item not found")
    if proposal.status != "open":
        raise HTTPException(
            status_code=409, detail=f"Proposal already {proposal.status}"
        )
    return proposal


@router.get("", response_model=InboxResponse)
def list_inbox(
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """List open items awaiting review, newest first."""
    proposals = (
        db.query(BindingProposal)
        .filter(BindingProposal.user_id == user.id, BindingProposal.status == "open")
        .order_by(BindingProposal.created_at.desc())
        .all()
    )
    items = [_proposal_to_item(db, p) for p in proposals]
    return InboxResponse(items=[i for i in items if i is not None])


@router.post("/{proposal_id}/confirm", response_model=InboxItem)
def confirm_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Bind the entry to the proposed record; the binding is sticky."""
    proposal = _owned_proposal(db, user, proposal_id)
    entry = db.query(ToolTableEntry).filter(
        ToolTableEntry.id == proposal.entry_id
    ).first()
    if entry is None:
        raise HTTPException(status_code=409, detail="Entry no longer exists")

    entry.tool_record_id = proposal.proposed_record_id
    entry.version += 1
    entry.updated_by = user.id
    proposal.status = "confirmed"
    proposal.version += 1
    proposal.updated_by = user.id
    db.flush()
    create_audit_log(
        session=db, user_id=user.id, operation="CONFIRM",
        entity_type="binding_proposal", entity_id=proposal.id,
        changes={"entry_id": entry.id, "tool_record_id": entry.tool_record_id},
    )
    item = _proposal_to_item(db, proposal)
    db.commit()
    return item


@router.post("/{proposal_id}/reject", response_model=InboxItem)
def reject_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Close the proposal; this (entry, record) pair is never re-proposed."""
    proposal = _owned_proposal(db, user, proposal_id)
    proposal.status = "rejected"
    proposal.version += 1
    proposal.updated_by = user.id
    db.flush()
    create_audit_log(
        session=db, user_id=user.id, operation="REJECT",
        entity_type="binding_proposal", entity_id=proposal.id,
        changes={"entry_id": proposal.entry_id,
                 "proposed_record_id": proposal.proposed_record_id},
    )
    item = _proposal_to_item(db, proposal)
    db.commit()
    return item
