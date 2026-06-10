# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
ToolRecord facade API — the v2 public contract.

ToolRecord is the user-facing tool object (UBIQUITOUS_LANGUAGE.md): name +
geometry + tags. It is the ONLY public surface for tool data; the deep schema
(ToolItem, ToolAssembly, ToolInstance) is private substrate that this facade
materializes and links server-side.

Assumptions (mirrors tests/contract/test_tool_records_api.py):
- Bulk-first: POST/PATCH accept {"items": [...]}; DELETE accepts {"ids": [...]}
- Responses use the envelope {"success_count", "errors", "items"}
- Partial success: per-item errors carry index and/or id
- Optimistic locking: PATCH requires the current integer version per item
- A ToolRecord's public id is stable for the life of the record; today it is
  backed 1:1 by a ToolItem row, but that is an implementation detail which
  MUST NOT leak into responses
- Facade responses contain exactly: id, name, description, tags, geometry,
  version, created_at, updated_at
- Every write is audited with entity_type "tool_record"
- Change detection: GET /api/v1/changes/tool-records/since-version returns
  facade-shaped records under "items"
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, get_authenticated_user
from smooth.database.schema import User, ToolItem, ToolTableEntry
from smooth.api.machines import ToolTableEntryResponse, entry_to_response
from smooth.audit import create_audit_log
from smooth.change_detection import get_changes_since_version, get_max_version


router = APIRouter(prefix="/api/v1/tool-records", tags=["tool-records"])

# Registered BEFORE the generic /api/v1/changes/{entity_type} router in
# main.py so the literal path wins route matching.
changes_router = APIRouter(prefix="/api/v1/changes/tool-records", tags=["changes"])


# Request/Response Models

class ToolRecordCreate(BaseModel):
    """Schema for creating a tool record.

    Assumptions:
    - name is required, but validated per-item in the endpoint so a bad item
      yields a partial-success error instead of failing the batch
    """
    name: Optional[str] = None
    description: Optional[str] = None
    geometry: Optional[dict] = None
    tags: List[str] = Field(default_factory=list)


class ToolRecordUpdate(BaseModel):
    """Schema for updating a tool record (optimistic locking required)."""
    id: str
    version: int
    name: Optional[str] = None
    description: Optional[str] = None
    geometry: Optional[dict] = None
    tags: Optional[List[str]] = None


class ToolRecordResponse(BaseModel):
    """Public facade shape. No deep-entity keys, no attribution internals.

    machines[] nests the ToolTableEntries bound to this record (one per
    machine where the tool is mounted) — the UL's ToolRecord.machines[].
    """
    id: str
    name: str
    description: Optional[str]
    tags: List[str]
    geometry: Optional[dict]
    machines: List[ToolTableEntryResponse] = []
    version: int
    created_at: str
    updated_at: str


class BulkCreateRequest(BaseModel):
    """Bulk create request."""
    items: List[ToolRecordCreate]


class BulkUpdateRequest(BaseModel):
    """Bulk update request."""
    items: List[ToolRecordUpdate]


class BulkDeleteRequest(BaseModel):
    """Bulk delete request."""
    ids: List[str]


class ErrorDetail(BaseModel):
    """Error detail for a failed item in a bulk operation."""
    index: Optional[int] = None
    id: Optional[str] = None
    message: str


class BulkResponse(BaseModel):
    """Envelope for bulk operations."""
    success_count: int
    errors: List[ErrorDetail] = []
    items: List[ToolRecordResponse] = []


class ListResponse(BaseModel):
    """Envelope for list/query operations."""
    items: List[ToolRecordResponse]


class ChangesResponse(BaseModel):
    """Envelope for facade change detection."""
    entity_type: str
    items: List[ToolRecordResponse]
    count: int
    max_version: int
    sync_method: str


# Helpers

def _iso(value) -> str:
    """Render a datetime column as an ISO string (passes strings through)."""
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _to_response(item: ToolItem, db: Session) -> ToolRecordResponse:
    """Serialize the backing ToolItem as a facade ToolRecord.

    Assumptions:
    - The facade shows exactly the public fields; everything else about the
      backing row (type, attribution, deep links) stays private
    - name falls back to description for rows predating the facade
    - machines[] lists ToolTableEntries bound to this record
    """
    entries = (
        db.query(ToolTableEntry)
        .filter(ToolTableEntry.tool_record_id == item.id)
        .order_by(ToolTableEntry.machine_id, ToolTableEntry.tool_number)
        .all()
    )
    return ToolRecordResponse(
        id=item.id,
        name=item.name or item.description or "",
        description=item.description,
        tags=item.tags or [],
        geometry=item.geometry,
        machines=[entry_to_response(e) for e in entries],
        version=item.version,
        created_at=_iso(item.created_at),
        updated_at=_iso(item.updated_at),
    )


