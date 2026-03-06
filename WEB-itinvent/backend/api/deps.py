"""
FastAPI dependency functions for authentication and database access.
"""
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status, Cookie, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.config import config
from backend.models.auth import User
from backend.utils.security import decode_access_token
from backend.database.connection import get_user_database
from backend.services import (
    authorization_service,
    session_service,
    settings_service,
    user_db_selection_service,
    user_service,
)


security_optional = HTTPBearer(auto_error=False)


def _resolve_access_token(
    credentials: Optional[HTTPAuthorizationCredentials],
    access_token_cookie: Optional[str],
) -> Optional[str]:
    if credentials and credentials.credentials:
        return credentials.credentials
    if access_token_cookie:
        return str(access_token_cookie).strip() or None
    return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    access_token_cookie: Optional[str] = Cookie(None, alias=config.app.auth_cookie_name),
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.

    Raises:
        HTTPException 401 if token is invalid or missing

    Returns:
        User object
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = _resolve_access_token(credentials, access_token_cookie)
    if not token:
        raise credentials_exception

    token_data = decode_access_token(token)

    if token_data is None:
        raise credentials_exception

    # Validate session (if token carries session id).
    if token_data.session_id and not session_service.is_session_active(token_data.session_id):
        raise credentials_exception

    # Load user from local JSON store.
    user_raw = None
    if token_data.user_id not in (None, 0):
        user_raw = user_service.get_by_id(token_data.user_id)
    if user_raw is None and token_data.username:
        user_raw = user_service.get_by_username(token_data.username)
    if not user_raw:
        raise credentials_exception

    if token_data.session_id:
        session_service.touch_session(token_data.session_id)

    public_user = user_service.to_public_user(user_raw)
    public_user["permissions"] = authorization_service.get_effective_permissions(
        public_user.get("role"),
        use_custom_permissions=bool(public_user.get("use_custom_permissions", False)),
        custom_permissions=public_user.get("custom_permissions"),
    )
    return User(**public_user)


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to get the current active user.

    Raises:
        HTTPException 400 if user is inactive

    Returns:
        Active User object
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Dependency to ensure caller has admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def ensure_user_permission(current_user: User, permission: str) -> None:
    """Raise HTTP 403 when user does not have the required permission."""
    current_permissions = set(getattr(current_user, "permissions", []) or [])
    if permission in current_permissions:
        return
    if not authorization_service.has_permission(
        current_user.role,
        permission,
        use_custom_permissions=bool(getattr(current_user, "use_custom_permissions", False)),
        custom_permissions=getattr(current_user, "custom_permissions", []),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions: {permission}",
        )


def require_permission(permission: str) -> Callable[..., User]:
    """Dependency factory for permission checks."""

    async def _dependency(current_user: User = Depends(get_current_active_user)) -> User:
        ensure_user_permission(current_user, permission)
        return current_user

    return _dependency


# Optional: Skip authentication for development
async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    access_token_cookie: Optional[str] = Cookie(None, alias=config.app.auth_cookie_name),
) -> Optional[User]:
    """
    Optional authentication - returns None if no token provided.
    Useful for endpoints that work for both authenticated and anonymous users.
    """
    token = _resolve_access_token(credentials, access_token_cookie)
    if not token:
        return None

    token_data = decode_access_token(token)
    if token_data is None:
        return None

    # If session exists and is not active, treat as anonymous.
    if token_data.session_id and not session_service.is_session_active(token_data.session_id):
        return None

    user_raw = None
    if token_data.user_id not in (None, 0):
        user_raw = user_service.get_by_id(token_data.user_id)
    if user_raw is None and token_data.username:
        user_raw = user_service.get_by_username(token_data.username)
    if not user_raw:
        return None

    if token_data.session_id:
        session_service.touch_session(token_data.session_id)

    public_user = user_service.to_public_user(user_raw)
    public_user["permissions"] = authorization_service.get_effective_permissions(
        public_user.get("role"),
        use_custom_permissions=bool(public_user.get("use_custom_permissions", False)),
        custom_permissions=public_user.get("custom_permissions"),
    )
    return User(**public_user)


async def get_current_database_id(
    x_database_id: Optional[str] = Header(None, alias="X-Database-ID"),
    selected_database: Optional[str] = Cookie(None),
    current_user: User = Depends(get_current_active_user),
) -> Optional[str]:
    """
    Dependency to get the current user's selected database ID.

    Returns:
        Database ID (e.g., "ITINVENT", "MSK-ITINVENT") or None
    """
    user_assigned_db = (str(current_user.assigned_database or "").strip() or None)
    # If user is linked to Telegram and has assigned DB in bot mapping:
    # non-admin users are strictly pinned to that DB.
    assigned_db = user_assigned_db or user_db_selection_service.get_assigned_database(current_user.telegram_id)
    if assigned_db and current_user.role != "admin":
        return assigned_db

    # Allow explicit request-scoped override.
    if x_database_id and x_database_id.strip():
        return x_database_id.strip()

    user_db = get_user_database(current_user.id, current_user.username)
    if user_db:
        return user_db

    # Fallback to user settings pinned DB.
    settings = settings_service.get_user_settings(current_user.id)
    pinned = (settings.get("pinned_database") or "").strip()
    if pinned:
        return pinned

    # Cookie fallback.
    if selected_database and selected_database.strip():
        return selected_database.strip()

    return None
