from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ACTIVE_TASK_STATUSES = ("queued", "delivered", "acknowledged")
FINAL_TASK_STATUSES = ("completed", "failed", "expired")


def _now_ts() -> int:
    return int(time.time())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: Any, default: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def _parse_date_or_ts(value: Any, *, end_of_day: bool = False) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except Exception:
        pass
    try:
        date_obj = datetime.strptime(text, "%Y-%m-%d")
        base = int(date_obj.timestamp())
        if end_of_day:
            return base + (24 * 60 * 60) - 1
        return base
    except Exception:
        return None


def _file_ext_from_values(file_name: Any, file_path: Any) -> str:
    raw_name = str(file_name or "").strip()
    raw_path = str(file_path or "").strip()
    candidate = raw_name or raw_path
    if not candidate:
        return ""
    name_part = candidate.replace("\\", "/").split("/")[-1]
    if "." not in name_part:
        return ""
    return name_part.rsplit(".", 1)[-1].strip().lower()


class ScanStore:
    def __init__(self, *, db_path: Path, archive_dir: Path, task_ack_timeout_sec: int) -> None:
        self.db_path = Path(db_path)
        self.archive_dir = Path(archive_dir)
        self.task_ack_timeout_sec = int(task_ack_timeout_sec)
        self._lock = threading.RLock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS scan_agents (
                    agent_id TEXT PRIMARY KEY,
                    hostname TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    ip_address TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'online',
                    last_seen_at INTEGER NOT NULL DEFAULT 0,
                    last_heartbeat_json TEXT NOT NULL DEFAULT '{}',
                    updated_at INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS scan_tasks (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    command TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    due_at INTEGER NOT NULL,
                    ttl_at INTEGER NOT NULL,
                    delivered_at INTEGER NULL,
                    acked_at INTEGER NULL,
                    completed_at INTEGER NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at INTEGER NOT NULL,
                    dedupe_key TEXT NULL,
                    error_text TEXT NULL,
                    result_json TEXT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_scan_tasks_agent_status_next
                    ON scan_tasks(agent_id, status, next_attempt_at, due_at);

                CREATE INDEX IF NOT EXISTS idx_scan_tasks_ttl
                    ON scan_tasks(ttl_at);

                CREATE INDEX IF NOT EXISTS idx_scan_tasks_dedupe
                    ON scan_tasks(agent_id, dedupe_key);

                CREATE TABLE IF NOT EXISTS scan_jobs (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL DEFAULT '',
                    hostname TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    user_login TEXT NOT NULL DEFAULT '',
                    user_full_name TEXT NOT NULL DEFAULT '',
                    file_path TEXT NOT NULL DEFAULT '',
                    file_name TEXT NOT NULL DEFAULT '',
                    file_hash TEXT NOT NULL DEFAULT '',
                    file_size INTEGER NOT NULL DEFAULT 0,
                    source_kind TEXT NOT NULL DEFAULT 'unknown',
                    event_id TEXT NULL,
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    started_at INTEGER NULL,
                    finished_at INTEGER NULL,
                    error_text TEXT NULL,
                    summary TEXT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_scan_jobs_status_created
                    ON scan_jobs(status, created_at);

                CREATE TABLE IF NOT EXISTS scan_findings (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    category TEXT NOT NULL,
                    matched_patterns_json TEXT NOT NULL DEFAULT '[]',
                    short_reason TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_scan_findings_job
                    ON scan_findings(job_id);

                CREATE TABLE IF NOT EXISTS scan_incidents (
                    id TEXT PRIMARY KEY,
                    finding_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL DEFAULT '',
                    hostname TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    user_login TEXT NOT NULL DEFAULT '',
                    user_full_name TEXT NOT NULL DEFAULT '',
                    file_path TEXT NOT NULL DEFAULT '',
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at INTEGER NOT NULL,
                    ack_at INTEGER NULL,
                    ack_by TEXT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_scan_incidents_status_created
                    ON scan_incidents(status, created_at);

                CREATE INDEX IF NOT EXISTS idx_scan_incidents_branch
                    ON scan_incidents(branch, created_at);

                CREATE TABLE IF NOT EXISTS scan_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_scan_artifacts_job
                    ON scan_artifacts(job_id);
                """
            )
            self._ensure_column(
                conn,
                table_name="scan_jobs",
                column_name="event_id",
                ddl="ALTER TABLE scan_jobs ADD COLUMN event_id TEXT NULL",
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_scan_jobs_event_id
                ON scan_jobs(event_id)
                WHERE event_id IS NOT NULL AND event_id <> ''
                """
            )
            conn.commit()

    def _ensure_column(self, conn: sqlite3.Connection, *, table_name: str, column_name: str, ddl: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing = {str(row["name"] or "").strip().lower() for row in rows}
        if str(column_name or "").strip().lower() in existing:
            return
        conn.execute(ddl)

    def upsert_agent_heartbeat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        agent_id = str(payload.get("agent_id") or "").strip()
        hostname = str(payload.get("hostname") or "").strip()
        if not agent_id:
            agent_id = hostname or f"agent-{uuid.uuid4().hex[:8]}"
        now_ts = _now_ts()
        row = {
            "agent_id": agent_id,
            "hostname": hostname,
            "branch": str(payload.get("branch") or "").strip(),
            "ip_address": str(payload.get("ip_address") or "").strip(),
            "version": str(payload.get("version") or "").strip(),
            "status": str(payload.get("status") or "online").strip() or "online",
            "last_seen_at": int(payload.get("last_seen_at") or now_ts),
            "last_heartbeat_json": _json_dumps(payload),
            "updated_at": now_ts,
        }
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO scan_agents(
                    agent_id, hostname, branch, ip_address, version, status, last_seen_at, last_heartbeat_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    hostname=excluded.hostname,
                    branch=excluded.branch,
                    ip_address=excluded.ip_address,
                    version=excluded.version,
                    status=excluded.status,
                    last_seen_at=excluded.last_seen_at,
                    last_heartbeat_json=excluded.last_heartbeat_json,
                    updated_at=excluded.updated_at
                """,
                (
                    row["agent_id"],
                    row["hostname"],
                    row["branch"],
                    row["ip_address"],
                    row["version"],
                    row["status"],
                    row["last_seen_at"],
                    row["last_heartbeat_json"],
                    row["updated_at"],
                ),
            )
            conn.commit()
        return row

    def create_task(
        self,
        *,
        agent_id: str,
        command: str,
        payload: Optional[Dict[str, Any]] = None,
        ttl_days: int = 7,
        dedupe_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        agent_id = str(agent_id or "").strip()
        command = str(command or "").strip().lower()
        if not agent_id:
            raise ValueError("agent_id is required")
        if command not in {"ping", "scan_now"}:
            raise ValueError("command must be one of: ping, scan_now")

        now_ts = _now_ts()
        ttl_at = now_ts + max(1, int(ttl_days)) * 24 * 60 * 60
        due_at = now_ts
        key = str(dedupe_key or "").strip() or None
        payload_json = _json_dumps(payload or {})

        with self._lock, self._connect() as conn:
            if key:
                existing = conn.execute(
                    """
                    SELECT id, command, status, created_at, ttl_at
                    FROM scan_tasks
                    WHERE agent_id=? AND dedupe_key=? AND status IN ('queued', 'delivered', 'acknowledged')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (agent_id, key),
                ).fetchone()
                if existing:
                    return dict(existing)

            task_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO scan_tasks(
                    id, agent_id, command, payload_json, status, created_at, updated_at, due_at, ttl_at, next_attempt_at, dedupe_key
                ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    agent_id,
                    command,
                    payload_json,
                    now_ts,
                    now_ts,
                    due_at,
                    ttl_at,
                    now_ts,
                    key,
                ),
            )
            conn.commit()
        return {
            "id": task_id,
            "agent_id": agent_id,
            "command": command,
            "status": "queued",
            "created_at": now_ts,
            "ttl_at": ttl_at,
        }

    def _maintain_tasks(self, conn: sqlite3.Connection, now_ts: int) -> None:
        conn.execute(
            """
            UPDATE scan_tasks
            SET status='expired', updated_at=?, completed_at=COALESCE(completed_at, ?)
            WHERE status IN ('queued', 'delivered', 'acknowledged') AND ttl_at <= ?
            """,
            (now_ts, now_ts, now_ts),
        )
        stale_before = now_ts - self.task_ack_timeout_sec
        conn.execute(
            """
            UPDATE scan_tasks
            SET status='queued', updated_at=?
            WHERE status='delivered'
              AND ttl_at > ?
              AND delivered_at IS NOT NULL
              AND delivered_at <= ?
            """,
            (now_ts, now_ts, stale_before),
        )

    def poll_tasks(self, *, agent_id: str, limit: int) -> List[Dict[str, Any]]:
        aid = str(agent_id or "").strip()
        if not aid:
            return []
        request_limit = max(1, min(50, int(limit)))
        now_ts = _now_ts()
        out: List[Dict[str, Any]] = []
        with self._lock, self._connect() as conn:
            self._maintain_tasks(conn, now_ts)
            rows = conn.execute(
                """
                SELECT id, command, payload_json, attempt_count, created_at, ttl_at
                FROM scan_tasks
                WHERE agent_id=?
                  AND status='queued'
                  AND due_at <= ?
                  AND next_attempt_at <= ?
                  AND ttl_at > ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (aid, now_ts, now_ts, now_ts, request_limit),
            ).fetchall()

            for row in rows:
                attempts = int(row["attempt_count"] or 0) + 1
                backoff = min(900, 30 * (2 ** min(attempts - 1, 5)))
                next_attempt = now_ts + backoff
                conn.execute(
                    """
                    UPDATE scan_tasks
                    SET status='delivered',
                        attempt_count=?,
                        delivered_at=?,
                        next_attempt_at=?,
                        updated_at=?
                    WHERE id=?
                    """,
                    (attempts, now_ts, next_attempt, now_ts, row["id"]),
                )
                out.append(
                    {
                        "task_id": row["id"],
                        "command": row["command"],
                        "payload": _json_loads(row["payload_json"], {}),
                        "attempt_count": attempts,
                        "created_at": int(row["created_at"] or now_ts),
                        "ttl_at": int(row["ttl_at"] or now_ts),
                    }
                )
            conn.commit()
        return out

    def report_task_result(
        self,
        *,
        agent_id: str,
        task_id: str,
        status: str,
        result: Optional[Dict[str, Any]],
        error_text: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        aid = str(agent_id or "").strip()
        tid = str(task_id or "").strip()
        normalized = str(status or "").strip().lower()
        if normalized not in {"acknowledged", "completed", "failed"}:
            raise ValueError("status must be acknowledged|completed|failed")
        if not aid or not tid:
            return None

        now_ts = _now_ts()
        update_fields = {
            "status": normalized,
            "updated_at": now_ts,
            "result_json": _json_dumps(result or {}),
            "error_text": str(error_text or "").strip() or None,
            "acked_at": now_ts if normalized in {"acknowledged", "completed", "failed"} else None,
            "completed_at": now_ts if normalized in {"completed", "failed"} else None,
        }
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id, agent_id FROM scan_tasks WHERE id=?",
                (tid,),
            ).fetchone()
            if row is None or str(row["agent_id"] or "").strip() != aid:
                return None

            conn.execute(
                """
                UPDATE scan_tasks
                SET status=?,
                    updated_at=?,
                    result_json=?,
                    error_text=?,
                    acked_at=COALESCE(?, acked_at),
                    completed_at=COALESCE(?, completed_at)
                WHERE id=?
                """,
                (
                    update_fields["status"],
                    update_fields["updated_at"],
                    update_fields["result_json"],
                    update_fields["error_text"],
                    update_fields["acked_at"],
                    update_fields["completed_at"],
                    tid,
                ),
            )
            conn.commit()
        return {"task_id": tid, "status": normalized}

    def queue_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now_ts = _now_ts()
        event_id = str(payload.get("event_id") or "").strip()
        job_id = uuid.uuid4().hex
        row = {
            "id": job_id,
            "agent_id": str(payload.get("agent_id") or "").strip(),
            "hostname": str(payload.get("hostname") or "").strip(),
            "branch": str(payload.get("branch") or "").strip(),
            "user_login": str(payload.get("user_login") or "").strip(),
            "user_full_name": str(payload.get("user_full_name") or "").strip(),
            "file_path": str(payload.get("file_path") or "").strip(),
            "file_name": str(payload.get("file_name") or "").strip(),
            "file_hash": str(payload.get("file_hash") or "").strip(),
            "file_size": int(payload.get("file_size") or 0),
            "source_kind": str(payload.get("source_kind") or "unknown").strip() or "unknown",
            "event_id": event_id,
            "status": "queued",
            "created_at": now_ts,
            "payload_json": _json_dumps(payload),
        }
        with self._lock, self._connect() as conn:
            if event_id:
                existing = conn.execute(
                    """
                    SELECT id, status, created_at
                    FROM scan_jobs
                    WHERE event_id=?
                    LIMIT 1
                    """,
                    (event_id,),
                ).fetchone()
                if existing is not None:
                    return {
                        "job_id": str(existing["id"]),
                        "status": str(existing["status"] or "queued"),
                        "deduped": True,
                    }

            try:
                conn.execute(
                    """
                    INSERT INTO scan_jobs(
                        id, agent_id, hostname, branch, user_login, user_full_name,
                        file_path, file_name, file_hash, file_size, source_kind, event_id, status,
                        created_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        row["agent_id"],
                        row["hostname"],
                        row["branch"],
                        row["user_login"],
                        row["user_full_name"],
                        row["file_path"],
                        row["file_name"],
                        row["file_hash"],
                        row["file_size"],
                        row["source_kind"],
                        row["event_id"],
                        row["status"],
                        row["created_at"],
                        row["payload_json"],
                    ),
                )
            except sqlite3.IntegrityError:
                if event_id:
                    existing = conn.execute(
                        "SELECT id, status FROM scan_jobs WHERE event_id=? LIMIT 1",
                        (event_id,),
                    ).fetchone()
                    if existing is not None:
                        conn.rollback()
                        return {
                            "job_id": str(existing["id"]),
                            "status": str(existing["status"] or "queued"),
                            "deduped": True,
                        }
                raise
            conn.commit()
        return {"job_id": job_id, "status": "queued", "deduped": False}

    def claim_next_job(self) -> Optional[Dict[str, Any]]:
        now_ts = _now_ts()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM scan_jobs
                WHERE status='queued'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE scan_jobs
                SET status='processing', started_at=?, error_text=NULL
                WHERE id=?
                """,
                (now_ts, row["id"]),
            )
            conn.commit()
        out = dict(row)
        out["status"] = "processing"
        out["started_at"] = now_ts
        return out

    def finalize_job(
        self,
        *,
        job_id: str,
        status: str,
        summary: Optional[str] = None,
        error_text: Optional[str] = None,
    ) -> None:
        now_ts = _now_ts()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE scan_jobs
                SET status=?, finished_at=?, summary=?, error_text=?
                WHERE id=?
                """,
                (
                    str(status or "").strip(),
                    now_ts,
                    str(summary or "").strip() or None,
                    str(error_text or "").strip() or None,
                    str(job_id or "").strip(),
                ),
            )
            conn.commit()

    def add_artifact(self, *, job_id: str, artifact_type: str, storage_path: str, size_bytes: int) -> None:
        now_ts = _now_ts()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO scan_artifacts(job_id, artifact_type, storage_path, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, artifact_type, storage_path, int(size_bytes), now_ts),
            )
            conn.commit()

    def create_finding_and_incident(
        self,
        *,
        job: Dict[str, Any],
        severity: str,
        category: str,
        matched_patterns: List[Dict[str, Any]],
        short_reason: str,
    ) -> Dict[str, str]:
        now_ts = _now_ts()
        finding_id = uuid.uuid4().hex
        incident_id = uuid.uuid4().hex
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO scan_findings(
                    id, job_id, severity, category, matched_patterns_json, short_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding_id,
                    str(job.get("id") or ""),
                    severity,
                    category,
                    _json_dumps(matched_patterns),
                    short_reason,
                    now_ts,
                ),
            )
            conn.execute(
                """
                INSERT INTO scan_incidents(
                    id, finding_id, job_id, agent_id, hostname, branch, user_login, user_full_name,
                    file_path, severity, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
                """,
                (
                    incident_id,
                    finding_id,
                    str(job.get("id") or ""),
                    str(job.get("agent_id") or ""),
                    str(job.get("hostname") or ""),
                    str(job.get("branch") or ""),
                    str(job.get("user_login") or ""),
                    str(job.get("user_full_name") or ""),
                    str(job.get("file_path") or ""),
                    severity,
                    now_ts,
                ),
            )
            conn.commit()
        return {"finding_id": finding_id, "incident_id": incident_id}

    def list_incidents(
        self,
        *,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        branch: Optional[str] = None,
        q: Optional[str] = None,
        hostname: Optional[str] = None,
        source_kind: Optional[str] = None,
        file_ext: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        has_fragment: Optional[bool] = None,
        ack_by: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        conditions: List[str] = []
        params: List[Any] = []
        if status:
            conditions.append("i.status = ?")
            params.append(str(status).strip())
        if severity:
            conditions.append("i.severity = ?")
            params.append(str(severity).strip())
        if branch:
            conditions.append("LOWER(i.branch) LIKE ?")
            params.append(f"%{str(branch).strip().lower()}%")
        if hostname:
            conditions.append("LOWER(i.hostname) LIKE ?")
            params.append(f"%{str(hostname).strip().lower()}%")
        if source_kind:
            conditions.append("LOWER(COALESCE(j.source_kind, '')) = ?")
            params.append(str(source_kind).strip().lower())
        if file_ext:
            ext = str(file_ext).strip().lower().lstrip(".")
            if ext:
                conditions.append(
                    "(LOWER(COALESCE(j.file_name, '')) LIKE ? OR LOWER(COALESCE(i.file_path, '')) LIKE ?)"
                )
                params.extend([f"%.{ext}", f"%.{ext}"])
        date_from_ts = _parse_date_or_ts(date_from, end_of_day=False)
        if date_from_ts is not None:
            conditions.append("i.created_at >= ?")
            params.append(int(date_from_ts))
        date_to_ts = _parse_date_or_ts(date_to, end_of_day=True)
        if date_to_ts is not None:
            conditions.append("i.created_at <= ?")
            params.append(int(date_to_ts))
        if has_fragment is True:
            conditions.append("LENGTH(TRIM(COALESCE(f.matched_patterns_json, ''))) > 2")
        elif has_fragment is False:
            conditions.append("LENGTH(TRIM(COALESCE(f.matched_patterns_json, ''))) <= 2")
        if ack_by:
            conditions.append("LOWER(COALESCE(i.ack_by, '')) LIKE ?")
            params.append(f"%{str(ack_by).strip().lower()}%")
        if q:
            needle = f"%{str(q).strip().lower()}%"
            conditions.append(
                "("
                "LOWER(i.hostname) LIKE ? OR LOWER(i.user_login) LIKE ? OR LOWER(i.user_full_name) LIKE ? "
                "OR LOWER(i.file_path) LIKE ? OR LOWER(COALESCE(j.file_name, '')) LIKE ? "
                "OR LOWER(COALESCE(j.source_kind, '')) LIKE ? OR LOWER(COALESCE(f.short_reason, '')) LIKE ? "
                "OR LOWER(COALESCE(f.matched_patterns_json, '')) LIKE ?"
                ")"
            )
            params.extend([needle, needle, needle, needle, needle, needle, needle, needle])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        safe_limit = max(1, min(500, int(limit)))
        safe_offset = max(0, int(offset))

        with self._lock, self._connect() as conn:
            total = conn.execute(
                f"""
                SELECT COUNT(*) as cnt
                FROM scan_incidents i
                LEFT JOIN scan_findings f ON f.id = i.finding_id
                LEFT JOIN scan_jobs j ON j.id = i.job_id
                {where_clause}
                """,
                params,
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"""
                SELECT
                    i.*, 
                    f.category,
                    f.short_reason,
                    f.matched_patterns_json,
                    j.source_kind,
                    j.file_name,
                    j.created_at as job_created_at
                FROM scan_incidents i
                LEFT JOIN scan_findings f ON f.id = i.finding_id
                LEFT JOIN scan_jobs j ON j.id = i.job_id
                {where_clause}
                ORDER BY i.created_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, safe_limit, safe_offset],
            ).fetchall()

        items: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["matched_patterns"] = _json_loads(item.pop("matched_patterns_json", "[]"), [])
            item["file_ext"] = _file_ext_from_values(item.get("file_name"), item.get("file_path"))
            items.append(item)
        return {"total": int(total), "items": items}

    def list_hosts(
        self,
        *,
        q: Optional[str] = None,
        branch: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        conditions: List[str] = []
        params: List[Any] = []

        if branch:
            conditions.append("LOWER(i.branch) LIKE ?")
            params.append(f"%{str(branch).strip().lower()}%")
        if status:
            conditions.append("LOWER(i.status) = ?")
            params.append(str(status).strip().lower())
        if severity:
            conditions.append("LOWER(i.severity) = ?")
            params.append(str(severity).strip().lower())
        if q:
            needle = f"%{str(q).strip().lower()}%"
            conditions.append(
                "("
                "LOWER(i.hostname) LIKE ? OR LOWER(i.user_login) LIKE ? OR LOWER(i.user_full_name) LIKE ? "
                "OR LOWER(i.file_path) LIKE ? OR LOWER(COALESCE(i.branch, '')) LIKE ?"
                ")"
            )
            params.extend([needle, needle, needle, needle, needle])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        safe_limit = max(1, min(500, int(limit)))

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    i.hostname as hostname,
                    COUNT(*) as incidents_total,
                    SUM(CASE WHEN i.status='new' THEN 1 ELSE 0 END) as incidents_new,
                    MAX(i.created_at) as last_incident_at,
                    MAX(
                        CASE LOWER(i.severity)
                            WHEN 'high' THEN 3
                            WHEN 'medium' THEN 2
                            WHEN 'low' THEN 1
                            ELSE 0
                        END
                    ) as top_severity_rank
                FROM scan_incidents i
                {where_clause}
                GROUP BY i.hostname
                ORDER BY incidents_new DESC, last_incident_at DESC
                LIMIT ?
                """,
                [*params, safe_limit],
            ).fetchall()

            out: List[Dict[str, Any]] = []
            for row in rows:
                host = str(row["hostname"] or "").strip()
                if not host:
                    continue

                detail_rows = conn.execute(
                    """
                    SELECT
                        i.branch,
                        i.user_login,
                        i.user_full_name,
                        i.created_at,
                        i.file_path,
                        j.file_name,
                        j.source_kind
                    FROM scan_incidents i
                    LEFT JOIN scan_jobs j ON j.id = i.job_id
                    WHERE LOWER(i.hostname) = LOWER(?)
                    ORDER BY i.created_at DESC
                    LIMIT 400
                    """,
                    (host,),
                ).fetchall()

                latest_branch = ""
                latest_user = ""
                ext_counts: Dict[str, int] = {}
                source_counts: Dict[str, int] = {}

                for d in detail_rows:
                    branch_value = str(d["branch"] or "").strip()
                    if not latest_branch and branch_value:
                        latest_branch = branch_value
                    full_name = str(d["user_full_name"] or "").strip()
                    user_login = str(d["user_login"] or "").strip()
                    if not latest_user and (full_name or user_login):
                        latest_user = full_name or user_login

                    ext = _file_ext_from_values(d["file_name"], d["file_path"])
                    if ext:
                        ext_counts[ext] = int(ext_counts.get(ext, 0) + 1)
                    source = str(d["source_kind"] or "").strip().lower()
                    if source:
                        source_counts[source] = int(source_counts.get(source, 0) + 1)

                ip_row = conn.execute(
                    """
                    SELECT ip_address
                    FROM scan_agents
                    WHERE LOWER(hostname) = LOWER(?) AND ip_address <> ''
                    ORDER BY last_seen_at DESC
                    LIMIT 1
                    """,
                    (host,),
                ).fetchone()

                rank = int(row["top_severity_rank"] or 0)
                if rank >= 3:
                    top_severity = "high"
                elif rank == 2:
                    top_severity = "medium"
                elif rank == 1:
                    top_severity = "low"
                else:
                    top_severity = "none"

                top_exts = [name for name, _ in sorted(ext_counts.items(), key=lambda it: (-it[1], it[0]))[:5]]
                top_sources = [name for name, _ in sorted(source_counts.items(), key=lambda it: (-it[1], it[0]))[:5]]

                out.append(
                    {
                        "hostname": host,
                        "incidents_total": int(row["incidents_total"] or 0),
                        "incidents_new": int(row["incidents_new"] or 0),
                        "last_incident_at": int(row["last_incident_at"] or 0),
                        "top_severity": top_severity,
                        "branch": latest_branch,
                        "user": latest_user,
                        "ip_address": str((ip_row["ip_address"] if ip_row else "") or "").strip(),
                        "top_exts": top_exts,
                        "top_source_kinds": top_sources,
                    }
                )
        return out

    def ack_incident(self, *, incident_id: str, ack_by: str) -> Optional[Dict[str, Any]]:
        iid = str(incident_id or "").strip()
        if not iid:
            return None
        now_ts = _now_ts()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id, status FROM scan_incidents WHERE id=?",
                (iid,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE scan_incidents
                SET status='ack', ack_at=?, ack_by=?
                WHERE id=?
                """,
                (now_ts, str(ack_by or "").strip(), iid),
            )
            conn.commit()
        return {"id": iid, "status": "ack", "ack_at": now_ts}

    def list_agents(self) -> List[Dict[str, Any]]:
        now_ts = _now_ts()
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    a.*,
                    COALESCE(
                        NULLIF(a.branch, ''),
                        (
                            SELECT j.branch
                            FROM scan_jobs j
                            WHERE j.agent_id = a.agent_id AND j.branch <> ''
                            ORDER BY j.created_at DESC
                            LIMIT 1
                        ),
                        (
                            SELECT i.branch
                            FROM scan_incidents i
                            WHERE i.agent_id = a.agent_id AND i.branch <> ''
                            ORDER BY i.created_at DESC
                            LIMIT 1
                        ),
                        ''
                    ) as resolved_branch,
                    COALESCE(
                        NULLIF(a.ip_address, ''),
                        (
                            SELECT h.ip_address
                            FROM scan_agents h
                            WHERE h.agent_id = a.agent_id AND h.ip_address <> ''
                            ORDER BY h.last_seen_at DESC
                            LIMIT 1
                        ),
                        ''
                    ) as resolved_ip_address,
                    (
                        SELECT COUNT(*)
                        FROM scan_tasks t
                        WHERE t.agent_id = a.agent_id
                          AND t.status IN ('queued', 'delivered', 'acknowledged')
                          AND t.ttl_at > ?
                    ) as queue_size,
                    (
                        SELECT COUNT(*)
                        FROM scan_tasks t
                        WHERE t.agent_id = a.agent_id
                          AND t.status = 'expired'
                    ) as expired_tasks
                FROM scan_agents a
                ORDER BY a.last_seen_at DESC
                """,
                (now_ts,),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["branch"] = str(item.get("resolved_branch") or item.get("branch") or "").strip()
            item["ip_address"] = str(item.get("resolved_ip_address") or item.get("ip_address") or "").strip()
            item.pop("resolved_branch", None)
            item.pop("resolved_ip_address", None)
            age_sec = max(0, now_ts - int(item.get("last_seen_at") or 0))
            item["age_seconds"] = age_sec
            item["is_online"] = age_sec <= 5 * 60
            item["last_heartbeat"] = _json_loads(item.get("last_heartbeat_json"), {})
            item.pop("last_heartbeat_json", None)
            out.append(item)
        return out

    def dashboard(self) -> Dict[str, Any]:
        now_ts = _now_ts()
        day_seconds = 24 * 60 * 60
        window_start = now_ts - 29 * day_seconds
        with self._lock, self._connect() as conn:
            agents_total = conn.execute("SELECT COUNT(*) as c FROM scan_agents").fetchone()["c"]
            agents_online = conn.execute(
                "SELECT COUNT(*) as c FROM scan_agents WHERE last_seen_at >= ?",
                (now_ts - 5 * 60,),
            ).fetchone()["c"]
            incidents_total = conn.execute(
                "SELECT COUNT(*) as c FROM scan_incidents",
            ).fetchone()["c"]
            incidents_new = conn.execute(
                "SELECT COUNT(*) as c FROM scan_incidents WHERE status='new'",
            ).fetchone()["c"]
            queue_active = conn.execute(
                """
                SELECT COUNT(*) as c
                FROM scan_tasks
                WHERE status IN ('queued', 'delivered', 'acknowledged') AND ttl_at > ?
                """,
                (now_ts,),
            ).fetchone()["c"]
            queue_expired = conn.execute(
                "SELECT COUNT(*) as c FROM scan_tasks WHERE status='expired'",
            ).fetchone()["c"]
            sev_rows = conn.execute(
                """
                SELECT severity, COUNT(*) as c
                FROM scan_incidents
                GROUP BY severity
                """,
            ).fetchall()
            branch_rows = conn.execute(
                """
                SELECT branch, COUNT(*) as c
                FROM scan_incidents
                GROUP BY branch
                ORDER BY c DESC
                LIMIT 10
                """
            ).fetchall()
            day_rows = conn.execute(
                """
                SELECT
                    DATE(created_at, 'unixepoch') as day_key,
                    COUNT(*) as c
                FROM scan_incidents
                WHERE created_at >= ?
                GROUP BY day_key
                ORDER BY day_key ASC
                """,
                (window_start,),
            ).fetchall()
            new_rows = conn.execute(
                """
                SELECT
                    COALESCE(NULLIF(TRIM(hostname), ''), 'unknown') as hostname,
                    MAX(created_at) as last_ts
                FROM scan_incidents
                WHERE status='new'
                GROUP BY COALESCE(NULLIF(TRIM(hostname), ''), 'unknown')
                ORDER BY last_ts DESC
                LIMIT 12
                """
            ).fetchall()

        daily_map = {str(row["day_key"]): int(row["c"] or 0) for row in day_rows}
        daily: List[Dict[str, Any]] = []
        start_day = window_start - (window_start % day_seconds)
        for idx in range(30):
            day_ts = start_day + idx * day_seconds
            day_key = time.strftime("%Y-%m-%d", time.gmtime(day_ts))
            daily.append({"date": day_key, "count": int(daily_map.get(day_key, 0))})

        return {
            "totals": {
                "agents_total": int(agents_total),
                "agents_online": int(agents_online),
                "agents_offline": int(max(0, agents_total - agents_online)),
                "incidents_total": int(incidents_total),
                "incidents_new": int(incidents_new),
                "queue_active": int(queue_active),
                "queue_expired": int(queue_expired),
            },
            "by_severity": [{"severity": str(row["severity"] or "unknown"), "count": int(row["c"] or 0)} for row in sev_rows],
            "by_branch": [{"branch": str(row["branch"] or "Без филиала"), "count": int(row["c"] or 0)} for row in branch_rows],
            "daily": daily,
            "new_hosts": [str(row["hostname"] or "unknown") for row in new_rows],
        }

    def cleanup_retention(self, *, retention_days: int) -> Dict[str, int]:
        cutoff = _now_ts() - max(1, int(retention_days)) * 24 * 60 * 60
        removed_artifacts = 0
        removed_files = 0
        with self._lock, self._connect() as conn:
            old_artifacts = conn.execute(
                "SELECT id, storage_path FROM scan_artifacts WHERE created_at < ?",
                (cutoff,),
            ).fetchall()
            for row in old_artifacts:
                removed_artifacts += 1
                path = Path(str(row["storage_path"] or "").strip())
                if path.exists():
                    try:
                        path.unlink()
                        removed_files += 1
                    except Exception:
                        logger.warning("Failed to remove artifact file: %s", path)
            conn.execute("DELETE FROM scan_artifacts WHERE created_at < ?", (cutoff,))
            conn.execute(
                "DELETE FROM scan_tasks WHERE status IN ('completed', 'failed', 'expired') AND updated_at < ?",
                (cutoff,),
            )
            conn.execute("DELETE FROM scan_incidents WHERE created_at < ?", (cutoff,))
            conn.execute("DELETE FROM scan_findings WHERE created_at < ?", (cutoff,))
            conn.execute("DELETE FROM scan_jobs WHERE created_at < ?", (cutoff,))
            conn.commit()
        return {"artifact_rows": removed_artifacts, "artifact_files": removed_files}
