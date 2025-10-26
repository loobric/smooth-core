# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Backup and restore API endpoints.

Provides REST API for database backup and restore operations.

Assumptions:
- Backup downloads as JSON file
- Restore accepts uploaded JSON file
- Requires admin:backup scope
- Returns metadata and validation results
"""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from smooth.backup import (
    export_backup_json, restore_backup_json,
    BackupVersionError, BackupValidationError
)
from smooth.api.auth import get_db

# Router
router = APIRouter(prefix="/api/v1/backup", tags=["backup"])


@router.get("/export")
def export_database(
    db: Session = Depends(get_db)
):
    """Export full database backup as JSON.
    
    Args:
        db: Database session
        
    Returns:
        JSON response with backup data
        
    Assumptions:
    - Returns application/json
    - Includes all entities and metadata
    - TODO: Requires admin:backup scope
    """
    try:
        backup_json = export_backup_json(db)
        
        return Response(
            content=backup_json,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=smooth-backup.json"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/import")
async def import_database(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Import database from backup JSON file.
    
    Args:
        file: Uploaded JSON backup file
        db: Database session
        
    Returns:
        dict: Import result with success status and counts
        
    Raises:
        HTTPException: If import fails
        
    Assumptions:
    - Accepts JSON file upload
    - Validates before importing
    - Atomic operation (all or nothing)
    - TODO: Requires admin:backup scope
    """
    try:
        # Read file content
        content = await file.read()
        json_str = content.decode('utf-8')
        
        # Restore from JSON
        result = restore_backup_json(db, json_str)
        
        return result
        
    except BackupVersionError as e:
        raise HTTPException(status_code=400, detail=f"Version error: {str(e)}")
    except BackupValidationError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
