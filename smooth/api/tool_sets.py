# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
ToolSet facade API — named collections of ToolRecords (v2 public contract).

ToolSet is both the public resource and the internal entity — the facade
rename of 2026-06-11 purged the client-flavored word "Library" so internal
and public nomenclature match. Each ToolSet is a tool_sets row with
type="set", its members array holding ToolRecord ids.

Assumptions (mirrors tests/contract/test_tool_sets_api.py):
- Standard bulk envelope; optimistic locking on PATCH
- Membership is replaced wholesale by tool_record_ids — matching
  file-based clients, where the file IS the membership list
- Member ids are validated against the user's records (per-item errors)
- Deleting a tool set never touches its records
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, get_authenticated_user
from smooth.database.schema import User, ToolItem, ToolSet
from smooth.audit import create_audit_log


router = APIRouter(prefix="/api/v1/tool-sets", tags=["tool-sets"])

TOOL_SET_TYPE = "set"


class ToolSetCreate(BaseModel):
    """Schema for creating a tool set (name validated per-item)."""
    name: Optional[str] = None
    description: Optional[str] = None
    tool_record_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    extra: Optional[dict] = None


class ToolSetUpdate(BaseModel):
    """Schema for updating a tool set (optimistic locking required)."""
    id: str
    version: int
    name: Optional[str] = None
    description: Optional[str] = None
    tool_record_ids: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    extra: Optional[dict] = None


class ToolSetResponse(BaseModel):
    """Public facade shape for a tool set."""
    id: str
    name: str
    description: Optional[str]
    tool_record_ids: List[str]
    tags: List[str]
    extra: Optional[dict] = None
    version: int
    created_at: str
    updated_at: str


class BulkCreateRequest(BaseModel):
    items: List[ToolSetCreate]


class BulkUpdateRequest(BaseModel):
    items: List[ToolSetUpdate]


class BulkDeleteRequest(BaseModel):
    ids: List[str]


class ErrorDetail(BaseModel):
    index: Optional[int] = None
    id: Optional[str] = None
    message: str


class BulkResponse(BaseModel):
    success_count: int
    errors: List[ErrorDetail] = []
    items: List[ToolSetResponse] = []


class ListResponse(BaseModel):
    items: List[ToolSetResponse]


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _to_response(tool_set: ToolSet) -> ToolSetResponse:
    return ToolSetResponse(
        id=tool_set.id,
        name=tool_set.name,
        description=tool_set.description,
        tool_record_ids=list(tool_set.members or []),
        tags=getattr(tool_set, "tags", None) or [],
        extra=tool_set.extra,
        version=tool_set.version,
        created_at=_iso(tool_set.created_at),
        updated_at=_iso(tool_set.updated_at),
    )


def _owned(db: Session, user: User, tool_set_id: str) -> Optional[ToolSet]:
    row = db.query(ToolSet).filter(
        ToolSet.id == tool_set_id, ToolSet.type == TOOL_SET_TYPE
    ).first()
    if row is None or (row.user_id != user.id and not user.is_admin):
        return None
    return row


def _bad_member_ids(db: Session, user: User, record_ids: List[str]) -> List[str]:
    """Return member ids that don't resolve to records the user owns."""
    if not record_ids:
        return []
    found = {
        r.id for r in db.query(ToolItem).filter(
            ToolItem.id.in_(record_ids), ToolItem.user_id == user.id
        ).all()
    }
    return [rid for rid in record_ids if rid not in found]


@router.post("", response_model=BulkResponse)
def create_tool_sets(
    payload: BulkCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Bulk create tool sets (partial success; members validated)."""
    created: List[ToolSetResponse] = []
    errors: List[ErrorDetail] = []

    for index, data in enumerate(payload.items):
        if not data.name:
            errors.append(ErrorDetail(index=index, message="name is required"))
            continue
        bad = _bad_member_ids(db, user, data.tool_record_ids)
        if bad:
            errors.append(ErrorDetail(
                index=index, message=f"unknown tool_record_ids: {', '.join(bad)}"
            ))
            continue
        row = ToolSet(
            name=data.name,
            description=data.description,
            type=TOOL_SET_TYPE,
            members=data.tool_record_ids,
            extra=data.extra,
            status="active",
            user_id=user.id,
            created_by=user.id,
            updated_by=user.id,
        )
        if hasattr(row, "tags"):
            row.tags = data.tags
        db.add(row)
        db.flush()
        create_audit_log(
            session=db, user_id=user.id, operation="CREATE",
            entity_type="tool_set", entity_id=row.id,
        )
        created.append(_to_response(row))

    db.commit()
    return BulkResponse(success_count=len(created), errors=errors, items=created)


@router.get("", response_model=ListResponse)
def list_tool_sets(
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """List the user's tool sets."""
    rows = db.query(ToolSet).filter(
        ToolSet.user_id == user.id, ToolSet.type == TOOL_SET_TYPE
    ).order_by(ToolSet.name).all()
    return ListResponse(items=[_to_response(r) for r in rows])


@router.get("/{tool_set_id}", response_model=ToolSetResponse)
def get_tool_set(
    tool_set_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Fetch one tool set."""
    row = _owned(db, user, tool_set_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Tool set not found")
    return _to_response(row)


@router.patch("", response_model=BulkResponse)
def update_tool_sets(
    payload: BulkUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Bulk update with optimistic locking; membership replaces wholesale."""
    updated: List[ToolSetResponse] = []
    errors: List[ErrorDetail] = []

    for index, data in enumerate(payload.items):
        row = _owned(db, user, data.id)
        if row is None:
            errors.append(ErrorDetail(index=index, id=data.id, message="Tool set not found"))
            continue
        if row.version != data.version:
            errors.append(ErrorDetail(
                index=index, id=data.id,
                message=f"Version conflict: expected {row.version}, got {data.version}",
            ))
            continue
        if data.tool_record_ids is not None:
            bad = _bad_member_ids(db, user, data.tool_record_ids)
            if bad:
                errors.append(ErrorDetail(
                    index=index, id=data.id,
                    message=f"unknown tool_record_ids: {', '.join(bad)}",
                ))
                continue
            row.members = data.tool_record_ids
        if data.name is not None:
            row.name = data.name
        if data.description is not None:
            row.description = data.description
        if data.tags is not None and hasattr(row, "tags"):
            row.tags = data.tags
        if data.extra is not None:
            row.extra = data.extra
        row.version += 1
        row.updated_by = user.id
        db.flush()
        create_audit_log(
            session=db, user_id=user.id, operation="UPDATE",
            entity_type="tool_set", entity_id=row.id,
        )
        updated.append(_to_response(row))

    db.commit()
    return BulkResponse(success_count=len(updated), errors=errors, items=updated)


@router.delete("", response_model=BulkResponse)
def delete_tool_sets(
    payload: BulkDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Bulk delete tool sets; member records are never touched."""
    errors: List[ErrorDetail] = []
    success = 0

    for index, tool_set_id in enumerate(payload.ids):
        row = _owned(db, user, tool_set_id)
        if row is None:
            errors.append(ErrorDetail(index=index, id=tool_set_id, message="Tool set not found"))
            continue
        db.delete(row)
        create_audit_log(
            session=db, user_id=user.id, operation="DELETE",
            entity_type="tool_set", entity_id=tool_set_id,
        )
        success += 1

    db.commit()
    return BulkResponse(success_count=success, errors=errors, items=[])