def _owned(db: Session, user: User, record_id: str) -> Optional[ToolItem]:
    """Fetch a facade-backing row owned by the user, or None."""
    item = db.query(ToolItem).filter(ToolItem.id == record_id).first()
    if item is None or (item.user_id != user.id and not user.is_admin):
        return None
    return item


# Endpoints

@router.post("", response_model=BulkResponse)
def create_tool_records(
    payload: BulkCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Bulk create tool records (partial success)."""
    created: List[ToolRecordResponse] = []
    errors: List[ErrorDetail] = []

    for index, data in enumerate(payload.items):
        if not data.name:
            errors.append(ErrorDetail(index=index, message="name is required"))
            continue
        item = ToolItem(
            type="cutting_tool",
            name=data.name,
            description=data.description,
            geometry=data.geometry,
            tags=data.tags,
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id,
        )
        db.add(item)
        db.flush()
        create_audit_log(
            session=db,
            user_id=user.id,
            operation="CREATE",
            entity_type="tool_record",
            entity_id=item.id,
        )
        created.append(_to_response(item, db))

    db.commit()
    return BulkResponse(success_count=len(created), errors=errors, items=created)


@router.get("", response_model=ListResponse)
def list_tool_records(
    tag: Optional[str] = Query(None, description="Only records carrying this tag"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """List the user's tool records with optional tag filter and pagination.

    Assumptions:
    - Tag filtering happens in Python for SQLite JSON compatibility (same
      approach as the v1 endpoints)
    """
    query = db.query(ToolItem).filter(ToolItem.user_id == user.id)
    rows = query.order_by(ToolItem.created_at).all()
    if tag is not None:
        rows = [r for r in rows if tag in (r.tags or [])]
    rows = rows[offset:offset + limit]
    return ListResponse(items=[_to_response(r, db) for r in rows])


@router.get("/{record_id}", response_model=ToolRecordResponse)
def get_tool_record(
    record_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Fetch one tool record by its stable public id."""
    item = _owned(db, user, record_id)
    if item is None:
        raise HTTPException(status_code=404, detail="ToolRecord not found")
    return _to_response(item, db)


@router.patch("", response_model=BulkResponse)
def update_tool_records(
    payload: BulkUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Bulk update with optimistic locking (partial success).

    Assumptions:
    - A stale version is a per-item error; other items still commit
    - Successful updates increment version by exactly 1
    """
    updated: List[ToolRecordResponse] = []
    errors: List[ErrorDetail] = []

    for index, data in enumerate(payload.items):
        item = _owned(db, user, data.id)
        if item is None:
            errors.append(ErrorDetail(index=index, id=data.id, message="ToolRecord not found"))
            continue
        if item.version != data.version:
            errors.append(ErrorDetail(
                index=index,
                id=data.id,
                message=f"Version conflict: expected {item.version}, got {data.version}",
            ))
            continue
        if data.name is not None:
            item.name = data.name
        if data.description is not None:
            item.description = data.description
        if data.geometry is not None:
            item.geometry = data.geometry
        if data.tags is not None:
            item.tags = data.tags
        item.version += 1
        item.updated_by = user.id
        db.flush()
        create_audit_log(
            session=db,
            user_id=user.id,
            operation="UPDATE",
            entity_type="tool_record",
            entity_id=item.id,
        )
        updated.append(_to_response(item, db))

    db.commit()
    return BulkResponse(success_count=len(updated), errors=errors, items=updated)


@router.delete("", response_model=BulkResponse)
def delete_tool_records(
    payload: BulkDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Bulk delete by id (partial success)."""
    errors: List[ErrorDetail] = []
    success = 0

    for index, record_id in enumerate(payload.ids):
        item = _owned(db, user, record_id)
        if item is None:
            errors.append(ErrorDetail(index=index, id=record_id, message="ToolRecord not found"))
            continue
        db.delete(item)
        create_audit_log(
            session=db,
            user_id=user.id,
            operation="DELETE",
            entity_type="tool_record",
            entity_id=record_id,
        )
        success += 1

    db.commit()
    return BulkResponse(success_count=success, errors=errors, items=[])


@changes_router.get("/since-version", response_model=ChangesResponse)
def tool_record_changes_since_version(
    since_version: int = Query(..., ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Facade change detection: records changed since a version horizon.

    Assumptions:
    - Reuses the core change-detection queries against the backing table
    - Returns facade-shaped records under "items"
    """
    changes = get_changes_since_version(
        session=db,
        entity_type=ToolItem,
        since_version=since_version,
        user_id=user.id,
        is_admin=user.is_admin,
        limit=limit,
    )
    max_version = get_max_version(
        session=db,
        entity_type=ToolItem,
        user_id=user.id,
        is_admin=user.is_admin,
    )
    items = [_to_response(c, db) for c in changes]
    return ChangesResponse(
        entity_type="tool-records",
        items=items,
        count=len(items),
        max_version=max_version,
        sync_method="version",
    )
