"""
Database management API endpoints - switch between databases.
"""
from fastapi import APIRouter, Depends, HTTPException, Cookie, Header, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import logging

from backend.api.deps import get_current_active_user
from backend.database.connection import get_database_config, set_user_database, get_user_database
from backend.models.auth import User
from backend.services import settings_service, user_db_selection_service

logger = logging.getLogger(__name__)


router = APIRouter()


def get_all_db_configs() -> List[dict]:
    """Get all available database configurations."""
    databases = [
        {
            "id": "ITINVENT",
            "name": "ITINVENT",
            "access": "read-only",
        },
        {
            "id": "MSK-ITINVENT",
            "name": "MSK-ITINVENT (Москва)",
            "access": "read-only",
        },
        {
            "id": "OBJ-ITINVENT",
            "name": "OBJ-ITINVENT (Объекты)",
            "access": "read-write",
        },
        {
            "id": "SPB-ITINVENT",
            "name": "SPB-ITINVENT (Санкт-Петербург)",
            "access": "read-only",
        },
    ]
    return databases


class DatabaseInfo(BaseModel):
    """Database information model."""
    id: str
    name: str
    access: str


def _get_assigned_db(current_user: Optional[User]) -> Optional[str]:
    if not current_user:
        return None
    user_assigned_db = (str(current_user.assigned_database or "").strip() or None)
    if user_assigned_db:
        return user_assigned_db
    return user_db_selection_service.get_assigned_database(current_user.telegram_id)


@router.get("/list")
async def get_available_databases(current_user: User = Depends(get_current_active_user)) -> List[DatabaseInfo]:
    """
    Get list of available databases.

    Returns:
        List of available databases
    """
    databases = get_all_db_configs()
    assigned_db = _get_assigned_db(current_user)
    if assigned_db and current_user and current_user.role != "admin":
        filtered = [db for db in databases if db["id"] == assigned_db]
        if filtered:
            return filtered
    return databases


@router.get("/current")
async def get_current_database(
    x_database_id: Optional[str] = Header(None, alias="X-Database-ID"),
    selected_database: Optional[str] = Cookie(None),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, str]:
    """
    Get current active database.

    Returns:
        Current database information
    """
    assigned_db = _get_assigned_db(current_user)
    if assigned_db and current_user and current_user.role != "admin":
        db_config = get_database_config(assigned_db)
        return {
            "id": assigned_db,
            "name": db_config["database"],
            "host": db_config["host"],
            "locked": "true",
        }

    # Try to get from header, user selection first (id/username), settings, then cookie fallback.
    header_db = (x_database_id or "").strip() or None
    user_db: Optional[str] = None
    if current_user:
        user_db = get_user_database(current_user.id, current_user.username)
        if not user_db:
            settings = settings_service.get_user_settings(current_user.id)
            user_db = (settings.get("pinned_database") or "").strip() or None

    cookie_db = (selected_database or "").strip() or None
    active_db = header_db or user_db or cookie_db
    if active_db:
        db_config = get_database_config(active_db)
        return {
            "id": active_db,
            "name": db_config["database"],
            "host": db_config["host"],
        }

    # Default database
    from backend.config import config
    return {
        "id": config.database.database,
        "name": config.database.database,
        "host": config.database.host,
    }


class SwitchDatabaseRequest(BaseModel):
    """Request to switch database."""
    database_id: str


@router.post("/switch")
async def switch_database(
    request: SwitchDatabaseRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Switch to a different database.

    The database selection is stored per-user session and takes effect immediately
    without requiring a server restart.

    Args:
        request: SwitchDatabaseRequest with database_id

    Returns:
        Success message
    """
    logger.info(f"Switch database request: {request.database_id}, user: {current_user}")

    # Check if database exists
    all_dbs = get_all_db_configs()
    db_info = next((db for db in all_dbs if db["id"] == request.database_id), None)
    if not db_info:
        raise HTTPException(status_code=404, detail="Database not found")

    assigned_db = _get_assigned_db(current_user)
    if assigned_db and current_user and current_user.role != "admin" and request.database_id != assigned_db:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Database is fixed for this user: {assigned_db}",
        )

    # Store user's database selection in memory (if authenticated by id or username)
    user_id = current_user.id
    username = current_user.username
    set_user_database(user_id, request.database_id, username)
    logger.info(f"Set database {request.database_id} for user id={user_id}, username={username}")

    # Get database config to verify connection
    db_config = get_database_config(request.database_id)

    payload = {
        "success": True,
        "message": f"Переключено на {db_info['name']}. База данных применена немедленно.",
        "database": {**db_info, **db_config},
        "user_id": user_id
    }
    response = JSONResponse(content=payload)
    response.set_cookie(
        key="selected_database",
        value=request.database_id,
        max_age=60 * 60 * 24 * 30,  # 30 days
        samesite="lax",
        httponly=True,
    )
    return response
