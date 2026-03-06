"""
Knowledge base API.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from backend.api.deps import get_current_active_user, require_permission
from backend.models.auth import User
from backend.models.kb import (
    KbArticleCreateRequest,
    KbArticleListResponse,
    KbArticleResponse,
    KbArticleStatusRequest,
    KbArticleUpdateRequest,
    KbCardCreateRequest,
    KbCardListResponse,
    KbCardResponse,
    KbCardStatusRequest,
    KbCardUpdateRequest,
    KbCategoryResponse,
    KbFeedEventResponse,
    KbServiceSummaryResponse,
)
from backend.services.authorization_service import (
    PERM_KB_PUBLISH,
    PERM_KB_READ,
    PERM_KB_WRITE,
)
from backend.services.kb_service import kb_service


router = APIRouter()


def _normalize_tags(value: str | None) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


@router.get("/categories", response_model=list[KbCategoryResponse])
async def get_categories(_: User = Depends(require_permission(PERM_KB_READ))):
    return kb_service.list_categories()


@router.get("/services", response_model=list[KbServiceSummaryResponse])
async def get_services(_: User = Depends(require_permission(PERM_KB_READ))):
    return kb_service.list_services_with_counts()


@router.get("/cards", response_model=KbCardListResponse)
async def get_cards(
    q: str = Query("", min_length=0),
    service: str = Query("", min_length=0),
    status_filter: str = Query("", alias="status", min_length=0),
    priority: str = Query("", min_length=0),
    tags: str = Query("", min_length=0, description="Comma separated tags"),
    pinned: Optional[bool] = Query(None),
    sort: str = Query("updated_desc", min_length=0),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_permission(PERM_KB_READ)),
):
    return kb_service.list_cards(
        q=q,
        service=service,
        status=status_filter,
        priority=priority,
        tags=_normalize_tags(tags),
        pinned=pinned,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/cards/{card_id}", response_model=KbCardResponse)
async def get_card(
    card_id: str,
    _: User = Depends(require_permission(PERM_KB_READ)),
):
    item = kb_service.get_card(card_id)
    if not item:
        raise HTTPException(status_code=404, detail="Card not found")
    return item


@router.post("/cards", response_model=KbCardResponse, status_code=status.HTTP_201_CREATED)
async def create_card(
    payload: KbCardCreateRequest,
    current_user: User = Depends(require_permission(PERM_KB_WRITE)),
):
    actor = str(current_user.username or "").strip() or "system"
    return kb_service.create_card(payload=payload.model_dump(mode="json"), actor_username=actor)


@router.patch("/cards/{card_id}", response_model=KbCardResponse)
async def update_card(
    card_id: str,
    payload: KbCardUpdateRequest,
    current_user: User = Depends(require_permission(PERM_KB_WRITE)),
):
    actor = str(current_user.username or "").strip() or "system"
    item = kb_service.update_card(
        card_id=card_id,
        payload=payload.model_dump(mode="json", exclude_unset=True),
        actor_username=actor,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Card not found")
    return item


@router.post("/cards/{card_id}/status", response_model=KbCardResponse)
async def set_card_status(
    card_id: str,
    payload: KbCardStatusRequest,
    current_user: User = Depends(require_permission(PERM_KB_PUBLISH)),
):
    actor = str(current_user.username or "").strip() or "system"
    item = kb_service.set_card_status(
        card_id=card_id,
        status=payload.status,
        actor_username=actor,
        change_note=payload.change_note,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Card not found")
    return item


@router.get("/articles", response_model=KbArticleListResponse)
async def get_articles(
    q: str = Query("", min_length=0),
    category: str = Query("", min_length=0),
    article_type: str = Query("", min_length=0),
    status_filter: str = Query("", alias="status", min_length=0),
    tags: str = Query("", min_length=0, description="Comma separated tags"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_permission(PERM_KB_READ)),
):
    return kb_service.list_articles(
        q=q,
        category=category,
        article_type=article_type,
        status=status_filter,
        tags=_normalize_tags(tags),
        limit=limit,
        offset=offset,
    )


@router.get("/articles/{article_id}", response_model=KbArticleResponse)
async def get_article(
    article_id: str,
    _: User = Depends(require_permission(PERM_KB_READ)),
):
    item = kb_service.get_article(article_id)
    if not item:
        raise HTTPException(status_code=404, detail="Article not found")
    return item


@router.post("/articles", response_model=KbArticleResponse, status_code=status.HTTP_201_CREATED)
async def create_article(
    payload: KbArticleCreateRequest,
    current_user: User = Depends(require_permission(PERM_KB_WRITE)),
):
    actor = str(current_user.username or "").strip() or "system"
    return kb_service.create_article(payload=payload.model_dump(), actor_username=actor)


@router.patch("/articles/{article_id}", response_model=KbArticleResponse)
async def update_article(
    article_id: str,
    payload: KbArticleUpdateRequest,
    current_user: User = Depends(require_permission(PERM_KB_WRITE)),
):
    actor = str(current_user.username or "").strip() or "system"
    item = kb_service.update_article(
        article_id=article_id,
        payload=payload.model_dump(exclude_unset=True),
        actor_username=actor,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Article not found")
    return item


@router.post("/articles/{article_id}/status", response_model=KbArticleResponse)
async def set_article_status(
    article_id: str,
    payload: KbArticleStatusRequest,
    current_user: User = Depends(require_permission(PERM_KB_PUBLISH)),
):
    actor = str(current_user.username or "").strip() or "system"
    item = kb_service.set_article_status(
        article_id=article_id,
        status=payload.status,
        actor_username=actor,
        change_note=payload.change_note,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Article not found")
    return item


@router.get("/feed", response_model=list[KbFeedEventResponse])
async def get_feed(
    limit: int = Query(50, ge=1, le=500),
    _: User = Depends(require_permission(PERM_KB_READ)),
):
    return kb_service.get_feed(limit=limit)


@router.post("/articles/{article_id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    article_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission(PERM_KB_WRITE)),
):
    actor = str(current_user.username or "").strip() or "system"
    item = kb_service.add_attachment(article_id=article_id, upload=file, actor_username=actor)
    if not item:
        raise HTTPException(status_code=404, detail="Article not found")
    return item


@router.get("/articles/{article_id}/attachments/{attachment_id}")
async def download_attachment(
    article_id: str,
    attachment_id: str,
    _: User = Depends(require_permission(PERM_KB_READ)),
):
    item = kb_service.get_attachment(article_id=article_id, attachment_id=attachment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Attachment not found")
    file_name = str(item.get("file_name") or "attachment.bin")
    media_type = str(item.get("content_type") or "application/octet-stream")
    return FileResponse(
        path=str(item["path"]),
        filename=file_name,
        media_type=media_type,
    )


@router.delete("/articles/{article_id}/attachments/{attachment_id}")
async def remove_attachment(
    article_id: str,
    attachment_id: str,
    current_user: User = Depends(require_permission(PERM_KB_WRITE)),
):
    actor = str(current_user.username or "").strip() or "system"
    ok = kb_service.delete_attachment(
        article_id=article_id,
        attachment_id=attachment_id,
        actor_username=actor,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return {"success": True}
