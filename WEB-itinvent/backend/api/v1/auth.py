"""
Authentication API endpoints.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
from typing import Optional
import logging

from fastapi import APIRouter, Depends, status, HTTPException, Request, Response, Cookie
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.api.deps import get_current_active_user, get_current_admin_user, get_current_user
from backend.config import config
from backend.models.auth import (
    User,
    LoginRequest,
    LoginResponse,
    ChangePasswordRequest,
    UserCreateRequest,
    UserUpdateRequest,
    SessionInfo,
)
from backend.utils.security import create_access_token, decode_access_token
from backend.services import (
    authorization_service,
    session_service,
    settings_service,
    user_db_selection_service,
    user_service,
)
from backend.services.ad_sync_service import run_ad_sync
from backend.database.connection import set_user_database
import asyncio


router = APIRouter()
security_optional = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


def _extract_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return ""


def _request_is_https(request: Request) -> bool:
    forwarded_proto = str(request.headers.get("x-forwarded-proto", "") or "").strip().lower()
    if forwarded_proto:
        return forwarded_proto.split(",")[0].strip() == "https"
    if str(request.headers.get("x-forwarded-ssl", "") or "").strip().lower() == "on":
        return True
    if str(request.headers.get("x-arr-ssl", "") or "").strip():
        return True
    if str(request.headers.get("front-end-https", "") or "").strip().lower() == "on":
        return True
    if str(request.headers.get("x-url-scheme", "") or "").strip().lower() == "https":
        return True
    return str(request.url.scheme or "").lower() == "https"


def _validate_assigned_database_or_raise(database_id: Optional[str]) -> Optional[str]:
    normalized = str(database_id or "").strip()
    if not normalized:
        return None
    from backend.api.v1.database import get_all_db_configs
    allowed = {str(item.get("id")) for item in get_all_db_configs()}
    if normalized not in allowed:
        raise HTTPException(status_code=400, detail="Invalid assigned_database")
    return normalized


def _apply_default_database(user: dict) -> None:
    """
    Resolve and apply default DB for user after login.

    Priority:
    1) Bot assignment by Telegram ID (user_db_selection.json)
    2) Pinned database in web settings
    """
    user_id = int(user["id"])
    username = str(user["username"])

    assigned_db = (str(user.get("assigned_database") or "").strip() or None)
    if not assigned_db:
        assigned_db = user_db_selection_service.get_assigned_database(user.get("telegram_id"))
    if assigned_db:
        set_user_database(user_id, assigned_db, username)
        return

    settings = settings_service.get_user_settings(user_id)
    pinned = (settings.get("pinned_database") or "").strip()
    if pinned:
        set_user_database(user_id, pinned, username)


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, http_request: Request, response: Response):
    """
    Login endpoint - authenticate user and return JWT token.
    """
    user = user_service.authenticate(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    session_id = uuid.uuid4().hex
    access_token_expires = timedelta(minutes=config.jwt.access_token_expire_minutes)
    expires_at = datetime.now(timezone.utc) + access_token_expires

    access_token = create_access_token(
        data={
            "sub": user["username"],
            "user_id": user["id"],
            "role": user.get("role", "viewer"),
            "session_id": session_id,
            "telegram_id": user.get("telegram_id"),
        },
        expires_delta=access_token_expires,
    )

    session_service.create_session(
        session_id=session_id,
        user_id=user["id"],
        username=user["username"],
        role=user.get("role", "viewer"),
        ip_address=_extract_ip(http_request),
        user_agent=http_request.headers.get("user-agent", ""),
        expires_at=expires_at.isoformat(),
    )

    _apply_default_database(user)

    response.set_cookie(
        key=config.app.auth_cookie_name,
        value=access_token,
        max_age=config.jwt.access_token_expire_minutes * 60,
        httponly=True,
        secure=bool(config.app.auth_cookie_secure),
        samesite=str(config.app.auth_cookie_samesite or "lax"),
        domain=config.app.auth_cookie_domain,
        path="/",
    )

    public_user = dict(user)
    public_user["permissions"] = authorization_service.get_effective_permissions(
        public_user.get("role"),
        use_custom_permissions=bool(public_user.get("use_custom_permissions", False)),
        custom_permissions=public_user.get("custom_permissions"),
    )

    return LoginResponse(
        access_token=None,
        token_type="bearer",
        user=User(**public_user),
        session_id=session_id,
    )


@router.post("/logout")
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    access_token_cookie: Optional[str] = Cookie(None, alias=config.app.auth_cookie_name),
):
    """
    Logout endpoint.
    """
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif access_token_cookie:
        token = str(access_token_cookie).strip() or None

    token_data = decode_access_token(token or "")
    if token_data and token_data.session_id:
        session_service.close_session(token_data.session_id)
    response.delete_cookie(
        key=config.app.auth_cookie_name,
        domain=config.app.auth_cookie_domain,
        path="/",
    )
    return {"message": "Successfully logged out", "username": current_user.username}


@router.get("/me", response_model=User)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get current authenticated user information.
    """
    return current_user


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Change current user's password.
    """
    changed = user_service.change_password(current_user.id, request.old_password, request.new_password)
    if not changed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password",
        )
    return {"message": "Password changed successfully"}


@router.get("/sessions", response_model=list[SessionInfo])
async def get_sessions(
    _: User = Depends(get_current_admin_user),
):
    """List active web sessions (admin only)."""
    return [SessionInfo(**item) for item in session_service.list_sessions(active_only=True)]


@router.delete("/sessions/{session_id}")
async def terminate_session(
    session_id: str,
    _: User = Depends(get_current_admin_user),
):
    """Terminate a session by id (admin only)."""
    closed = session_service.close_session_by_id(session_id)
    if not closed:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "session_id": session_id}


@router.get("/users", response_model=list[User])
async def list_users(
    _: User = Depends(get_current_admin_user),
):
    """List all web users (admin only)."""
    return [User(**item) for item in user_service.list_users()]


@router.post("/users", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    _: User = Depends(get_current_admin_user),
):
    """Create a web user (admin only)."""
    try:
        assigned_database = _validate_assigned_database_or_raise(payload.assigned_database)
        created = user_service.create_user(
            username=payload.username,
            password=payload.password,
            role=payload.role,
            email=payload.email,
            full_name=payload.full_name,
            telegram_id=payload.telegram_id,
            assigned_database=assigned_database,
            is_active=payload.is_active,
            auth_source=payload.auth_source,
            use_custom_permissions=payload.use_custom_permissions,
            custom_permissions=payload.custom_permissions,
            mailbox_email=payload.mailbox_email,
            mailbox_login=payload.mailbox_login,
            mailbox_password=payload.mailbox_password,
            mail_signature_html=payload.mail_signature_html,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return User(**created)


@router.patch("/users/{user_id}", response_model=User)
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_admin_user),
):
    """Update web user properties (admin only)."""
    if current_user.id == user_id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate current admin user")

    payload_data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    if "assigned_database" in payload_data:
        payload_data["assigned_database"] = _validate_assigned_database_or_raise(payload_data.get("assigned_database"))
    try:
        updated = user_service.update_user(
            user_id,
            **payload_data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return User(**updated)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
):
    """Delete a user (admin only). Cannot delete the default admin (id=1)."""
    if str(user_id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")
        
    deleted = user_service.delete_user(user_id)
    if not deleted:
        if user_id == 1:
             raise HTTPException(status_code=403, detail="Cannot delete the default admin account.")
        raise HTTPException(status_code=404, detail="User not found")
        
    return {"message": "User deleted successfully"}


@router.post("/sync-ad")
async def trigger_ad_sync(
    current_user: User = Depends(get_current_admin_user),
):
    """
    Manually trigger Active Directory synchronization.
    Requires admin privileges.
    """
    try:
        # Run blocking I/O in thread pool
        result = await asyncio.to_thread(run_ad_sync, True)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message", "Sync failed"))
        return result
    except Exception as e:
        logger.error(f"AD sync endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
