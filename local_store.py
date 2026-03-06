#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared local SQLite store for bot/backend JSON replacement.

Design goals:
- keep compatibility with existing JSON-style read/write APIs
- normalize key names to a stable canonical schema
- store all records in one SQLite file with db_name segmentation
- support staged cutover via JSON read fallback
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


FILE_KIND_MAP: Dict[str, str] = {
    "unfound_equipment.json": "list",
    "equipment_transfers.json": "list",
    "cartridge_replacements.json": "list",
    "battery_replacements.json": "list",
    "component_replacements.json": "list",
    "pc_cleanings.json": "list",
    "equipment_installations.json": "list",
    "web_users.json": "list",
    "web_sessions.json": "list",
    "cartridge_database.json": "dict",
    "printer_component_cache.json": "dict",
    "printer_color_cache.json": "dict",
    "user_db_selection.json": "dict",
    "web_user_settings.json": "dict",
    "export_state.json": "dict",
}


def _normalize_filename(filename: str) -> str:
    return Path(str(filename or "")).name or str(filename or "")


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_non_empty(record: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _clean_str(record.get(key))
        if value:
            return value
    return ""


def _normalize_payload(file_name: str, payload: Any) -> Any:
    """
    Normalize legacy keys to canonical keys while keeping compatibility aliases.
    """
    if not isinstance(payload, dict):
        return payload

    record = dict(payload)

    serial_no = _first_non_empty(record, "serial_no", "serial_number", "serial", "SERIAL_NO", "HW_SERIAL_NO")
    if serial_no:
        record["serial_no"] = serial_no
        record.setdefault("serial_number", serial_no)

    inv_no = _first_non_empty(record, "inv_no", "inventory_number", "INV_NO", "INV_NO_BUH")
    if inv_no:
        record["inv_no"] = inv_no
        if file_name == "unfound_equipment.json":
            record.setdefault("inventory_number", inv_no)

    employee = _first_non_empty(record, "employee", "employee_name", "EMPLOYEE_NAME", "EMPL_NAME")
    if employee:
        record["employee"] = employee
        if file_name == "unfound_equipment.json":
            record.setdefault("employee_name", employee)

    branch = _first_non_empty(record, "branch", "branch_name", "BRANCH_NAME")
    if branch:
        record["branch"] = branch

    location = _first_non_empty(record, "location", "LOCATION", "loc_name")
    if location:
        record["location"] = location

    db_name = _first_non_empty(record, "db_name", "DB_NAME")
    if not db_name and isinstance(record.get("additional_data"), dict):
        db_name = _first_non_empty(record["additional_data"], "db_name")
    if db_name:
        record["db_name"] = db_name

    ts = _first_non_empty(record, "timestamp", "created_at", "event_ts", "CREATE_DATE")
    if ts:
        record["timestamp"] = ts

    if file_name == "cartridge_replacements.json":
        component_type = _first_non_empty(record, "component_type", "work_type") or "cartridge"
        record["component_type"] = component_type
        component_color = _first_non_empty(record, "component_color", "cartridge_color")
        if component_color:
            record["component_color"] = component_color
            if component_type == "cartridge":
                record.setdefault("cartridge_color", component_color)
        printer_model = _first_non_empty(record, "printer_model", "model_name")
        if printer_model:
            record["printer_model"] = printer_model
            record.setdefault("model_name", printer_model)

    if file_name in {"battery_replacements.json", "pc_cleanings.json", "component_replacements.json"}:
        model_name = _first_non_empty(record, "model_name", "printer_model", "equipment_model", "MODEL_NAME")
        if model_name:
            record["model_name"] = model_name

    if file_name == "equipment_transfers.json":
        new_employee = _first_non_empty(record, "new_employee")
        old_employee = _first_non_empty(record, "old_employee")
        if new_employee:
            record["new_employee"] = new_employee
        if old_employee:
            record["old_employee"] = old_employee

    return record


def _extract_index_fields(payload: Any) -> Dict[str, str]:
    if not isinstance(payload, dict):
        return {
            "db_name": "",
            "event_ts": "",
            "inv_no": "",
            "serial_no": "",
            "branch": "",
            "location": "",
            "employee": "",
            "component_type": "",
            "model_name": "",
        }

    additional = payload.get("additional_data") if isinstance(payload.get("additional_data"), dict) else {}
    branch = _first_non_empty(payload, "branch", "branch_name", "BRANCH_NAME")
    if not branch:
        branch = _first_non_empty(additional, "branch", "branch_name", "BRANCH_NAME")

    location = _first_non_empty(payload, "location", "LOCATION", "loc_name")
    if not location:
        location = _first_non_empty(additional, "location", "LOCATION", "loc_name")

    return {
        "db_name": _first_non_empty(payload, "db_name", "DB_NAME"),
        "event_ts": _first_non_empty(payload, "timestamp", "created_at", "updated_at", "CREATE_DATE"),
        "inv_no": _first_non_empty(payload, "inv_no", "inventory_number", "INV_NO", "INV_NO_BUH"),
        "serial_no": _first_non_empty(payload, "serial_no", "serial_number", "SERIAL_NO", "HW_SERIAL_NO"),
        "branch": branch,
        "location": location,
        "employee": _first_non_empty(payload, "employee", "employee_name", "EMPLOYEE_NAME", "new_employee"),
        "component_type": _first_non_empty(payload, "component_type", "equipment_type"),
        "model_name": _first_non_empty(payload, "model_name", "printer_model", "equipment_model", "MODEL_NAME"),
    }


def _payload_hash(file_name: str, payload: Any) -> str:
    normalized_payload = _normalize_payload(file_name, payload)
    stable = json.dumps(
        normalized_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


@dataclass
class MigrationResult:
    file_name: str
    status: str
    rows: int
    checksum: str
    note: str = ""


class SQLiteLocalStore:
    """
    Compatibility store that mimics JSON load/save/append on top of SQLite.
    """

    def __init__(
        self,
        *,
        data_dir: Optional[Path | str] = None,
        db_path: Optional[Path | str] = None,
        enable_json_fallback: bool = False,
    ) -> None:
        repo_root = Path(__file__).resolve().parent
        self.data_dir = Path(data_dir) if data_dir else repo_root / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path else (self.data_dir / "local_store.db")
        self.enable_json_fallback = bool(enable_json_fallback)
        self._lock = threading.RLock()
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
                CREATE TABLE IF NOT EXISTS local_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT NOT NULL,
                    entry_key TEXT NULL,
                    db_name TEXT NULL,
                    event_ts TEXT NULL,
                    inv_no TEXT NULL,
                    serial_no TEXT NULL,
                    branch TEXT NULL,
                    location TEXT NULL,
                    employee TEXT NULL,
                    component_type TEXT NULL,
                    model_name TEXT NULL,
                    payload_json TEXT NOT NULL,
                    raw_payload_json TEXT NULL,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_local_records_file_key_unique
                    ON local_records(file_name, entry_key)
                    WHERE entry_key IS NOT NULL;

                CREATE INDEX IF NOT EXISTS idx_local_records_file_id
                    ON local_records(file_name, id);

                CREATE INDEX IF NOT EXISTS idx_local_records_file_db_ts
                    ON local_records(file_name, db_name, event_ts);

                CREATE INDEX IF NOT EXISTS idx_local_records_file_inv
                    ON local_records(file_name, inv_no);

                CREATE INDEX IF NOT EXISTS idx_local_records_file_serial
                    ON local_records(file_name, serial_no);

                CREATE INDEX IF NOT EXISTS idx_local_records_file_branch_location
                    ON local_records(file_name, branch, location);

                CREATE TABLE IF NOT EXISTS migration_meta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    rows_count INTEGER NOT NULL DEFAULT 0,
                    checksum TEXT NOT NULL DEFAULT '',
                    imported_at TEXT NOT NULL,
                    note TEXT NULL
                );
                """
            )
            conn.commit()

    def _json_file_path(self, file_name: str) -> Path:
        return self.data_dir / _normalize_filename(file_name)

    def _fallback_read_json(self, file_name: str, default_content: Any) -> Any:
        path = self._json_file_path(file_name)
        if not path.exists():
            return default_content
        try:
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                return default_content
            return json.loads(text)
        except Exception as exc:
            logger.warning("JSON fallback read failed for %s: %s", path, exc)
            return default_content

    def _infer_kind(self, file_name: str, default_content: Any) -> str:
        normalized = _normalize_filename(file_name)
        if normalized in FILE_KIND_MAP:
            return FILE_KIND_MAP[normalized]
        if isinstance(default_content, dict):
            return "dict"
        if isinstance(default_content, list):
            return "list"
        return "list"

    def _insert_record(
        self,
        conn: sqlite3.Connection,
        *,
        file_name: str,
        entry_key: Optional[str],
        payload: Any,
    ) -> None:
        normalized_payload = _normalize_payload(file_name, payload)
        fields = _extract_index_fields(normalized_payload)
        now = _utc_now_iso()
        conn.execute(
            """
            INSERT INTO local_records(
                file_name, entry_key, db_name, event_ts, inv_no, serial_no,
                branch, location, employee, component_type, model_name,
                payload_json, raw_payload_json, schema_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                file_name,
                entry_key,
                fields["db_name"] or None,
                fields["event_ts"] or None,
                fields["inv_no"] or None,
                fields["serial_no"] or None,
                fields["branch"] or None,
                fields["location"] or None,
                fields["employee"] or None,
                fields["component_type"] or None,
                fields["model_name"] or None,
                json.dumps(normalized_payload, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
                now,
                now,
            ),
        )

    def load_json(self, file_name: str, default_content: Any = None) -> Any:
        normalized_name = _normalize_filename(file_name)
        kind = self._infer_kind(normalized_name, default_content)

        with self._lock, self._connect() as conn:
            if kind == "dict":
                rows = conn.execute(
                    """
                    SELECT entry_key, payload_json
                    FROM local_records
                    WHERE file_name = ? AND entry_key IS NOT NULL
                    ORDER BY id ASC
                    """,
                    (normalized_name,),
                ).fetchall()
                if rows:
                    result: Dict[str, Any] = {}
                    for row in rows:
                        result[str(row["entry_key"])] = json.loads(row["payload_json"])
                    return result
            elif kind == "list":
                rows = conn.execute(
                    """
                    SELECT payload_json
                    FROM local_records
                    WHERE file_name = ? AND entry_key IS NULL
                    ORDER BY id ASC
                    """,
                    (normalized_name,),
                ).fetchall()
                if rows:
                    return [json.loads(row["payload_json"]) for row in rows]
            else:
                row = conn.execute(
                    """
                    SELECT payload_json
                    FROM local_records
                    WHERE file_name = ? AND entry_key = '__value__'
                    ORDER BY id DESC LIMIT 1
                    """,
                    (normalized_name,),
                ).fetchone()
                if row:
                    return json.loads(row["payload_json"])

        if not self.enable_json_fallback:
            return default_content

        fallback_data = self._fallback_read_json(normalized_name, default_content)
        if fallback_data is default_content:
            return default_content

        try:
            self.save_json(normalized_name, fallback_data)
        except Exception as exc:
            logger.warning("Could not hydrate SQLite from JSON fallback (%s): %s", normalized_name, exc)
        return fallback_data

    def save_json(self, file_name: str, data: Any) -> bool:
        normalized_name = _normalize_filename(file_name)
        kind = self._infer_kind(normalized_name, data)

        try:
            with self._lock, self._connect() as conn:
                conn.execute("DELETE FROM local_records WHERE file_name = ?", (normalized_name,))

                if kind == "dict":
                    source = data if isinstance(data, dict) else {}
                    for key, value in source.items():
                        self._insert_record(conn, file_name=normalized_name, entry_key=str(key), payload=value)
                elif kind == "list":
                    source = data if isinstance(data, list) else []
                    for item in source:
                        self._insert_record(conn, file_name=normalized_name, entry_key=None, payload=item)
                else:
                    self._insert_record(conn, file_name=normalized_name, entry_key="__value__", payload=data)

                conn.commit()
            return True
        except Exception as exc:
            logger.error("SQLite save failed for %s: %s", normalized_name, exc)
            return False

    def append_to_json(self, file_name: str, record: Any) -> bool:
        normalized_name = _normalize_filename(file_name)
        kind = self._infer_kind(normalized_name, [])
        if kind != "list":
            # fallback to read-modify-write for non-list payloads
            current = self.load_json(normalized_name, default_content=[])
            if not isinstance(current, list):
                current = []
            current.append(record)
            return self.save_json(normalized_name, current)

        try:
            with self._lock, self._connect() as conn:
                self._insert_record(conn, file_name=normalized_name, entry_key=None, payload=record)
                conn.commit()
            return True
        except Exception as exc:
            logger.error("SQLite append failed for %s: %s", normalized_name, exc)
            return False

    def update_json_array(
        self,
        file_name: str,
        predicate: Callable[[Dict[str, Any]], bool],
        updater: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> int:
        normalized_name = _normalize_filename(file_name)
        rows = self.load_json(normalized_name, default_content=[])
        if not isinstance(rows, list):
            return 0

        changed = 0
        updated_rows: List[Dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict) and predicate(row):
                updated_rows.append(updater(row))
                changed += 1
            else:
                updated_rows.append(row)
        if changed:
            self.save_json(normalized_name, updated_rows)
        return changed

    def get_json_files(self) -> List[str]:
        files: set[str] = set()
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT file_name FROM local_records").fetchall()
            files.update(str(row["file_name"]) for row in rows)
        files.update(p.name for p in self.data_dir.glob("*.json"))
        return sorted(files)

    def count_rows(self, file_name: str) -> int:
        normalized_name = _normalize_filename(file_name)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM local_records WHERE file_name = ?",
                (normalized_name,),
            ).fetchone()
            return int(row["cnt"]) if row else 0

    def merge_json_payload(
        self,
        file_name: str,
        payload: Any,
        *,
        conflict_policy: str = "keep_sqlite",
    ) -> Dict[str, int]:
        """
        Incrementally merge payload into SQLite.

        conflict_policy:
        - keep_sqlite: keep existing row on key conflict
        - update_from_json: replace existing row from incoming JSON
        """
        normalized_name = _normalize_filename(file_name)
        kind = self._infer_kind(normalized_name, payload)
        stats = {
            "imported": 0,
            "updated": 0,
            "skipped_duplicate": 0,
            "skipped_conflict": 0,
            "errors": 0,
        }

        if kind == "list":
            source = payload if isinstance(payload, list) else []
            with self._lock, self._connect() as conn:
                existing_rows = conn.execute(
                    """
                    SELECT payload_json
                    FROM local_records
                    WHERE file_name = ? AND entry_key IS NULL
                    """,
                    (normalized_name,),
                ).fetchall()
                existing_hashes = {
                    _payload_hash(normalized_name, json.loads(row["payload_json"]))
                    for row in existing_rows
                }

                for item in source:
                    incoming_hash = _payload_hash(normalized_name, item)
                    if incoming_hash in existing_hashes:
                        stats["skipped_duplicate"] += 1
                        continue
                    self._insert_record(conn, file_name=normalized_name, entry_key=None, payload=item)
                    existing_hashes.add(incoming_hash)
                    stats["imported"] += 1
                conn.commit()
            return stats

        if kind == "dict":
            source_dict = payload if isinstance(payload, dict) else {}
            with self._lock, self._connect() as conn:
                existing_rows = conn.execute(
                    """
                    SELECT entry_key, payload_json
                    FROM local_records
                    WHERE file_name = ? AND entry_key IS NOT NULL
                    """,
                    (normalized_name,),
                ).fetchall()
                existing_map = {
                    str(row["entry_key"]): _payload_hash(normalized_name, json.loads(row["payload_json"]))
                    for row in existing_rows
                }

                for key, value in source_dict.items():
                    entry_key = str(key)
                    incoming_hash = _payload_hash(normalized_name, value)
                    existing_hash = existing_map.get(entry_key)
                    if existing_hash is None:
                        self._insert_record(conn, file_name=normalized_name, entry_key=entry_key, payload=value)
                        existing_map[entry_key] = incoming_hash
                        stats["imported"] += 1
                        continue
                    if existing_hash == incoming_hash:
                        stats["skipped_duplicate"] += 1
                        continue

                    if conflict_policy == "update_from_json":
                        conn.execute(
                            "DELETE FROM local_records WHERE file_name = ? AND entry_key = ?",
                            (normalized_name, entry_key),
                        )
                        self._insert_record(conn, file_name=normalized_name, entry_key=entry_key, payload=value)
                        existing_map[entry_key] = incoming_hash
                        stats["updated"] += 1
                    else:
                        stats["skipped_conflict"] += 1
                conn.commit()
            return stats

        # scalar/single-value payload
        value_key = "__value__"
        with self._lock, self._connect() as conn:
            existing_row = conn.execute(
                """
                SELECT payload_json
                FROM local_records
                WHERE file_name = ? AND entry_key = ?
                ORDER BY id DESC LIMIT 1
                """,
                (normalized_name, value_key),
            ).fetchone()
            incoming_hash = _payload_hash(normalized_name, payload)
            if existing_row:
                existing_hash = _payload_hash(normalized_name, json.loads(existing_row["payload_json"]))
                if existing_hash == incoming_hash:
                    stats["skipped_duplicate"] += 1
                    return stats
                if conflict_policy == "update_from_json":
                    conn.execute(
                        "DELETE FROM local_records WHERE file_name = ? AND entry_key = ?",
                        (normalized_name, value_key),
                    )
                    self._insert_record(conn, file_name=normalized_name, entry_key=value_key, payload=payload)
                    conn.commit()
                    stats["updated"] += 1
                    return stats
                stats["skipped_conflict"] += 1
                return stats

            self._insert_record(conn, file_name=normalized_name, entry_key=value_key, payload=payload)
            conn.commit()
            stats["imported"] += 1
            return stats

    def merge_json_file(self, file_name: str, *, conflict_policy: str = "keep_sqlite") -> MigrationResult:
        normalized_name = _normalize_filename(file_name)
        path = self._json_file_path(normalized_name)
        if not path.exists():
            return MigrationResult(
                file_name=normalized_name,
                status="skipped_missing",
                rows=0,
                checksum="",
                note="source file does not exist",
            )

        try:
            raw = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            payload = json.loads(raw) if raw.strip() else ([] if self._infer_kind(normalized_name, None) == "list" else {})
        except Exception as exc:
            return MigrationResult(
                file_name=normalized_name,
                status="error",
                rows=0,
                checksum="",
                note=str(exc),
            )

        stats = self.merge_json_payload(normalized_name, payload, conflict_policy=conflict_policy)
        note = (
            f"imported={stats['imported']};updated={stats['updated']};"
            f"skipped_duplicate={stats['skipped_duplicate']};"
            f"skipped_conflict={stats['skipped_conflict']};errors={stats['errors']}"
        )
        status = "merged"
        if stats["errors"] > 0:
            status = "error"
        elif stats["imported"] == 0 and stats["updated"] == 0:
            status = "skipped_existing"

        return MigrationResult(
            file_name=normalized_name,
            status=status,
            rows=stats["imported"] + stats["updated"],
            checksum=checksum,
            note=note,
        )

    def migrate_json_files(
        self,
        *,
        overwrite: bool = False,
        merge: bool = False,
        conflict_policy: str = "keep_sqlite",
        files: Optional[Iterable[str]] = None,
    ) -> List[MigrationResult]:
        if files is None:
            source_files = sorted(p.name for p in self.data_dir.glob("*.json"))
        else:
            source_files = sorted(_normalize_filename(item) for item in files)

        results: List[MigrationResult] = []
        for file_name in source_files:
            path = self._json_file_path(file_name)
            if not path.exists():
                continue
            try:
                raw = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                data = json.loads(raw) if raw.strip() else ([] if self._infer_kind(file_name, None) == "list" else {})
            except Exception as exc:
                result = MigrationResult(file_name=file_name, status="error", rows=0, checksum="", note=str(exc))
                self._write_migration_meta(result)
                results.append(result)
                continue

            if merge and not overwrite:
                result = self.merge_json_file(file_name, conflict_policy=conflict_policy)
                self._write_migration_meta(result)
                results.append(result)
                continue

            if not overwrite and self.count_rows(file_name) > 0:
                result = MigrationResult(
                    file_name=file_name,
                    status="skipped_existing",
                    rows=self.count_rows(file_name),
                    checksum=checksum,
                    note="target already has rows; use merge mode to add only new records",
                )
                self._write_migration_meta(result)
                results.append(result)
                continue

            ok = self.save_json(file_name, data)
            rows_count = len(data) if isinstance(data, (list, dict)) else (1 if data is not None else 0)
            result = MigrationResult(
                file_name=file_name,
                status="imported" if ok else "error",
                rows=rows_count if ok else 0,
                checksum=checksum,
                note="" if ok else "save_json failed",
            )
            self._write_migration_meta(result)
            results.append(result)

        return results

    def _write_migration_meta(self, result: MigrationResult) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO migration_meta(file_name, status, rows_count, checksum, imported_at, note)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.file_name,
                    result.status,
                    int(result.rows),
                    result.checksum,
                    _utc_now_iso(),
                    result.note,
                ),
            )
            conn.commit()


_STORE_SINGLETON: Optional[SQLiteLocalStore] = None


def get_local_store(
    *,
    data_dir: Optional[Path | str] = None,
    db_path: Optional[Path | str] = None,
    enable_json_fallback: bool = False,
) -> SQLiteLocalStore:
    global _STORE_SINGLETON
    if _STORE_SINGLETON is None:
        _STORE_SINGLETON = SQLiteLocalStore(
            data_dir=data_dir,
            db_path=db_path,
            enable_json_fallback=enable_json_fallback,
        )
    return _STORE_SINGLETON
