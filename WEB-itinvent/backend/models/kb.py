"""
Knowledge base models.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import AnyHttpUrl, BaseModel, Field


KbArticleType = Literal["runbook", "faq", "template", "note"]
KbArticleStatus = Literal["draft", "published", "archived"]
KbCardPriority = Literal["low", "normal", "high", "critical"]


class KbFaqItem(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    answer: str = Field(..., min_length=1, max_length=5000)


class KbContentBlock(BaseModel):
    overview: str = ""
    symptoms: str = ""
    checks: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    resolution_steps: list[str] = Field(default_factory=list)
    rollback_steps: list[str] = Field(default_factory=list)
    escalation: str = ""
    faq: list[KbFaqItem] = Field(default_factory=list)


class KbArticleCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    category: str = Field(..., min_length=1, max_length=64)
    article_type: KbArticleType = "runbook"
    summary: str = Field(default="", max_length=500)
    tags: list[str] = Field(default_factory=list)
    owner_user_id: Optional[int] = None
    owner_name: str = Field(default="", max_length=200)
    content: KbContentBlock = Field(default_factory=KbContentBlock)
    last_reviewed_at: Optional[str] = None
    change_note: str = Field(default="", max_length=300)


class KbArticleUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    category: Optional[str] = Field(default=None, min_length=1, max_length=64)
    article_type: Optional[KbArticleType] = None
    summary: Optional[str] = Field(default=None, max_length=500)
    tags: Optional[list[str]] = None
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = Field(default=None, max_length=200)
    content: Optional[KbContentBlock] = None
    last_reviewed_at: Optional[str] = None
    change_note: str = Field(default="", max_length=300)


class KbArticleStatusRequest(BaseModel):
    status: KbArticleStatus
    change_note: str = Field(default="", max_length=300)


class KbAttachmentResponse(BaseModel):
    id: str
    file_name: str
    content_type: str
    size: int
    uploaded_at: str
    uploaded_by: str


class KbRevisionResponse(BaseModel):
    id: str
    action: str
    version: int
    status: KbArticleStatus
    changed_at: str
    changed_by: str
    change_note: str = ""


class KbArticleResponse(BaseModel):
    id: str
    title: str
    category: str
    article_type: KbArticleType
    status: KbArticleStatus
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    owner_user_id: Optional[int] = None
    owner_name: str = ""
    version: int
    last_reviewed_at: Optional[str] = None
    created_at: str
    updated_at: str
    created_by: str
    updated_by: str
    content: KbContentBlock = Field(default_factory=KbContentBlock)
    attachments: list[KbAttachmentResponse] = Field(default_factory=list)
    revisions: list[KbRevisionResponse] = Field(default_factory=list)


class KbArticleListResponse(BaseModel):
    items: list[KbArticleResponse]
    total: int
    limit: int
    offset: int


class KbCategoryResponse(BaseModel):
    id: str
    title: str
    description: str
    order: int
    total_articles: int = 0
    published_articles: int = 0


class KbFeedEventResponse(BaseModel):
    article_id: str
    article_title: str
    action: str
    status: KbArticleStatus
    version: int
    changed_at: str
    changed_by: str
    change_note: str = ""


class KbCardImage(BaseModel):
    id: str = ""
    url: str = Field(..., min_length=3, max_length=500)
    thumb_url: str = Field(default="", max_length=500)
    caption: str = Field(default="", max_length=200)
    order: int = 0


class KbCardCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    summary_short: str = Field(..., min_length=3, max_length=500)
    service_key: str = Field(..., min_length=1, max_length=64)
    external_url: AnyHttpUrl
    tags: list[str] = Field(default_factory=list)
    priority: KbCardPriority = "normal"
    is_pinned: bool = False
    cover_image_url: str = Field(default="", max_length=500)
    gallery: list[KbCardImage] = Field(default_factory=list, max_length=3)
    quick_steps: list[str] = Field(default_factory=list, max_length=12)
    owner_name: str = Field(default="", max_length=200)
    change_note: str = Field(default="", max_length=300)


class KbCardUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    summary_short: Optional[str] = Field(default=None, min_length=3, max_length=500)
    service_key: Optional[str] = Field(default=None, min_length=1, max_length=64)
    external_url: Optional[AnyHttpUrl] = None
    tags: Optional[list[str]] = None
    priority: Optional[KbCardPriority] = None
    is_pinned: Optional[bool] = None
    cover_image_url: Optional[str] = Field(default=None, max_length=500)
    gallery: Optional[list[KbCardImage]] = Field(default=None, max_length=3)
    quick_steps: Optional[list[str]] = Field(default=None, max_length=12)
    owner_name: Optional[str] = Field(default=None, max_length=200)
    change_note: str = Field(default="", max_length=300)


class KbCardStatusRequest(BaseModel):
    status: KbArticleStatus
    change_note: str = Field(default="", max_length=300)


class KbCardResponse(BaseModel):
    id: str
    title: str
    summary_short: str
    service_key: str
    external_url: str
    tags: list[str] = Field(default_factory=list)
    priority: KbCardPriority = "normal"
    status: KbArticleStatus = "draft"
    is_pinned: bool = False
    cover_image_url: str = ""
    gallery: list[KbCardImage] = Field(default_factory=list)
    quick_steps: list[str] = Field(default_factory=list)
    owner_name: str = ""
    version: int = 1
    created_at: str
    updated_at: str
    created_by: str
    updated_by: str


class KbCardListResponse(BaseModel):
    items: list[KbCardResponse]
    total: int
    limit: int
    offset: int


class KbServiceSummaryResponse(BaseModel):
    id: str
    title: str
    description: str
    order: int
    total_cards: int = 0
    published_cards: int = 0
    critical_cards: int = 0
