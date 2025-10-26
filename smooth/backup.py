# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Backup and restore operations.

Handles full database export/import with validation and atomic operations.

Assumptions:
- Backup format is JSON
- All data serializable (datetimes as ISO strings)
- Atomic restore (all or nothing)
- Validates schema version compatibility
- Preserves versioning fields (created_at, updated_at, version)
- Excludes temporary data (password reset tokens, sessions)
"""
import json
from datetime import datetime, UTC
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import inspect

from smooth.database.schema import (
    User, ApiKey, ToolItem, ToolAssembly, ToolInstance,
    ToolPreset, ToolUsage, ToolSet
)


class BackupVersionError(Exception):
    """Raised when backup version is incompatible."""
    pass


class BackupValidationError(Exception):
    """Raised when backup data fails validation."""
    pass


# Entity order for restore (respects foreign key dependencies)
ENTITY_ORDER = [
    ("users", User),
    ("tool_items", ToolItem),
    ("tool_assemblies", ToolAssembly),
    ("tool_instances", ToolInstance),
    ("tool_presets", ToolPreset),
    ("tool_usage", ToolUsage),
    ("tool_sets", ToolSet),
    ("api_keys", ApiKey),
]


def _serialize_entity(entity: Any) -> dict:
    """Serialize a SQLAlchemy entity to a dictionary.
    
    Args:
        entity: SQLAlchemy model instance
        
    Returns:
        dict: Serialized entity with ISO datetime strings
    """
    result = {}
    
    for column in inspect(entity).mapper.column_attrs:
        value = getattr(entity, column.key)
        
        # Convert datetime to ISO string
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            result[column.key] = value.isoformat()
        else:
            result[column.key] = value
    
    return result


def export_backup(session: Session, user_id: str = None, admin: bool = False) -> dict:
    """Export database backup (user-level or admin-level).
    
    Args:
        session: Database session
        user_id: User ID for user-level backup (None for legacy full backup)
        admin: If True, exports all data (requires admin privileges)
        
    Returns:
        dict: Backup data with metadata and entities
        
    Assumptions:
    - admin=True: Exports entire database (all users, all data)
    - admin=False: Exports only user's own data (tool entities filtered by user_id)
    - User-level backup includes: their account + their tool data + their API keys
    - Excludes temporary data (password reset tokens)
    - Serializes all timestamps as ISO strings
    """
    entities = {}
    counts = {}
    
    # Determine backup type
    backup_type = "admin" if admin else "user"
    
    for entity_name, entity_class in ENTITY_ORDER:
        if admin or user_id is None:
            # Admin backup or legacy: get all records
            records = session.query(entity_class).all()
        else:
            # User backup: filter by user_id
            if entity_name == "users":
                # Only include the user's own account
                records = session.query(entity_class).filter(entity_class.id == user_id).all()
            elif entity_name == "api_keys":
                # Only include user's API keys
                records = session.query(entity_class).filter(entity_class.user_id == user_id).all()
            elif entity_name in ["tool_items", "tool_assemblies", "tool_instances", 
                                "tool_presets", "tool_usage", "tool_sets"]:
                # Only include user's tool data (filter by user_id field)
                if hasattr(entity_class, 'user_id'):
                    records = session.query(entity_class).filter(entity_class.user_id == user_id).all()
                else:
                    records = []
            else:
                records = []
        
        entities[entity_name] = [_serialize_entity(record) for record in records]
        counts[entity_name] = len(records)
    
    metadata = {
        "version": "0.1.0",
        "timestamp": datetime.now(UTC).isoformat(),
        "backup_type": backup_type,
        "counts": counts
    }
    
    # Add user_id to metadata for user backups
    if not admin and user_id:
        metadata["user_id"] = user_id
    
    backup = {
        "metadata": metadata,
        "entities": entities
    }
    
    return backup


def export_backup_json(session: Session, user_id: str = None, admin: bool = False) -> str:
    """Export backup as JSON string.
    
    Args:
        session: Database session
        user_id: User ID for user-level backup
        admin: If True, exports all data
        
    Returns:
        str: JSON-formatted backup
    """
    backup = export_backup(session, user_id=user_id, admin=admin)
    return json.dumps(backup, indent=2)


def _validate_backup(backup: dict) -> None:
    """Validate backup structure and version compatibility.
    
    Args:
        backup: Backup data dictionary
        
    Raises:
        BackupVersionError: If version is incompatible
        BackupValidationError: If structure is invalid
    """
    # Check required top-level keys
    if "metadata" not in backup or "entities" not in backup:
        raise BackupValidationError("Backup missing required keys: metadata, entities")
    
    # Check version compatibility
    version = backup["metadata"].get("version")
    if not version:
        raise BackupValidationError("Backup missing version in metadata")
    
    # Simple version check (for now, just major version)
    major_version = version.split(".")[0]
    if major_version != "0":
        raise BackupVersionError(f"Incompatible backup version: {version}")


def _validate_entity(entity_name: str, entity_data: dict, entity_class: Any) -> None:
    """Validate entity data has required fields.
    
    Args:
        entity_name: Entity type name
        entity_data: Entity data dictionary
        entity_class: SQLAlchemy model class
        
    Raises:
        BackupValidationError: If required fields are missing
    """
    # Get required columns (non-nullable, no default)
    mapper = inspect(entity_class)
    required_fields = []
    
    for column in mapper.columns:
        # Skip auto-increment IDs with defaults
        if not column.nullable and column.default is None and column.server_default is None:
            required_fields.append(column.name)
    
    # Check for missing fields
    missing = [field for field in required_fields if field not in entity_data]
    if missing:
        raise BackupValidationError(
            f"Entity {entity_name} missing required fields: {missing}"
        )


def _deserialize_entity(entity_class: Any, entity_data: dict) -> Any:
    """Deserialize entity data to SQLAlchemy model instance.
    
    Args:
        entity_class: SQLAlchemy model class
        entity_data: Entity data dictionary
        
    Returns:
        SQLAlchemy model instance
    """
    # Convert ISO datetime strings back to datetime objects
    data = {}
    mapper = inspect(entity_class)
    
    for key, value in entity_data.items():
        column = mapper.columns.get(key)
        if column is not None:
            # Check if column is a datetime type
            if hasattr(column.type, 'python_type') and column.type.python_type == datetime:
                if isinstance(value, str):
                    # Parse ISO format and ensure UTC
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    # Convert to naive datetime for SQLite compatibility
                    data[key] = dt.replace(tzinfo=None)
                else:
                    data[key] = value
            else:
                data[key] = value
        else:
            data[key] = value
    
    return entity_class(**data)


def _clear_user_data(session: Session, user_id: str) -> None:
    """Clear existing data for a specific user before restore.
    
    Args:
        session: Database session
        user_id: User ID to clear data for
    """
    from smooth.database.schema import ApiKey, ToolItem, ToolAssembly, ToolInstance
    from smooth.database.schema import ToolPreset, ToolUsage, ToolSet, User
    
    # Delete in reverse dependency order
    session.query(ApiKey).filter(ApiKey.user_id == user_id).delete()
    
    # Delete tool data
    for entity_class in [ToolUsage, ToolSet, ToolPreset, ToolInstance, ToolAssembly, ToolItem]:
        if hasattr(entity_class, 'user_id'):
            session.query(entity_class).filter(entity_class.user_id == user_id).delete()
    
    # Delete user account last
    session.query(User).filter(User.id == user_id).delete()


def _clear_all_data(session: Session) -> None:
    """Clear all data from database before admin restore.
    
    Args:
        session: Database session
    """
    from smooth.database.schema import (
        ApiKey, ToolItem, ToolAssembly, ToolInstance,
        ToolPreset, ToolUsage, ToolSet, User
    )
    
    # Delete in reverse dependency order
    session.query(ApiKey).delete()
    session.query(ToolUsage).delete()
    session.query(ToolSet).delete()
    session.query(ToolPreset).delete()
    session.query(ToolInstance).delete()
    session.query(ToolAssembly).delete()
    session.query(ToolItem).delete()
    session.query(User).delete()


def restore_backup(session: Session, backup: dict) -> dict:
    """Restore database from backup.
    
    Args:
        session: Database session
        backup: Backup data dictionary
        
    Returns:
        dict: Restore result with success status and counts
        
    Raises:
        BackupVersionError: If version is incompatible
        BackupValidationError: If data is invalid
        
    Assumptions:
    - Atomic operation (all or nothing)
    - Validates before restoring
    - Clears existing data before restore
    - User-level restore: Clears only that user's data
    - Admin-level restore: Clears entire database
    """
    # Validate backup
    _validate_backup(backup)
    
    # Check backup type and clear appropriate data
    backup_type = backup.get("metadata", {}).get("backup_type", "admin")
    user_id = backup.get("metadata", {}).get("user_id")
    
    if backup_type == "user" and user_id:
        # Clear only this user's data
        _clear_user_data(session, user_id)
    else:
        # Admin backup or legacy: Clear all data
        _clear_all_data(session)
    
    restored_count = 0
    
    try:
        # Begin transaction
        entities_data = backup.get("entities", {})
        
        # Restore entities in order
        for entity_name, entity_class in ENTITY_ORDER:
            entity_list = entities_data.get(entity_name, [])
            
            for entity_data in entity_list:
                # Validate entity
                _validate_entity(entity_name, entity_data, entity_class)
                
                # Deserialize and add
                entity = _deserialize_entity(entity_class, entity_data)
                session.add(entity)
                restored_count += 1
        
        # Commit transaction
        session.commit()
        
        return {
            "success": True,
            "restored_count": restored_count
        }
        
    except (BackupValidationError, BackupVersionError):
        # Re-raise validation errors
        session.rollback()
        raise
    except Exception as e:
        # Rollback on any error
        session.rollback()
        raise BackupValidationError(f"Restore failed: {str(e)}")


def restore_backup_json(session: Session, json_str: str) -> dict:
    """Restore database from JSON string.
    
    Args:
        session: Database session
        json_str: JSON-formatted backup string
        
    Returns:
        dict: Restore result
        
    Raises:
        BackupValidationError: If JSON is invalid or data is invalid
    """
    try:
        backup = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise BackupValidationError(f"Invalid JSON: {str(e)}")
    
    return restore_backup(session, backup)
