"""
Knowledge base service.
"""
from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import UploadFile

from backend.json_db.manager import JSONDataManager


KB_ARTICLES_FILE = "kb_articles.json"
KB_CARDS_FILE = "kb_cards.json"
KB_DEFAULT_CATEGORIES = [
    {"id": "mail", "title": "Почта", "description": "Exchange/почтовые сценарии", "order": 10},
    {"id": "trueconf", "title": "TrueConf", "description": "ВКС, клиенты, диагностика", "order": 20},
    {"id": "apps", "title": "Приложения", "description": "Корпоративные приложения и клиенты", "order": 30},
    {"id": "otrs", "title": "OTRS", "description": "Процессы заявок и эскалации", "order": 40},
    {"id": "vpn", "title": "VPN", "description": "Удалённый доступ и туннели", "order": 50},
    {"id": "ad", "title": "AD", "description": "Учетные записи, группы, политики", "order": 60},
    {"id": "print", "title": "Печать и МФУ", "description": "Принтеры, картриджи, очереди", "order": 70},
    {"id": "network", "title": "Сеть", "description": "DNS, DHCP, маршрутизация, доступ", "order": 80},
    {"id": "monitoring", "title": "Мониторинг", "description": "Алерты, реакция, проверки", "order": 90},
    {"id": "backup", "title": "Резервные копии", "description": "Backup/restore процедуры", "order": 100},
]

