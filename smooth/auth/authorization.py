# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Authorization and permission checking functions.

Implements scope-based authorization, data isolation, and permission helpers.

Assumptions:
- Scopes follow pattern: "read", "write:<entity>", "delete:<entity>", "admin:<entity>"
- Wildcards supported: "admin:*" grants all permissions, "write:*" grants write to all
- Users can only access their own data unless admin
- Authorization decisions are logged for audit trail
"""
import structlog
from typing import Optional

logger = structlog.get_logger()


class PermissionDeniedError(Exception):
    """Raised when user lacks required permission."""
    pass


def has_scope(scopes: list[str], required_scope: str) -> bool:
    """Check if user has required scope.
    
    Args:
        scopes: List of scopes granted to user
        required_scope: Required scope (e.g., "read", "write:items")
        
    Returns:
        bool: True if user has required scope, False otherwise
        
    Assumptions:
    - Exact match grants permission
    - "admin:*" grants all permissions
    - Wildcard entity matching (e.g., "write:*" matches "write:items")
    - Case-sensitive matching
    """
    if not scopes:
        return False
    
    # Check exact match
    if required_scope in scopes:
        return True
    
    # Check for admin wildcard (grants everything)
    if "admin:*" in scopes:
        return True
    
    # Check for action wildcard (e.g., "write:*" matches "write:items")
    if ":" in required_scope:
        action, entity = required_scope.split(":", 1)
        wildcard_scope = f"{action}:*"
        if wildcard_scope in scopes:
            return True
    
    # Check if user has "read" scope (covers all read operations)
    if required_scope == "read" and "read" in scopes:
        return True
    
    return False


def require_scope(scopes: list[str], required_scope: str) -> None:
    """Require user to have specific scope, raise if not.
    
    Args:
        scopes: List of scopes granted to user
        required_scope: Required scope
        
    Raises:
        PermissionDeniedError: If user lacks required scope
        
    Assumptions:
    - Raises exception instead of returning boolean
    - Used in API endpoints for enforcement
    """
    if not has_scope(scopes, required_scope):
        raise PermissionDeniedError(
            f"Permission denied: required scope '{required_scope}' not granted"
        )


def check_resource_ownership(
    user_id: str,
    resource_owner_id: str,
    is_admin: bool = False
) -> bool:
    """Check if user can access a resource.
    
    Args:
        user_id: ID of user attempting access
        resource_owner_id: ID of user who owns the resource
        is_admin: Whether the accessing user is an admin
        
    Returns:
        bool: True if access allowed, False otherwise
        
    Assumptions:
    - Users can access their own resources
    - Admins can access all resources
    - Multi-tenant data isolation
    """
    if is_admin:
        return True
    
    return user_id == resource_owner_id


def require_resource_ownership(
    user_id: str,
    resource_owner_id: str,
    is_admin: bool = False
) -> None:
    """Require user to own resource, raise if not.
    
    Args:
        user_id: ID of user attempting access
        resource_owner_id: ID of user who owns the resource
        is_admin: Whether the accessing user is an admin
        
    Raises:
        PermissionDeniedError: If user doesn't own resource and isn't admin
        
    Assumptions:
    - Used for update/delete operations
    - Enforces data isolation
    """
    if not check_resource_ownership(user_id, resource_owner_id, is_admin):
        raise PermissionDeniedError(
            f"User not authorized to access resource owned by {resource_owner_id}"
        )


def should_filter_by_user(is_admin: bool) -> bool:
    """Check if queries should be filtered by user_id.
    
    Args:
        is_admin: Whether the user is an admin
        
    Returns:
        bool: True if queries should be filtered, False otherwise
        
    Assumptions:
    - Regular users only see their own data
    - Admins see all data
    """
    return not is_admin


def get_authorization_context(user, scopes: list[str]) -> dict:
    """Create authorization context dict from user and scopes.
    
    Args:
        user: User object
        scopes: List of scopes
        
    Returns:
        dict: Authorization context with user_id, is_admin, scopes, email
        
    Assumptions:
    - Used for passing auth context through application
    - Standardized format for all endpoints
    """
    return {
        "user_id": user.id,
        "is_admin": user.is_admin,
        "scopes": scopes,
        "email": user.email
    }


def log_authorization_decision(
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    granted: bool,
    reason: str
) -> None:
    """Log an authorization decision for audit trail.
    
    Args:
        user_id: ID of user attempting action
        action: Action attempted (e.g., "write:items", "delete:presets")
        resource_type: Type of resource (e.g., "tool_items")
        resource_id: ID of specific resource
        granted: Whether access was granted
        reason: Human-readable reason for decision
        
    Assumptions:
    - Uses structured logging
    - Logs go to audit system
    - Critical for compliance and debugging
    """
    logger.info(
        "authorization_decision",
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        granted=granted,
        reason=reason
    )


def check_machine_access(
    machine_restriction: Optional[str],
    requested_machine: str
) -> bool:
    """Check if API key can access requested machine.
    
    Args:
        machine_restriction: Machine ID restriction from API key (None if unrestricted)
        requested_machine: Machine ID being accessed
        
    Returns:
        bool: True if access allowed, False otherwise
        
    Assumptions:
    - None restriction means access to all machines
    - Specific restriction limits to that machine only
    """
    if machine_restriction is None:
        return True
    
    return machine_restriction == requested_machine


def require_machine_access(
    machine_restriction: Optional[str],
    requested_machine: str
) -> None:
    """Require API key to have access to requested machine.
    
    Args:
        machine_restriction: Machine ID restriction from API key
        requested_machine: Machine ID being accessed
        
    Raises:
        PermissionDeniedError: If key doesn't have access to machine
        
    Assumptions:
    - Used for machine-specific API key enforcement
    - Prevents cross-machine access
    """
    if not check_machine_access(machine_restriction, requested_machine):
        raise PermissionDeniedError(
            f"API key not authorized for machine {requested_machine}"
        )
