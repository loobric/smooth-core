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
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, get_authenticated_user
from smooth.database.schema import (
    User, ToolTableEntryRecord as Row, ToolInstanceRecord as InstanceRow,
)
from smooth.audit import create_audit_log
from smooth.binding_v2 import close_open_proposal_on_bind
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


class SlotIn(BaseModel):
    tool_number: int
    offsets: dict = {}          # plain values + optional <key>_unit, e.g. {"diameter": 6.35, "diameter_unit": "mm"}
    data: dict = {}             # the client section's opaque payload
    client_item_id: Optional[str] = None


class SlotSyncRequest(BaseModel):
    machine_id: str
    client: str                 # e.g. "linuxcnc"
    machine_name: str           # observation source: observed:<client>@<machine_name>
    client_version: str = ""
    mode: Literal["merge", "snapshot"] = "merge"
    force: bool = False
    slots: List[SlotIn]


@router.post("/sync")
def sync_slots(req: SlotSyncRequest, db: Session = Depends(get_db),
               user: User = Depends(get_authenticated_user)):
    """The machine-table push: upsert a machine's slots by tool_number in one
    call. Each slot's number+offsets are OBSERVED (the machine measured them)
    and the client section is written. mode=snapshot reconciles away slots
    absent from the payload (the controller is authoritative), guarded against a
    mass-wipe. Bindings survive an update; a removed slot's proposals are dropped.
    """
    existing = {}
    for r in db.query(Row).filter(Row.user_id == user.id,
                                  Row.machine_id == req.machine_id).all():
        tn = (r.canonical.get("tool_number") or {}).get("value")
        if tn is not None:
            existing[tn] = r
    src = Provenance.observed(req.client, req.machine_name)

    if req.mode == "snapshot" and not req.force and existing:
        present = {s.tool_number for s in req.slots}
        doomed = [tn for tn in existing if tn not in present]
        if doomed and (not req.slots or len(doomed) * 2 > len(existing)):
            raise HTTPException(status_code=409,
                detail="snapshot would remove %d of %d slots — refusing as a likely "
                       "partial read; resend with force=true if intended"
                       % (len(doomed), len(existing)))

    items = []
    present = set()
    for s in req.slots:
        present.add(s.tool_number)
        row = existing.get(s.tool_number)
        if row is None:
            row = Row(machine_id=req.machine_id, bound_instance_id=None,
                      canonical=_blank_canonical(), clients={},
                      user_id=user.id, created_by=user.id, updated_by=user.id)
            db.add(row)
            db.flush()
        canonical = copy.deepcopy(row.canonical)
        canonical["tool_number"] = {"value": s.tool_number, "source": src}
        offsets = canonical.setdefault("offsets", {})
        for key, value in s.offsets.items():
            if key.endswith("_unit"):
                continue
            field = {"value": value, "source": src}
            unit = s.offsets.get(key + "_unit")
            if unit:
                field["unit"] = unit
            offsets[key] = field
        _validate_canonical(canonical)
        row.canonical = canonical
        clients = copy.deepcopy(row.clients)
        existing_sec = clients.get(req.client) or {}
        clients[req.client] = {
            "client_version": req.client_version,
            "client_item_id": s.client_item_id,
            "created_at": existing_sec.get("created_at") or _now(),
            "updated_at": _now(), "data": s.data,
        }
        row.clients = clients
        row.version += 1
        row.updated_by = user.id
        items.append(row)

    removed = []
    if req.mode == "snapshot":
        from smooth.database.schema import SlotProposal
        for tn, row in existing.items():
            if tn in present:
                continue
            db.query(SlotProposal).filter(SlotProposal.slot_id == row.id).delete()
            db.delete(row)
            removed.append(tn)

    create_audit_log(session=db, user_id=user.id, operation="SYNC_TABLE",
                     entity_type="tool_table_entry_record", entity_id=req.machine_id,
                     changes={"client": req.client, "count": len(req.slots),
                              "removed": removed})
    db.commit()
    return {"items": [_response(r) for r in items], "removed_tool_numbers": removed}


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
    close_open_proposal_on_bind(db, user, row.id, req.instance_id)
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


class AdoptRequest(BaseModel):
    actor: str = "human@inbox"


@router.post("/{record_id}/adopt")
def adopt_new_instance(record_id: str, req: AdoptRequest, db: Session = Depends(get_db),
                       user: User = Depends(get_authenticated_user)):
    """The slot holds a tool the catalog doesn't know yet: mint a new instance
    seeded from the slot's observations (its measured diameter carries through
    with its provenance) and install it. The 'new tool' path of the inbox."""
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    if row.bound_instance_id is not None:
        raise HTTPException(status_code=409, detail="slot is already bound")

    canonical = {
        "name": {"value": None, "source": UNKNOWN},
        "catalog_type_id": {"value": None, "source": UNKNOWN},
        "geometry": {},
    }
    slot_dia = (row.canonical.get("offsets") or {}).get("diameter")
    if slot_dia and slot_dia.get("value") is not None:
        canonical["geometry"]["diameter"] = dict(slot_dia)   # measured, with provenance
    inst = InstanceRow(canonical=canonical, clients={}, catalog_type_id=None,
                       user_id=user.id, created_by=user.id, updated_by=user.id)
    db.add(inst)
    db.flush()
    create_audit_log(session=db, user_id=user.id, operation="CREATE",
                     entity_type="tool_instance_record", entity_id=inst.id,
                     changes={"adopted_from_slot": row.id})

    _set_binding(row, inst.id, req.actor)
    row.updated_by = user.id
    close_open_proposal_on_bind(db, user, row.id, inst.id)
    create_audit_log(session=db, user_id=user.id, operation="BIND",
                     entity_type="tool_table_entry_record", entity_id=row.id,
                     changes={"instance_id": inst.id, "adopted": True})
    db.commit()
    return {"instance_id": inst.id, "slot": _response(row)}


@router.delete("/{record_id}")
def delete_slot(record_id: str, db: Session = Depends(get_db),
                user: User = Depends(get_authenticated_user)):
    """Remove a machine-reported slot (and its open proposals). The instance it
    held, if any, is not deleted. If the controller re-pushes, the slot returns."""
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    from smooth.database.schema import SlotProposal
    db.query(SlotProposal).filter(SlotProposal.slot_id == record_id).delete()
    db.delete(row)
    create_audit_log(session=db, user_id=user.id, operation="DELETE",
                     entity_type="tool_table_entry_record", entity_id=record_id)
    db.commit()
    return {"deleted": record_id}


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