KB_DEFAULT_SERVICES = [
    {"id": "mail", "title": "Почта", "description": "Exchange и корпоративная почта", "order": 10},
    {"id": "trueconf", "title": "TrueConf", "description": "Видеосвязь и клиентские проблемы", "order": 20},
    {"id": "apps", "title": "Приложения", "description": "Корпоративные приложения и клиенты", "order": 30},
    {"id": "otrs", "title": "OTRS", "description": "Заявки, эскалации и SLA", "order": 40},
    {"id": "vpn", "title": "VPN", "description": "Удаленный доступ и туннели", "order": 50},
    {"id": "print", "title": "Печать", "description": "Принтеры, МФУ и драйверы", "order": 60},
    {"id": "network", "title": "Сеть", "description": "DNS, DHCP, маршрутизация, доступ", "order": 70},
    {"id": "monitoring", "title": "Мониторинг", "description": "Оповещения, проверки и реакции", "order": 80},
    {"id": "other", "title": "Другое", "description": "Прочие инструкции", "order": 999},
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_tags(tags: Optional[list[str]]) -> list[str]:
    if not isinstance(tags, list):
        return []
    normalized = []
    seen = set()
    for item in tags:
        value = str(item or "").strip()
        if not value:
            continue
        low = value.lower()
        if low in seen:
            continue
        seen.add(low)
        normalized.append(value)
    return normalized


def _safe_file_name(file_name: str) -> str:
    base = Path(str(file_name or "").strip()).name
    base = re.sub(r"[^A-Za-z0-9._\-\u0400-\u04FF ]+", "_", base)
    return base.strip() or "file.bin"


class KnowledgeBaseService:
    def __init__(self, data_manager: Optional[JSONDataManager] = None) -> None:
        self.data_manager = data_manager or JSONDataManager()
        self._lock = threading.RLock()
        self._attachments_root = self.data_manager.data_dir / "kb_attachments"
        self._attachments_root.mkdir(parents=True, exist_ok=True)

    def _load_articles(self) -> list[dict[str, Any]]:
        rows = self.data_manager.load_json(KB_ARTICLES_FILE, default_content=[])
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _save_articles(self, rows: list[dict[str, Any]]) -> None:
        self.data_manager.save_json(KB_ARTICLES_FILE, rows)

    @staticmethod
    def _content_to_search_text(content: dict[str, Any]) -> str:
        if not isinstance(content, dict):
            return ""
        parts: list[str] = []
        for key in ("overview", "symptoms", "escalation"):
            parts.append(str(content.get(key) or ""))
        for key in ("checks", "commands", "resolution_steps", "rollback_steps"):
            value = content.get(key)
            if isinstance(value, list):
                parts.extend(str(item or "") for item in value)
        faq = content.get("faq")
        if isinstance(faq, list):
            for item in faq:
                if not isinstance(item, dict):
                    continue
                parts.append(str(item.get("question") or ""))
                parts.append(str(item.get("answer") or ""))
        return " ".join(parts)

    @staticmethod
    def _build_revision(
        *,
        action: str,
        version: int,
        status: str,
        changed_by: str,
        change_note: str = "",
    ) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "action": str(action),
            "version": int(version),
            "status": str(status),
            "changed_at": _utc_now_iso(),
            "changed_by": str(changed_by or "").strip() or "system",
            "change_note": str(change_note or "").strip(),
        }

    def list_categories(self) -> list[dict[str, Any]]:
        rows = self._load_articles()
        counts: dict[str, dict[str, int]] = {}
        for row in rows:
            category = str(row.get("category") or "").strip().lower()
            if not category:
                continue
            if category not in counts:
                counts[category] = {"total": 0, "published": 0}
            counts[category]["total"] += 1
            if str(row.get("status") or "") == "published":
                counts[category]["published"] += 1

        result: list[dict[str, Any]] = []
        for item in KB_DEFAULT_CATEGORIES:
            category_id = str(item["id"]).strip().lower()
            category_counts = counts.get(category_id, {"total": 0, "published": 0})
            result.append(
                {
                    "id": category_id,
                    "title": item["title"],
                    "description": item["description"],
                    "order": int(item["order"]),
                    "total_articles": int(category_counts["total"]),
                    "published_articles": int(category_counts["published"]),
                }
            )

        result.sort(key=lambda row: (int(row.get("order", 0)), row.get("title", "")))
        return result

    def list_articles(
        self,
        *,
        q: str = "",
        category: str = "",
        article_type: str = "",
        status: str = "",
        tags: Optional[list[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = self._load_articles()
        query = str(q or "").strip().lower()
        category_filter = str(category or "").strip().lower()
        type_filter = str(article_type or "").strip().lower()
        status_filter = str(status or "").strip().lower()
        tag_filters = [str(tag or "").strip().lower() for tag in (tags or []) if str(tag or "").strip()]

        def _match(row: dict[str, Any]) -> bool:
            if category_filter and str(row.get("category") or "").strip().lower() != category_filter:
                return False
            if type_filter and str(row.get("article_type") or "").strip().lower() != type_filter:
                return False
            if status_filter and str(row.get("status") or "").strip().lower() != status_filter:
                return False
            row_tags = [str(tag or "").strip().lower() for tag in row.get("tags") or []]
            if tag_filters and not all(tag in row_tags for tag in tag_filters):
                return False
            if query:
                search_blob = " ".join(
                    [
                        str(row.get("title") or ""),
                        str(row.get("summary") or ""),
                        " ".join(str(tag or "") for tag in row.get("tags") or []),
                        self._content_to_search_text(row.get("content") or {}),
                    ]
                ).lower()
                if query not in search_blob:
                    return False
            return True

        filtered = [row for row in rows if _match(row)]
        filtered.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)

        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(500, int(limit or 100)))
        page = filtered[safe_offset:safe_offset + safe_limit]
        return {
            "items": page,
            "total": len(filtered),
            "limit": safe_limit,
            "offset": safe_offset,
        }

    def get_article(self, article_id: str) -> Optional[dict[str, Any]]:
        target = str(article_id or "").strip()
        if not target:
            return None
        for row in self._load_articles():
            if str(row.get("id") or "").strip() == target:
                return row
        return None

    @staticmethod
    def _normalize_content(content: Any) -> dict[str, Any]:
        source = content if isinstance(content, dict) else {}

        def _list_of_text(value: Any) -> list[str]:
            if not isinstance(value, list):
                return []
            return [str(item or "").strip() for item in value if str(item or "").strip()]

        faq_rows = []
        raw_faq = source.get("faq")
        if isinstance(raw_faq, list):
            for item in raw_faq:
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question") or "").strip()
                answer = str(item.get("answer") or "").strip()
                if question and answer:
                    faq_rows.append({"question": question, "answer": answer})

        return {
            "overview": str(source.get("overview") or "").strip(),
            "symptoms": str(source.get("symptoms") or "").strip(),
            "checks": _list_of_text(source.get("checks")),
            "commands": _list_of_text(source.get("commands")),
            "resolution_steps": _list_of_text(source.get("resolution_steps")),
            "rollback_steps": _list_of_text(source.get("rollback_steps")),
            "escalation": str(source.get("escalation") or "").strip(),
            "faq": faq_rows,
        }

    def create_article(
        self,
        *,
        payload: dict[str, Any],
        actor_username: str,
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        article_id = str(uuid.uuid4())
        owner_name = str(payload.get("owner_name") or "").strip()
        article = {
            "id": article_id,
            "title": str(payload.get("title") or "").strip(),
            "category": str(payload.get("category") or "").strip().lower(),
            "article_type": str(payload.get("article_type") or "runbook").strip().lower(),
            "status": "draft",
            "summary": str(payload.get("summary") or "").strip(),
            "tags": _normalize_tags(payload.get("tags")),
            "owner_user_id": payload.get("owner_user_id"),
            "owner_name": owner_name,
            "version": 1,
            "last_reviewed_at": payload.get("last_reviewed_at"),
            "created_at": now,
            "updated_at": now,
            "created_by": actor_username,
            "updated_by": actor_username,
            "content": self._normalize_content(payload.get("content")),
            "attachments": [],
            "revisions": [
                self._build_revision(
                    action="create",
                    version=1,
                    status="draft",
                    changed_by=actor_username,
                    change_note=str(payload.get("change_note") or "").strip(),
                )
            ],
        }

        with self._lock:
            rows = self._load_articles()
            rows.append(article)
            self._save_articles(rows)
        return article

    def update_article(
        self,
        *,
        article_id: str,
        payload: dict[str, Any],
        actor_username: str,
    ) -> Optional[dict[str, Any]]:
        target = str(article_id or "").strip()
        if not target:
            return None

        now = _utc_now_iso()
        with self._lock:
            rows = self._load_articles()
            for index, row in enumerate(rows):
                if str(row.get("id") or "") != target:
                    continue

                if "title" in payload and payload.get("title") is not None:
                    row["title"] = str(payload.get("title") or "").strip()
                if "category" in payload and payload.get("category") is not None:
                    row["category"] = str(payload.get("category") or "").strip().lower()
                if "article_type" in payload and payload.get("article_type") is not None:
                    row["article_type"] = str(payload.get("article_type") or "runbook").strip().lower()
                if "summary" in payload and payload.get("summary") is not None:
                    row["summary"] = str(payload.get("summary") or "").strip()
                if "tags" in payload and payload.get("tags") is not None:
                    row["tags"] = _normalize_tags(payload.get("tags"))
                if "owner_user_id" in payload:
                    row["owner_user_id"] = payload.get("owner_user_id")
                if "owner_name" in payload and payload.get("owner_name") is not None:
                    row["owner_name"] = str(payload.get("owner_name") or "").strip()
                if "last_reviewed_at" in payload:
                    row["last_reviewed_at"] = payload.get("last_reviewed_at")
                if "content" in payload and payload.get("content") is not None:
                    row["content"] = self._normalize_content(payload.get("content"))

                row["updated_at"] = now
                row["updated_by"] = actor_username
                revisions = row.get("revisions")
                if not isinstance(revisions, list):
                    revisions = []
                revisions.append(
                    self._build_revision(
                        action="edit",
                        version=int(row.get("version") or 1),
                        status=str(row.get("status") or "draft"),
                        changed_by=actor_username,
                        change_note=str(payload.get("change_note") or "").strip(),
                    )
                )
                row["revisions"] = revisions
                rows[index] = row
                self._save_articles(rows)
                return row

        return None

    def set_article_status(
        self,
        *,
        article_id: str,
        status: str,
        actor_username: str,
        change_note: str = "",
    ) -> Optional[dict[str, Any]]:
        target = str(article_id or "").strip()
        next_status = str(status or "").strip().lower()
        if not target or next_status not in {"draft", "published", "archived"}:
            return None

        now = _utc_now_iso()
        with self._lock:
            rows = self._load_articles()
            for index, row in enumerate(rows):
                if str(row.get("id") or "") != target:
                    continue

                current_status = str(row.get("status") or "draft")
                if current_status == "published" and next_status == "published":
                    row["version"] = int(row.get("version") or 1) + 1
                elif current_status != "published" and next_status == "published":
                    row["version"] = max(1, int(row.get("version") or 1))

                row["status"] = next_status
                row["updated_at"] = now
                row["updated_by"] = actor_username
                if next_status == "published":
                    row["last_reviewed_at"] = now

                revisions = row.get("revisions")
                if not isinstance(revisions, list):
                    revisions = []
                revisions.append(
                    self._build_revision(
                        action=f"status:{next_status}",
                        version=int(row.get("version") or 1),
                        status=next_status,
                        changed_by=actor_username,
                        change_note=change_note,
                    )
                )
                row["revisions"] = revisions
                rows[index] = row
                self._save_articles(rows)
                return row
        return None

    def get_feed(self, *, limit: int = 50) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for article in self._load_articles():
            title = str(article.get("title") or "")
            article_id = str(article.get("id") or "")
            for revision in article.get("revisions") or []:
                if not isinstance(revision, dict):
                    continue
                events.append(
                    {
                        "article_id": article_id,
                        "article_title": title,
                        "action": str(revision.get("action") or ""),
                        "status": str(revision.get("status") or article.get("status") or "draft"),
                        "version": int(revision.get("version") or article.get("version") or 1),
                        "changed_at": str(revision.get("changed_at") or ""),
                        "changed_by": str(revision.get("changed_by") or ""),
                        "change_note": str(revision.get("change_note") or ""),
                    }
                )
        events.sort(key=lambda item: item.get("changed_at", ""), reverse=True)
        return events[: max(1, min(500, int(limit or 50)))]

    def add_attachment(
        self,
        *,
        article_id: str,
        upload: UploadFile,
        actor_username: str,
    ) -> Optional[dict[str, Any]]:
        target = str(article_id or "").strip()
        if not target:
            return None

        raw_name = _safe_file_name(upload.filename or "file.bin")
        attachment_id = str(uuid.uuid4())
        stored_name = f"{attachment_id}_{raw_name}"
        article_dir = self._attachments_root / target
        article_dir.mkdir(parents=True, exist_ok=True)
        full_path = article_dir / stored_name
        payload = upload.file.read()
        full_path.write_bytes(payload)

        attachment = {
            "id": attachment_id,
            "file_name": raw_name,
            "content_type": str(upload.content_type or "application/octet-stream"),
            "size": int(len(payload)),
            "uploaded_at": _utc_now_iso(),
            "uploaded_by": actor_username,
            "storage_name": stored_name,
        }

        with self._lock:
            rows = self._load_articles()
            for index, row in enumerate(rows):
                if str(row.get("id") or "") != target:
                    continue
                attachments = row.get("attachments")
                if not isinstance(attachments, list):
                    attachments = []
                attachments.append(attachment)
                row["attachments"] = attachments
                row["updated_at"] = _utc_now_iso()
                row["updated_by"] = actor_username
                revisions = row.get("revisions")
                if not isinstance(revisions, list):
                    revisions = []
                revisions.append(
                    self._build_revision(
                        action="attachment:add",
                        version=int(row.get("version") or 1),
                        status=str(row.get("status") or "draft"),
                        changed_by=actor_username,
                        change_note=raw_name,
                    )
                )
                row["revisions"] = revisions
                rows[index] = row
                self._save_articles(rows)
                return attachment
        # rollback orphan file
        try:
            full_path.unlink(missing_ok=True)
        except Exception:
            pass
        return None

    def get_attachment(
        self,
        *,
        article_id: str,
        attachment_id: str,
    ) -> Optional[dict[str, Any]]:
        article = self.get_article(article_id)
        if not article:
            return None

        attachments = article.get("attachments")
        if not isinstance(attachments, list):
            return None
        for attachment in attachments:
            if str(attachment.get("id") or "") != str(attachment_id or ""):
                continue
            storage_name = str(attachment.get("storage_name") or "").strip()
            if not storage_name:
                return None
            path = self._attachments_root / str(article_id) / storage_name
            if not path.exists() or not path.is_file():
                return None
            result = dict(attachment)
            result["path"] = str(path)
            return result
        return None

    def delete_attachment(
        self,
        *,
        article_id: str,
        attachment_id: str,
        actor_username: str,
    ) -> bool:
        target_article = str(article_id or "").strip()
        target_attachment = str(attachment_id or "").strip()
        if not target_article or not target_attachment:
            return False

        with self._lock:
            rows = self._load_articles()
            for index, row in enumerate(rows):
                if str(row.get("id") or "") != target_article:
                    continue
                attachments = row.get("attachments")
                if not isinstance(attachments, list):
                    return False
                keep = []
                removed = None
                for item in attachments:
                    if str(item.get("id") or "") == target_attachment and removed is None:
                        removed = item
                    else:
                        keep.append(item)
                if removed is None:
                    return False
                row["attachments"] = keep
                row["updated_at"] = _utc_now_iso()
                row["updated_by"] = actor_username
                revisions = row.get("revisions")
                if not isinstance(revisions, list):
                    revisions = []
                revisions.append(
                    self._build_revision(
                        action="attachment:remove",
                        version=int(row.get("version") or 1),
                        status=str(row.get("status") or "draft"),
                        changed_by=actor_username,
                        change_note=str(removed.get("file_name") or ""),
                    )
                )
                row["revisions"] = revisions
                rows[index] = row
                self._save_articles(rows)

                storage_name = str(removed.get("storage_name") or "").strip()
                if storage_name:
                    path = self._attachments_root / target_article / storage_name
                    try:
                        path.unlink(missing_ok=True)
                    except Exception:
                        pass
                return True
        return False

    def _load_cards(self) -> list[dict[str, Any]]:
        rows = self.data_manager.load_json(KB_CARDS_FILE, default_content=[])
        if isinstance(rows, list):
            cards = [row for row in rows if isinstance(row, dict)]
            if cards:
                return cards
        # One-time compatibility bootstrap: old article records become card stubs.
        bootstrap_cards: list[dict[str, Any]] = []
        for article in self._load_articles():
            article_id = str(article.get("id") or "").strip()
            if not article_id:
                continue
            summary = str(article.get("summary") or "").strip()
            if not summary:
                summary = str((article.get("content") or {}).get("overview") or "").strip()
            service_key = self._normalize_service_key(article.get("category"))
            bootstrap_cards.append(
                {
                    "id": article_id,
                    "title": str(article.get("title") or "").strip() or "Без названия",
                    "summary_short": summary[:500] if summary else "Краткое описание не заполнено",
                    "service_key": service_key,
                    "external_url": "#",
                    "tags": _normalize_tags(article.get("tags")),
                    "priority": "normal",
                    "status": str(article.get("status") or "draft"),
                    "is_pinned": False,
                    "cover_image_url": "",
                    "gallery": [],
                    "quick_steps": self._normalize_steps((article.get("content") or {}).get("resolution_steps")),
                    "owner_name": str(article.get("owner_name") or "").strip(),
                    "version": int(article.get("version") or 1),
                    "created_at": str(article.get("created_at") or _utc_now_iso()),
                    "updated_at": str(article.get("updated_at") or _utc_now_iso()),
                    "created_by": str(article.get("created_by") or "system"),
                    "updated_by": str(article.get("updated_by") or "system"),
                    "revisions": article.get("revisions") if isinstance(article.get("revisions"), list) else [],
                }
            )
        if bootstrap_cards:
            self._save_cards(bootstrap_cards)
        return bootstrap_cards

    def _save_cards(self, rows: list[dict[str, Any]]) -> None:
        self.data_manager.save_json(KB_CARDS_FILE, rows)

    @staticmethod
    def _normalize_service_key(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return "other"
        return re.sub(r"[^a-z0-9_\-]+", "-", raw).strip("-") or "other"

    @staticmethod
    def _priority_rank(value: str) -> int:
        normalized = str(value or "").strip().lower()
        if normalized == "critical":
            return 4
        if normalized == "high":
            return 3
        if normalized == "normal":
            return 2
        if normalized == "low":
            return 1
        return 0

    @staticmethod
    def _normalize_steps(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
            if len(result) >= 12:
                break
        return result

    @staticmethod
    def _normalize_gallery(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        result: list[dict[str, Any]] = []
        for index, item in enumerate(value):
            if len(result) >= 3:
                break
            if isinstance(item, str):
                url = str(item or "").strip()
                if not url:
                    continue
                result.append(
                    {
                        "id": str(uuid.uuid4()),
                        "url": url,
                        "thumb_url": url,
                        "caption": "",
                        "order": index + 1,
                    }
                )
                continue
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            thumb_url = str(item.get("thumb_url") or "").strip() or url
            caption = str(item.get("caption") or "").strip()
            order = item.get("order")
            try:
                numeric_order = int(order)
            except Exception:
                numeric_order = index + 1
            result.append(
                {
                    "id": str(item.get("id") or str(uuid.uuid4())),
                    "url": url,
                    "thumb_url": thumb_url,
                    "caption": caption[:200],
                    "order": numeric_order,
                }
            )
        result.sort(key=lambda row: int(row.get("order") or 0))
        return result

    def list_services_with_counts(self) -> list[dict[str, Any]]:
        rows = self._load_cards()
        counts: dict[str, dict[str, int]] = {}
        for row in rows:
            key = self._normalize_service_key(row.get("service_key"))
            if key not in counts:
                counts[key] = {"total": 0, "published": 0, "critical": 0}
            counts[key]["total"] += 1
            if str(row.get("status") or "") == "published":
                counts[key]["published"] += 1
            if str(row.get("priority") or "") == "critical":
                counts[key]["critical"] += 1

        result: list[dict[str, Any]] = []
        default_ids = set()
        for item in KB_DEFAULT_SERVICES:
            service_id = self._normalize_service_key(item.get("id"))
            default_ids.add(service_id)
            meta = counts.get(service_id, {"total": 0, "published": 0, "critical": 0})
            result.append(
                {
                    "id": service_id,
                    "title": str(item.get("title") or service_id),
                    "description": str(item.get("description") or ""),
                    "order": int(item.get("order") or 999),
                    "total_cards": int(meta["total"]),
                    "published_cards": int(meta["published"]),
                    "critical_cards": int(meta["critical"]),
                }
            )

        extra_keys = sorted(key for key in counts.keys() if key not in default_ids)
        for index, key in enumerate(extra_keys):
            meta = counts[key]
            result.append(
                {
                    "id": key,
                    "title": key.upper(),
                    "description": "Пользовательская категория",
                    "order": 1200 + index,
                    "total_cards": int(meta["total"]),
                    "published_cards": int(meta["published"]),
                    "critical_cards": int(meta["critical"]),
                }
            )

        result.sort(key=lambda row: (int(row.get("order") or 0), str(row.get("title") or "")))
        return result

    def list_cards(
        self,
        *,
        q: str = "",
        service: str = "",
        tags: Optional[list[str]] = None,
        status: str = "",
        priority: str = "",
        pinned: Optional[bool] = None,
        sort: str = "updated_desc",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = self._load_cards()
        query = str(q or "").strip().lower()
        service_filter = self._normalize_service_key(service) if str(service or "").strip() else ""
        status_filter = str(status or "").strip().lower()
        priority_filter = str(priority or "").strip().lower()
        tag_filters = [str(item or "").strip().lower() for item in (tags or []) if str(item or "").strip()]
        pinned_filter = pinned if isinstance(pinned, bool) else None

        def _match(row: dict[str, Any]) -> bool:
            if service_filter and self._normalize_service_key(row.get("service_key")) != service_filter:
                return False
            if status_filter and str(row.get("status") or "").strip().lower() != status_filter:
                return False
            if priority_filter and str(row.get("priority") or "").strip().lower() != priority_filter:
                return False
            if pinned_filter is not None and bool(row.get("is_pinned")) != pinned_filter:
                return False
            row_tags = [str(tag or "").strip().lower() for tag in row.get("tags") or []]
            if tag_filters and not all(tag in row_tags for tag in tag_filters):
                return False
            if query:
                blob = " ".join(
                    [
                        str(row.get("title") or ""),
                        str(row.get("summary_short") or ""),
                        str(row.get("service_key") or ""),
                        " ".join(str(tag or "") for tag in row.get("tags") or []),
                        " ".join(str(step or "") for step in row.get("quick_steps") or []),
                    ]
                ).lower()
                if query not in blob:
                    return False
            return True

        filtered = [row for row in rows if _match(row)]
        sort_key = str(sort or "updated_desc").strip().lower()
        if sort_key == "critical":
            filtered.sort(
                key=lambda row: (
                    self._priority_rank(str(row.get("priority") or "")),
                    str(row.get("updated_at") or ""),
                ),
                reverse=True,
            )
        elif sort_key == "title_asc":
            filtered.sort(key=lambda row: str(row.get("title") or "").lower())
        else:
            filtered.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)

        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(500, int(limit or 100)))
        page = filtered[safe_offset:safe_offset + safe_limit]
        return {
            "items": page,
            "total": len(filtered),
            "limit": safe_limit,
            "offset": safe_offset,
        }

    def get_card(self, card_id: str) -> Optional[dict[str, Any]]:
        target = str(card_id or "").strip()
        if not target:
            return None
        for row in self._load_cards():
            if str(row.get("id") or "").strip() == target:
                return row
        return None

    def create_card(
        self,
        *,
        payload: dict[str, Any],
        actor_username: str,
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        card_id = str(uuid.uuid4())
        title = str(payload.get("title") or "").strip()
        summary_short = str(payload.get("summary_short") or "").strip()
        service_key = self._normalize_service_key(payload.get("service_key"))
        external_url = str(payload.get("external_url") or "").strip()
        if not external_url:
            external_url = "#"

        card = {
            "id": card_id,
            "title": title,
            "summary_short": summary_short,
            "service_key": service_key,
            "external_url": external_url,
            "tags": _normalize_tags(payload.get("tags")),
            "priority": str(payload.get("priority") or "normal").strip().lower() or "normal",
            "status": "draft",
            "is_pinned": bool(payload.get("is_pinned")),
            "cover_image_url": str(payload.get("cover_image_url") or "").strip(),
            "gallery": self._normalize_gallery(payload.get("gallery")),
            "quick_steps": self._normalize_steps(payload.get("quick_steps")),
            "owner_name": str(payload.get("owner_name") or "").strip(),
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "created_by": actor_username,
            "updated_by": actor_username,
            "revisions": [
                self._build_revision(
                    action="create",
                    version=1,
                    status="draft",
                    changed_by=actor_username,
                    change_note=str(payload.get("change_note") or "").strip(),
                )
            ],
        }

        with self._lock:
            rows = self._load_cards()
            rows.append(card)
            self._save_cards(rows)
        return card

    def update_card(
        self,
        *,
        card_id: str,
        payload: dict[str, Any],
        actor_username: str,
    ) -> Optional[dict[str, Any]]:
        target = str(card_id or "").strip()
        if not target:
            return None

        with self._lock:
            rows = self._load_cards()
            for index, row in enumerate(rows):
                if str(row.get("id") or "") != target:
                    continue

                if "title" in payload and payload.get("title") is not None:
                    row["title"] = str(payload.get("title") or "").strip()
                if "summary_short" in payload and payload.get("summary_short") is not None:
                    row["summary_short"] = str(payload.get("summary_short") or "").strip()
                if "service_key" in payload and payload.get("service_key") is not None:
                    row["service_key"] = self._normalize_service_key(payload.get("service_key"))
                if "external_url" in payload and payload.get("external_url") is not None:
                    row["external_url"] = str(payload.get("external_url") or "").strip()
                if "tags" in payload and payload.get("tags") is not None:
                    row["tags"] = _normalize_tags(payload.get("tags"))
                if "priority" in payload and payload.get("priority") is not None:
                    row["priority"] = str(payload.get("priority") or "normal").strip().lower()
                if "is_pinned" in payload and payload.get("is_pinned") is not None:
                    row["is_pinned"] = bool(payload.get("is_pinned"))
                if "cover_image_url" in payload and payload.get("cover_image_url") is not None:
                    row["cover_image_url"] = str(payload.get("cover_image_url") or "").strip()
                if "gallery" in payload and payload.get("gallery") is not None:
                    row["gallery"] = self._normalize_gallery(payload.get("gallery"))
                if "quick_steps" in payload and payload.get("quick_steps") is not None:
                    row["quick_steps"] = self._normalize_steps(payload.get("quick_steps"))
                if "owner_name" in payload and payload.get("owner_name") is not None:
                    row["owner_name"] = str(payload.get("owner_name") or "").strip()

                row["updated_at"] = _utc_now_iso()
                row["updated_by"] = actor_username
                revisions = row.get("revisions")
                if not isinstance(revisions, list):
                    revisions = []
                revisions.append(
                    self._build_revision(
                        action="edit",
                        version=int(row.get("version") or 1),
                        status=str(row.get("status") or "draft"),
                        changed_by=actor_username,
                        change_note=str(payload.get("change_note") or "").strip(),
                    )
                )
                row["revisions"] = revisions
                rows[index] = row
                self._save_cards(rows)
                return row
        return None

    def set_card_status(
        self,
        *,
        card_id: str,
        status: str,
        actor_username: str,
        change_note: str = "",
    ) -> Optional[dict[str, Any]]:
        target = str(card_id or "").strip()
        next_status = str(status or "").strip().lower()
        if not target or next_status not in {"draft", "published", "archived"}:
            return None

        with self._lock:
            rows = self._load_cards()
            for index, row in enumerate(rows):
                if str(row.get("id") or "") != target:
                    continue

                current_status = str(row.get("status") or "draft").lower()
                if current_status == "published" and next_status == "published":
                    row["version"] = int(row.get("version") or 1) + 1
                elif current_status != "published" and next_status == "published":
                    row["version"] = max(1, int(row.get("version") or 1))
                row["status"] = next_status
                row["updated_at"] = _utc_now_iso()
                row["updated_by"] = actor_username

                revisions = row.get("revisions")
                if not isinstance(revisions, list):
                    revisions = []
                revisions.append(
                    self._build_revision(
                        action=f"status:{next_status}",
                        version=int(row.get("version") or 1),
                        status=next_status,
                        changed_by=actor_username,
                        change_note=str(change_note or "").strip(),
                    )
                )
                row["revisions"] = revisions
                rows[index] = row
                self._save_cards(rows)
                return row
        return None


kb_service = KnowledgeBaseService()
