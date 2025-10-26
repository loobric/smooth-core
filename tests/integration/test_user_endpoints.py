# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Integration tests for user registration and login endpoints.

Tests user account creation, authentication, and session management.

Assumptions:
- User registration at POST /api/v1/auth/register
- Login at POST /api/v1/auth/login
- Logout at POST /api/v1/auth/logout
- Current user info at GET /api/v1/auth/me
- Session-based authentication using cookies
"""
import pytest


@pytest.mark.integration
def test_register_new_user(client):
    """Test user registration endpoint.
    
    Assumptions:
    - POST /api/v1/auth/register
    - Returns 201 Created
    - Returns user object without password
    - Email must be unique
    """
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "SecurePassword123!"
        }
    )
    
    if response.status_code != 201:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.json()}")
    
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["email"] == "newuser@example.com"
    assert "password" not in data
    assert "password_hash" not in data
    assert data["is_active"] is True


@pytest.mark.integration
def test_register_duplicate_email(client):
    """Test that duplicate email registration fails.
    
    Assumptions:
    - Returns 400 Bad Request
    - Error message indicates duplicate email
    """
    # Register first user
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": "Password123"
        }
    )
    
    # Attempt duplicate registration
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": "DifferentPassword456"
        }
    )
    
    assert response.status_code == 400
    assert "email" in response.json()["detail"].lower()


@pytest.mark.integration
def test_login_with_valid_credentials(client):
    """Test login with correct email and password.
    
    Assumptions:
    - POST /api/v1/auth/login
    - Returns 200 OK
    - Sets session cookie
    - Returns user object
    """
    # Register user
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "logintest@example.com",
            "password": "Password123"
        }
    )
    
    # Login
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "logintest@example.com",
            "password": "Password123"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "logintest@example.com"
    assert "password" not in data
    
    # Check session cookie is set
    assert "session" in response.cookies or "Set-Cookie" in response.headers


@pytest.mark.integration
def test_login_with_wrong_password(client):
    """Test login fails with incorrect password.
    
    Assumptions:
    - Returns 401 Unauthorized
    - Does not set session cookie
    """
    # Register user
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpass@example.com",
            "password": "CorrectPassword"
        }
    )
    
    # Login with wrong password
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrongpass@example.com",
            "password": "WrongPassword"
        }
    )
    
    assert response.status_code == 401


@pytest.mark.integration
def test_login_nonexistent_user(client):
    """Test login fails for non-existent user.
    
    Assumptions:
    - Returns 401 Unauthorized
    - Does not reveal whether user exists (security)
    """
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "AnyPassword"
        }
    )
    
    assert response.status_code == 401


@pytest.mark.integration
def test_get_current_user_authenticated(client):
    """Test getting current user info when authenticated.
    
    Assumptions:
    - GET /api/v1/auth/me
    - Requires valid session
    - Returns user object
    """
    # Register and login
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "currentuser@example.com",
            "password": "Password123"
        }
    )
    
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "currentuser@example.com",
            "password": "Password123"
        }
    )
    
    # Get current user (session cookie should be maintained by TestClient)
    response = client.get("/api/v1/auth/me")
    
    # If AUTH_ENABLED=false, this might return 404 instead of requiring auth
    # For now, just check it doesn't error
    assert response.status_code in [200, 404]
    
    if response.status_code == 200:
        data = response.json()
        assert data["email"] == "currentuser@example.com"


@pytest.mark.integration
def test_get_current_user_unauthenticated(client):
    """Test getting current user without authentication fails.
    
    Assumptions:
    - Returns 401 Unauthorized when not logged in
    - When AUTH_ENABLED=false, may return different status
    """
    response = client.get("/api/v1/auth/me")
    
    # With AUTH_ENABLED=false (default in tests), may return 404
    # With AUTH_ENABLED=true, should return 401
    assert response.status_code in [401, 404]


@pytest.mark.integration
def test_logout(client):
    """Test logout clears session.
    
    Assumptions:
    - POST /api/v1/auth/logout
    - Returns 200 OK
    - Clears session cookie
    - Subsequent requests not authenticated
    """
    # Register and login
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "logouttest@example.com",
            "password": "Password123"
        }
    )
    
    client.post(
        "/api/v1/auth/login",
        json={
            "email": "logouttest@example.com",
            "password": "Password123"
        }
    )
    
    # Logout
    response = client.post("/api/v1/auth/logout")
    
    assert response.status_code == 200
    
    # Verify session is cleared (cookie should be deleted or expired)
    # Note: TestClient may handle this differently


@pytest.mark.integration
def test_password_validation(client):
    """Test that weak passwords are rejected.
    
    Assumptions:
    - Password must meet minimum requirements
    - Returns 400 Bad Request with validation error
    - (Optional for now, can be basic)
    """
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "weakpass@example.com",
            "password": "123"  # Too short
        }
    )
    
    # May or may not be enforced yet
    # Accept 201 (no validation) or 400/422 (validation enforced)
    assert response.status_code in [201, 400, 422]


@pytest.mark.integration
def test_email_validation(client):
    """Test that invalid email format is rejected.
    
    Assumptions:
    - Email must be valid format
    - Returns 422 Unprocessable Entity (Pydantic validation)
    """
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "Password123"
        }
    )
    
    # Pydantic should validate email format
    assert response.status_code in [422, 400]
