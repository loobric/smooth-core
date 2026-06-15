# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
ToolSetRecord facade — an agnostic named collection, sectioned
(docs/TOOL_SCHEMA.md). NOT a FreeCAD library; a .fctl/Fusion lib/drawer is one
client's representation in clients.<name>.data.

Members carry a canonical, provenance-tagged `number`. When the set is linked to
a machine (machine_id asserted), `reconcile` inherits each member's number from
that machine's slots — the machine is observed fact, the set conforms.
"""
import copy
from datetime import datetime, UTC
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, get_authenticated_user
from smooth.database.schema import (
    User, ToolSetRecord as Row, ToolTableEntryRecord as EntryRow,
)
from smooth.audit import create_audit_log
from smooth.contract import (
    ToolSet, ToolSetCanonical, Provenance, UNKNOWN, LaneViolation, reject_out_of_lane,
)

router = APIRouter(prefix="/api/v1/tool-set-records", tags=["tool-set-records"])

ASSERTABLE_PATHS = {"name", "machine_id"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _blank_canonical() -> dict:
    return {
        "name": {"value": None, "source": UNKNOWN},
        "machine_id": {"value": None, "source": UNKNOWN},
        "members": [],
    }


def _response(row: Row) -> dict:
    doc = {
        "internal": {
            "id": row.id, "version": row.version,
            "created_at": _iso(row.created_at), "updated_at": _iso(row.updated_at),
        },
        "canonical": row.canonical,
        "clients": row.clients,
    }
    ToolSet.model_validate(doc)
    return doc


def _owned(db: Session, user: User, record_id: str) -> Optional[Row]:
    return db.query(Row).filter(Row.id == record_id, Row.user_id == user.id).first()


def _validate_canonical(canonical: dict) -> None:
    try:
        ToolSetCanonical.model_validate(canonical)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid canonical: %s" % exc)


# -- requests -----------------------------------------------------------------

class CreateRequest(BaseModel):
    client: Optional[str] = None
    client_version: Optional[str] = None
    client_item_id: Optional[str] = None
    data: dict = {}


class AssertRequest(BaseModel):
    path: str
    value: Any = None
    actor: str


class MemberIn(BaseModel):
    tool_record_id: str
    number: Optional[int] = None


class MembersRequest(BaseModel):
    members: List[MemberIn]
    actor: str


# -- endpoints ----------------------------------------------------------------

@router.post("")
def create_set(payload: CreateRequest, db: Session = Depends(get_db),
               user: User = Depends(get_authenticated_user)):
    clients = {}
    if payload.client:
        clients[payload.client] = {
            "client_version": payload.client_version or "",
            "client_item_id": payload.client_item_id,
            "created_at": _now(), "updated_at": _now(), "data": payload.data or {},
        }
    row = Row(machine_id=None, canonical=_blank_canonical(), clients=clients,
              user_id=user.id, created_by=user.id, updated_by=user.id)
    db.add(row)
    db.flush()
    create_audit_log(session=db, user_id=user.id, operation="CREATE",
                     entity_type="tool_set_record", entity_id=row.id)
    db.commit()
    return _response(row)


@router.get("")
def list_sets(db: Session = Depends(get_db),
              user: User = Depends(get_authenticated_user)):
    rows = db.query(Row).filter(Row.user_id == user.id).order_by(Row.created_at).all()
    return {"items": [_response(r) for r in rows]}


@router.get("/{record_id}")
def get_set(record_id: str, db: Session = Depends(get_db),
            user: User = Depends(get_authenticated_user)):
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return _response(row)


@router.put("/{record_id}/clients/{client}")
def write_client_section(record_id: str, client: str, payload: dict,
                         db: Session = Depends(get_db),
                         user: User = Depends(get_authenticated_user)):
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    try:
        write = reject_out_of_lane(payload)
    except LaneViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    clients = copy.deepcopy(row.clients)
    existing = clients.get(client) or {}
    clients[client] = {
        "client_version": write.client_version,
        "client_item_id": write.client_item_id,
        "created_at": existing.get("created_at") or _now(),
        "updated_at": _now(), "data": write.data,
    }
    row.clients = clients
    row.version += 1
    row.updated_by = user.id
    create_audit_log(session=db, user_id=user.id, operation="SYNC",
                     entity_type="tool_set_record", entity_id=row.id,
                     changes={"client": client})
    db.commit()
    return _response(row)


@router.post("/{record_id}/assert")
def assert_canonical(record_id: str, req: AssertRequest,
                     db: Session = Depends(get_db),
                     user: User = Depends(get_authenticated_user)):
    """Assert `name` or the `machine_id` link. Linking a machine makes the set
    machine-bound (its member numbers can then be reconciled from slots)."""
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    if req.path not in ASSERTABLE_PATHS:
        raise HTTPException(status_code=400, detail="cannot assert %r" % req.path)
    canonical = copy.deepcopy(row.canonical)
    canonical[req.path] = {"value": req.value, "source": Provenance.asserted(req.actor)}
    _validate_canonical(canonical)
    row.canonical = canonical
    if req.path == "machine_id":
        row.machine_id = req.value
    row.version += 1
    row.updated_by = user.id
    create_audit_log(session=db, user_id=user.id, operation="ASSERT",
                     entity_type="tool_set_record", entity_id=row.id,
                     changes={"path": req.path})
    db.commit()
    return _response(row)


@router.post("/{record_id}/members")
def set_members(record_id: str, req: MembersRequest, db: Session = Depends(get_db),
                user: User = Depends(get_authenticated_user)):
    """Replace membership. A supplied number is asserted; an omitted one is
    unknown (until reconciled from a machine, if the set is machine-bound)."""
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    members = []
    for m in req.members:
        number = ({"value": m.number, "source": Provenance.asserted(req.actor)}
                  if m.number is not None else {"value": None, "source": UNKNOWN})
        members.append({"tool_record_id": m.tool_record_id, "number": number})
    canonical = copy.deepcopy(row.canonical)
    canonical["members"] = members
    _validate_canonical(canonical)
    row.canonical = canonical
    row.version += 1
    row.updated_by = user.id
    create_audit_log(session=db, user_id=user.id, operation="MEMBERS",
                     entity_type="tool_set_record", entity_id=row.id,
                     changes={"count": len(members)})
    db.commit()
    return _response(row)


@router.post("/{record_id}/reconcile")
def reconcile_numbers(record_id: str, db: Session = Depends(get_db),
                      user: User = Depends(get_authenticated_user)):
    """For a machine-bound set, inherit each member's number from that machine's
    slots (machine wins). Members with no slot are reported as unreconciled
    rather than silently renumbered."""
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    machine_id = (row.canonical.get("machine_id") or {}).get("value")
    if not machine_id:
        raise HTTPException(status_code=400,
                            detail="set is not linked to a machine (machine_id unknown)")

    # instance_id -> the slot entry that holds it on this machine
    slot_of = {}
    for e in db.query(EntryRow).filter(
            EntryRow.user_id == user.id, EntryRow.machine_id == machine_id).all():
        if e.bound_instance_id:
            slot_of[e.bound_instance_id] = e

    canonical = copy.deepcopy(row.canonical)
    unreconciled = []
    for member in canonical.get("members", []):
        entry = slot_of.get(member["tool_record_id"])
        if entry is None:
            unreconciled.append(member["tool_record_id"])
            continue
        tn = entry.canonical.get("tool_number") or {}
        member["number"] = {"value": tn.get("value"),
                            "source": tn.get("source") or UNKNOWN}
    _validate_canonical(canonical)
    row.canonical = canonical
    row.version += 1
    row.updated_by = user.id
    create_audit_log(session=db, user_id=user.id, operation="RECONCILE",
                     entity_type="tool_set_record", entity_id=row.id,
                     changes={"unreconciled": unreconciled})
    db.commit()
    return {**_response(row), "unreconciled": unreconciled}
