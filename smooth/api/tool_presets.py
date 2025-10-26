# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
ToolPreset API endpoints.

Bulk-first design: all operations accept arrays.

Assumptions:
- POST /api/v1/tool-presets - Create (bulk)
- GET /api/v1/tool-presets - List/query with filters
- PUT /api/v1/tool-presets - Update (bulk) with version checking
- DELETE /api/v1/tool-presets - Delete (bulk)
- instance_id references ToolInstance
- machine_id and tool_number identify preset on machine
"""
from typing import Annotated, Optional, List
from uuid import uuid4
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, require_auth
from smooth.database.schema import User, ToolPreset


router = APIRouter(prefix="/api/v1/tool-presets", tags=["tool-presets"])


# Request/Response Models
class ToolPresetCreate(BaseModel):
    """Schema for creating a tool preset."""
    machine_id: Optional[str] = None
    tool_number: Optional[int] = None
    instance_id: Optional[str] = None
    pocket: Optional[int] = None
    description: Optional[str] = None
    metadata: Optional[dict] = None
    offsets: Optional[dict] = None
    orientation: Optional[dict] = None
    limits: Optional[dict] = None
    loaded_at: Optional[datetime] = None
    loaded_by: Optional[str] = None


class ToolPresetUpdate(BaseModel):
    """Schema for updating a tool preset."""
    id: str
    version: int
    machine_id: Optional[str] = None
    tool_number: Optional[int] = None
    instance_id: Optional[str] = None
    pocket: Optional[int] = None
    description: Optional[str] = None
    metadata: Optional[dict] = None
    offsets: Optional[dict] = None
    orientation: Optional[dict] = None
    limits: Optional[dict] = None
    loaded_at: Optional[datetime] = None
    loaded_by: Optional[str] = None


class ToolPresetResponse(BaseModel):
    """Schema for tool preset response."""
    id: str
    machine_id: str
    tool_number: int
    instance_id: Optional[str]
    pocket: Optional[int]
    description: Optional[str]
    metadata: Optional[dict]
    offsets: Optional[dict]
    orientation: Optional[dict]
    limits: Optional[dict]
    loaded_at: Optional[str]
    loaded_by: Optional[str]
    user_id: str
    created_by: str
    updated_by: str
    created_at: str
    updated_at: str
    version: int


class BulkCreateRequest(BaseModel):
    """Bulk create request."""
    items: List[ToolPresetCreate]


class BulkUpdateRequest(BaseModel):
    """Bulk update request."""
    items: List[ToolPresetUpdate]


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
    results: List[ToolPresetResponse] = []
    errors: List[ErrorDetail] = []


class QueryResponse(BaseModel):
    """Response for query operations."""
    items: List[ToolPresetResponse]
    total: int
    limit: int
    offset: int


@router.post("", response_model=BulkOperationResponse)
def create_tool_presets(
    request: BulkCreateRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Create tool presets in bulk."""
    results = []
    errors = []
    
    for index, preset_data in enumerate(request.items):
        try:
            # Validate required fields
            if not preset_data.machine_id:
                raise ValueError("Field 'machine_id' is required")
            if preset_data.tool_number is None:
                raise ValueError("Field 'tool_number' is required")
            
            # Create tool preset
            tool_preset = ToolPreset(
                id=str(uuid4()),
                machine_id=preset_data.machine_id,
                tool_number=preset_data.tool_number,
                instance_id=preset_data.instance_id,
                pocket=preset_data.pocket,
                description=preset_data.description,
                preset_metadata=preset_data.metadata,
                offsets=preset_data.offsets,
                orientation=preset_data.orientation,
                limits=preset_data.limits,
                loaded_at=preset_data.loaded_at,
                loaded_by=preset_data.loaded_by,
                user_id=current_user.id,
                created_by=current_user.id,
                updated_by=current_user.id
            )
            
            db.add(tool_preset)
            db.flush()
            
            results.append(_to_response(tool_preset))
            
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
def list_tool_presets(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    machine_id: Optional[str] = Query(None, description="Filter by machine_id"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List tool presets with filters and pagination."""
    query = db.query(ToolPreset).filter(ToolPreset.user_id == current_user.id)
    
    if machine_id:
        query = query.filter(ToolPreset.machine_id == machine_id)
    
    total = query.count()
    presets = query.limit(limit).offset(offset).all()
    
    return QueryResponse(
        items=[_to_response(preset) for preset in presets],
        total=total,
        limit=limit,
        offset=offset
    )


@router.put("", response_model=BulkOperationResponse)
def update_tool_presets(
    request: BulkUpdateRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update tool presets in bulk."""
    results = []
    errors = []
    
    for index, update_data in enumerate(request.items):
        try:
            preset = db.query(ToolPreset).filter(
                ToolPreset.id == update_data.id,
                ToolPreset.user_id == current_user.id
            ).first()
            
            if not preset:
                errors.append(ErrorDetail(
                    index=index,
                    id=update_data.id,
                    message="Preset not found or access denied"
                ))
                continue
            
            if preset.version != update_data.version:
                errors.append(ErrorDetail(
                    index=index,
                    id=update_data.id,
                    message=f"Version conflict: expected {preset.version}, got {update_data.version}"
                ))
                continue
            
            # Apply updates
            if update_data.machine_id is not None:
                preset.machine_id = update_data.machine_id
            if update_data.tool_number is not None:
                preset.tool_number = update_data.tool_number
            if update_data.instance_id is not None:
                preset.instance_id = update_data.instance_id
            if update_data.pocket is not None:
                preset.pocket = update_data.pocket
            if update_data.description is not None:
                preset.description = update_data.description
            if update_data.metadata is not None:
                preset.preset_metadata = update_data.metadata
            if update_data.offsets is not None:
                preset.offsets = update_data.offsets
            if update_data.orientation is not None:
                preset.orientation = update_data.orientation
            if update_data.limits is not None:
                preset.limits = update_data.limits
            if update_data.loaded_at is not None:
                preset.loaded_at = update_data.loaded_at
            if update_data.loaded_by is not None:
                preset.loaded_by = update_data.loaded_by
            
            preset.updated_by = current_user.id
            preset.updated_at = datetime.now(UTC)
            preset.version += 1
            
            db.flush()
            results.append(_to_response(preset))
            
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
def delete_tool_presets(
    request: BulkDeleteRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Delete tool presets in bulk."""
    results = []
    errors = []
    
    for index, preset_id in enumerate(request.ids):
        try:
            preset = db.query(ToolPreset).filter(
                ToolPreset.id == preset_id,
                ToolPreset.user_id == current_user.id
            ).first()
            
            if not preset:
                errors.append(ErrorDetail(
                    index=index,
                    id=preset_id,
                    message="Preset not found or access denied"
                ))
                continue
            
            response = _to_response(preset)
            db.delete(preset)
            db.flush()
            
            results.append(response)
            
        except Exception as e:
            errors.append(ErrorDetail(
                index=index,
                id=preset_id,
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


def _to_response(preset: ToolPreset) -> ToolPresetResponse:
    """Convert ToolPreset entity to response model."""
    return ToolPresetResponse(
        id=preset.id,
        machine_id=preset.machine_id,
        tool_number=preset.tool_number,
        instance_id=preset.instance_id,
        pocket=preset.pocket,
        description=preset.description,
        metadata=preset.preset_metadata,
        offsets=preset.offsets,
        orientation=preset.orientation,
        limits=preset.limits,
        loaded_at=preset.loaded_at.isoformat() if preset.loaded_at else None,
        loaded_by=preset.loaded_by,
        user_id=preset.user_id,
        created_by=preset.created_by,
        updated_by=preset.updated_by,
        created_at=preset.created_at.isoformat() if preset.created_at else "",
        updated_at=preset.updated_at.isoformat() if preset.updated_at else "",
        version=preset.version
    )
