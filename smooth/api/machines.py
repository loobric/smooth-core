# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Machine and ToolTableEntry facade API — v2 public contract (smooth-core#4).

Machine is a first-class entity (decision D4): identity, controller type,
and a .fcm-shaped definition JSON. ToolTableEntry is one machine's table
row; entries may be UNBOUND (no ToolRecord yet) and are upserted on
(machine, tool_number) — the natural shape of a controller pushing its
tool table.

Assumptions (mirrors tests/contract/test_machines_api.py):
- Machines use the same bulk envelope as tool-records
- PUT /machines/{id}/tool-table upserts by tool_number with partial success
- Explicit binding (client supplies tool_record_id) is allowed — that is
  user intent; HEURISTIC binding goes through the inbox (#5), never here
- provenance and extra JSON round-trip untouched (lossless principle)
- Every write is audited
"""
from typing import Optional, List, Literal
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, get_authenticated_user
from smooth.database.schema import User, Machine, ToolTableEntry, ToolItem
from smooth.audit import create_audit_log
from smooth.binding import (
    propose_binding,
    delete_proposals_for_entries,
    close_open_proposal_on_bind,
)


router = APIRouter(prefix="/api/v1/machines", tags=["machines"])


# Request/Response Models

class MachineCreate(BaseModel):
    """Schema for creating a machine (name validated per-item)."""
    name: Optional[str] = None
    controller_type: Optional[str] = None
    definition: Optional[dict] = None
    tags: List[str] = Field(default_factory=list)


class MachineUpdate(BaseModel):
    """Schema for updating a machine (optimistic locking required)."""
    id: str
    version: int
    name: Optional[str] = None
    controller_type: Optional[str] = None
    definition: Optional[dict] = None
    tags: Optional[List[str]] = None


class MachineResponse(BaseModel):
    """Public facade shape for a machine."""
    id: str
    name: str
    controller_type: Optional[str]
    definition: Optional[dict]
    tags: List[str]
    version: int
    created_at: str
    updated_at: str


class ToolTableEntryUpsert(BaseModel):
    """Schema for upserting a tool-table entry (keyed on tool_number)."""
    tool_number: int
    pocket: Optional[int] = None
    description: Optional[str] = None
    offsets: Optional[dict] = None
    provenance: dict = Field(default_factory=dict)
    extra: Optional[dict] = None
    tool_record_id: Optional[str] = None


class ToolTableEntryResponse(BaseModel):
    """Public facade shape for a tool-table entry."""
    id: str
    machine_id: str
    tool_number: int
    pocket: Optional[int]
    description: Optional[str]
    offsets: Optional[dict]
    provenance: dict
    extra: Optional[dict]
    tool_record_id: Optional[str]
    version: int
    created_at: str
    updated_at: str


class MachineBulkCreateRequest(BaseModel):
    items: List[MachineCreate]


class MachineBulkUpdateRequest(BaseModel):
    items: List[MachineUpdate]


class MachineBulkDeleteRequest(BaseModel):
    ids: List[str]


class ToolTableUpsertRequest(BaseModel):
    items: List[ToolTableEntryUpsert]
    # "merge" (default) touches only the tool_numbers present — the safe shape
    # for partial/delta callers. "snapshot" declares the items ARE the machine's
    # complete current table, so entries absent from the payload are reconciled
    # away (the controller is authoritative over what its table contains).
    mode: Literal["merge", "snapshot"] = "merge"
    # Snapshot reconciliation refuses a suspicious mass-wipe (empty payload, or
    # removing more than half the table) unless force is set — a guard against a
    # partial/garbled client read masquerading as deliberate deletions.
    force: bool = False


class ToolTableDeleteRequest(BaseModel):
    tool_numbers: List[int]


class BindRequest(BaseModel):
    """Explicit, user-driven binding of one entry to one owned ToolRecord."""
    tool_record_id: str


class CreateRecordRequest(BaseModel):
    """Promote an entry into a record; name defaults to the entry description."""
    name: Optional[str] = None


class ErrorDetail(BaseModel):
    index: Optional[int] = None
    id: Optional[str] = None
    message: str


class MachineBulkResponse(BaseModel):
    success_count: int
    errors: List[ErrorDetail] = []
    items: List[MachineResponse] = []


class MachineListResponse(BaseModel):
    items: List[MachineResponse]


class ToolTableBulkResponse(BaseModel):
    success_count: int
    errors: List[ErrorDetail] = []
    items: List[ToolTableEntryResponse] = []
    # Tool numbers reconciled away in snapshot mode (empty for merge).
    removed_tool_numbers: List[int] = []


class ToolTableListResponse(BaseModel):
    items: List[ToolTableEntryResponse]


# Helpers

def _iso(value) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def machine_to_response(machine: Machine) -> MachineResponse:
    return MachineResponse(
        id=machine.id,
        name=machine.name,
        controller_type=machine.controller_type,
        definition=machine.definition,
        tags=machine.tags or [],
        version=machine.version,
        created_at=_iso(machine.created_at),
        updated_at=_iso(machine.updated_at),
    )


def entry_to_response(entry: ToolTableEntry) -> ToolTableEntryResponse:
    return ToolTableEntryResponse(
        id=entry.id,
        machine_id=entry.machine_id,
        tool_number=entry.tool_number,
        pocket=entry.pocket,
        description=entry.description,
        offsets=entry.offsets,
        provenance=entry.provenance or {},
        extra=entry.extra,
        tool_record_id=entry.tool_record_id,
        version=entry.version,
        created_at=_iso(entry.created_at),
        updated_at=_iso(entry.updated_at),
    )


def _owned_machine(db: Session, user: User, machine_id: str) -> Optional[Machine]:
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if machine is None or (machine.user_id != user.id and not user.is_admin):
        return None
    return machine


# Machine endpoints

@router.post("", response_model=MachineBulkResponse)
def create_machines(
    payload: MachineBulkCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Bulk create machines (partial success; name unique per user)."""
    created: List[MachineResponse] = []
    errors: List[ErrorDetail] = []

    for index, data in enumerate(payload.items):
        if not data.name:
            errors.append(ErrorDetail(index=index, message="name is required"))
            continue
        exists = db.query(Machine).filter(
            Machine.user_id == user.id, Machine.name == data.name
        ).first()
        if exists or any(m.name == data.name for m in created):
            errors.append(ErrorDetail(
                index=index, message=f"machine name already exists: {data.name}"
            ))
            continue
        machine = Machine(
            name=data.name,
            controller_type=data.controller_type,
            definition=data.definition,
            tags=data.tags,
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id,
        )
        db.add(machine)
        db.flush()
        create_audit_log(
            session=db, user_id=user.id, operation="CREATE",
            entity_type="machine", entity_id=machine.id,
        )
        created.append(machine_to_response(machine))

    db.commit()
    return MachineBulkResponse(success_count=len(created), errors=errors, items=created)


@router.get("", response_model=MachineListResponse)
def list_machines(
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """List the user's machines."""
    rows = db.query(Machine).filter(Machine.user_id == user.id).order_by(Machine.name).all()
    return MachineListResponse(items=[machine_to_response(m) for m in rows])


@router.get("/{machine_id}", response_model=MachineResponse)
def get_machine(
    machine_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Fetch one machine by id."""
    machine = _owned_machine(db, user, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    return machine_to_response(machine)


@router.patch("", response_model=MachineBulkResponse)
def update_machines(
    payload: MachineBulkUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Bulk update machines with optimistic locking (partial success)."""
    updated: List[MachineResponse] = []
    errors: List[ErrorDetail] = []

    for index, data in enumerate(payload.items):
        machine = _owned_machine(db, user, data.id)
        if machine is None:
            errors.append(ErrorDetail(index=index, id=data.id, message="Machine not found"))
            continue
        if machine.version != data.version:
            errors.append(ErrorDetail(
                index=index, id=data.id,
                message=f"Version conflict: expected {machine.version}, got {data.version}",
            ))
            continue
        if data.name is not None:
            machine.name = data.name
        if data.controller_type is not None:
            machine.controller_type = data.controller_type
        if data.definition is not None:
            machine.definition = data.definition
        if data.tags is not None:
            machine.tags = data.tags
        machine.version += 1
        machine.updated_by = user.id
        db.flush()
        create_audit_log(
            session=db, user_id=user.id, operation="UPDATE",
            entity_type="machine", entity_id=machine.id,
        )
        updated.append(machine_to_response(machine))

    db.commit()
    return MachineBulkResponse(success_count=len(updated), errors=errors, items=updated)


@router.delete("", response_model=MachineBulkResponse)
def delete_machines(
    payload: MachineBulkDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Bulk delete machines and their tool-table entries (partial success)."""
    errors: List[ErrorDetail] = []
    success = 0

    for index, machine_id in enumerate(payload.ids):
        machine = _owned_machine(db, user, machine_id)
        if machine is None:
            errors.append(ErrorDetail(index=index, id=machine_id, message="Machine not found"))
            continue
        entry_ids = [
            e.id for e in db.query(ToolTableEntry).filter(
                ToolTableEntry.machine_id == machine.id
            ).all()
        ]
        delete_proposals_for_entries(db, entry_ids)
        db.query(ToolTableEntry).filter(ToolTableEntry.machine_id == machine.id).delete()
        db.delete(machine)
        create_audit_log(
            session=db, user_id=user.id, operation="DELETE",
            entity_type="machine", entity_id=machine_id,
        )
        success += 1

    db.commit()
    return MachineBulkResponse(success_count=success, errors=errors, items=[])


# Tool-table endpoints

def _guard_snapshot(db: Session, machine: Machine, payload: "ToolTableUpsertRequest") -> None:
    """Refuse a suspicious snapshot before it deletes anything.

    A full-table snapshot that is empty, or that would remove more than half
    the existing entries, looks far more like a partial/garbled client read
    than a deliberate bulk deletion. Refuse with 409 unless force is set.
    """
    if payload.force:
        return
    present = {item.tool_number for item in payload.items}
    existing = db.query(ToolTableEntry).filter(
        ToolTableEntry.machine_id == machine.id
    ).all()
    if not existing:
        return
    to_remove = [e for e in existing if e.tool_number not in present]
    if not to_remove:
        return
    if not present or len(to_remove) * 2 > len(existing):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Snapshot would remove {len(to_remove)} of {len(existing)} "
                f"tool-table entries — refusing as a likely partial read. "
                f"Re-send with force=true if the deletions are intended."
            ),
        )


def _reconcile_snapshot(
    db: Session, user: User, machine: Machine, payload: "ToolTableUpsertRequest"
) -> List[int]:
    """Remove server entries absent from a full-table snapshot.

    The controller is authoritative over what its table contains, so a tool
    the operator deleted locally must not linger as a phantom. We delete only
    the ENTRY; any bound ToolRecord survives (the link dies with the slot).
    Open proposals for removed entries are withdrawn. Returns the removed
    tool numbers. Caller commits.
    """
    present = {item.tool_number for item in payload.items}
    existing = db.query(ToolTableEntry).filter(
        ToolTableEntry.machine_id == machine.id
    ).all()
    orphaned = [e for e in existing if e.tool_number not in present]
    removed: List[int] = []
    delete_proposals_for_entries(db, [e.id for e in orphaned])
    for entry in orphaned:
        create_audit_log(
            session=db, user_id=user.id, operation="DELETE",
            entity_type="tool_table_entry", entity_id=entry.id,
            changes={
                "reason": "absent from snapshot",
                "tool_number": entry.tool_number,
                "was_bound": entry.tool_record_id is not None,
            },
        )
        db.delete(entry)
        removed.append(entry.tool_number)
    return removed


@router.put("/{machine_id}/tool-table", response_model=ToolTableBulkResponse)
def upsert_tool_table(
    machine_id: str,
    payload: ToolTableUpsertRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Bulk upsert tool-table entries keyed on (machine, tool_number).

    Assumptions:
    - Existing tool_number updates in place (id stable, version increments)
    - tool_record_id, when supplied, must reference a ToolRecord the user
      owns (explicit binding); otherwise that item errors
    - Entries without tool_record_id stay/become whatever binding they had:
      an upsert that omits tool_record_id does NOT unbind an existing entry
    - mode="snapshot" additionally reconciles: entries on the server but
      absent from this (complete) payload are removed, because the controller
      is authoritative over what its table holds. Only the ENTRY (the
      observation) is removed — a bound ToolRecord (the tool's identity) is
      never touched; the link simply dies with the slot. A mass-wipe is
      refused unless force=True.
    """
    machine = _owned_machine(db, user, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")

    if payload.mode == "snapshot":
        _guard_snapshot(db, machine, payload)

    results: List[ToolTableEntryResponse] = []
    errors: List[ErrorDetail] = []

    for index, data in enumerate(payload.items):
        if data.tool_record_id is not None:
            record = db.query(ToolItem).filter(ToolItem.id == data.tool_record_id).first()
            if record is None or record.user_id != user.id:
                errors.append(ErrorDetail(
                    index=index, id=data.tool_record_id,
                    message=f"ToolRecord not found: {data.tool_record_id}",
                ))
                continue

        entry = db.query(ToolTableEntry).filter(
            ToolTableEntry.machine_id == machine.id,
            ToolTableEntry.tool_number == data.tool_number,
        ).first()

        if entry is None:
            entry = ToolTableEntry(
                machine_id=machine.id,
                tool_number=data.tool_number,
                pocket=data.pocket,
                description=data.description,
                offsets=data.offsets,
                provenance=data.provenance,
                extra=data.extra,
                tool_record_id=data.tool_record_id,
                user_id=user.id,
                created_by=user.id,
                updated_by=user.id,
            )
            db.add(entry)
            operation = "CREATE"
        else:
            entry.pocket = data.pocket
            entry.description = data.description
            entry.offsets = data.offsets
            entry.provenance = data.provenance
            entry.extra = data.extra
            if data.tool_record_id is not None:
                entry.tool_record_id = data.tool_record_id
            entry.version += 1
            entry.updated_by = user.id
            operation = "UPDATE"

        db.flush()
        create_audit_log(
            session=db, user_id=user.id, operation=operation,
            entity_type="tool_table_entry", entity_id=entry.id,
        )
        # Binding engine (#5): unbound entries get at most one open
        # heuristic proposal for human review. Never auto-binds.
        propose_binding(db, user, entry)
        results.append(entry_to_response(entry))

    removed: List[int] = []
    if payload.mode == "snapshot":
        removed = _reconcile_snapshot(db, user, machine, payload)

    db.commit()
    return ToolTableBulkResponse(
        success_count=len(results), errors=errors, items=results,
        removed_tool_numbers=removed,
    )


@router.post("/{machine_id}/tool-table/{tool_number}/bind", response_model=ToolTableEntryResponse)
def bind_entry(
    machine_id: str,
    tool_number: int,
    payload: BindRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Explicitly link an unbound entry to a record the user owns.

    The UI-facing counterpart to /unbind, and what makes "link later" real:
    a rejected heuristic suggestion can always be resolved by hand here.

    Assumptions:
    - Entry data (offsets, description, extra) is untouched; only the link
      is set; version increments
    - 409 if the entry is already bound (rebind = unbind first)
    - 404 for unknown machine, tool number, or a record the user can't see
    - Any open proposal for the entry is resolved (it no longer needs review)
    """
    machine = _owned_machine(db, user, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    entry = db.query(ToolTableEntry).filter(
        ToolTableEntry.machine_id == machine.id,
        ToolTableEntry.tool_number == tool_number,
    ).first()
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for tool number {tool_number}")
    if entry.tool_record_id is not None:
        raise HTTPException(status_code=409, detail="Entry is already bound")

    record = db.query(ToolItem).filter(ToolItem.id == payload.tool_record_id).first()
    if record is None or record.user_id != user.id:
        raise HTTPException(
            status_code=404, detail=f"ToolRecord not found: {payload.tool_record_id}"
        )

    entry.tool_record_id = record.id
    entry.version += 1
    entry.updated_by = user.id
    close_open_proposal_on_bind(db, user, entry.id, record.id)
    db.flush()
    create_audit_log(
        session=db, user_id=user.id, operation="BIND",
        entity_type="tool_table_entry", entity_id=entry.id,
        changes={"tool_record_id": record.id},
    )
    db.commit()
    return entry_to_response(entry)


@router.post("/{machine_id}/tool-table/{tool_number}/create-record", response_model=ToolTableEntryResponse)
def create_record_from_entry(
    machine_id: str,
    tool_number: int,
    payload: Optional[CreateRecordRequest] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Materialize a ToolRecord from an entry and bind it, in one step.

    Closes the new-tool dead-end: a controller can push a tool the server
    has never seen, which matches nothing and so gets no proposal. Rather
    than leave the row unbound forever, the user promotes it here.

    Mapping (lossless principle): the entry's description becomes the record
    name; its diameter becomes record geometry. The diameter is the only
    offset that is tool geometry — z and friends are machine offsets, so the
    full original offsets ride along in `extra` rather than being guessed
    into geometry.

    Assumptions:
    - 409 if the entry is already bound; 404 for unknown machine/tool number
    - CREATE (tool_record) and BIND (tool_table_entry) are both audited
    """
    machine = _owned_machine(db, user, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    entry = db.query(ToolTableEntry).filter(
        ToolTableEntry.machine_id == machine.id,
        ToolTableEntry.tool_number == tool_number,
    ).first()
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for tool number {tool_number}")
    if entry.tool_record_id is not None:
        raise HTTPException(status_code=409, detail="Entry is already bound")

    offsets = entry.offsets or {}
    geometry = {}
    if offsets.get("diameter") is not None:
        geometry["diameter"] = offsets["diameter"]
        if offsets.get("diameter_unit"):
            geometry["diameter_unit"] = offsets["diameter_unit"]

    name = (payload.name if payload else None) or entry.description or f"T{tool_number}"
    extra = dict(entry.extra or {})
    extra["smooth"] = {
        "created_from": {
            "machine_id": machine.id,
            "tool_number": tool_number,
            "offsets": offsets,
        }
    }
    record = ToolItem(
        type="cutting_tool",
        name=name,
        description=entry.description,
        geometry=geometry or None,
        tags=[],
        extra=extra,
        user_id=user.id,
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(record)
    db.flush()
    create_audit_log(
        session=db, user_id=user.id, operation="CREATE",
        entity_type="tool_record", entity_id=record.id,
    )

    entry.tool_record_id = record.id
    entry.version += 1
    entry.updated_by = user.id
    db.flush()
    create_audit_log(
        session=db, user_id=user.id, operation="BIND",
        entity_type="tool_table_entry", entity_id=entry.id,
        changes={"tool_record_id": record.id},
    )
    db.commit()
    return entry_to_response(entry)


@router.post("/{machine_id}/tool-table/{tool_number}/unbind", response_model=ToolTableEntryResponse)
def unbind_entry(
    machine_id: str,
    tool_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Clear an entry's binding (the undo for a wrong confirm).

    Assumptions:
    - Entry data (offsets, description, extra) is untouched; only the link
      to the ToolRecord is cleared
    - The entry becomes eligible for binding proposals again on next sync
    - 409 if the entry isn't bound; 404 for unknown machine/tool number
    """
    machine = _owned_machine(db, user, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    entry = db.query(ToolTableEntry).filter(
        ToolTableEntry.machine_id == machine.id,
        ToolTableEntry.tool_number == tool_number,
    ).first()
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry for tool number {tool_number}")
    if entry.tool_record_id is None:
        raise HTTPException(status_code=409, detail="Entry is not bound")

    previous = entry.tool_record_id
    entry.tool_record_id = None
    entry.version += 1
    entry.updated_by = user.id
    db.flush()
    create_audit_log(
        session=db, user_id=user.id, operation="UNBIND",
        entity_type="tool_table_entry", entity_id=entry.id,
        changes={"tool_record_id": previous},
    )
    db.commit()
    return entry_to_response(entry)


@router.get("/{machine_id}/tool-table", response_model=ToolTableListResponse)
def list_tool_table(
    machine_id: str,
    bound: Optional[bool] = Query(None, description="Filter by binding state"),
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """List a machine's tool-table entries, optionally by binding state."""
    machine = _owned_machine(db, user, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")

    query = db.query(ToolTableEntry).filter(ToolTableEntry.machine_id == machine.id)
    if bound is True:
        query = query.filter(ToolTableEntry.tool_record_id.isnot(None))
    elif bound is False:
        query = query.filter(ToolTableEntry.tool_record_id.is_(None))
    rows = query.order_by(ToolTableEntry.tool_number).all()
    return ToolTableListResponse(items=[entry_to_response(e) for e in rows])


@router.delete("/{machine_id}/tool-table", response_model=ToolTableBulkResponse)
def delete_tool_table_entries(
    machine_id: str,
    payload: ToolTableDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Delete entries from a machine's table by tool number (partial success)."""
    machine = _owned_machine(db, user, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")

    errors: List[ErrorDetail] = []
    success = 0

    for index, tool_number in enumerate(payload.tool_numbers):
        entry = db.query(ToolTableEntry).filter(
            ToolTableEntry.machine_id == machine.id,
            ToolTableEntry.tool_number == tool_number,
        ).first()
        if entry is None:
            errors.append(ErrorDetail(
                index=index, message=f"No entry for tool number {tool_number}"
            ))
            continue
        delete_proposals_for_entries(db, [entry.id])
        db.delete(entry)
        create_audit_log(
            session=db, user_id=user.id, operation="DELETE",
            entity_type="tool_table_entry", entity_id=entry.id,
        )
        success += 1

    db.commit()
    return ToolTableBulkResponse(success_count=success, errors=errors, items=[])
