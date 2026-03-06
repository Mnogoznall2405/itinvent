"""
Hub service for dashboard announcements, tasks, and notifications.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Optional

from local_store import get_local_store
from backend.services.authorization_service import PERM_TASKS_REVIEW, authorization_service
from backend.services.user_service import user_service


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _safe_file_name(value: str) -> str:
    base = Path(str(value or "").strip()).name
    base = re.sub(r"[^A-Za-z0-9._\-\u0400-\u04FF ]+", "_", base)
    return base.strip() or "file.bin"


class HubService:
    _ANN_TABLE = "hub_announcements"
    _ANN_READS_TABLE = "hub_announcement_reads"
    _ANN_ATTACH_TABLE = "hub_announcement_attachments"
    _TASKS_TABLE = "hub_tasks"
    _TASK_REPORTS_TABLE = "hub_task_reports"
    _TASK_ATTACH_TABLE = "hub_task_attachments"
    _NOTIF_TABLE = "hub_notifications"
    _NOTIF_READS_TABLE = "hub_notification_reads"

    def __init__(self) -> None:
        self.store = get_local_store()
        self.db_path = Path(self.store.db_path)
        self.data_dir = Path(self.store.data_dir)
        self.announcement_attachments_root = self.data_dir / "hub_announcement_attachments"
        self.task_attachments_root = self.data_dir / "hub_task_attachments"
        self.announcement_attachments_root.mkdir(parents=True, exist_ok=True)
        self.task_attachments_root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _table_columns(self, conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row["name"]) for row in rows}

    def _user_can_review_tasks(self, user: dict[str, Any]) -> bool:
        if not bool(user.get("is_active", True)):
            return False
        return authorization_service.has_permission(
            user.get("role"),
            PERM_TASKS_REVIEW,
            use_custom_permissions=bool(user.get("use_custom_permissions", False)),
            custom_permissions=user.get("custom_permissions", []),
        )

    def _ensure_task_controller_columns(self, conn: sqlite3.Connection) -> None:
        columns = self._table_columns(conn, self._TASKS_TABLE)
        if "controller_user_id" not in columns:
            conn.execute(
                f"ALTER TABLE {self._TASKS_TABLE} ADD COLUMN controller_user_id INTEGER NOT NULL DEFAULT 0"
            )
        if "controller_username" not in columns:
            conn.execute(
                f"ALTER TABLE {self._TASKS_TABLE} ADD COLUMN controller_username TEXT NOT NULL DEFAULT ''"
            )
        if "controller_full_name" not in columns:
            conn.execute(
                f"ALTER TABLE {self._TASKS_TABLE} ADD COLUMN controller_full_name TEXT NOT NULL DEFAULT ''"
            )
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self._TASKS_TABLE}_controller
                ON {self._TASKS_TABLE}(controller_user_id, status, updated_at DESC)
            """
        )
        self._backfill_task_controllers(conn)

    def _backfill_task_controllers(self, conn: sqlite3.Connection) -> None:
        users = user_service.list_users()
        users_by_id = {self._as_int(user.get("id")): user for user in users}
        review_candidates = [user for user in users if self._user_can_review_tasks(user)]
        default_reviewer = review_candidates[0] if review_candidates else None

        rows = conn.execute(
            f"""
            SELECT id, created_by_user_id, controller_user_id, controller_username, controller_full_name
            FROM {self._TASKS_TABLE}
            """
        ).fetchall()

        for row in rows:
            row_dict = dict(row)
            current_id = self._as_int(row_dict.get("controller_user_id"))
            current_username = _normalize_text(row_dict.get("controller_username"))
            current_full_name = _normalize_text(row_dict.get("controller_full_name"))
            current_user = users_by_id.get(current_id)
            if current_id > 0 and current_user and bool(current_user.get("is_active", True)) and current_username:
                continue

            created_by_id = self._as_int(row_dict.get("created_by_user_id"))
            creator_user = users_by_id.get(created_by_id)
            chosen = None
            if creator_user and bool(creator_user.get("is_active", True)) and self._user_can_review_tasks(creator_user):
                chosen = creator_user
            elif default_reviewer:
                chosen = default_reviewer
            elif creator_user and bool(creator_user.get("is_active", True)):
                chosen = creator_user

            if chosen is None:
                continue

            conn.execute(
                f"""
                UPDATE {self._TASKS_TABLE}
                SET controller_user_id = ?, controller_username = ?, controller_full_name = ?
                WHERE id = ?
                """,
                (
                    self._as_int(chosen.get("id")),
                    _normalize_text(chosen.get("username")),
                    _normalize_text(chosen.get("full_name")) or _normalize_text(chosen.get("username")),
                    _normalize_text(row_dict.get("id")),
                ),
            )

    def _ensure_task_priority_column(self, conn: sqlite3.Connection) -> None:
        cols = self._table_columns(conn, self._TASKS_TABLE)
        if "priority" not in cols:
            conn.execute(f"ALTER TABLE {self._TASKS_TABLE} ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'")

    _TASK_COMMENTS_TABLE = "hub_task_comments"

    def _ensure_task_comments_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._TASK_COMMENTS_TABLE} (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                full_name TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self._TASK_COMMENTS_TABLE}_task
                ON {self._TASK_COMMENTS_TABLE}(task_id, created_at ASC)
        """)

    def _ensure_task_status_log_table(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hub_task_status_log (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                old_status TEXT NOT NULL DEFAULT '',
                new_status TEXT NOT NULL DEFAULT '',
                changed_by_user_id INTEGER NOT NULL,
                changed_by_username TEXT NOT NULL DEFAULT '',
                changed_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hub_task_status_log_task
                ON hub_task_status_log(task_id, changed_at ASC)
        """)

    def _log_status_change(self, conn: sqlite3.Connection, *, task_id: str, old_status: str, new_status: str, user_id: int, username: str) -> None:
        import uuid as _uuid
        now_iso = _utc_now_iso()
        conn.execute(
            "INSERT INTO hub_task_status_log (id, task_id, old_status, new_status, changed_by_user_id, changed_by_username, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(_uuid.uuid4()), task_id, old_status, new_status, user_id, username, now_iso),
        )

    def list_task_comments(self, task_id: str) -> list[dict[str, Any]]:
        normalized_id = _normalize_text(task_id)
        if not normalized_id:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self._TASK_COMMENTS_TABLE} WHERE task_id = ? ORDER BY created_at ASC",
                (normalized_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_task_comment(self, *, task_id: str, user: dict[str, Any], body: str) -> Optional[dict[str, Any]]:
        normalized_id = _normalize_text(task_id)
        body_text = _normalize_text(body)
        if not normalized_id or not body_text:
            return None
        user_id = self._as_int(user.get("id"))
        now_iso = _utc_now_iso()
        comment_id = str(uuid.uuid4())
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT id FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            if row is None:
                return None
            conn.execute(
                f"INSERT INTO {self._TASK_COMMENTS_TABLE} (id, task_id, user_id, username, full_name, body, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (comment_id, normalized_id, user_id, _normalize_text(user.get("username")), _normalize_text(user.get("full_name")), body_text, now_iso),
            )
            conn.execute(f"UPDATE {self._TASKS_TABLE} SET updated_at = ? WHERE id = ?", (now_iso, normalized_id))
            conn.commit()
            created = conn.execute(f"SELECT * FROM {self._TASK_COMMENTS_TABLE} WHERE id = ?", (comment_id,)).fetchone()
            return dict(created) if created else None

    def list_task_status_log(self, task_id: str) -> list[dict[str, Any]]:
        normalized_id = _normalize_text(task_id)
        if not normalized_id:
            return []
        with self._lock, self._connect() as conn:
            self._ensure_task_status_log_table(conn)
            rows = conn.execute(
                "SELECT * FROM hub_task_status_log WHERE task_id = ? ORDER BY changed_at ASC",
                (normalized_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {self._ANN_TABLE} (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    preview TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    author_user_id INTEGER NOT NULL DEFAULT 0,
                    author_username TEXT NOT NULL DEFAULT '',
                    author_full_name TEXT NOT NULL DEFAULT '',
                    published_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {self._ANN_READS_TABLE} (
                    announcement_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL DEFAULT '',
                    full_name TEXT NOT NULL DEFAULT '',
                    read_at TEXT NOT NULL,
                    PRIMARY KEY (announcement_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS {self._ANN_ATTACH_TABLE} (
                    id TEXT PRIMARY KEY,
                    announcement_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_mime TEXT NULL,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    uploaded_by_user_id INTEGER NOT NULL,
                    uploaded_by_username TEXT NOT NULL DEFAULT '',
                    uploaded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {self._TASKS_TABLE} (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'new',
                    due_at TEXT NULL,
                    assignee_user_id INTEGER NOT NULL,
                    assignee_username TEXT NOT NULL DEFAULT '',
                    assignee_full_name TEXT NOT NULL DEFAULT '',
                    controller_user_id INTEGER NOT NULL DEFAULT 0,
                    controller_username TEXT NOT NULL DEFAULT '',
                    controller_full_name TEXT NOT NULL DEFAULT '',
                    created_by_user_id INTEGER NOT NULL,
                    created_by_username TEXT NOT NULL DEFAULT '',
                    created_by_full_name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    submitted_at TEXT NULL,
                    reviewed_at TEXT NULL,
                    reviewer_user_id INTEGER NULL,
                    reviewer_username TEXT NULL,
                    review_comment TEXT NULL,
                    priority TEXT NOT NULL DEFAULT 'normal'
                );
                CREATE TABLE IF NOT EXISTS {self._TASK_REPORTS_TABLE} (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    file_name TEXT NULL,
                    file_path TEXT NULL,
                    file_mime TEXT NULL,
                    file_size INTEGER NULL,
                    uploaded_by_user_id INTEGER NOT NULL,
                    uploaded_by_username TEXT NOT NULL DEFAULT '',
                    uploaded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {self._TASK_ATTACH_TABLE} (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'task',
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_mime TEXT NULL,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    uploaded_by_user_id INTEGER NOT NULL,
                    uploaded_by_username TEXT NOT NULL DEFAULT '',
                    uploaded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {self._NOTIF_TABLE} (
                    id TEXT PRIMARY KEY,
                    recipient_user_id INTEGER NULL,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    entity_type TEXT NOT NULL DEFAULT '',
                    entity_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {self._NOTIF_READS_TABLE} (
                    notification_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    read_at TEXT NOT NULL,
                    PRIMARY KEY (notification_id, user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_{self._ANN_TABLE}_published
                    ON {self._ANN_TABLE}(is_active, published_at DESC);
                CREATE INDEX IF NOT EXISTS idx_{self._ANN_ATTACH_TABLE}_announcement
                    ON {self._ANN_ATTACH_TABLE}(announcement_id, uploaded_at DESC);
                CREATE INDEX IF NOT EXISTS idx_{self._TASKS_TABLE}_assignee
                    ON {self._TASKS_TABLE}(assignee_user_id, status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_{self._TASK_ATTACH_TABLE}_task
                    ON {self._TASK_ATTACH_TABLE}(task_id, uploaded_at DESC);
                CREATE INDEX IF NOT EXISTS idx_{self._NOTIF_TABLE}_recipient
                    ON {self._NOTIF_TABLE}(recipient_user_id, created_at DESC);
                """
            )
            self._ensure_task_controller_columns(conn)
            self._ensure_task_priority_column(conn)
            self._ensure_task_comments_table(conn)
            conn.commit()

    @staticmethod
    def _as_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    @staticmethod
    def _coerce_limit(value: Any, *, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = default
        return max(minimum, min(maximum, parsed))

    @staticmethod
    def _parse_iso_datetime(value: Any) -> Optional[datetime]:
        text = _normalize_text(value)
        if not text:
            return None
        candidate = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except Exception:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _is_task_overdue(due_at: Any, status: Any) -> bool:
        if _normalize_text(status).lower() == "done":
            return False
        parsed_due = HubService._parse_iso_datetime(due_at)
        if parsed_due is None:
            return False
        return parsed_due < datetime.now(timezone.utc)

    @staticmethod
    def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
        if row is None:
            return None
        return {key: row[key] for key in row.keys()}

    @staticmethod
    def _attachment_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["file_size"] = HubService._as_int(item.get("file_size"))
        item["scope"] = _normalize_text(item.get("scope"))
        return item

    def _store_attachment_file(
        self,
        *,
        root: Path,
        parent_id: str,
        attachment_id: str,
        file_name: str,
        file_bytes: bytes,
    ) -> tuple[str, str, int]:
        safe_name = _safe_file_name(file_name or "file.bin")
        parent_dir = root / parent_id
        parent_dir.mkdir(parents=True, exist_ok=True)
        full_path = parent_dir / f"{attachment_id}_{safe_name}"
        full_path.write_bytes(file_bytes or b"")
        rel_path = str(full_path.relative_to(self.data_dir)).replace("\\", "/")
        return safe_name, rel_path, len(file_bytes or b"")

    def _remove_relative_files(self, rel_paths: list[str]) -> None:
        for rel_path in rel_paths:
            normalized_rel = _normalize_text(rel_path)
            if not normalized_rel:
                continue
            abs_path = (self.data_dir / normalized_rel).resolve()
            try:
                abs_path.relative_to(self.data_dir.resolve())
            except Exception:
                continue
            try:
                if abs_path.exists() and abs_path.is_file():
                    abs_path.unlink()
            except Exception:
                continue

    @staticmethod
    def _remove_dir_quiet(path: Path) -> None:
        try:
            if path.exists() and path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            return

    def _list_announcement_attachments(self, conn: sqlite3.Connection, announcement_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"""
            SELECT id, announcement_id, file_name, file_mime, file_size, uploaded_by_user_id, uploaded_by_username, uploaded_at
            FROM {self._ANN_ATTACH_TABLE}
            WHERE announcement_id = ?
            ORDER BY uploaded_at DESC
            """,
            (announcement_id,),
        ).fetchall()
        return [self._attachment_row_to_dict(row) for row in rows]

    def _list_task_attachments(self, conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"""
            SELECT id, task_id, scope, file_name, file_mime, file_size, uploaded_by_user_id, uploaded_by_username, uploaded_at
            FROM {self._TASK_ATTACH_TABLE}
            WHERE task_id = ?
            ORDER BY uploaded_at DESC
            """,
            (task_id,),
        ).fetchall()
        return [self._attachment_row_to_dict(row) for row in rows]

    def _insert_task_attachment(
        self,
        *,
        conn: sqlite3.Connection,
        attachment_id: Optional[str] = None,
        task_id: str,
        scope: str,
        file_name: str,
        file_path: str,
        file_mime: Optional[str],
        file_size: int,
        user_id: int,
        username: str,
        uploaded_at: str,
    ) -> str:
        normalized_attachment_id = _normalize_text(attachment_id) or str(uuid.uuid4())
        conn.execute(
            f"""
            INSERT INTO {self._TASK_ATTACH_TABLE}
            (id, task_id, scope, file_name, file_path, file_mime, file_size, uploaded_by_user_id, uploaded_by_username, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_attachment_id,
                task_id,
                _normalize_text(scope, "task"),
                _normalize_text(file_name, "file.bin"),
                _normalize_text(file_path),
                _normalize_text(file_mime),
                self._as_int(file_size),
                self._as_int(user_id),
                _normalize_text(username),
                uploaded_at,
            ),
        )
        return normalized_attachment_id

    def _create_notification(
        self,
        *,
        recipient_user_id: Optional[int],
        event_type: str,
        title: str,
        body: str = "",
        entity_type: str = "",
        entity_id: str = "",
        conn: Optional[sqlite3.Connection] = None,
    ) -> str:
        now_iso = _utc_now_iso()
        notification_id = str(uuid.uuid4())
        row = (
            notification_id,
            recipient_user_id,
            _normalize_text(event_type),
            _normalize_text(title),
            _normalize_text(body),
            _normalize_text(entity_type),
            _normalize_text(entity_id),
            now_iso,
        )
        if conn is None:
            with self._lock, self._connect() as local_conn:
                local_conn.execute(
                    f"""
                    INSERT INTO {self._NOTIF_TABLE}
                    (id, recipient_user_id, event_type, title, body, entity_type, entity_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
                local_conn.commit()
        else:
            conn.execute(
                f"""
                INSERT INTO {self._NOTIF_TABLE}
                (id, recipient_user_id, event_type, title, body, entity_type, entity_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
        return notification_id

    def _task_with_latest_report(self, conn: sqlite3.Connection, task_row: sqlite3.Row) -> dict[str, Any]:
        item = dict(task_row)
        report = conn.execute(
            f"""
            SELECT id, comment, file_name, file_mime, file_size, uploaded_by_username, uploaded_at
            FROM {self._TASK_REPORTS_TABLE}
            WHERE task_id = ?
            ORDER BY uploaded_at DESC
            LIMIT 1
            """,
            (item["id"],),
        ).fetchone()
        item["latest_report"] = self._row_to_dict(report)
        item["attachments"] = self._list_task_attachments(conn, item["id"])
        return item

    def list_assignees(self) -> list[dict[str, Any]]:
        users = user_service.list_users()
        out: list[dict[str, Any]] = []
        for row in users:
            if not bool(row.get("is_active", True)):
                continue
            out.append(
                {
                    "id": self._as_int(row.get("id")),
                    "username": _normalize_text(row.get("username")),
                    "full_name": _normalize_text(row.get("full_name")) or _normalize_text(row.get("username")),
                    "role": _normalize_text(row.get("role"), "viewer"),
                }
            )
        out.sort(key=lambda item: (item.get("full_name") or "", item.get("username") or ""))
        return out

    def list_controllers(self) -> list[dict[str, Any]]:
        users = user_service.list_users()
        out: list[dict[str, Any]] = []
        for row in users:
            if not self._user_can_review_tasks(row):
                continue
            out.append(
                {
                    "id": self._as_int(row.get("id")),
                    "username": _normalize_text(row.get("username")),
                    "full_name": _normalize_text(row.get("full_name")) or _normalize_text(row.get("username")),
                    "role": _normalize_text(row.get("role"), "viewer"),
                }
            )
        out.sort(key=lambda item: (item.get("full_name") or "", item.get("username") or ""))
        return out

    def create_announcement(
        self,
        *,
        title: str,
        preview: str,
        body: str,
        priority: str,
        actor: dict[str, Any],
        attachments: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        now_iso = _utc_now_iso()
        ann_id = str(uuid.uuid4())
        title_text = _normalize_text(title)
        if len(title_text) < 3:
            raise ValueError("Announcement title must contain at least 3 characters")
        priority_text = _normalize_text(priority, "normal").lower()
        if priority_text not in {"low", "normal", "high"}:
            priority_text = "normal"
        attachment_payloads = attachments if isinstance(attachments, list) else []

        with self._lock, self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self._ANN_TABLE}
                (id, title, preview, body, priority, is_active, author_user_id, author_username, author_full_name, published_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    ann_id,
                    title_text,
                    _normalize_text(preview),
                    _normalize_text(body),
                    priority_text,
                    self._as_int(actor.get("id")),
                    _normalize_text(actor.get("username")),
                    _normalize_text(actor.get("full_name")),
                    now_iso,
                    now_iso,
                ),
            )
            for payload in attachment_payloads:
                file_bytes = payload.get("file_bytes")
                if not isinstance(file_bytes, (bytes, bytearray)) or len(file_bytes) == 0:
                    continue
                attachment_id = str(uuid.uuid4())
                safe_name, rel_path, file_size = self._store_attachment_file(
                    root=self.announcement_attachments_root,
                    parent_id=ann_id,
                    attachment_id=attachment_id,
                    file_name=_normalize_text(payload.get("file_name"), "file.bin"),
                    file_bytes=bytes(file_bytes),
                )
                conn.execute(
                    f"""
                    INSERT INTO {self._ANN_ATTACH_TABLE}
                    (id, announcement_id, file_name, file_path, file_mime, file_size, uploaded_by_user_id, uploaded_by_username, uploaded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attachment_id,
                        ann_id,
                        safe_name,
                        rel_path,
                        _normalize_text(payload.get("file_mime")),
                        file_size,
                        self._as_int(actor.get("id")),
                        _normalize_text(actor.get("username")),
                        now_iso,
                    ),
                )
            self._create_notification(
                recipient_user_id=None,
                event_type="announcement.new",
                title="Новое объявление",
                body=title_text,
                entity_type="announcement",
                entity_id=ann_id,
                conn=conn,
            )
            conn.commit()
            row = conn.execute(f"SELECT * FROM {self._ANN_TABLE} WHERE id = ?", (ann_id,)).fetchone()
            if row is None:
                return {}
            item = dict(row)
            item["attachments"] = self._list_announcement_attachments(conn, ann_id)
            return item

    def update_announcement(
        self,
        announcement_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: int,
    ) -> Optional[dict[str, Any]]:
        ann_id = _normalize_text(announcement_id)
        if not ann_id:
            return None
        actor_id = self._as_int(actor_user_id)
        allowed = {"title", "preview", "body", "priority", "is_active"}
        updates: list[str] = []
        params: list[Any] = []
        for key in allowed:
            if key not in payload:
                continue
            if key == "priority":
                value = _normalize_text(payload.get(key), "normal").lower()
                if value not in {"low", "normal", "high"}:
                    value = "normal"
            elif key == "is_active":
                value = 1 if bool(payload.get(key)) else 0
            else:
                value = _normalize_text(payload.get(key))
            updates.append(f"{key} = ?")
            params.append(value)
        if not updates:
            return self.get_announcement(ann_id)
        updates.append("updated_at = ?")
        params.append(_utc_now_iso())
        params.append(ann_id)
        with self._lock, self._connect() as conn:
            author_row = conn.execute(
                f"SELECT id, author_user_id FROM {self._ANN_TABLE} WHERE id = ?",
                (ann_id,),
            ).fetchone()
            if author_row is None:
                return None
            if self._as_int(author_row["author_user_id"]) != actor_id:
                raise PermissionError("Only announcement author can edit it")
            conn.execute(f"UPDATE {self._ANN_TABLE} SET {', '.join(updates)} WHERE id = ?", tuple(params))
            conn.commit()
            row = conn.execute(f"SELECT * FROM {self._ANN_TABLE} WHERE id = ?", (ann_id,)).fetchone()
            if row is None:
                return None
            item = dict(row)
            item["attachments"] = self._list_announcement_attachments(conn, ann_id)
            return item

    def get_announcement(self, announcement_id: str) -> Optional[dict[str, Any]]:
        ann_id = _normalize_text(announcement_id)
        if not ann_id:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT * FROM {self._ANN_TABLE} WHERE id = ?", (ann_id,)).fetchone()
            if row is None:
                return None
            item = dict(row)
            item["attachments"] = self._list_announcement_attachments(conn, ann_id)
            return item

    def delete_announcement(self, *, announcement_id: str, actor_user_id: int) -> bool:
        ann_id = _normalize_text(announcement_id)
        if not ann_id:
            return False
        actor_id = self._as_int(actor_user_id)
        attachment_paths: list[str] = []
        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"SELECT id, author_user_id FROM {self._ANN_TABLE} WHERE id = ?",
                (ann_id,),
            ).fetchone()
            if row is None:
                return False
            if self._as_int(row["author_user_id"]) != actor_id:
                raise PermissionError("Only announcement author can delete it")

            file_rows = conn.execute(
                f"SELECT file_path FROM {self._ANN_ATTACH_TABLE} WHERE announcement_id = ?",
                (ann_id,),
            ).fetchall()
            attachment_paths = [_normalize_text(item["file_path"]) for item in file_rows]

            notif_ids = conn.execute(
                f"SELECT id FROM {self._NOTIF_TABLE} WHERE entity_type = 'announcement' AND entity_id = ?",
                (ann_id,),
            ).fetchall()
            notif_id_values = [_normalize_text(item["id"]) for item in notif_ids if _normalize_text(item["id"])]
            if notif_id_values:
                placeholders = ", ".join(["?"] * len(notif_id_values))
                conn.execute(
                    f"DELETE FROM {self._NOTIF_READS_TABLE} WHERE notification_id IN ({placeholders})",
                    tuple(notif_id_values),
                )
            conn.execute(
                f"DELETE FROM {self._NOTIF_TABLE} WHERE entity_type = 'announcement' AND entity_id = ?",
                (ann_id,),
            )
            conn.execute(f"DELETE FROM {self._ANN_READS_TABLE} WHERE announcement_id = ?", (ann_id,))
            conn.execute(f"DELETE FROM {self._ANN_ATTACH_TABLE} WHERE announcement_id = ?", (ann_id,))
            conn.execute(f"DELETE FROM {self._ANN_TABLE} WHERE id = ?", (ann_id,))
            conn.commit()

        self._remove_relative_files(attachment_paths)
        self._remove_dir_quiet(self.announcement_attachments_root / ann_id)
        return True

    def list_announcements(
        self,
        *,
        user_id: int,
        limit: int = 30,
        offset: int = 0,
        q: str = "",
        priority: str = "",
        unread_only: bool = False,
        has_attachments: bool = False,
        sort_by: str = "published_at",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        safe_limit = self._coerce_limit(limit, default=30, minimum=1, maximum=300)
        safe_offset = max(0, self._as_int(offset, 0))
        query_text = _normalize_text(q).lower()
        query_terms = [term for term in query_text.split() if term]
        priority_value = _normalize_text(priority).lower()
        normalized_sort_by = _normalize_text(sort_by, "published_at").lower()
        normalized_sort_dir = "asc" if _normalize_text(sort_dir).lower() == "asc" else "desc"

        where_clauses: list[str] = ["a.is_active = 1"]
        params: list[Any] = [int(user_id)]
        if query_terms:
            for term in query_terms:
                where_clauses.append("(LOWER(a.title) LIKE ? OR LOWER(a.preview) LIKE ? OR LOWER(a.body) LIKE ?)")
                like = f"%{term}%"
                params.extend([like, like, like])
        if priority_value in {"low", "normal", "high"}:
            where_clauses.append("a.priority = ?")
            params.append(priority_value)
        if bool(unread_only):
            where_clauses.append("r.user_id IS NULL")
        if bool(has_attachments):
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM {self._ANN_ATTACH_TABLE} aa WHERE aa.announcement_id = a.id)"
            )

        sort_map = {
            "published_at": "a.published_at",
            "updated_at": "a.updated_at",
            "priority": "CASE a.priority WHEN 'high' THEN 3 WHEN 'normal' THEN 2 WHEN 'low' THEN 1 ELSE 0 END",
        }
        sort_expr = sort_map.get(normalized_sort_by, sort_map["published_at"])
        where_sql = " AND ".join(where_clauses)

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT a.*,
                       CASE WHEN r.user_id IS NULL THEN 1 ELSE 0 END AS unread,
                       (
                         SELECT COUNT(*) FROM {self._ANN_ATTACH_TABLE} aa
                         WHERE aa.announcement_id = a.id
                       ) AS attachments_count
                FROM {self._ANN_TABLE} a
                LEFT JOIN {self._ANN_READS_TABLE} r
                  ON r.announcement_id = a.id AND r.user_id = ?
                WHERE {where_sql}
                ORDER BY {sort_expr} {normalized_sort_dir}, a.published_at DESC
                LIMIT ? OFFSET ?
                """,
                tuple([*params, safe_limit, safe_offset]),
            ).fetchall()
            total = conn.execute(
                f"""
                SELECT COUNT(*) AS c
                FROM {self._ANN_TABLE} a
                LEFT JOIN {self._ANN_READS_TABLE} r
                  ON r.announcement_id = a.id AND r.user_id = ?
                WHERE {where_sql}
                """,
                tuple(params),
            ).fetchone()
            unread_total = conn.execute(
                f"""
                SELECT COUNT(*) AS c
                FROM {self._ANN_TABLE} a
                LEFT JOIN {self._ANN_READS_TABLE} r
                  ON r.announcement_id = a.id AND r.user_id = ?
                WHERE a.is_active = 1 AND r.user_id IS NULL
                """,
                (int(user_id),),
            ).fetchone()
            items: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["attachments_count"] = self._as_int(item.get("attachments_count"))
                item["attachments"] = self._list_announcement_attachments(conn, item["id"])
                items.append(item)
        return {
            "items": items,
            "total": self._as_int(total["c"] if total else 0),
            "unread_total": self._as_int(unread_total["c"] if unread_total else 0),
            "limit": safe_limit,
            "offset": safe_offset,
            "filters": {
                "q": query_text,
                "q_terms": query_terms,
                "priority": priority_value,
                "unread_only": bool(unread_only),
                "has_attachments": bool(has_attachments),
                "sort_by": normalized_sort_by,
                "sort_dir": normalized_sort_dir,
            },
        }

    def mark_announcement_read(self, *, announcement_id: str, user: dict[str, Any]) -> bool:
        ann_id = _normalize_text(announcement_id)
        if not ann_id:
            return False
        now_iso = _utc_now_iso()
        with self._lock, self._connect() as conn:
            ann = conn.execute(
                f"SELECT id FROM {self._ANN_TABLE} WHERE id = ? AND is_active = 1",
                (ann_id,),
            ).fetchone()
            if ann is None:
                return False
            conn.execute(
                f"""
                INSERT OR IGNORE INTO {self._ANN_READS_TABLE}
                (announcement_id, user_id, username, full_name, read_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ann_id,
                    self._as_int(user.get("id")),
                    _normalize_text(user.get("username")),
                    _normalize_text(user.get("full_name")),
                    now_iso,
                ),
            )
            conn.commit()
        return True

    def get_announcement_reads(self, announcement_id: str) -> list[dict[str, Any]]:
        ann_id = _normalize_text(announcement_id)
        if not ann_id:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT announcement_id, user_id, username, full_name, read_at
                FROM {self._ANN_READS_TABLE}
                WHERE announcement_id = ?
                ORDER BY read_at DESC
                """,
                (ann_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_announcement_attachment(self, *, announcement_id: str, attachment_id: str) -> Optional[dict[str, Any]]:
        ann_id = _normalize_text(announcement_id)
        normalized_attachment_id = _normalize_text(attachment_id)
        if not ann_id or not normalized_attachment_id:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT id, announcement_id, file_name, file_path, file_mime, file_size, uploaded_by_user_id, uploaded_by_username, uploaded_at
                FROM {self._ANN_ATTACH_TABLE}
                WHERE id = ? AND announcement_id = ?
                """,
                (normalized_attachment_id, ann_id),
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            rel_path = _normalize_text(item.get("file_path"))
            item["file_abs_path"] = str((self.data_dir / rel_path).resolve()) if rel_path else ""
            item["file_size"] = self._as_int(item.get("file_size"))
            return item

    def add_task_attachment(
        self,
        *,
        task_id: str,
        user: dict[str, Any],
        file_name: str,
        file_bytes: bytes,
        file_mime: Optional[str],
        can_review: bool = False,
    ) -> Optional[dict[str, Any]]:
        normalized_task_id = _normalize_text(task_id)
        if not normalized_task_id:
            return None
        payload = bytes(file_bytes or b"")
        if not payload:
            raise ValueError("Attachment payload is empty")

        user_id = self._as_int(user.get("id"))
        now_iso = _utc_now_iso()
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT * FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_task_id,)).fetchone()
            if row is None:
                return None
            task = dict(row)
            is_assignee = self._as_int(task.get("assignee_user_id")) == user_id
            is_creator = self._as_int(task.get("created_by_user_id")) == user_id
            is_controller = self._as_int(task.get("controller_user_id")) == user_id
            # Compatibility fallback for legacy tasks that might not have controller assigned yet.
            controller_missing = self._as_int(task.get("controller_user_id")) <= 0
            if not (is_assignee or is_creator or is_controller or (bool(can_review) and controller_missing)):
                raise PermissionError("Only assignee, creator, or reviewer can attach files")

            attachment_id = str(uuid.uuid4())
            safe_name, rel_path, file_size = self._store_attachment_file(
                root=self.task_attachments_root,
                parent_id=normalized_task_id,
                attachment_id=attachment_id,
                file_name=file_name,
                file_bytes=payload,
            )
            self._insert_task_attachment(
                conn=conn,
                attachment_id=attachment_id,
                task_id=normalized_task_id,
                scope="task",
                file_name=safe_name,
                file_path=rel_path,
                file_mime=file_mime,
                file_size=file_size,
                user_id=user_id,
                username=_normalize_text(user.get("username")),
                uploaded_at=now_iso,
            )
            conn.execute(
                f"UPDATE {self._TASKS_TABLE} SET updated_at = ? WHERE id = ?",
                (now_iso, normalized_task_id),
            )
            conn.commit()
            created_row = conn.execute(
                f"""
                SELECT id, task_id, scope, file_name, file_path, file_mime, file_size, uploaded_by_user_id, uploaded_by_username, uploaded_at
                FROM {self._TASK_ATTACH_TABLE}
                WHERE id = ?
                """,
                (attachment_id,),
            ).fetchone()
            return self._attachment_row_to_dict(created_row) if created_row else None

    def get_task_attachment(self, *, task_id: str, attachment_id: str) -> Optional[dict[str, Any]]:
        normalized_task_id = _normalize_text(task_id)
        normalized_attachment_id = _normalize_text(attachment_id)
        if not normalized_task_id or not normalized_attachment_id:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT id, task_id, scope, file_name, file_path, file_mime, file_size, uploaded_by_user_id, uploaded_by_username, uploaded_at
                FROM {self._TASK_ATTACH_TABLE}
                WHERE id = ? AND task_id = ?
                """,
                (normalized_attachment_id, normalized_task_id),
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            rel_path = _normalize_text(item.get("file_path"))
            item["file_abs_path"] = str((self.data_dir / rel_path).resolve()) if rel_path else ""
            item["file_size"] = self._as_int(item.get("file_size"))
            return item

    def create_task(
        self,
        *,
        title: str,
        description: str,
        assignee_user_id: int,
        controller_user_id: int,
        due_at: Optional[str],
        priority: Optional[str] = "normal",
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        title_text = _normalize_text(title)
        if len(title_text) < 3:
            raise ValueError("Task title must contain at least 3 characters")
        assignee = user_service.get_by_id(int(assignee_user_id))
        if not assignee or not bool(assignee.get("is_active", True)):
            raise ValueError("Assignee user is not available")
        controller = user_service.get_by_id(int(controller_user_id))
        if not controller or not bool(controller.get("is_active", True)):
            raise ValueError("Controller user is not available")
        if not self._user_can_review_tasks(controller):
            raise ValueError("Controller must have tasks.review permission")

        now_iso = _utc_now_iso()
        task_id = str(uuid.uuid4())
        with self._lock, self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self._TASKS_TABLE}
                (id, title, description, status, due_at, priority, assignee_user_id, assignee_username, assignee_full_name,
                 controller_user_id, controller_username, controller_full_name,
                 created_by_user_id, created_by_username, created_by_full_name, created_at, updated_at)
                VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    title_text,
                    _normalize_text(description),
                    _normalize_text(due_at) or None,
                    _normalize_text(priority) if priority else "normal",
                    self._as_int(assignee.get("id")),
                    _normalize_text(assignee.get("username")),
                    _normalize_text(assignee.get("full_name")) or _normalize_text(assignee.get("username")),
                    self._as_int(controller.get("id")),
                    _normalize_text(controller.get("username")),
                    _normalize_text(controller.get("full_name")) or _normalize_text(controller.get("username")),
                    self._as_int(actor.get("id")),
                    _normalize_text(actor.get("username")),
                    _normalize_text(actor.get("full_name")) or _normalize_text(actor.get("username")),
                    now_iso,
                    now_iso,
                ),
            )
            self._create_notification(
                recipient_user_id=self._as_int(assignee.get("id")),
                event_type="task.assigned",
                title="Новая задача",
                body=title_text,
                entity_type="task",
                entity_id=task_id,
                conn=conn,
            )
            self._create_notification(
                recipient_user_id=self._as_int(controller.get("id")),
                event_type="task.controller_assigned",
                title="Вы назначены контролером задачи",
                body=title_text,
                entity_type="task",
                entity_id=task_id,
                conn=conn,
            )
            conn.commit()
            row = conn.execute(f"SELECT * FROM {self._TASKS_TABLE} WHERE id = ?", (task_id,)).fetchone()
            return self._task_with_latest_report(conn, row) if row else {}

    def update_task(self, task_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        normalized_id = _normalize_text(task_id)
        if not normalized_id:
            return None
        updates: list[str] = []
        params: list[Any] = []
        for key in ("title", "description", "due_at", "priority", "assignee_user_id", "controller_user_id"):
            if key not in payload:
                continue
            if key == "assignee_user_id":
                assignee = user_service.get_by_id(int(payload.get(key)))
                if not assignee or not bool(assignee.get("is_active", True)):
                    raise ValueError("Assignee user is not available")
                updates.extend(["assignee_user_id = ?", "assignee_username = ?", "assignee_full_name = ?"])
                params.extend(
                    [
                        self._as_int(assignee.get("id")),
                        _normalize_text(assignee.get("username")),
                        _normalize_text(assignee.get("full_name")) or _normalize_text(assignee.get("username")),
                    ]
                )
            elif key == "controller_user_id":
                controller = user_service.get_by_id(int(payload.get(key)))
                if not controller or not bool(controller.get("is_active", True)):
                    raise ValueError("Controller user is not available")
                if not self._user_can_review_tasks(controller):
                    raise ValueError("Controller must have tasks.review permission")
                updates.extend(["controller_user_id = ?", "controller_username = ?", "controller_full_name = ?"])
                params.extend(
                    [
                        self._as_int(controller.get("id")),
                        _normalize_text(controller.get("username")),
                        _normalize_text(controller.get("full_name")) or _normalize_text(controller.get("username")),
                    ]
                )
            elif key == "due_at":
                updates.append("due_at = ?")
                params.append(_normalize_text(payload.get(key)) or None)
            elif key == "priority":
                pval = _normalize_text(payload.get(key), "normal").lower()
                if pval not in {"low", "normal", "high", "urgent"}:
                    pval = "normal"
                updates.append("priority = ?")
                params.append(pval)
            else:
                value = _normalize_text(payload.get(key))
                if key == "title" and len(value) < 3:
                    raise ValueError("Task title must contain at least 3 characters")
                updates.append(f"{key} = ?")
                params.append(value)
        if not updates:
            return self.get_task(normalized_id)
        updates.append("updated_at = ?")
        params.append(_utc_now_iso())
        params.append(normalized_id)
        with self._lock, self._connect() as conn:
            conn.execute(f"UPDATE {self._TASKS_TABLE} SET {', '.join(updates)} WHERE id = ?", tuple(params))
            conn.commit()
            row = conn.execute(f"SELECT * FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            return self._task_with_latest_report(conn, row) if row else None

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        normalized_id = _normalize_text(task_id)
        if not normalized_id:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT * FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            return self._task_with_latest_report(conn, row) if row else None

    def delete_task(self, *, task_id: str, actor_user_id: int, is_admin: bool = False) -> bool:
        normalized_id = _normalize_text(task_id)
        if not normalized_id:
            return False
        actor_id = self._as_int(actor_user_id)
        file_paths: list[str] = []
        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"SELECT id, created_by_user_id FROM {self._TASKS_TABLE} WHERE id = ?",
                (normalized_id,),
            ).fetchone()
            if row is None:
                return False
            if not is_admin and self._as_int(row["created_by_user_id"]) != actor_id:
                raise PermissionError("Only task creator or admin can delete it")

            task_attach_rows = conn.execute(
                f"SELECT file_path FROM {self._TASK_ATTACH_TABLE} WHERE task_id = ?",
                (normalized_id,),
            ).fetchall()
            task_report_rows = conn.execute(
                f"SELECT file_path FROM {self._TASK_REPORTS_TABLE} WHERE task_id = ?",
                (normalized_id,),
            ).fetchall()
            file_paths = [
                _normalize_text(item["file_path"])
                for item in [*task_attach_rows, *task_report_rows]
                if _normalize_text(item["file_path"])
            ]

            notif_ids = conn.execute(
                f"SELECT id FROM {self._NOTIF_TABLE} WHERE entity_type = 'task' AND entity_id = ?",
                (normalized_id,),
            ).fetchall()
            notif_id_values = [_normalize_text(item["id"]) for item in notif_ids if _normalize_text(item["id"])]
            if notif_id_values:
                placeholders = ", ".join(["?"] * len(notif_id_values))
                conn.execute(
                    f"DELETE FROM {self._NOTIF_READS_TABLE} WHERE notification_id IN ({placeholders})",
                    tuple(notif_id_values),
                )
            conn.execute(
                f"DELETE FROM {self._NOTIF_TABLE} WHERE entity_type = 'task' AND entity_id = ?",
                (normalized_id,),
            )
            conn.execute(f"DELETE FROM {self._TASK_ATTACH_TABLE} WHERE task_id = ?", (normalized_id,))
            conn.execute(f"DELETE FROM {self._TASK_REPORTS_TABLE} WHERE task_id = ?", (normalized_id,))
            conn.execute(f"DELETE FROM {self._TASK_COMMENTS_TABLE} WHERE task_id = ?", (normalized_id,))
            conn.execute("DELETE FROM hub_task_status_log WHERE task_id = ?", (normalized_id,))
            conn.execute(f"DELETE FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,))
            conn.commit()

        self._remove_relative_files(file_paths)
        self._remove_dir_quiet(self.task_attachments_root / normalized_id)
        return True

    def list_tasks(
        self,
        *,
        user_id: int,
        scope: str = "my",
        role_scope: str = "both",
        status_filter: str = "",
        q: str = "",
        assignee_user_id: Optional[int] = None,
        has_attachments: bool = False,
        due_state: str = "",
        sort_by: str = "status",
        sort_dir: str = "asc",
        limit: int = 100,
        offset: int = 0,
        allow_all_scope: bool = False,
    ) -> dict[str, Any]:
        safe_limit = self._coerce_limit(limit, default=100, minimum=1, maximum=500)
        safe_offset = max(0, self._as_int(offset, 0))
        now_iso = _utc_now_iso()
        normalized_scope = "all" if _normalize_text(scope).lower() == "all" and allow_all_scope else "my"
        normalized_role_scope = _normalize_text(role_scope).lower()
        if normalized_role_scope not in {"assignee", "creator", "controller", "both"}:
            normalized_role_scope = "both"
        normalized_query = _normalize_text(q).lower()
        normalized_due_state = _normalize_text(due_state).lower()
        normalized_sort_by = _normalize_text(sort_by, "status").lower()
        normalized_sort_dir = "desc" if _normalize_text(sort_dir).lower() == "desc" else "asc"
        where_clauses: list[str] = []
        params: list[Any] = []
        if normalized_scope == "my":
            if normalized_role_scope == "assignee":
                where_clauses.append("assignee_user_id = ?")
                params.append(int(user_id))
            elif normalized_role_scope == "creator":
                where_clauses.append("created_by_user_id = ?")
                params.append(int(user_id))
            elif normalized_role_scope == "controller":
                where_clauses.append("controller_user_id = ?")
                params.append(int(user_id))
            else:
                where_clauses.append("(assignee_user_id = ? OR created_by_user_id = ?)")
                params.extend([int(user_id), int(user_id)])
        elif assignee_user_id is not None:
            where_clauses.append("assignee_user_id = ?")
            params.append(self._as_int(assignee_user_id))
        normalized_status = _normalize_text(status_filter).lower()
        if normalized_status:
            where_clauses.append("status = ?")
            params.append(normalized_status)
        if normalized_query:
            where_clauses.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ?)")
            like = f"%{normalized_query}%"
            params.extend([like, like])
        if bool(has_attachments):
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM {self._TASK_ATTACH_TABLE} ta WHERE ta.task_id = {self._TASKS_TABLE}.id)"
            )
        if normalized_due_state == "overdue":
            where_clauses.append("due_at IS NOT NULL AND due_at <> '' AND due_at < ? AND status <> 'done'")
            params.append(now_iso)
        elif normalized_due_state == "today":
            where_clauses.append("due_at IS NOT NULL AND due_at <> '' AND date(due_at) = date('now', 'localtime')")
        elif normalized_due_state == "upcoming":
            where_clauses.append("due_at IS NOT NULL AND due_at <> '' AND date(due_at) > date('now', 'localtime')")
        elif normalized_due_state == "none":
            where_clauses.append("(due_at IS NULL OR due_at = '')")
        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sort_map = {
            "status": (
                "CASE status "
                "WHEN 'new' THEN 1 "
                "WHEN 'in_progress' THEN 2 "
                "WHEN 'review' THEN 3 "
                "WHEN 'done' THEN 4 "
                "ELSE 9 END"
            ),
            "updated_at": "updated_at",
            "due_at": "CASE WHEN due_at IS NULL OR due_at = '' THEN 1 ELSE 0 END, due_at",
        }
        sort_expr = sort_map.get(normalized_sort_by, sort_map["status"])
        tie_breaker = "updated_at DESC"
        if normalized_sort_by == "updated_at":
            tie_breaker = "id DESC"

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM {self._TASKS_TABLE}
                {where_sql}
                ORDER BY
                  {sort_expr} {normalized_sort_dir},
                  {tie_breaker}
                LIMIT ? OFFSET ?
                """,
                tuple([*params, safe_limit, safe_offset]),
            ).fetchall()
            total = conn.execute(
                f"SELECT COUNT(*) AS c FROM {self._TASKS_TABLE}{where_sql}",
                tuple(params),
            ).fetchone()
            items = []
            for row in rows:
                item = self._task_with_latest_report(conn, row)
                attachments = item.get("attachments") if isinstance(item.get("attachments"), list) else []
                item["attachments_count"] = len(attachments)
                item["is_overdue"] = self._is_task_overdue(item.get("due_at"), item.get("status"))
                items.append(item)

        return {
            "items": items,
            "total": self._as_int(total["c"] if total else 0),
            "limit": safe_limit,
            "offset": safe_offset,
            "scope": normalized_scope,
            "filters": {
                "role_scope": normalized_role_scope,
                "status": normalized_status,
                "q": normalized_query,
                "assignee_user_id": self._as_int(assignee_user_id) if assignee_user_id is not None else None,
                "has_attachments": bool(has_attachments),
                "due_state": normalized_due_state,
                "sort_by": normalized_sort_by,
                "sort_dir": normalized_sort_dir,
            },
        }

    def start_task(self, *, task_id: str, user: dict[str, Any]) -> Optional[dict[str, Any]]:
        normalized_id = _normalize_text(task_id)
        if not normalized_id:
            return None
        user_id = self._as_int(user.get("id"))
        now_iso = _utc_now_iso()
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT * FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            if row is None:
                return None
            task = dict(row)
            if self._as_int(task.get("assignee_user_id")) != user_id:
                raise PermissionError("Only assignee can start the task")
            if _normalize_text(task.get("status")).lower() == "done":
                raise ValueError("Task is already completed")
            old_status = _normalize_text(task.get("status"))
            conn.execute(
                f"UPDATE {self._TASKS_TABLE} SET status = 'in_progress', updated_at = ? WHERE id = ?",
                (now_iso, normalized_id),
            )
            self._ensure_task_status_log_table(conn)
            self._log_status_change(conn, task_id=normalized_id, old_status=old_status, new_status="in_progress", user_id=user_id, username=_normalize_text(user.get("username")))
            conn.commit()
            updated = conn.execute(f"SELECT * FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            return self._task_with_latest_report(conn, updated) if updated else None

    def submit_task(
        self,
        *,
        task_id: str,
        user: dict[str, Any],
        comment: str,
        file_name: Optional[str],
        file_bytes: Optional[bytes],
        file_mime: Optional[str],
    ) -> Optional[dict[str, Any]]:
        normalized_id = _normalize_text(task_id)
        if not normalized_id:
            return None
        user_id = self._as_int(user.get("id"))
        now_iso = _utc_now_iso()
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT * FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            if row is None:
                return None
            task = dict(row)
            if self._as_int(task.get("assignee_user_id")) != user_id:
                raise PermissionError("Only assignee can submit the task")
            if _normalize_text(task.get("status")).lower() == "done":
                raise ValueError("Task is already completed")

            report_id = str(uuid.uuid4())
            rel_path: Optional[str] = None
            safe_name: Optional[str] = None
            file_size: Optional[int] = None
            if file_bytes:
                safe_name, rel_path, file_size = self._store_attachment_file(
                    root=self.task_attachments_root,
                    parent_id=normalized_id,
                    attachment_id=report_id,
                    file_name=file_name or "report.bin",
                    file_bytes=bytes(file_bytes),
                )

            conn.execute(
                f"""
                INSERT INTO {self._TASK_REPORTS_TABLE}
                (id, task_id, comment, file_name, file_path, file_mime, file_size, uploaded_by_user_id, uploaded_by_username, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    normalized_id,
                    _normalize_text(comment),
                    safe_name,
                    rel_path,
                    _normalize_text(file_mime),
                    file_size,
                    user_id,
                    _normalize_text(user.get("username")),
                    now_iso,
                ),
            )
            if rel_path and safe_name:
                self._insert_task_attachment(
                    conn=conn,
                    task_id=normalized_id,
                    scope="report",
                    file_name=safe_name,
                    file_path=rel_path,
                    file_mime=file_mime,
                    file_size=self._as_int(file_size),
                    user_id=user_id,
                    username=_normalize_text(user.get("username")),
                    uploaded_at=now_iso,
                )
            conn.execute(
                f"""
                UPDATE {self._TASKS_TABLE}
                SET status = 'review', submitted_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now_iso, now_iso, normalized_id),
            )
            self._create_notification(
                recipient_user_id=self._as_int(task.get("created_by_user_id")),
                event_type="task.submitted",
                title="Задача отправлена на проверку",
                body=_normalize_text(task.get("title")),
                entity_type="task",
                entity_id=normalized_id,
                conn=conn,
            )
            controller_user_id = self._as_int(task.get("controller_user_id"))
            if controller_user_id > 0:
                self._create_notification(
                    recipient_user_id=controller_user_id,
                    event_type="task.review_required",
                    title="Требуется проверка задачи",
                    body=_normalize_text(task.get("title")),
                    entity_type="task",
                    entity_id=normalized_id,
                    conn=conn,
                )
            conn.commit()
            updated = conn.execute(f"SELECT * FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            return self._task_with_latest_report(conn, updated) if updated else None

    def review_task(
        self,
        *,
        task_id: str,
        reviewer: dict[str, Any],
        decision: str,
        comment: str,
    ) -> Optional[dict[str, Any]]:
        normalized_id = _normalize_text(task_id)
        if not normalized_id:
            return None
        decision_text = _normalize_text(decision).lower()
        if decision_text not in {"approve", "reject"}:
            raise ValueError("Review decision must be approve or reject")
        now_iso = _utc_now_iso()
        next_status = "done" if decision_text == "approve" else "in_progress"
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT * FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            if row is None:
                return None
            task = dict(row)
            reviewer_id = self._as_int(reviewer.get("id"))
            if reviewer_id != self._as_int(task.get("controller_user_id")):
                raise PermissionError("Only assigned controller can review this task")
            conn.execute(
                f"""
                UPDATE {self._TASKS_TABLE}
                SET status = ?, reviewed_at = ?, reviewer_user_id = ?, reviewer_username = ?, review_comment = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_status,
                    now_iso,
                    reviewer_id,
                    _normalize_text(reviewer.get("username")),
                    _normalize_text(comment),
                    now_iso,
                    normalized_id,
                ),
            )
            self._create_notification(
                recipient_user_id=self._as_int(task.get("assignee_user_id")),
                event_type="task.reviewed",
                title="Результат проверки задачи",
                body=f"{_normalize_text(task.get('title'))}: {'Принято' if next_status == 'done' else 'Возвращено'}",
                entity_type="task",
                entity_id=normalized_id,
                conn=conn,
            )
            conn.commit()
            updated = conn.execute(f"SELECT * FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            return self._task_with_latest_report(conn, updated) if updated else None

    def get_report(self, report_id: str) -> Optional[dict[str, Any]]:
        normalized_id = _normalize_text(report_id)
        if not normalized_id:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT * FROM {self._TASK_REPORTS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            if row is None:
                return None
            item = dict(row)
            rel_path = _normalize_text(item.get("file_path"))
            item["file_abs_path"] = str((self.data_dir / rel_path).resolve()) if rel_path else ""
            return item

    def mark_notification_read(self, *, notification_id: str, user_id: int) -> bool:
        normalized_id = _normalize_text(notification_id)
        if not normalized_id:
            return False
        now_iso = _utc_now_iso()
        with self._lock, self._connect() as conn:
            exists = conn.execute(f"SELECT id FROM {self._NOTIF_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            if exists is None:
                return False
            conn.execute(
                f"""
                INSERT OR IGNORE INTO {self._NOTIF_READS_TABLE}(notification_id, user_id, read_at)
                VALUES (?, ?, ?)
                """,
                (normalized_id, int(user_id), now_iso),
            )
            conn.commit()
        return True

    def mark_task_notifications_read(
        self,
        *,
        task_id: str,
        user_id: int,
        event_types: Optional[list[str]] = None,
    ) -> int:
        normalized_task_id = _normalize_text(task_id)
        if not normalized_task_id:
            return 0
        normalized_events = [
            _normalize_text(item).lower()
            for item in (
                event_types
                or ["task.assigned", "task.controller_assigned", "task.reviewed", "task.review_required", "task.submitted"]
            )
            if _normalize_text(item)
        ]
        if not normalized_events:
            return 0
        placeholders = ", ".join(["?"] * len(normalized_events))
        params: list[Any] = [int(user_id), _utc_now_iso(), int(user_id), normalized_task_id]
        params.extend(normalized_events)
        with self._lock, self._connect() as conn:
            conn.execute(
                f"""
                INSERT OR IGNORE INTO {self._NOTIF_READS_TABLE}(notification_id, user_id, read_at)
                SELECT n.id, ?, ?
                FROM {self._NOTIF_TABLE} n
                WHERE (n.recipient_user_id IS NULL OR n.recipient_user_id = ?)
                  AND n.entity_type = 'task'
                  AND n.entity_id = ?
                  AND LOWER(n.event_type) IN ({placeholders})
                """,
                tuple(params),
            )
            changed = self._as_int(conn.total_changes)
            conn.commit()
        return changed

    def get_unread_counts(self, *, user_id: int) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            unread_notifications = conn.execute(
                f"""
                SELECT COUNT(*) AS c
                FROM {self._NOTIF_TABLE} n
                LEFT JOIN {self._NOTIF_READS_TABLE} r
                  ON r.notification_id = n.id AND r.user_id = ?
                WHERE (n.recipient_user_id IS NULL OR n.recipient_user_id = ?) AND r.user_id IS NULL
                """,
                (int(user_id), int(user_id)),
            ).fetchone()
            unread_announcements = conn.execute(
                f"""
                SELECT COUNT(*) AS c
                FROM {self._ANN_TABLE} a
                LEFT JOIN {self._ANN_READS_TABLE} r
                  ON r.announcement_id = a.id AND r.user_id = ?
                WHERE a.is_active = 1 AND r.user_id IS NULL
                """,
                (int(user_id),),
            ).fetchone()
            open_tasks = conn.execute(
                f"""
                SELECT COUNT(*) AS c
                FROM {self._TASKS_TABLE}
                WHERE assignee_user_id = ? AND status IN ('new', 'in_progress', 'review')
                """,
                (int(user_id),),
            ).fetchone()
            new_tasks = conn.execute(
                f"""
                SELECT COUNT(*) AS c
                FROM {self._TASKS_TABLE}
                WHERE assignee_user_id = ? AND status = 'new'
                """,
                (int(user_id),),
            ).fetchone()
        return {
            "notifications_unread_total": self._as_int(unread_notifications["c"] if unread_notifications else 0),
            "announcements_unread": self._as_int(unread_announcements["c"] if unread_announcements else 0),
            "tasks_open": self._as_int(open_tasks["c"] if open_tasks else 0),
            "tasks_new": self._as_int(new_tasks["c"] if new_tasks else 0),
        }

    def poll_notifications(
        self,
        *,
        user_id: int,
        since: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        safe_limit = self._coerce_limit(limit, default=50, minimum=1, maximum=200)
        since_text = _normalize_text(since)
        params: list[Any] = [int(user_id), int(user_id)]
        extra_where = ""
        if since_text:
            extra_where = " AND n.created_at > ?"
            params.append(since_text)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT n.*,
                       CASE WHEN r.user_id IS NULL THEN 1 ELSE 0 END AS unread
                FROM {self._NOTIF_TABLE} n
                LEFT JOIN {self._NOTIF_READS_TABLE} r
                  ON r.notification_id = n.id AND r.user_id = ?
                WHERE (n.recipient_user_id IS NULL OR n.recipient_user_id = ?){extra_where}
                ORDER BY n.created_at DESC
                LIMIT ?
                """,
                tuple([*params, safe_limit]),
            ).fetchall()
        counts = self.get_unread_counts(user_id=user_id)
        return {
            "items": [dict(row) for row in rows],
            "since": since_text or None,
            "limit": safe_limit,
            "unread_counts": counts,
            "generated_at": _utc_now_iso(),
        }

    def get_dashboard(self, *, user_id: int, announcements_limit: int = 20, tasks_limit: int = 10) -> dict[str, Any]:
        announcements = self.list_announcements(user_id=user_id, limit=announcements_limit, offset=0)
        tasks = self.list_tasks(
            user_id=user_id,
            scope="my",
            role_scope="assignee",
            status_filter="",
            limit=tasks_limit,
            offset=0,
            allow_all_scope=False,
        )
        unread_counts = self.get_unread_counts(user_id=user_id)
        return {
            "generated_at": _utc_now_iso(),
            "announcements": announcements,
            "my_tasks": tasks,
            "unread_counts": unread_counts,
        }


hub_service = HubService()

