"""
Mail service for Exchange (EWS/NTLM) inbox access, sending and IT request templates.
"""
from __future__ import annotations

import base64
import html
import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Optional

from local_store import get_local_store
from backend.services.secret_crypto_service import SecretCryptoError, decrypt_secret
from backend.services.user_service import user_service

logger = logging.getLogger(__name__)
_UNSET = object()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _plain_text_to_html(text: Any) -> str:
    value = str(text or "")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return html.escape(normalized).replace("\n", "<br>")


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_recipients(value: str | None) -> list[str]:
    text = _normalize_text(value)
    if not text:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[;,]+", text):
        email = _normalize_text(part).lower()
        if not email:
            continue
        if email in seen:
            continue
        seen.add(email)
        result.append(email)
    return result


class MailServiceError(RuntimeError):
    """Domain error for mail service operations."""


class MailPayloadTooLargeError(MailServiceError):
    """Payload is too large (attachments count/size limits)."""


class MailService:
    _TEMPLATES_TABLE = "mail_it_templates"
    _LOG_TABLE = "mail_messages_log"
    _ATTACHMENT_TOKEN_PREFIX = "att1_"
    _IT_REQUEST_RECIPIENTS = ["it@zsgp.ru"]
    _SEARCH_WINDOW_LIMIT = 5000
    _SEARCH_BATCH_SIZE = 250
    _MAX_IT_FILES = 10
    _MAX_IT_FILE_SIZE = 15 * 1024 * 1024
    _MAX_IT_TOTAL_SIZE = 25 * 1024 * 1024
    _MAX_MAIL_FILES = 10
    _MAX_MAIL_FILE_SIZE = 15 * 1024 * 1024
    _MAX_MAIL_TOTAL_SIZE = 25 * 1024 * 1024
    _MAIL_LOG_RETENTION_DAYS_DEFAULT = 90
    _FIELD_TYPES = {"text", "textarea", "select", "multiselect", "date", "checkbox", "email", "tel"}

    def __init__(self) -> None:
        store = get_local_store()
        self.db_path = Path(store.db_path)
        self._lock = RLock()
        self._last_log_cleanup_at: datetime | None = None
        self._ensure_schema()
        self._migrate_legacy_template_fields()
        self._cleanup_message_log()
        # Globally disable TLS verification for Exchange connections if configured.
        if not self.verify_tls:
            self._disable_tls_verification()

    def _disable_tls_verification(self) -> None:
        """Set NoVerifyHTTPAdapter globally and suppress SSL warnings."""
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        try:
            from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
            BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter
        except Exception:
            pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {self._TEMPLATES_TABLE} (
                    id TEXT PRIMARY KEY,
                    code TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    subject_template TEXT NOT NULL,
                    body_template_md TEXT NOT NULL DEFAULT '',
                    required_fields_json TEXT NOT NULL DEFAULT '[]',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_by_user_id INTEGER NOT NULL DEFAULT 0,
                    created_by_username TEXT NOT NULL DEFAULT '',
                    updated_by_user_id INTEGER NOT NULL DEFAULT 0,
                    updated_by_username TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS {self._LOG_TABLE} (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    username TEXT NOT NULL DEFAULT '',
                    direction TEXT NOT NULL DEFAULT 'outgoing',
                    folder_hint TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL DEFAULT '',
                    recipients_json TEXT NOT NULL DEFAULT '[]',
                    sent_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'sent',
                    exchange_item_id TEXT NULL,
                    error_text TEXT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_{self._TEMPLATES_TABLE}_active
                    ON {self._TEMPLATES_TABLE}(is_active, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_{self._LOG_TABLE}_user_time
                    ON {self._LOG_TABLE}(user_id, sent_at DESC);
                """
            )
            conn.commit()

    @property
    def exchange_host(self) -> str:
        return _normalize_text(os.getenv("MAIL_EXCHANGE_HOST"), "10.103.0.50")

    @property
    def exchange_ews_url(self) -> str:
        raw = _normalize_text(os.getenv("MAIL_EWS_URL"))
        if raw:
            return raw
        return f"https://{self.exchange_host}/EWS/Exchange.asmx"

    @property
    def verify_tls(self) -> bool:
        return _to_bool(os.getenv("MAIL_VERIFY_TLS"), default=False)

    @property
    def it_request_recipients(self) -> list[str]:
        return _parse_recipients(os.getenv("MAIL_IT_RECIPIENTS", ""))

    @property
    def mail_log_retention_days(self) -> int:
        raw = _normalize_text(
            os.getenv("MAIL_LOG_RETENTION_DAYS"),
            str(self._MAIL_LOG_RETENTION_DAYS_DEFAULT),
        )
        try:
            return max(0, int(raw))
        except Exception:
            return self._MAIL_LOG_RETENTION_DAYS_DEFAULT

    @property
    def search_window_limit(self) -> int:
        raw = _normalize_text(os.getenv("MAIL_SEARCH_WINDOW_LIMIT"), str(self._SEARCH_WINDOW_LIMIT))
        try:
            return max(500, min(20000, int(raw)))
        except Exception:
            return self._SEARCH_WINDOW_LIMIT

    @property
    def max_mail_files(self) -> int:
        raw = _normalize_text(os.getenv("MAIL_MAX_FILES"), str(self._MAX_MAIL_FILES))
        try:
            return max(1, min(50, int(raw)))
        except Exception:
            return self._MAX_MAIL_FILES

    @property
    def max_mail_file_size(self) -> int:
        raw = _normalize_text(
            os.getenv("MAIL_MAX_FILE_SIZE_MB"),
            str(self._MAX_MAIL_FILE_SIZE // (1024 * 1024)),
        )
        try:
            return max(1, min(200, int(raw))) * 1024 * 1024
        except Exception:
            return self._MAX_MAIL_FILE_SIZE

    @property
    def max_mail_total_size(self) -> int:
        raw = _normalize_text(
            os.getenv("MAIL_MAX_TOTAL_SIZE_MB"),
            str(self._MAX_MAIL_TOTAL_SIZE // (1024 * 1024)),
        )
        try:
            return max(1, min(500, int(raw))) * 1024 * 1024
        except Exception:
            return self._MAX_MAIL_TOTAL_SIZE

    def _maybe_cleanup_message_log(self) -> None:
        now = datetime.now(timezone.utc)
        if self._last_log_cleanup_at and (now - self._last_log_cleanup_at) < timedelta(hours=1):
            return
        self._cleanup_message_log()
        self._last_log_cleanup_at = now

    def _cleanup_message_log(self) -> None:
        retention_days = self.mail_log_retention_days
        if retention_days <= 0:
            return
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        try:
            with self._lock, self._connect() as conn:
                cursor = conn.execute(
                    f"DELETE FROM {self._LOG_TABLE} WHERE sent_at < ?",
                    (cutoff,),
                )
                conn.commit()
                deleted = int(cursor.rowcount or 0)
            if deleted > 0:
                logger.info(
                    "Mail log retention cleanup completed: deleted=%s retention_days=%s",
                    deleted,
                    retention_days,
                )
        except Exception as exc:
            logger.warning("Mail log retention cleanup failed: %s", exc)

    @staticmethod
    def _encode_message_id(folder: str, exchange_id: str) -> str:
        raw = f"{_normalize_text(folder, 'inbox')}::{_normalize_text(exchange_id)}"
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8").rstrip("=")

    @staticmethod
    def _decode_message_id(token: str) -> tuple[str, str]:
        value = _normalize_text(token)
        if not value:
            raise MailServiceError("Message id is required")
        padded = value + "=" * ((4 - len(value) % 4) % 4)
        try:
            raw = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        except Exception as exc:
            raise MailServiceError("Invalid message id") from exc
        if "::" not in raw:
            raise MailServiceError("Invalid message id payload")
        folder, exchange_id = raw.split("::", 1)
        if not exchange_id:
            raise MailServiceError("Invalid message id payload")
        return _normalize_text(folder, "inbox").lower(), exchange_id

    @staticmethod
    def _encode_attachment_token(attachment_id: str) -> str:
        value = _normalize_text(attachment_id)
        if not value:
            return ""
        encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8").rstrip("=")
        return f"{MailService._ATTACHMENT_TOKEN_PREFIX}{encoded}"

    @staticmethod
    def _decode_attachment_token(token: str) -> str:
        value = _normalize_text(token)
        if not value:
            raise MailServiceError("Attachment token is required")
        if not value.startswith(MailService._ATTACHMENT_TOKEN_PREFIX):
            raise MailServiceError("Attachment token format is invalid")
        encoded_part = value[len(MailService._ATTACHMENT_TOKEN_PREFIX):]
        if not encoded_part:
            raise MailServiceError("Attachment token payload is empty")
        padded = encoded_part + "=" * ((4 - len(encoded_part) % 4) % 4)
        try:
            raw = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        except Exception as exc:
            raise MailServiceError("Attachment token payload is invalid") from exc
        resolved = _normalize_text(raw)
        if not resolved:
            raise MailServiceError("Attachment token payload is invalid")
        return resolved

    def resolve_attachment_id(self, token_or_id: str) -> str:
        value = _normalize_text(token_or_id)
        if not value:
            raise MailServiceError("Attachment id is required")
        if value.startswith(self._ATTACHMENT_TOKEN_PREFIX):
            return self._decode_attachment_token(value)
        # Backward-compatible fallback for legacy clients sending raw exchangelib attachment id.
        return value

    def _resolve_user_mail_profile(self, user_id: int, *, require_password: bool) -> dict[str, Any]:
        user = user_service.get_by_id(int(user_id))
        if not user:
            raise MailServiceError("User not found")
        email = _normalize_text(user.get("mailbox_email") or user.get("email")).lower()
        login = _normalize_text(user.get("mailbox_login") or email)
        signature = _normalize_text(user.get("mail_signature_html"))
        password_enc = _normalize_text(user.get("mailbox_password_enc"))
        if not email:
            raise MailServiceError("Mailbox email is not configured")
        if not login:
            raise MailServiceError("Mailbox login is not configured")
        password = ""
        if require_password:
            if not password_enc:
                raise MailServiceError("Mailbox password is not configured")
            try:
                password = decrypt_secret(password_enc)
            except SecretCryptoError as exc:
                raise MailServiceError(str(exc)) from exc
            if not password:
                raise MailServiceError("Mailbox password is empty")
        return {
            "user": user,
            "email": email,
            "login": login,
            "password": password,
            "signature": signature,
        }

    @contextmanager
    def _exchange_protocol_context(self):
        if self.verify_tls:
            yield
            return
        try:
            from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
        except Exception:
            # If exchangelib is unavailable, downstream connection call will fail with explicit error.
            yield
            return
        old_adapter = BaseProtocol.HTTP_ADAPTER_CLS
        BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter
        try:
            yield
        finally:
            BaseProtocol.HTTP_ADAPTER_CLS = old_adapter

    def _create_account(self, *, email: str, login: str, password: str):
        try:
            from exchangelib import Account, Configuration, Credentials, DELEGATE, NTLM
        except Exception as exc:
            raise MailServiceError("exchangelib package is not installed") from exc

        config_kwargs = {
            "credentials": Credentials(username=login, password=password),
            "auth_type": NTLM,
        }
        ews_url = self.exchange_ews_url
        if ews_url:
            config_kwargs["service_endpoint"] = ews_url
        else:
            config_kwargs["server"] = self.exchange_host

        with self._exchange_protocol_context():
            cfg = Configuration(**config_kwargs)
            return Account(
                primary_smtp_address=email,
                config=cfg,
                autodiscover=False,
                access_type=DELEGATE,
            )

    @staticmethod
    def _resolve_folder(account, folder: str):
        key = _normalize_text(folder, "inbox").lower()
        mapping = {
            "inbox": account.inbox,
            "sent": account.sent,
            "sentitems": account.sent,
            "drafts": account.drafts,
            "trash": account.trash,
            "deleted": account.trash,
        }
        return mapping.get(key, account.inbox), key

    @staticmethod
    def _item_sender(item) -> str:
        sender = getattr(item, "sender", None)
        if sender is not None:
            value = _normalize_text(getattr(sender, "email_address", None))
            if value:
                return value.lower()
        author = getattr(item, "author", None)
        if author is not None:
            value = _normalize_text(getattr(author, "email_address", None))
            if value:
                return value.lower()
        return ""

    @staticmethod
    def _item_recipients(item) -> list[str]:
        recipients: list[str] = []
        seen: set[str] = set()
        for attr in ("to_recipients", "cc_recipients"):
            values = getattr(item, attr, None) or []
            for rec in values:
                email = _normalize_text(getattr(rec, "email_address", None)).lower()
                if not email or email in seen:
                    continue
                seen.add(email)
                recipients.append(email)
        return recipients

    def _serialize_message_preview(self, item, folder_key: str) -> dict[str, Any]:
        received = getattr(item, "datetime_received", None) or getattr(item, "datetime_created", None)
        received_iso = received.isoformat() if received else None
        body_text = _normalize_text(getattr(item, "text_body", None))
        if not body_text:
            body_text = _normalize_text(getattr(item, "body", None))
        body_preview = body_text[:350]
        attachments_count = len(getattr(item, "attachments", None) or [])
        return {
            "id": self._encode_message_id(folder_key, _normalize_text(getattr(item, "id", ""))),
            "exchange_id": _normalize_text(getattr(item, "id", "")),
            "folder": folder_key,
            "subject": _normalize_text(getattr(item, "subject", "")),
            "sender": self._item_sender(item),
            "recipients": self._item_recipients(item),
            "received_at": received_iso,
            "is_read": bool(getattr(item, "is_read", False)),
            "has_attachments": attachments_count > 0,
            "attachments_count": attachments_count,
            "body_preview": body_preview,
        }

    def list_messages(
        self,
        *,
        user_id: int,
        folder: str = "inbox",
        limit: int = 50,
        offset: int = 0,
        q: str = "",
        unread_only: bool = False,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(200, int(limit or 50)))
        safe_offset = max(0, int(offset or 0))
        query_text = _normalize_text(q).lower()

        profile = self._resolve_user_mail_profile(int(user_id), require_password=True)
        account = self._create_account(
            email=profile["email"],
            login=profile["login"],
            password=profile["password"],
        )
        folder_obj, folder_key = self._resolve_folder(account, folder)

        queryset = folder_obj.all().order_by("-datetime_received")
        if unread_only:
            queryset = queryset.filter(is_read=False)

        search_limited = False
        searched_window = 0
        if query_text:
            filtered = []
            search_limit = max(self.search_window_limit, safe_offset + safe_limit)
            scanned = 0
            while scanned < search_limit:
                batch_items = list(queryset[scanned : scanned + self._SEARCH_BATCH_SIZE])
                if not batch_items:
                    break
                for item in batch_items:
                    subject = _normalize_text(getattr(item, "subject", "")).lower()
                    sender = self._item_sender(item).lower()
                    body_preview = _normalize_text(getattr(item, "text_body", "")).lower()
                    if query_text in subject or query_text in sender or query_text in body_preview:
                        filtered.append(item)
                scanned += len(batch_items)
                if len(batch_items) < self._SEARCH_BATCH_SIZE:
                    break
            searched_window = scanned
            search_limited = scanned >= search_limit
            total = len(filtered)
            page_items = filtered[safe_offset : safe_offset + safe_limit]
        else:
            try:
                total = int(queryset.count())
            except Exception:
                total = 0
            page_items = list(queryset[safe_offset : safe_offset + safe_limit])

        items = [self._serialize_message_preview(item, folder_key) for item in page_items]
        return {
            "items": items,
            "folder": folder_key,
            "limit": safe_limit,
            "offset": safe_offset,
            "total": max(total, safe_offset + len(items)),
            "search_limited": bool(query_text) and search_limited,
            "searched_window": searched_window,
        }

    def get_message(self, *, user_id: int, message_id: str) -> dict[str, Any]:
        folder_key, exchange_id = self._decode_message_id(message_id)
        profile = self._resolve_user_mail_profile(int(user_id), require_password=True)
        account = self._create_account(
            email=profile["email"],
            login=profile["login"],
            password=profile["password"],
        )
        folder_obj, folder_key = self._resolve_folder(account, folder_key)
        try:
            item = folder_obj.get(id=exchange_id)
        except Exception as exc:
            raise MailServiceError(f"Message not found: {exchange_id}") from exc

        received = getattr(item, "datetime_received", None) or getattr(item, "datetime_created", None)
        received_iso = received.isoformat() if received else None
        body_html = _normalize_text(getattr(item, "body", None))
        recipients = self._item_recipients(item)
        cc_values = getattr(item, "cc_recipients", None) or []
        cc = [
            _normalize_text(getattr(rec, "email_address", None)).lower()
            for rec in cc_values
            if _normalize_text(getattr(rec, "email_address", None))
        ]
        attachments = []
        for att in (getattr(item, "attachments", None) or []):
            attachment_raw_id = _normalize_text(getattr(getattr(att, "attachment_id", None), "id", ""))
            attachments.append(
                {
                    "id": attachment_raw_id,
                    "download_token": self._encode_attachment_token(attachment_raw_id),
                    "name": _normalize_text(getattr(att, "name", "attachment.bin")),
                    "content_type": _normalize_text(getattr(att, "content_type", "")),
                    "size": int(getattr(att, "size", 0) or 0),
                }
            )

        return {
            "id": self._encode_message_id(folder_key, exchange_id),
            "exchange_id": exchange_id,
            "folder": folder_key,
            "subject": _normalize_text(getattr(item, "subject", "")),
            "sender": self._item_sender(item),
            "to": recipients,
            "cc": cc,
            "received_at": received_iso,
            "is_read": bool(getattr(item, "is_read", False)),
            "body_html": body_html,
            "attachments": attachments,
        }

    def mark_as_read(self, *, user_id: int, message_id: str) -> bool:
        """Mark a message as read in the Exchange server."""
        folder_key, exchange_id = self._decode_message_id(message_id)
        profile = self._resolve_user_mail_profile(int(user_id), require_password=True)
        account = self._create_account(
            email=profile["email"],
            login=profile["login"],
            password=profile["password"],
        )
        folder_obj, _ = self._resolve_folder(account, folder_key)
        try:
            item = folder_obj.get(id=exchange_id)
            if getattr(item, "is_read", None) is False:
                item.is_read = True
                item.save(update_fields=["is_read"])
            return True
        except Exception as exc:
            raise MailServiceError(f"Failed to mark message as read: {exc}") from exc

    def get_unread_count(self, *, user_id: int) -> int:
        """Get the total number of unread messages in the inbox."""
        try:
            profile = self._resolve_user_mail_profile(int(user_id), require_password=True)
            account = self._create_account(
                email=profile["email"],
                login=profile["login"],
                password=profile["password"],
            )
            return int(account.inbox.filter(is_read=False).count())
        except Exception:
            return 0

    def download_attachment(self, *, user_id: int, message_id: str, attachment_id: str) -> tuple[str, str, bytes]:
        folder_key, exchange_id = self._decode_message_id(message_id)
        profile = self._resolve_user_mail_profile(int(user_id), require_password=True)
        account = self._create_account(
            email=profile["email"],
            login=profile["login"],
            password=profile["password"],
        )
        folder_obj, _ = self._resolve_folder(account, folder_key)
        try:
            item = folder_obj.get(id=exchange_id)
        except Exception as exc:
            raise MailServiceError(f"Message not found: {exchange_id}") from exc

        try:
            from exchangelib.attachments import FileAttachment
            for att in getattr(item, "attachments", []) or []:
                att_id = _normalize_text(getattr(getattr(att, "attachment_id", None), "id", ""))
                if att_id == attachment_id:
                    if isinstance(att, FileAttachment):
                        content = att.content
                        if not content:
                            # Sometimes we need to download it explicitly if not pre-fetched
                            account.protocol.get_attachments([att])
                            content = att.content
                        return (
                            _normalize_text(getattr(att, "name", "attachment.bin")),
                            _normalize_text(getattr(att, "content_type", "application/octet-stream")),
                            content or b"",
                        )
            raise MailServiceError(f"Attachment not found: {attachment_id}")
        except Exception as exc:
            raise MailServiceError(f"Failed to download attachment: {exc}") from exc

    def _log_message(
        self,
        *,
        message_id: str,
        user_id: int,
        username: str,
        direction: str,
        folder_hint: str,
        subject: str,
        recipients: list[str],
        status: str,
        exchange_item_id: Optional[str] = None,
        error_text: Optional[str] = None,
    ) -> None:
        self._maybe_cleanup_message_log()
        with self._lock, self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self._LOG_TABLE}
                (id, user_id, username, direction, folder_hint, subject, recipients_json, sent_at, status, exchange_item_id, error_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _normalize_text(message_id),
                    int(user_id),
                    _normalize_text(username),
                    _normalize_text(direction, "outgoing"),
                    _normalize_text(folder_hint),
                    _normalize_text(subject),
                    json.dumps(recipients or [], ensure_ascii=False),
                    _utc_now_iso(),
                    _normalize_text(status, "sent"),
                    _normalize_text(exchange_item_id) or None,
                    _normalize_text(error_text) or None,
                ),
            )
            conn.commit()

    def send_message(
        self,
        *,
        user_id: int,
        to: list[str],
        subject: str,
        body: str,
        is_html: bool = True,
        attachments: list[tuple[str, bytes]] = None,
    ) -> dict[str, Any]:
        recipients = [item for item in _parse_recipients(";".join(to or [])) if item]
        if not recipients:
            raise MailServiceError("At least one recipient is required")
        safe_attachments = attachments or []
        self._validate_outgoing_attachments_dynamic(safe_attachments)

        profile = self._resolve_user_mail_profile(int(user_id), require_password=True)
        account = self._create_account(
            email=profile["email"],
            login=profile["login"],
            password=profile["password"],
        )

        message_id = _normalize_text(base64.urlsafe_b64encode(os.urandom(12)).decode("utf-8"))
        final_subject = _normalize_text(subject)
        final_body = _normalize_text(body)
        signature = _normalize_text(profile["signature"])
        if signature:
            separator = "<br><br>" if is_html else "\n\n"
            final_body = f"{final_body}{separator}{signature}" if final_body else signature

        try:
            from exchangelib import HTMLBody, Mailbox, Message
            from exchangelib.attachments import FileAttachment
        except Exception as exc:
            raise MailServiceError("exchangelib package is not installed") from exc

        try:
            to_recipients = [Mailbox(email_address=email) for email in recipients]
            body_payload = HTMLBody(final_body) if is_html else final_body
            msg = Message(
                account=account,
                folder=account.sent,
                subject=final_subject,
                body=body_payload,
                to_recipients=to_recipients,
            )
            
            if safe_attachments:
                for filename, content in safe_attachments:
                    att = FileAttachment(name=filename, content=content)
                    msg.attach(att)

            msg.send_and_save()
            self._log_message(
                message_id=message_id,
                user_id=int(profile["user"]["id"]),
                username=_normalize_text(profile["user"].get("username")),
                direction="outgoing",
                folder_hint="sent",
                subject=final_subject,
                recipients=recipients,
                status="sent",
                exchange_item_id=_normalize_text(getattr(msg, "id", "")) or None,
            )
            return {
                "ok": True,
                "message_id": message_id,
                "subject": final_subject,
                "recipients": recipients,
            }
        except Exception as exc:
            self._log_message(
                message_id=message_id,
                user_id=int(profile["user"]["id"]),
                username=_normalize_text(profile["user"].get("username")),
                direction="outgoing",
                folder_hint="sent",
                subject=final_subject,
                recipients=recipients,
                status="failed",
                error_text=str(exc),
            )
            raise MailServiceError(f"Failed to send message: {exc}") from exc

    @classmethod
    def _normalize_field_options(cls, value: Any) -> list[str]:
        if value is None:
            return []
        raw_options: list[Any]
        if isinstance(value, str):
            raw_options = [part for part in re.split(r"[;\n]+", value) if _normalize_text(part)]
        elif isinstance(value, list):
            raw_options = value
        else:
            raise MailServiceError("Template field options must be an array or string")

        normalized: list[str] = []
        seen: set[str] = set()
        for item in raw_options:
            if isinstance(item, dict):
                option_value = _normalize_text(item.get("value") or item.get("label"))
            else:
                option_value = _normalize_text(item)
            if not option_value:
                continue
            if option_value in seen:
                continue
            seen.add(option_value)
            normalized.append(option_value)
        return normalized

    @classmethod
    def _normalize_template_field(cls, raw_field: Any, index: int = 0) -> dict[str, Any]:
        if not isinstance(raw_field, dict):
            raise MailServiceError("Each template field must be an object")
        key = _normalize_text(raw_field.get("key")).lower()
        key = re.sub(r"[^a-z0-9_.-]", "_", key)
        key = re.sub(r"_+", "_", key).strip("_")
        if not key:
            raise MailServiceError("Template field key is required")

        field_type = _normalize_text(raw_field.get("type"), "text").lower()
        if field_type not in cls._FIELD_TYPES:
            raise MailServiceError(f"Unsupported template field type: {field_type}")

        label = _normalize_text(raw_field.get("label"), key)
        placeholder = _normalize_text(raw_field.get("placeholder"))
        help_text = _normalize_text(raw_field.get("help_text"))
        default_value = raw_field.get("default_value")
        required = bool(raw_field.get("required", True))
        try:
            order = int(raw_field.get("order", index))
        except Exception:
            order = index
        options = cls._normalize_field_options(raw_field.get("options"))
        if field_type in {"select", "multiselect"} and not options:
            raise MailServiceError(f"Field '{key}' requires non-empty options")
        if field_type not in {"select", "multiselect"}:
            options = []

        if field_type == "checkbox":
            default_normalized: Any = bool(default_value)
        elif field_type == "multiselect":
            if isinstance(default_value, list):
                default_normalized = [item for item in cls._normalize_field_options(default_value) if item in options]
            else:
                default_normalized = []
        else:
            default_normalized = _normalize_text(default_value)

        return {
            "key": key,
            "label": label,
            "type": field_type,
            "required": required,
            "placeholder": placeholder,
            "help_text": help_text,
            "default_value": default_normalized,
            "options": options,
            "order": order,
        }

    @classmethod
    def _normalize_template_fields(cls, raw_fields: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_fields, list):
            raise MailServiceError("Template fields must be an array")
        normalized = [cls._normalize_template_field(item, idx) for idx, item in enumerate(raw_fields)]
        normalized.sort(key=lambda item: int(item.get("order", 0)))
        return normalized

    @classmethod
    def _parse_template_fields_json(cls, raw_json: str) -> list[dict[str, Any]]:
        try:
            loaded = json.loads(raw_json or "[]")
        except Exception as exc:
            raise MailServiceError("Template fields JSON is invalid") from exc
        return cls._normalize_template_fields(loaded)

    def _migrate_legacy_template_fields(self) -> None:
        migrated_count = 0
        deactivated_count = 0
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT id, required_fields_json, is_active FROM {self._TEMPLATES_TABLE}"
            ).fetchall()
            for row in rows:
                template_id = _normalize_text(row["id"])
                raw = _normalize_text(row["required_fields_json"], "[]")
                try:
                    loaded = json.loads(raw or "[]")
                except Exception:
                    conn.execute(
                        f"UPDATE {self._TEMPLATES_TABLE} SET is_active = 0, updated_at = ? WHERE id = ?",
                        (_utc_now_iso(), template_id),
                    )
                    deactivated_count += 1
                    logger.warning("Template %s disabled during migration: invalid fields JSON", template_id)
                    continue

                if not isinstance(loaded, list):
                    conn.execute(
                        f"UPDATE {self._TEMPLATES_TABLE} SET is_active = 0, updated_at = ? WHERE id = ?",
                        (_utc_now_iso(), template_id),
                    )
                    deactivated_count += 1
                    logger.warning("Template %s disabled during migration: fields payload is not an array", template_id)
                    continue

                is_new_schema = all(isinstance(item, dict) and _normalize_text(item.get("type")) for item in loaded)
                try:
                    if is_new_schema:
                        normalized = self._normalize_template_fields(loaded)
                    else:
                        converted = []
                        for index, item in enumerate(loaded):
                            if not isinstance(item, dict):
                                raise MailServiceError("Legacy field entry must be an object")
                            converted.append(
                                {
                                    "key": _normalize_text(item.get("key")).lower(),
                                    "label": _normalize_text(item.get("label")),
                                    "type": "text",
                                    "required": bool(item.get("required", True)),
                                    "placeholder": _normalize_text(item.get("placeholder")),
                                    "help_text": "",
                                    "default_value": "",
                                    "options": [],
                                    "order": index,
                                }
                            )
                        normalized = self._normalize_template_fields(converted)
                    serialized = json.dumps(normalized, ensure_ascii=False)
                    if serialized != raw:
                        conn.execute(
                            f"UPDATE {self._TEMPLATES_TABLE} SET required_fields_json = ?, updated_at = ? WHERE id = ?",
                            (serialized, _utc_now_iso(), template_id),
                        )
                        migrated_count += 1
                except Exception as exc:
                    conn.execute(
                        f"UPDATE {self._TEMPLATES_TABLE} SET is_active = 0, updated_at = ? WHERE id = ?",
                        (_utc_now_iso(), template_id),
                    )
                    deactivated_count += 1
                    logger.warning("Template %s disabled during migration: %s", template_id, exc)
            conn.commit()

        if migrated_count or deactivated_count:
            logger.info(
                "IT template migration completed: migrated=%s deactivated=%s",
                migrated_count,
                deactivated_count,
            )

    @staticmethod
    def _value_to_template_string(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(_normalize_text(item) for item in value if _normalize_text(item))
        if isinstance(value, bool):
            return "Да" if value else "Нет"
        return _normalize_text(value)

    @classmethod
    def _render_template(cls, text: str, values: dict[str, Any]) -> str:
        source = _normalize_text(text)

        def _replace(match: re.Match[str]) -> str:
            key = _normalize_text(match.group(1))
            return cls._value_to_template_string(values.get(key))

        return re.sub(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", _replace, source)

    @classmethod
    def _coerce_field_value(cls, field: dict[str, Any], raw_value: Any) -> Any:
        field_type = _normalize_text(field.get("type"), "text").lower()
        options = field.get("options") if isinstance(field.get("options"), list) else []
        default_value = field.get("default_value")
        value = raw_value if raw_value is not None else default_value

        if field_type == "checkbox":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"1", "true", "yes", "on", "да"}

        if field_type == "multiselect":
            if isinstance(value, list):
                values = [_normalize_text(item) for item in value]
            else:
                values = [part for part in re.split(r"[;,]+", _normalize_text(value)) if _normalize_text(part)]
            filtered: list[str] = []
            seen: set[str] = set()
            for item in values:
                if item in seen:
                    continue
                if options and item not in options:
                    continue
                seen.add(item)
                filtered.append(item)
            return filtered

        text = _normalize_text(value)
        if field_type == "select":
            if not text:
                return ""
            if options and text not in options:
                raise MailServiceError(f"Field '{field.get('key')}' has unsupported value")
            return text
        if field_type == "email":
            if text and not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", text):
                raise MailServiceError(f"Field '{field.get('key')}' must contain a valid email")
            return text
        if field_type == "tel":
            if text and not re.match(r"^[0-9+\-() ]{5,}$", text):
                raise MailServiceError(f"Field '{field.get('key')}' must contain a valid phone")
            return text
        if field_type == "date":
            if text and not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
                raise MailServiceError(f"Field '{field.get('key')}' must be in YYYY-MM-DD format")
            return text
        return text

    @classmethod
    def _validate_template_values(cls, template_fields: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any]:
        normalized_values: dict[str, Any] = {}
        missing: list[str] = []
        for field in template_fields:
            key = _normalize_text(field.get("key"))
            if not key:
                continue
            coerced = cls._coerce_field_value(field, values.get(key))
            normalized_values[key] = coerced

            if not bool(field.get("required", True)):
                continue
            field_type = _normalize_text(field.get("type"))
            if field_type == "checkbox":
                if coerced is not True:
                    missing.append(key)
                continue
            if field_type == "multiselect":
                if not isinstance(coerced, list) or len(coerced) == 0:
                    missing.append(key)
                continue
            if not _normalize_text(coerced):
                missing.append(key)

        if missing:
            raise MailServiceError(f"Missing required template fields: {', '.join(missing)}")
        return normalized_values

    @classmethod
    def _validate_attachments_limits(
        cls,
        attachments: list[tuple[str, bytes]],
        *,
        max_files: int,
        max_file_size: int,
        max_total_size: int,
    ) -> None:
        safe_attachments = attachments or []
        if len(safe_attachments) > int(max_files):
            raise MailPayloadTooLargeError(
                f"Too many attachments. Maximum is {int(max_files)}"
            )
        total_size = 0
        for filename, content in safe_attachments:
            size = len(content or b"")
            if size > int(max_file_size):
                raise MailPayloadTooLargeError(
                    f"Attachment '{_normalize_text(filename, 'attachment.bin')}' exceeds {int(max_file_size) // (1024 * 1024)}MB limit"
                )
            total_size += size
            if total_size > int(max_total_size):
                raise MailPayloadTooLargeError(
                    f"Total attachment size exceeds {int(max_total_size) // (1024 * 1024)}MB limit"
                )

    @classmethod
    def _validate_it_attachments(cls, attachments: list[tuple[str, bytes]]) -> None:
        cls._validate_attachments_limits(
            attachments,
            max_files=cls._MAX_IT_FILES,
            max_file_size=cls._MAX_IT_FILE_SIZE,
            max_total_size=cls._MAX_IT_TOTAL_SIZE,
        )

    @classmethod
    def _validate_outgoing_attachments(cls, attachments: list[tuple[str, bytes]]) -> None:
        cls._validate_attachments_limits(
            attachments,
            max_files=cls._MAX_MAIL_FILES,
            max_file_size=cls._MAX_MAIL_FILE_SIZE,
            max_total_size=cls._MAX_MAIL_TOTAL_SIZE,
        )

    def _validate_outgoing_attachments_dynamic(self, attachments: list[tuple[str, bytes]]) -> None:
        self._validate_attachments_limits(
            attachments,
            max_files=self.max_mail_files,
            max_file_size=self.max_mail_file_size,
            max_total_size=self.max_mail_total_size,
        )

    def search_contacts(self, user_id: int, q: str) -> list[dict[str, str]]:
        query = _normalize_text(q)
        if len(query) < 2:
            return []
        
        try:
            profile = self._resolve_user_mail_profile(user_id, require_password=True)
            account = self._create_account(
                email=profile["email"],
                login=profile["login"],
                password=profile["password"]
            )
            # resolve_names searches in GAL and personal contacts
            results = account.protocol.resolve_names(
                names=[query], 
                search_scope='ActiveDirectory', 
                return_full_contact_data=False
            )
            contacts = []
            for item in results:
                name = _normalize_text(item.name)
                email = _normalize_text(item.email_address)
                if email and {'name': name, 'email': email} not in contacts:
                    contacts.append({"name": name, "email": email})
            return contacts
        except Exception as exc:
            logger.warning("Error searching contacts in GAL (user_id=%s, q=%s): %s", user_id, query, exc)
            raise MailServiceError(f"Failed to search contacts: {exc}") from exc

    def list_templates(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        where_sql = "WHERE is_active = 1" if active_only else ""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM {self._TEMPLATES_TABLE}
                {where_sql}
                ORDER BY updated_at DESC, title COLLATE NOCASE
                """
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["fields"] = self._parse_template_fields_json(item.get("required_fields_json") or "[]")
            except MailServiceError:
                item["fields"] = []
            result.append(item)
        return result

    def get_template(self, template_id: str, *, active_only: bool = False) -> Optional[dict[str, Any]]:
        normalized_id = _normalize_text(template_id)
        if not normalized_id:
            return None
        sql = f"SELECT * FROM {self._TEMPLATES_TABLE} WHERE id = ?"
        params: list[Any] = [normalized_id]
        if active_only:
            sql += " AND is_active = 1"
        with self._lock, self._connect() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["fields"] = self._parse_template_fields_json(item.get("required_fields_json") or "[]")
        except MailServiceError:
            item["fields"] = []
        return item

    def create_template(self, *, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        if "required_fields" in payload:
            raise MailServiceError("required_fields is no longer supported. Use fields")
        template_id = _normalize_text(payload.get("id")) or base64.urlsafe_b64encode(os.urandom(9)).decode("utf-8")
        code = _normalize_text(payload.get("code")).lower()
        title = _normalize_text(payload.get("title"))
        subject_template = _normalize_text(payload.get("subject_template"))
        body_template_md = _normalize_text(payload.get("body_template_md"))
        category = _normalize_text(payload.get("category"))
        template_fields = self._normalize_template_fields(payload.get("fields") or [])
        if not code:
            raise MailServiceError("Template code is required")
        if not title:
            raise MailServiceError("Template title is required")
        if not subject_template:
            raise MailServiceError("Template subject is required")
        now = _utc_now_iso()

        with self._lock, self._connect() as conn:
            exists = conn.execute(
                f"SELECT id FROM {self._TEMPLATES_TABLE} WHERE code = ?",
                (code,),
            ).fetchone()
            if exists is not None:
                raise MailServiceError(f"Template code already exists: {code}")
            conn.execute(
                f"""
                INSERT INTO {self._TEMPLATES_TABLE}
                (id, code, title, category, subject_template, body_template_md, required_fields_json, is_active,
                 created_by_user_id, created_by_username, updated_by_user_id, updated_by_username, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template_id,
                    code,
                    title,
                    category,
                    subject_template,
                    body_template_md,
                    json.dumps(template_fields, ensure_ascii=False),
                    int(actor.get("id") or 0),
                    _normalize_text(actor.get("username")),
                    int(actor.get("id") or 0),
                    _normalize_text(actor.get("username")),
                    now,
                    now,
                ),
            )
            conn.commit()
        created = self.get_template(template_id)
        if not created:
            raise MailServiceError("Template was not created")
        return created

    def update_template(self, *, template_id: str, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        current = self.get_template(template_id, active_only=False)
        if current is None:
            raise MailServiceError("Template not found")
        if "required_fields" in payload:
            raise MailServiceError("required_fields is no longer supported. Use fields")
        fields: list[str] = []
        params: list[Any] = []

        if "code" in payload:
            code = _normalize_text(payload.get("code")).lower()
            if not code:
                raise MailServiceError("Template code cannot be empty")
            fields.append("code = ?")
            params.append(code)
        if "title" in payload:
            title = _normalize_text(payload.get("title"))
            if not title:
                raise MailServiceError("Template title cannot be empty")
            fields.append("title = ?")
            params.append(title)
        if "category" in payload:
            fields.append("category = ?")
            params.append(_normalize_text(payload.get("category")))
        if "subject_template" in payload:
            subject_template = _normalize_text(payload.get("subject_template"))
            if not subject_template:
                raise MailServiceError("Template subject cannot be empty")
            fields.append("subject_template = ?")
            params.append(subject_template)
        if "body_template_md" in payload:
            fields.append("body_template_md = ?")
            params.append(_normalize_text(payload.get("body_template_md")))
        if "fields" in payload:
            template_fields = self._normalize_template_fields(payload.get("fields") or [])
            fields.append("required_fields_json = ?")
            params.append(json.dumps(template_fields, ensure_ascii=False))
        if "is_active" in payload:
            fields.append("is_active = ?")
            params.append(1 if bool(payload.get("is_active")) else 0)

        if not fields:
            return current
        fields.extend(["updated_by_user_id = ?", "updated_by_username = ?", "updated_at = ?"])
        params.extend([int(actor.get("id") or 0), _normalize_text(actor.get("username")), _utc_now_iso()])
        params.append(_normalize_text(template_id))

        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE {self._TEMPLATES_TABLE} SET {', '.join(fields)} WHERE id = ?",
                tuple(params),
            )
            conn.commit()
        updated = self.get_template(template_id, active_only=False)
        if updated is None:
            raise MailServiceError("Template not found after update")
        return updated

    def delete_template(self, *, template_id: str, actor: dict[str, Any]) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT id FROM {self._TEMPLATES_TABLE} WHERE id = ?", (_normalize_text(template_id),)).fetchone()
            if row is None:
                return False
            conn.execute(
                f"""
                UPDATE {self._TEMPLATES_TABLE}
                SET is_active = 0, updated_by_user_id = ?, updated_by_username = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    int(actor.get("id") or 0),
                    _normalize_text(actor.get("username")),
                    _utc_now_iso(),
                    _normalize_text(template_id),
                ),
            )
            conn.commit()
        return True

    def get_my_config(self, *, user_id: int) -> dict[str, Any]:
        user = user_service.get_by_id(int(user_id))
        if not user:
            raise MailServiceError("User not found")
        mailbox_email = _normalize_text(user.get("mailbox_email") or user.get("email")) or None
        mailbox_login = _normalize_text(user.get("mailbox_login") or mailbox_email) or None
        signature = _normalize_text(user.get("mail_signature_html")) or None
        password_enc = _normalize_text(user.get("mailbox_password_enc"))
        return {
            "user_id": int(user.get("id") or 0),
            "username": _normalize_text(user.get("username")),
            "mailbox_email": mailbox_email,
            "mailbox_login": mailbox_login,
            "mail_signature_html": signature,
            "mail_is_configured": bool(mailbox_email and mailbox_login and password_enc),
            "mail_updated_at": _normalize_text(user.get("mail_updated_at")) or None,
        }

    def update_user_config(
        self,
        *,
        user_id: int,
        mailbox_email: Optional[str] | object = _UNSET,
        mailbox_login: Optional[str] | object = _UNSET,
        mailbox_password: Optional[str] | object = _UNSET,
        mail_signature_html: Optional[str] | object = _UNSET,
    ) -> dict[str, Any]:
        update_payload: dict[str, Any] = {}
        if mailbox_email is not _UNSET:
            update_payload["mailbox_email"] = mailbox_email
        if mailbox_login is not _UNSET:
            update_payload["mailbox_login"] = mailbox_login
        if mailbox_password is not _UNSET:
            update_payload["mailbox_password"] = mailbox_password
        if mail_signature_html is not _UNSET:
            update_payload["mail_signature_html"] = mail_signature_html
        updated = user_service.update_user(
            int(user_id),
            **update_payload,
        )
        if not updated:
            raise MailServiceError("User not found")
        return self.get_my_config(user_id=int(user_id))

    def test_connection(self, *, user_id: int) -> dict[str, Any]:
        profile = self._resolve_user_mail_profile(int(user_id), require_password=True)
        account = self._create_account(
            email=profile["email"],
            login=profile["login"],
            password=profile["password"],
        )
        inbox = account.inbox
        sample = list(inbox.all().order_by("-datetime_received")[:1])
        return {
            "ok": True,
            "exchange_host": self.exchange_host,
            "ews_url": self.exchange_ews_url,
            "mailbox_email": profile["email"],
            "sample_size": len(sample),
        }

    def send_it_request(
        self,
        *,
        user_id: int,
        template_id: str,
        fields: dict[str, Any],
        attachments: Optional[list[tuple[str, bytes]]] = None,
    ) -> dict[str, Any]:
        template = self.get_template(template_id, active_only=True)
        if template is None:
            raise MailServiceError("Template not found")

        recipients = list(self._IT_REQUEST_RECIPIENTS)

        user = user_service.get_by_id(int(user_id))
        if not user:
            raise MailServiceError("User not found")

        template_fields = template.get("fields") if isinstance(template.get("fields"), list) else []
        normalized_user_fields = self._validate_template_values(template_fields, fields or {})

        values = {
            "full_name": _normalize_text(user.get("full_name") or user.get("username")),
            "username": _normalize_text(user.get("username")),
            "mailbox_email": _normalize_text(user.get("mailbox_email") or user.get("email")),
            "date": datetime.now().strftime("%Y-%m-%d"),
            **normalized_user_fields,
        }

        subject = self._render_template(_normalize_text(template.get("subject_template")), values)
        body = self._render_template(_normalize_text(template.get("body_template_md")), values)
        body_html = _plain_text_to_html(body)
        safe_attachments = attachments or []
        self._validate_it_attachments(safe_attachments)

        return self.send_message(
            user_id=int(user_id),
            to=recipients,
            subject=subject,
            body=body_html,
            is_html=True,
            attachments=safe_attachments,
        )


mail_service = MailService()
