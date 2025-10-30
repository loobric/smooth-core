# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Integration tests for user registration security.

Tests the security model where:
- First user registration is open and creates an admin
- Subsequent registrations require admin authentication

Assumptions:
- First user automatically becomes admin (is_admin=True, role="admin")
- Non-admin users cannot register new users
- Only admins can register additional users
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_first_user_registration_is_open(client):
    """Test that first user can register without authentication.
    
    Assumptions:
    - Empty database allows open registration
    - No authentication required for first user
    - Returns 201 Created with user details
    """
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "first@example.com",
            "password": "password123"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "first@example.com"
    assert "id" in data
    assert data["is_active"] is True


@pytest.mark.integration
def test_first_user_becomes_admin(client, db_session):
    """Test that first user automatically becomes admin.
    
    Assumptions:
    - First user gets is_admin=True
    - First user gets role="admin"
    - This happens automatically without explicit request
    """
    from smooth.database.schema import User
    
    # Register first user
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@example.com",
            "password": "password123"
        }
    )
    assert response.status_code == 201
    
    # Verify user is admin in database
    user = db_session.query(User).filter(User.email == "admin@example.com").first()
    assert user is not None
    assert user.is_admin is True
    assert user.role == "admin"


@pytest.mark.integration
def test_second_user_registration_requires_auth(client):
    """Test that second user registration requires authentication.
    
    Assumptions:
    - After first user exists, registration requires authentication
    - Unauthenticated registration returns 401
    """
    # Create first user
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "first@example.com",
            "password": "password123"
        }
    )
    
    # Try to register second user without authentication
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "second@example.com",
            "password": "password123"
        }
    )
    assert response.status_code == 401


@pytest.mark.integration
def test_non_admin_cannot_register_users(client, db_session):
    """Test that non-admin users cannot register new users.
    
    Assumptions:
    - Only admin users can register additional users
    - Non-admin authenticated users get 403 Forbidden
    """
    from smooth.database.schema import User
    from smooth.auth.password import hash_password
    
    # Create first user (admin)
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@example.com",
            "password": "admin123"
        }
    )
    
    # Manually create a non-admin user in the test database
    non_admin = User(
        email="user@example.com",
        password_hash=hash_password("user123"),
        is_active=True,
        is_admin=False,
        role="user",
        is_verified=True
    )
    db_session.add(non_admin)
    db_session.commit()
    
    # Login as non-admin and get cookies
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "user@example.com",
            "password": "user123"
        }
    )
    assert login_response.status_code == 200
    
    # Extract cookies from login response
    cookies = login_response.cookies
    
    # Try to register new user as non-admin (with cookies)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "password123"
        },
        cookies=cookies
    )
    assert response.status_code == 403
    assert "administrator" in response.json()["detail"].lower()


@pytest.mark.integration
def test_admin_can_register_additional_users(client):
    """Test that admin users can register additional users.
    
    Assumptions:
    - Admin users can register new users
    - Authentication via session cookie works
    - Returns 201 Created for successful registration
    """
    # Register and login as admin (first user)
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@example.com",
            "password": "admin123"
        }
    )
    
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@example.com",
            "password": "admin123"
        }
    )
    assert login_response.status_code == 200
    
    # Extract cookies from login response
    cookies = login_response.cookies
    
    # Register second user as admin (with cookies)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "password123"
        },
        cookies=cookies
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "user@example.com"


@pytest.mark.integration
def test_subsequent_users_are_not_admin(client, db_session):
    """Test that users registered by admin are not automatically admin.
    
    Assumptions:
    - Only first user becomes admin automatically
    - Users registered by admin have is_admin=False by default
    """
    from smooth.database.schema import User
    
    # Register first user (becomes admin)
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@example.com",
            "password": "admin123"
        }
    )
    
    # Login as admin
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@example.com",
            "password": "admin123"
        }
    )
    cookies = login_response.cookies
    
    # Register second user (with cookies)
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "password123"
        },
        cookies=cookies
    )
    
    # Verify second user is not admin
    user = db_session.query(User).filter(User.email == "user@example.com").first()
    assert user is not None
    assert user.is_admin is False
    assert user.role == "user"


@pytest.mark.integration
def test_duplicate_email_registration_fails(client):
    """Test that registering with duplicate email fails.
    
    Assumptions:
    - Email addresses must be unique
    - Returns 400 Bad Request for duplicate email
    - Error message indicates email already registered
    """
    # Register first user
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "password123"
        }
    )
    
    # Login as admin
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "user@example.com",
            "password": "password123"
        }
    )
    cookies = login_response.cookies
    
    # Try to register with same email (with cookies)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "different_password"
        },
        cookies=cookies
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()
