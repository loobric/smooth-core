# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
OAuth2 authentication providers (Google, GitHub).

Placeholder for future OAuth2 integration.

Assumptions:
- OAuth2 will be optional alongside email/password auth
- Users can link multiple OAuth providers to one account
- OAuth tokens stored securely, never logged
- First-time OAuth login creates new user account
"""
from typing import Optional
from sqlalchemy.orm import Session

# TODO: Add OAuth2 dependencies when implementing
# from authlib.integrations.starlette_client import OAuth


class OAuth2Provider:
    """Base class for OAuth2 providers."""
    
    def __init__(self, client_id: str, client_secret: str):
        """Initialize OAuth2 provider.
        
        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
    
    async def get_authorization_url(self, redirect_uri: str) -> str:
        """Get OAuth2 authorization URL.
        
        Args:
            redirect_uri: Callback URL after authorization
            
        Returns:
            str: Authorization URL to redirect user to
        """
        raise NotImplementedError
    
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> dict:
        """Exchange authorization code for access token.
        
        Args:
            code: Authorization code from OAuth provider
            redirect_uri: Callback URL (must match authorization request)
            
        Returns:
            dict: Token response with access_token, refresh_token, etc.
        """
        raise NotImplementedError
    
    async def get_user_info(self, access_token: str) -> dict:
        """Get user information from OAuth provider.
        
        Args:
            access_token: OAuth2 access token
            
        Returns:
            dict: User info (email, name, etc.)
        """
        raise NotImplementedError


class GoogleOAuth2Provider(OAuth2Provider):
    """Google OAuth2 provider."""
    
    # TODO: Implement Google OAuth2
    # - Use authlib or similar library
    # - Scopes: openid, email, profile
    # - Store refresh tokens for long-term access
    pass


class GitHubOAuth2Provider(OAuth2Provider):
    """GitHub OAuth2 provider."""
    
    # TODO: Implement GitHub OAuth2
    # - Use authlib or similar library
    # - Scopes: user:email
    # - Handle GitHub-specific user info format
    pass


def link_oauth_account(
    session: Session,
    user_id: str,
    provider: str,
    provider_user_id: str,
    access_token: str,
    refresh_token: Optional[str] = None
) -> None:
    """Link OAuth account to existing user.
    
    Args:
        session: Database session
        user_id: User ID to link to
        provider: OAuth provider name (google, github)
        provider_user_id: User ID from OAuth provider
        access_token: OAuth access token
        refresh_token: OAuth refresh token (optional)
        
    Assumptions:
    - User can have multiple OAuth providers linked
    - Tokens are encrypted before storage
    - Linking requires existing authenticated session
    """
    # TODO: Implement OAuth account linking
    # - Create OAuthAccount table in schema
    # - Store encrypted tokens
    # - Prevent duplicate provider links
    raise NotImplementedError


def authenticate_with_oauth(
    session: Session,
    provider: str,
    provider_user_id: str
) -> Optional[dict]:
    """Authenticate user with OAuth provider.
    
    Args:
        session: Database session
        provider: OAuth provider name
        provider_user_id: User ID from OAuth provider
        
    Returns:
        dict: User info if found, None otherwise
        
    Assumptions:
    - Returns existing user if OAuth account is linked
    - Returns None if no linked account found
    - Does not create new users (use register_with_oauth)
    """
    # TODO: Implement OAuth authentication
    # - Look up user by provider + provider_user_id
    # - Return user info for session creation
    raise NotImplementedError


def register_with_oauth(
    session: Session,
    provider: str,
    provider_user_id: str,
    email: str,
    access_token: str,
    refresh_token: Optional[str] = None
) -> dict:
    """Register new user with OAuth provider.
    
    Args:
        session: Database session
        provider: OAuth provider name
        provider_user_id: User ID from OAuth provider
        email: User email from OAuth provider
        access_token: OAuth access token
        refresh_token: OAuth refresh token (optional)
        
    Returns:
        dict: Created user info
        
    Assumptions:
    - Creates new user account with role="user"
    - Links OAuth account automatically
    - Email must be verified by OAuth provider
    - No password set (OAuth-only account)
    """
    # TODO: Implement OAuth registration
    # - Create user with create_user (generate random password)
    # - Link OAuth account
    # - Mark email as verified
    raise NotImplementedError
