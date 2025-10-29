# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
ToolInstance API endpoints.

Bulk-first design: all operations accept arrays.

Assumptions:
- POST /api/v1/tool-instances - Create (bulk)
- GET /api/v1/tool-instances - List/query with filters
- PUT /api/v1/tool-instances - Update (bulk) with version checking
- DELETE /api/v1/tool-instances - Delete (bulk)
- assembly_id references ToolAssembly
- status: available, in_use, needs_inspection, retired
"""
from typing import Annotated, Optional, List
from uuid import uuid4
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, require_auth
from smooth.database.schema import User, ToolInstance


router = APIRouter(prefix="/api/v1/tool-instances", tags=["tool-instances"])


# Request/Response Models
class ToolInstanceCreate(BaseModel):
    """Schema for creating a tool instance."""
    assembly_id: Optional[str] = None
    serial_number: Optional[str] = None
    status: Optional[str] = "available"
    location: Optional[dict] = None
    measured_geometry: Optional[dict] = None
    lifecycle: Optional[dict] = None


class ToolInstanceUpdate(BaseModel):
    """Schema for updating a tool instance."""
    id: str
    version: int
    assembly_id: Optional[str] = None
    serial_number: Optional[str] = None
    status: Optional[str] = None
    location: Optional[dict] = None
    measured_geometry: Optional[dict] = None
    lifecycle: Optional[dict] = None


class ToolInstanceResponse(BaseModel):
    """Schema for tool instance response."""
    id: str
    assembly_id: str
    serial_number: Optional[str]
    status: str
    location: Optional[dict]
    measured_geometry: Optional[dict]
    lifecycle: Optional[dict]
    user_id: str
    created_by: str
    updated_by: str
    created_at: str
    updated_at: str
    version: int


class BulkCreateRequest(BaseModel):
    """Bulk create request."""
    items: List[ToolInstanceCreate]


class BulkUpdateRequest(BaseModel):
    """Bulk update request."""
    items: List[ToolInstanceUpdate]


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
    results: List[ToolInstanceResponse] = []
    errors: List[ErrorDetail] = []


class QueryResponse(BaseModel):
    """Response for query operations."""
    items: List[ToolInstanceResponse]
    total: int
    limit: int
    offset: int


@router.post("", response_model=BulkOperationResponse)
def create_tool_instances(
    request: BulkCreateRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Create tool instances in bulk."""
    results = []
    errors = []
    
    for index, instance_data in enumerate(request.items):
        try:
            # Validate required fields
            if not instance_data.assembly_id:
                raise ValueError("Field 'assembly_id' is required")
            
            # Create tool instance
            tool_instance = ToolInstance(
                id=str(uuid4()),
                assembly_id=instance_data.assembly_id,
                serial_number=instance_data.serial_number,
                status=instance_data.status or "available",
                location=instance_data.location,
                measured_geometry=instance_data.measured_geometry,
                lifecycle=instance_data.lifecycle,
                user_id=current_user.id,
                created_by=current_user.id,
                updated_by=current_user.id
            )
            
            db.add(tool_instance)
            db.flush()
            
            results.append(_to_response(tool_instance))
            
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
def list_tool_instances(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List tool instances with filters and pagination."""
    query = db.query(ToolInstance).filter(ToolInstance.user_id == current_user.id)
    
    if status:
        query = query.filter(ToolInstance.status == status)
    
    total = query.count()
    instances = query.limit(limit).offset(offset).all()
    
    return QueryResponse(
        items=[_to_response(instance) for instance in instances],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{instance_id}", response_model=ToolInstanceResponse)
def get_tool_instance(
    instance_id: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Retrieve a single ToolInstance by ID if owned by the current user."""
    instance = db.query(ToolInstance).filter(
        ToolInstance.id == instance_id,
        ToolInstance.user_id == current_user.id
    ).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Not Found")
    return _to_response(instance)


@router.put("", response_model=BulkOperationResponse)
def update_tool_instances(
    request: BulkUpdateRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update tool instances in bulk."""
    results = []
    errors = []
    
    for index, update_data in enumerate(request.items):
        try:
            instance = db.query(ToolInstance).filter(
                ToolInstance.id == update_data.id,
                ToolInstance.user_id == current_user.id
            ).first()
            
            if not instance:
                errors.append(ErrorDetail(
                    index=index,
                    id=update_data.id,
                    message="Instance not found or access denied"
                ))
                continue
            
            if instance.version != update_data.version:
                errors.append(ErrorDetail(
                    index=index,
                    id=update_data.id,
                    message=f"Version conflict: expected {instance.version}, got {update_data.version}"
                ))
                continue
            
            # Apply updates
            if update_data.assembly_id is not None:
                instance.assembly_id = update_data.assembly_id
            if update_data.serial_number is not None:
                instance.serial_number = update_data.serial_number
            if update_data.status is not None:
                instance.status = update_data.status
            if update_data.location is not None:
                instance.location = update_data.location
            if update_data.measured_geometry is not None:
                instance.measured_geometry = update_data.measured_geometry
            if update_data.lifecycle is not None:
                instance.lifecycle = update_data.lifecycle
            
            instance.updated_by = current_user.id
            instance.updated_at = datetime.now(UTC)
            instance.version += 1
            
            db.flush()
            results.append(_to_response(instance))
            
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


@router.delete("", response_model=BulkOperationResponse)
def delete_tool_instances(
    request: BulkDeleteRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Delete tool instances in bulk."""
    results = []
    errors = []
    
    for index, instance_id in enumerate(request.ids):
        try:
            instance = db.query(ToolInstance).filter(
                ToolInstance.id == instance_id,
                ToolInstance.user_id == current_user.id
            ).first()
            
            if not instance:
                errors.append(ErrorDetail(
                    index=index,
                    id=instance_id,
                    message="Instance not found or access denied"
                ))
                continue
            
            response = _to_response(instance)
            db.delete(instance)
            db.flush()
            
            results.append(response)
            
        except Exception as e:
            errors.append(ErrorDetail(
                index=index,
                id=instance_id,
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


def _to_response(instance: ToolInstance) -> ToolInstanceResponse:
    """Convert ToolInstance entity to response model."""
    return ToolInstanceResponse(
        id=instance.id,
        assembly_id=instance.assembly_id,
        serial_number=instance.serial_number,
        status=instance.status,
        location=instance.location,
        measured_geometry=instance.measured_geometry,
        lifecycle=instance.lifecycle,
        user_id=instance.user_id,
        created_by=instance.created_by,
        updated_by=instance.updated_by,
        created_at=instance.created_at.isoformat() if instance.created_at else "",
        updated_at=instance.updated_at.isoformat() if instance.updated_at else "",
        version=instance.version
    )
