# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
ToolAssembly API endpoints.

Bulk-first design: all operations accept arrays.

Assumptions:
- POST /api/v1/tool-assemblies - Create (bulk)
- GET /api/v1/tool-assemblies - List/query with filters
- PUT /api/v1/tool-assemblies - Update (bulk) with version checking
- DELETE /api/v1/tool-assemblies - Delete (bulk)
- Multi-tenant: Users only access their own data
- Partial success: Returns per-item results and errors
"""
from typing import Annotated, Optional, List
from uuid import uuid4
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, require_auth
from smooth.database.schema import User, ToolAssembly


router = APIRouter(prefix="/api/v1/tool-assemblies", tags=["tool-assemblies"])


# Request/Response Models
class ToolAssemblyCreate(BaseModel):
    """Schema for creating a tool assembly."""
    name: Optional[str] = None
    description: Optional[str] = None
    components: Optional[list] = None
    computed_geometry: Optional[dict] = None


class ToolAssemblyUpdate(BaseModel):
    """Schema for updating a tool assembly."""
    id: str
    version: int
    name: Optional[str] = None
    description: Optional[str] = None
    components: Optional[list] = None
    computed_geometry: Optional[dict] = None


class ToolAssemblyResponse(BaseModel):
    """Schema for tool assembly response."""
    id: str
    name: str
    description: Optional[str]
    components: list
    computed_geometry: Optional[dict]
    user_id: str
    created_by: str
    updated_by: str
    created_at: str
    updated_at: str
    version: int


class BulkCreateRequest(BaseModel):
    """Bulk create request."""
    items: List[ToolAssemblyCreate]


class BulkUpdateRequest(BaseModel):
    """Bulk update request."""
    items: List[ToolAssemblyUpdate]


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
    results: List[ToolAssemblyResponse] = []
    errors: List[ErrorDetail] = []


class QueryResponse(BaseModel):
    """Response for query operations."""
    items: List[ToolAssemblyResponse]
    total: int
    limit: int
    offset: int


@router.post("", response_model=BulkOperationResponse)
def create_tool_assemblies(
    request: BulkCreateRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Create tool assemblies in bulk.
    
    Args:
        request: Bulk create request with array of assemblies
        current_user: Authenticated user
        db: Database session
        
    Returns:
        BulkOperationResponse with success/error counts and results
    """
    results = []
    errors = []
    
    for index, assembly_data in enumerate(request.items):
        try:
            # Validate required fields
            if not assembly_data.name:
                raise ValueError("Field 'name' is required")
            if not assembly_data.components:
                raise ValueError("Field 'components' is required")
            
            # Create tool assembly
            tool_assembly = ToolAssembly(
                id=str(uuid4()),
                name=assembly_data.name,
                description=assembly_data.description,
                components=assembly_data.components,
                computed_geometry=assembly_data.computed_geometry,
                user_id=current_user.id,
                created_by=current_user.id,
                updated_by=current_user.id
            )
            
            db.add(tool_assembly)
            db.flush()
            
            results.append(_to_response(tool_assembly))
            
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
def list_tool_assemblies(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip")
):
    """List tool assemblies with pagination.
    
    Args:
        current_user: Authenticated user
        db: Database session
        limit: Max items to return
        offset: Items to skip
        
    Returns:
        QueryResponse with assemblies, total count, limit, offset
    """
    # Build query with user filter
    query = db.query(ToolAssembly).filter(ToolAssembly.user_id == current_user.id)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    assemblies = query.limit(limit).offset(offset).all()
    
    return QueryResponse(
        items=[_to_response(assembly) for assembly in assemblies],
        total=total,
        limit=limit,
        offset=offset
    )


@router.put("", response_model=BulkOperationResponse)
def update_tool_assemblies(
    request: BulkUpdateRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update tool assemblies in bulk.
    
    Args:
        request: Bulk update request with array of assemblies
        current_user: Authenticated user
        db: Database session
        
    Returns:
        BulkOperationResponse with success/error counts and results
    """
    results = []
    errors = []
    
    for index, update_data in enumerate(request.items):
        try:
            # Find assembly (with user check)
            assembly = db.query(ToolAssembly).filter(
                ToolAssembly.id == update_data.id,
                ToolAssembly.user_id == current_user.id
            ).first()
            
            if not assembly:
                errors.append(ErrorDetail(
                    index=index,
                    id=update_data.id,
                    message="Assembly not found or access denied"
                ))
                continue
            
            # Check version for optimistic locking
            if assembly.version != update_data.version:
                errors.append(ErrorDetail(
                    index=index,
                    id=update_data.id,
                    message=f"Version conflict: expected {assembly.version}, got {update_data.version}"
                ))
                continue
            
            # Apply updates
            if update_data.name is not None:
                assembly.name = update_data.name
            if update_data.description is not None:
                assembly.description = update_data.description
            if update_data.components is not None:
                assembly.components = update_data.components
            if update_data.computed_geometry is not None:
                assembly.computed_geometry = update_data.computed_geometry
            
            # Update metadata
            assembly.updated_by = current_user.id
            assembly.updated_at = datetime.now(UTC)
            assembly.version += 1
            
            db.flush()
            results.append(_to_response(assembly))
            
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
def delete_tool_assemblies(
    request: BulkDeleteRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Delete tool assemblies in bulk.
    
    Args:
        request: Bulk delete request with array of IDs
        current_user: Authenticated user
        db: Database session
        
    Returns:
        BulkOperationResponse with success/error counts
    """
    results = []
    errors = []
    
    for index, assembly_id in enumerate(request.ids):
        try:
            # Find assembly (with user check)
            assembly = db.query(ToolAssembly).filter(
                ToolAssembly.id == assembly_id,
                ToolAssembly.user_id == current_user.id
            ).first()
            
            if not assembly:
                errors.append(ErrorDetail(
                    index=index,
                    id=assembly_id,
                    message="Assembly not found or access denied"
                ))
                continue
            
            # Store response before deletion
            response = _to_response(assembly)
            
            # Delete assembly
            db.delete(assembly)
            db.flush()
            
            results.append(response)
            
        except Exception as e:
            errors.append(ErrorDetail(
                index=index,
                id=assembly_id,
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


def _to_response(assembly: ToolAssembly) -> ToolAssemblyResponse:
    """Convert ToolAssembly entity to response model.
    
    Args:
        assembly: ToolAssembly entity
        
    Returns:
        ToolAssemblyResponse model
    """
    return ToolAssemblyResponse(
        id=assembly.id,
        name=assembly.name,
        description=assembly.description,
        components=assembly.components,
        computed_geometry=assembly.computed_geometry,
        user_id=assembly.user_id,
        created_by=assembly.created_by,
        updated_by=assembly.updated_by,
        created_at=assembly.created_at.isoformat() if assembly.created_at else "",
        updated_at=assembly.updated_at.isoformat() if assembly.updated_at else "",
        version=assembly.version
    )
