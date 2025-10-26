# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
ToolItem API endpoints.

Bulk-first design: all operations accept arrays.

Assumptions:
- POST /api/v1/tool-items - Create (bulk)
- GET /api/v1/tool-items - List/query with filters
- PUT /api/v1/tool-items - Update (bulk) with version checking
- DELETE /api/v1/tool-items - Delete (bulk)
- Multi-tenant: Users only access their own data
- Partial success: Returns per-item results and errors
"""
from typing import Annotated, Optional, List
from uuid import uuid4
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from smooth.api.auth import get_db, require_auth
from smooth.database.schema import User, ToolItem


router = APIRouter(prefix="/api/v1/tool-items", tags=["tool-items"])


# Request/Response Models
class ToolItemCreate(BaseModel):
    """Schema for creating a tool item.
    
    Assumptions:
    - Type is required but validated in endpoint for partial success
    - Other fields are optional
    """
    type: Optional[str] = Field(None, description="Tool type: cutting_tool, holder, insert, adapter")
    manufacturer: Optional[str] = None
    product_code: Optional[str] = None
    description: Optional[str] = None
    geometry: Optional[dict] = None
    material: Optional[dict] = None
    iso_13399_reference: Optional[str] = None


class ToolItemUpdate(BaseModel):
    """Schema for updating a tool item."""
    id: str
    version: int
    type: Optional[str] = None
    manufacturer: Optional[str] = None
    product_code: Optional[str] = None
    description: Optional[str] = None
    geometry: Optional[dict] = None
    material: Optional[dict] = None
    iso_13399_reference: Optional[str] = None


class ToolItemResponse(BaseModel):
    """Schema for tool item response."""
    id: str
    type: str
    manufacturer: Optional[str]
    product_code: Optional[str]
    description: Optional[str]
    geometry: Optional[dict]
    material: Optional[dict]
    iso_13399_reference: Optional[str]
    user_id: str
    created_by: str
    updated_by: str
    created_at: str
    updated_at: str
    version: int


class BulkCreateRequest(BaseModel):
    """Bulk create request."""
    items: List[ToolItemCreate]


class BulkUpdateRequest(BaseModel):
    """Bulk update request."""
    items: List[ToolItemUpdate]


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
    results: List[ToolItemResponse] = []
    errors: List[ErrorDetail] = []


class QueryResponse(BaseModel):
    """Response for query operations."""
    items: List[ToolItemResponse]
    total: int
    limit: int
    offset: int


@router.post("", response_model=BulkOperationResponse)
def create_tool_items(
    request: BulkCreateRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Create tool items in bulk.
    
    Args:
        request: Bulk create request with array of items
        current_user: Authenticated user
        db: Database session
        
    Returns:
        BulkOperationResponse with success/error counts and results
        
    Assumptions:
    - Auto-generates IDs if not provided
    - Sets user_id, created_by, updated_by from authenticated user
    - Partial success: valid items created, invalid items return errors
    """
    results = []
    errors = []
    
    for index, item_data in enumerate(request.items):
        try:
            # Validate required fields
            if not item_data.type:
                raise ValueError("Field 'type' is required")
            
            # Create tool item
            tool_item = ToolItem(
                id=str(uuid4()),
                type=item_data.type,
                manufacturer=item_data.manufacturer,
                product_code=item_data.product_code,
                description=item_data.description,
                geometry=item_data.geometry,
                material=item_data.material,
                iso_13399_reference=item_data.iso_13399_reference,
                user_id=current_user.id,
                created_by=current_user.id,
                updated_by=current_user.id
            )
            
            db.add(tool_item)
            db.flush()  # Flush to get the generated timestamps
            
            results.append(_to_response(tool_item))
            
        except Exception as e:
            errors.append(ErrorDetail(
                index=index,
                message=str(e)
            ))
    
    # Commit all successful creates
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
def list_tool_items(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    type: Optional[str] = Query(None, description="Filter by tool type"),
    manufacturer: Optional[str] = Query(None, description="Filter by manufacturer"),
    product_code: Optional[str] = Query(None, description="Filter by product code"),
    limit: int = Query(100, ge=1, le=1000, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip")
):
    """List tool items with filters and pagination.
    
    Args:
        current_user: Authenticated user
        db: Database session
        type: Optional filter by tool type
        manufacturer: Optional filter by manufacturer
        product_code: Optional filter by product code
        limit: Max items to return
        offset: Items to skip
        
    Returns:
        QueryResponse with items, total count, limit, offset
        
    Assumptions:
    - Automatically filters by user_id (multi-tenant)
    - Supports pagination
    - Returns total count for pagination
    """
    # Build query with user filter
    query = db.query(ToolItem).filter(ToolItem.user_id == current_user.id)
    
    # Apply filters
    if type:
        query = query.filter(ToolItem.type == type)
    if manufacturer:
        query = query.filter(ToolItem.manufacturer == manufacturer)
    if product_code:
        query = query.filter(ToolItem.product_code == product_code)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    items = query.limit(limit).offset(offset).all()
    
    return QueryResponse(
        items=[_to_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset
    )


@router.put("", response_model=BulkOperationResponse)
def update_tool_items(
    request: BulkUpdateRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update tool items in bulk.
    
    Args:
        request: Bulk update request with array of items
        current_user: Authenticated user
        db: Database session
        
    Returns:
        BulkOperationResponse with success/error counts and results
        
    Assumptions:
    - Checks version for optimistic locking
    - Users can only update their own items
    - Partial success: valid updates applied, invalid updates return errors
    - Increments version on successful update
    """
    results = []
    errors = []
    
    for index, update_data in enumerate(request.items):
        try:
            # Find item (with user check)
            item = db.query(ToolItem).filter(
                ToolItem.id == update_data.id,
                ToolItem.user_id == current_user.id
            ).first()
            
            if not item:
                errors.append(ErrorDetail(
                    index=index,
                    id=update_data.id,
                    message="Item not found or access denied"
                ))
                continue
            
            # Check version for optimistic locking
            if item.version != update_data.version:
                errors.append(ErrorDetail(
                    index=index,
                    id=update_data.id,
                    message=f"Version conflict: expected {item.version}, got {update_data.version}"
                ))
                continue
            
            # Apply updates
            if update_data.type is not None:
                item.type = update_data.type
            if update_data.manufacturer is not None:
                item.manufacturer = update_data.manufacturer
            if update_data.product_code is not None:
                item.product_code = update_data.product_code
            if update_data.description is not None:
                item.description = update_data.description
            if update_data.geometry is not None:
                item.geometry = update_data.geometry
            if update_data.material is not None:
                item.material = update_data.material
            if update_data.iso_13399_reference is not None:
                item.iso_13399_reference = update_data.iso_13399_reference
            
            # Update metadata
            item.updated_by = current_user.id
            item.updated_at = datetime.now(UTC)
            item.version += 1
            
            db.flush()
            results.append(_to_response(item))
            
        except Exception as e:
            errors.append(ErrorDetail(
                index=index,
                id=update_data.id,
                message=str(e)
            ))
    
    # Commit all successful updates
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
def delete_tool_items(
    request: BulkDeleteRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Delete tool items in bulk.
    
    Args:
        request: Bulk delete request with array of IDs
        current_user: Authenticated user
        db: Database session
        
    Returns:
        BulkOperationResponse with success/error counts
        
    Assumptions:
    - Users can only delete their own items
    - Hard delete (not soft delete)
    - Partial success: valid deletes applied, invalid deletes return errors
    """
    results = []
    errors = []
    
    for index, item_id in enumerate(request.ids):
        try:
            # Find item (with user check)
            item = db.query(ToolItem).filter(
                ToolItem.id == item_id,
                ToolItem.user_id == current_user.id
            ).first()
            
            if not item:
                errors.append(ErrorDetail(
                    index=index,
                    id=item_id,
                    message="Item not found or access denied"
                ))
                continue
            
            # Store response before deletion
            response = _to_response(item)
            
            # Delete item
            db.delete(item)
            db.flush()
            
            results.append(response)
            
        except Exception as e:
            errors.append(ErrorDetail(
                index=index,
                id=item_id,
                message=str(e)
            ))
    
    # Commit all successful deletes
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


def _to_response(item: ToolItem) -> ToolItemResponse:
    """Convert ToolItem entity to response model.
    
    Args:
        item: ToolItem entity
        
    Returns:
        ToolItemResponse model
    """
    return ToolItemResponse(
        id=item.id,
        type=item.type,
        manufacturer=item.manufacturer,
        product_code=item.product_code,
        description=item.description,
        geometry=item.geometry,
        material=item.material,
        iso_13399_reference=item.iso_13399_reference,
        user_id=item.user_id,
        created_by=item.created_by,
        updated_by=item.updated_by,
        created_at=item.created_at.isoformat() if item.created_at else "",
        updated_at=item.updated_at.isoformat() if item.updated_at else "",
        version=item.version
    )
