# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Instance inbox — the human review surface for the sectioned binding engine
(docs/TOOL_SCHEMA.md). Lists unbound slots with the instance the engine thinks
sits in them; confirm installs it, reject remembers. Nothing auto-installs.
"""
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, get_authenticated_user
from smooth.database.schema import (
    User, ToolInstanceRecord as InstanceRow, ToolTableEntryRecord as SlotRow,
    SlotProposal,
)
from smooth.audit import create_audit_log
from smooth.binding_v2 import propose_for_slot
from smooth.contract import Provenance, UNKNOWN

router = APIRouter(prefix="/api/v1/instance-inbox", tags=["instance-inbox"])


def _value(canonical: dict, *path: str):
    node = canonical or {}
    for p in path:
        node = (node or {}).get(p) or {}
    return node.get("value")


@router.get("")
def inbox(db: Session = Depends(get_db),
          user: User = Depends(get_authenticated_user)):
    """Generate proposals for any unbound slots, then list the open ones,
    enriched with the slot and the proposed instance."""
    for slot in db.query(SlotRow).filter(
            SlotRow.user_id == user.id, SlotRow.bound_instance_id.is_(None)).all():
        propose_for_slot(db, user, slot)
    db.commit()

    items = []
    for p in db.query(SlotProposal).filter(
            SlotProposal.user_id == user.id, SlotProposal.status == "open").all():
        slot = db.query(SlotRow).filter(SlotRow.id == p.slot_id).first()
        inst = db.query(InstanceRow).filter(InstanceRow.id == p.proposed_instance_id).first()
        if slot is None or inst is None:
            continue
        items.append({
            "id": p.id, "confidence": p.confidence, "reason": p.reason,
            "slot": {"id": slot.id, "machine_id": slot.machine_id,
                     "tool_number": _value(slot.canonical, "tool_number")},
            "proposed_instance": {"id": inst.id,
                                  "name": _value(inst.canonical, "name"),
                                  "diameter": _value(inst.canonical, "geometry", "diameter")},
        })
    return {"items": items}


def _resolve(db: Session, user: User, proposal_id: str) -> SlotProposal:
    p = db.query(SlotProposal).filter(
        SlotProposal.id == proposal_id, SlotProposal.user_id == user.id).first()
    if p is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    if p.status != "open":
        raise HTTPException(status_code=409, detail="proposal already %s" % p.status)
    return p


@router.post("/{proposal_id}/confirm")
def confirm(proposal_id: str, db: Session = Depends(get_db),
            user: User = Depends(get_authenticated_user)):
    """Same tool: install the proposed instance in the slot (install-once
    enforced), and mark the proposal confirmed."""
    p = _resolve(db, user, proposal_id)
    slot = db.query(SlotRow).filter(SlotRow.id == p.slot_id,
                                    SlotRow.user_id == user.id).first()
    if slot is None:
        raise HTTPException(status_code=404, detail="slot gone")

    other = db.query(SlotRow).filter(
        SlotRow.user_id == user.id,
        SlotRow.bound_instance_id == p.proposed_instance_id,
        SlotRow.id != slot.id).first()
    if other is not None:
        raise HTTPException(status_code=409,
                            detail="instance already installed elsewhere — unbind it first")

    canonical = dict(slot.canonical)
    canonical["bound_instance_id"] = {"value": p.proposed_instance_id,
                                      "source": Provenance.asserted("human@inbox")}
    slot.canonical = canonical
    slot.bound_instance_id = p.proposed_instance_id
    slot.version += 1
    slot.updated_by = user.id
    p.status = "confirmed"
    p.version += 1
    p.updated_by = user.id
    create_audit_log(session=db, user_id=user.id, operation="CONFIRM",
                     entity_type="slot_proposal", entity_id=p.id,
                     changes={"slot_id": slot.id, "instance_id": p.proposed_instance_id})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="instance already installed elsewhere")
    return {"status": "confirmed", "slot_id": slot.id,
            "instance_id": p.proposed_instance_id}


@router.post("/{proposal_id}/reject")
def reject(proposal_id: str, db: Session = Depends(get_db),
           user: User = Depends(get_authenticated_user)):
    """Different tool: drop the suggestion; this (slot, instance) pair is never
    proposed again."""
    p = _resolve(db, user, proposal_id)
    p.status = "rejected"
    p.version += 1
    p.updated_by = user.id
    create_audit_log(session=db, user_id=user.id, operation="REJECT",
                     entity_type="slot_proposal", entity_id=p.id)
    db.commit()
    return {"status": "rejected"}
