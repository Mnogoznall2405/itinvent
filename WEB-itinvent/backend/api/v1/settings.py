"""
User settings API endpoints.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.api.deps import get_current_active_user
from backend.models.auth import User
from backend.services import settings_service


router = APIRouter()


class UserSettingsResponse(BaseModel):
    pinned_database: Optional[str] = None
    theme_mode: str = "light"
    font_family: str = "Inter"
    font_scale: float = 1.0


class UserSettingsPatchRequest(BaseModel):
    pinned_database: Optional[str] = None
    theme_mode: Optional[str] = None
    font_family: Optional[str] = None
    font_scale: Optional[float] = Field(default=None, ge=0.9, le=1.2)


@router.get("/me", response_model=UserSettingsResponse)
async def get_my_settings(
    current_user: User = Depends(get_current_active_user),
):
    settings = settings_service.get_user_settings(current_user.id)
    return UserSettingsResponse(**settings)


@router.patch("/me", response_model=UserSettingsResponse)
async def update_my_settings(
    payload: UserSettingsPatchRequest,
    current_user: User = Depends(get_current_active_user),
):
    payload_data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    updated = settings_service.update_user_settings(
        current_user.id,
        payload_data,
    )
    return UserSettingsResponse(**updated)
