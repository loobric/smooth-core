# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
ToolSet API endpoints.

Bulk-first design: all operations accept arrays.

Assumptions:
- POST /api/v1/tool-sets - Create (bulk)
- GET /api/v1/tool-sets - List/query with filters
- PUT /api/v1/tool-sets - Update (bulk) with version checking
- DELETE /api/v1/tool-sets - Delete (bulk)
- type: machine_setup, job_specific, template, project
- status: draft, active, archived
- members is JSON array of tool references
"""
from typing import Annotated, Optional, List
from uuid import uuid4
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, require_auth
from smooth.database.schema import User, ToolSet, ToolSetHistory
from smooth.versioning import snapshot_tool_set, get_tool_set_history, restore_tool_set, compare_versions


router = APIRouter(prefix="/api/v1/tool-sets", tags=["tool-sets"])


# Request/Response Models
class ToolSetCreate(BaseModel):
    """Schema for creating a tool set."""
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    machine_id: Optional[str] = None
    job_id: Optional[str] = None
    members: Optional[list] = None
    capacity: Optional[dict] = None
    status: Optional[str] = "draft"
    activation: Optional[dict] = None


class ToolSetUpdate(BaseModel):
    """Schema for updating a tool set."""
    id: str
    version: int
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    machine_id: Optional[str] = None
    job_id: Optional[str] = None
    members: Optional[list] = None
    capacity: Optional[dict] = None
    status: Optional[str] = None
    activation: Optional[dict] = None


class ToolSetResponse(BaseModel):
    """Schema for tool set response."""
    id: str
    name: str
    description: Optional[str]
    type: str
    machine_id: Optional[str]
    job_id: Optional[str]
    members: list
    capacity: Optional[dict]
    status: str
    activation: Optional[dict]
    user_id: str
    created_by: str
    updated_by: str
    created_at: str
    updated_at: str
    version: int


class BulkCreateRequest(BaseModel):
    """Bulk create request."""
    items: List[ToolSetCreate]


class BulkUpdateRequest(BaseModel):
    """Bulk update request."""
    items: List[ToolSetUpdate]


class BulkDeleteRequest(BaseModel):
    """Bulk delete request."""
    ids: List[str]


class ErrorDetail(BaseModel):
    """Error detail for a failed operation."""
    index: Optional[int] = None
    id: Optional[str] = None
    message: str


class BulkOperationResponse(BaseModel):
    """Response for bulk operations."""
    success_count: int
    error_count: int
    results: List[ToolSetResponse] = []
    errors: List[ErrorDetail] = []


class QueryResponse(BaseModel):
    """Response for query operations."""
    items: List[ToolSetResponse]
    total: int
    limit: int
    offset: int


@router.post("", response_model=BulkOperationResponse)
def create_tool_sets(
    request: BulkCreateRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Create tool sets in bulk."""
    results = []
    errors = []
    
    for index, set_data in enumerate(request.items):
        try:
            # Validate required fields
            if not set_data.name:
                raise ValueError("Field 'name' is required")
            if not set_data.type:
                raise ValueError("Field 'type' is required")
            if not set_data.members:
                raise ValueError("Field 'members' is required")
            
            # Create tool set
            tool_set = ToolSet(
                id=str(uuid4()),
                name=set_data.name,
                description=set_data.description,
                type=set_data.type,
                machine_id=set_data.machine_id,
                job_id=set_data.job_id,
                members=set_data.members,
                capacity=set_data.capacity,
                status=set_data.status or "draft",
                activation=set_data.activation,
                user_id=current_user.id,
                created_by=current_user.id,
                updated_by=current_user.id
            )
            
            db.add(tool_set)
            db.flush()
            
            results.append(_to_response(tool_set))
            
        except Exception as e:
            errors.append(ErrorDetail(
                index=index,
                message=str(e)
            ))
    
    if results:
        db.commit()
    else:
        db.rollback()
    
    return BulkOperationResponse(
        success_count=len(results),
        error_count=len(errors),
        results=results,
        errors=errors
    )


