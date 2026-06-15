# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
ToolTableEntryRecord facade — a machine slot, sectioned (docs/TOOL_SCHEMA.md).

Like the instance tracer, plus the install-once invariant: a physical instance
is in at most one slot, globally. The hard guarantee is the UNIQUE index on the
`bound_instance_id` column; the bind endpoint adds the friendly experience —
a 409 naming where the tool already lives, and an atomic `move`.
"""
import copy
from datetime import datetime, UTC
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, get_authenticated_user
from smooth.database.schema import User, ToolTableEntryRecord as Row
from smooth.audit import create_audit_log
from smooth.contract import (
    ToolTableEntry, EntryCanonical, Provenance, UNKNOWN,
    LaneViolation, reject_out_of_lane,
)

router = APIRouter(prefix="/api/v1/tool-table-entry-records", tags=["tool-table-entries"])

# A machine may only OBSERVE these slot facts; the binding is set via /bind.
OBSERVABLE_PATHS = {"tool_number", "offsets.diameter", "offsets.z", "offsets.x", "offsets.y"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _blank_canonical() -> dict:
    return {
        "tool_number": {"value": None, "source": UNKNOWN},
        "bound_instance_id": {"value": None, "source": UNKNOWN},
        "offsets": {},
    }


def _response(row: Row) -> dict:
    doc = {
        "internal": {
            "id": row.id, "machine_id": row.machine_id, "version": row.version,
            "created_at": _iso(row.created_at), "updated_at": _iso(row.updated_at),
        },
        "canonical": row.canonical,
        "clients": row.clients,
    }
    ToolTableEntry.model_validate(doc)
    return doc


def _owned(db: Session, user: User, record_id: str) -> Optional[Row]:
    return db.query(Row).filter(Row.id == record_id, Row.user_id == user.id).first()


def _validate_canonical(canonical: dict) -> None:
    try:
        EntryCanonical.model_validate(canonical)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid canonical: %s" % exc)


def _set_path(canonical: dict, path: str, field: dict) -> dict:
    out = copy.deepcopy(canonical)
    node = out
    parts = path.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = field
    return out


def _slot_label(row: Row) -> str:
    n = (row.canonical.get("tool_number") or {}).get("value")
    return "machine %s slot %s" % (row.machine_id[:8], n if n is not None else "?")


# -- requests -----------------------------------------------------------------

class CreateRequest(BaseModel):
    machine_id: str
    client: Optional[str] = None
    client_version: Optional[str] = None
    client_item_id: Optional[str] = None
    data: dict = {}


class ObserveRequest(BaseModel):
    path: str
    value: Any = None
    unit: Optional[str] = None
    client: str
    machine: str


class BindRequest(BaseModel):
    instance_id: str
    actor: str = "human@inbox"
    move: bool = False      # if the instance is installed elsewhere, relocate it


# -- endpoints ----------------------------------------------------------------

@router.post("")
def create_entry(payload: CreateRequest, db: Session = Depends(get_db),
                 user: User = Depends(get_authenticated_user)):
    clients = {}
    if payload.client:
        clients[payload.client] = {
            "client_version": payload.client_version or "",
            "client_item_id": payload.client_item_id,
            "created_at": _now(), "updated_at": _now(), "data": payload.data or {},
        }
    row = Row(machine_id=payload.machine_id, bound_instance_id=None,
              canonical=_blank_canonical(), clients=clients,
              user_id=user.id, created_by=user.id, updated_by=user.id)
    db.add(row)
    db.flush()
    create_audit_log(session=db, user_id=user.id, operation="CREATE",
                     entity_type="tool_table_entry_record", entity_id=row.id)
    db.commit()
    return _response(row)


@router.get("")
def list_entries(machine_id: Optional[str] = None, db: Session = Depends(get_db),
                 user: User = Depends(get_authenticated_user)):
    q = db.query(Row).filter(Row.user_id == user.id)
    if machine_id:
        q = q.filter(Row.machine_id == machine_id)
    return {"items": [_response(r) for r in q.order_by(Row.created_at).all()]}


@router.get("/{record_id}")
def get_entry(record_id: str, db: Session = Depends(get_db),
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
                     entity_type="tool_table_entry_record", entity_id=row.id,
                     changes={"client": client})
    db.commit()
    return _response(row)


@router.post("/{record_id}/observe")
def observe_canonical(record_id: str, req: ObserveRequest,
                      db: Session = Depends(get_db),
                      user: User = Depends(get_authenticated_user)):
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    if req.path not in OBSERVABLE_PATHS:
        raise HTTPException(status_code=400,
                            detail="%r is not observable on a slot" % req.path)
    field = {"value": req.value, "source": Provenance.observed(req.client, req.machine)}
    if req.unit is not None:
        field["unit"] = req.unit
    canonical = _set_path(row.canonical, req.path, field)
    _validate_canonical(canonical)
    row.canonical = canonical
    row.version += 1
    row.updated_by = user.id
    create_audit_log(session=db, user_id=user.id, operation="OBSERVE",
                     entity_type="tool_table_entry_record", entity_id=row.id,
                     changes={"path": req.path, "source": field["source"]})
    db.commit()
    return _response(row)


def _set_binding(row: Row, instance_id: Optional[str], actor: str) -> None:
    field = ({"value": instance_id, "source": Provenance.asserted(actor)}
             if instance_id else {"value": None, "source": UNKNOWN})
    row.canonical = _set_path(row.canonical, "bound_instance_id", field)
    row.bound_instance_id = instance_id          # the unique-indexed column
    row.version += 1


@router.post("/{record_id}/bind")
def bind_instance(record_id: str, req: BindRequest, db: Session = Depends(get_db),
                  user: User = Depends(get_authenticated_user)):
    """Install a physical instance in this slot. Install-once: if the instance
    is already in another slot, 409 (with where) unless move=true, which
    relocates it atomically."""
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")

    other = db.query(Row).filter(
        Row.user_id == user.id,
        Row.bound_instance_id == req.instance_id,
        Row.id != record_id,
    ).first()
    if other is not None:
        if not req.move:
            raise HTTPException(
                status_code=409,
                detail="instance %s is already installed in %s — unbind it "
                       "there first, or bind with move=true"
                       % (req.instance_id[:8], _slot_label(other)))
        _set_binding(other, None, req.actor)     # vacate the old slot
        other.updated_by = user.id
        create_audit_log(session=db, user_id=user.id, operation="UNBIND",
                         entity_type="tool_table_entry_record", entity_id=other.id,
                         changes={"reason": "moved", "to": record_id})

    _set_binding(row, req.instance_id, req.actor)
    row.updated_by = user.id
    create_audit_log(session=db, user_id=user.id, operation="BIND",
                     entity_type="tool_table_entry_record", entity_id=row.id,
                     changes={"instance_id": req.instance_id})
    try:
        db.commit()
    except IntegrityError:                        # unique index is the backstop
        db.rollback()
        raise HTTPException(status_code=409,
                            detail="instance %s is already installed elsewhere"
                                   % req.instance_id[:8])
    return _response(row)


@router.post("/{record_id}/unbind")
def unbind_instance(record_id: str, db: Session = Depends(get_db),
                    user: User = Depends(get_authenticated_user)):
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    _set_binding(row, None, "human@inbox")
    row.updated_by = user.id
    create_audit_log(session=db, user_id=user.id, operation="UNBIND",
                     entity_type="tool_table_entry_record", entity_id=row.id)
    db.commit()
    return _response(row)