@router.get("", response_model=QueryResponse)
def list_tool_sets(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    type: Optional[str] = Query(None, description="Filter by type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List tool sets with filters and pagination."""
    query = db.query(ToolSet).filter(ToolSet.user_id == current_user.id)
    
    if type:
        query = query.filter(ToolSet.type == type)
    if status:
        query = query.filter(ToolSet.status == status)
    
    total = query.count()
    tool_sets = query.limit(limit).offset(offset).all()
    
    return QueryResponse(
        items=[_to_response(tool_set) for tool_set in tool_sets],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{tool_set_id}", response_model=ToolSetResponse)
def get_tool_set(
    tool_set_id: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Retrieve a single ToolSet by ID if owned by the current user."""
    tool_set = db.query(ToolSet).filter(
        ToolSet.id == tool_set_id,
        ToolSet.user_id == current_user.id
    ).first()
    if not tool_set:
        raise HTTPException(status_code=404, detail="Not Found")
    return _to_response(tool_set)


@router.put("", response_model=BulkOperationResponse)
def update_tool_sets(
    request: BulkUpdateRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update tool sets in bulk."""
    results = []
    errors = []
    
    for index, update_data in enumerate(request.items):
        try:
            tool_set = db.query(ToolSet).filter(
                ToolSet.id == update_data.id,
                ToolSet.user_id == current_user.id
            ).first()
            
            if not tool_set:
                errors.append(ErrorDetail(
                    index=index,
                    id=update_data.id,
                    message="Tool set not found or access denied"
                ))
                continue
            
            if tool_set.version != update_data.version:
                errors.append(ErrorDetail(
                    index=index,
                    id=update_data.id,
                    message=f"Version conflict: expected {tool_set.version}, got {update_data.version}"
                ))
                continue
            
            # Snapshot current state before update
            snapshot_tool_set(db, tool_set, current_user.id)
            
            # Apply updates
            if update_data.name is not None:
                tool_set.name = update_data.name
            if update_data.description is not None:
                tool_set.description = update_data.description
            if update_data.type is not None:
                tool_set.type = update_data.type
            if update_data.machine_id is not None:
                tool_set.machine_id = update_data.machine_id
            if update_data.job_id is not None:
                tool_set.job_id = update_data.job_id
            if update_data.members is not None:
                tool_set.members = update_data.members
            if update_data.capacity is not None:
                tool_set.capacity = update_data.capacity
            if update_data.status is not None:
                tool_set.status = update_data.status
            if update_data.activation is not None:
                tool_set.activation = update_data.activation
            
            tool_set.updated_by = current_user.id
            tool_set.updated_at = datetime.now(UTC)
            tool_set.version += 1
            
            db.flush()
            results.append(_to_response(tool_set))
            
        except Exception as e:
            errors.append(ErrorDetail(
                index=index,
                id=update_data.id,
                message=str(e)
            ))
    
    if results:
        db.commit()
    else:
        db.rollback()
    
    return BulkOperationResponse(
        success_count=len(results),
        error_count=len(errors),
        results=results,
        errors=errors
    )


@router.get("/{tool_set_id}/history")
def list_tool_set_history(
    tool_set_id: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get version history for a ToolSet."""
    history = get_tool_set_history(db, tool_set_id, current_user.id)
    
    return {
        "tool_set_id": tool_set_id,
        "versions": [
            {
                "version": h.version,
                "changed_at": h.changed_at.isoformat(),
                "changed_by": h.changed_by,
                "change_summary": h.change_summary
            }
            for h in history
        ]
    }


@router.get("/{tool_set_id}/versions/{version}")
def get_tool_set_version(
    tool_set_id: str,
    version: int,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get a specific version of a ToolSet."""
    history = db.query(ToolSetHistory).filter(
        ToolSetHistory.tool_set_id == tool_set_id,
        ToolSetHistory.version == version
    ).first()
    
    if not history:
        return {"error": "Version not found"}
    
    # Verify ownership
    tool_set = db.get(ToolSet, tool_set_id)
    if not tool_set or tool_set.user_id != current_user.id:
        return {"error": "Access denied"}
    
    return {
        "version": history.version,
        "changed_at": history.changed_at.isoformat(),
        "changed_by": history.changed_by,
        "change_summary": history.change_summary,
        "snapshot": history.snapshot
    }


@router.post("/{tool_set_id}/restore/{version}")
def restore_tool_set_version(
    tool_set_id: str,
    version: int,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Restore a ToolSet to a previous version."""
    tool_set = restore_tool_set(db, tool_set_id, version, current_user.id)
    
    if not tool_set:
        return {"error": "ToolSet or version not found"}
    
    db.commit()
    
    return {
        "success": True,
        "message": f"Restored to version {version}",
        "current_version": tool_set.version,
        "tool_set": _to_response(tool_set)
    }


@router.get("/{tool_set_id}/compare/{version_a}/{version_b}")
def compare_tool_set_versions(
    tool_set_id: str,
    version_a: int,
    version_b: int,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Compare two versions of a ToolSet."""
    comparison = compare_versions(db, tool_set_id, version_a, version_b, current_user.id)
    
    if not comparison:
        return {"error": "Versions not found"}
    
    return comparison


@router.delete("", response_model=BulkOperationResponse)
def delete_tool_sets(
    request: BulkDeleteRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Delete tool sets in bulk."""
    results = []
    errors = []
    
    for index, set_id in enumerate(request.ids):
        try:
            tool_set = db.query(ToolSet).filter(
                ToolSet.id == set_id,
                ToolSet.user_id == current_user.id
            ).first()
            
            if not tool_set:
                errors.append(ErrorDetail(
                    index=index,
                    id=set_id,
                    message="Tool set not found or access denied"
                ))
                continue
            
            response = _to_response(tool_set)
            db.delete(tool_set)
            db.flush()
            
            results.append(response)
            
        except Exception as e:
            errors.append(ErrorDetail(
                index=index,
                id=set_id,
                message=str(e)
            ))
    
    if results:
        db.commit()
    else:
        db.rollback()
    
    return BulkOperationResponse(
        success_count=len(results),
        error_count=len(errors),
        results=results,
        errors=errors
    )


def _to_response(tool_set: ToolSet) -> ToolSetResponse:
    """Convert ToolSet entity to response model."""
    return ToolSetResponse(
        id=tool_set.id,
        name=tool_set.name,
        description=tool_set.description,
        type=tool_set.type,
        machine_id=tool_set.machine_id,
        job_id=tool_set.job_id,
        members=tool_set.members,
        capacity=tool_set.capacity,
        status=tool_set.status,
        activation=tool_set.activation,
        user_id=tool_set.user_id,
        created_by=tool_set.created_by,
        updated_by=tool_set.updated_by,
        created_at=tool_set.created_at.isoformat() if tool_set.created_at else "",
        updated_at=tool_set.updated_at.isoformat() if tool_set.updated_at else "",
        version=tool_set.version
    )
