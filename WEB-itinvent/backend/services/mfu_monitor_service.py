"""
Runtime monitor for MFU/printer devices (ping + optional SNMP supplies).
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import platform
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import logging
from local_store import get_local_store

logger = logging.getLogger(__name__)

try:
    from pysnmp.hlapi import (  # type: ignore
        CommunityData as LegacyCommunityData,
        ContextData as LegacyContextData,
        nextCmd as legacy_next_cmd,
        ObjectIdentity as LegacyObjectIdentity,
        ObjectType as LegacyObjectType,
        SnmpEngine as LegacySnmpEngine,
        UdpTransportTarget as LegacyUdpTransportTarget,
        getCmd as legacy_get_cmd,
    )
    _SNMP_LEGACY_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _SNMP_LEGACY_AVAILABLE = False

try:
    from pysnmp.hlapi.asyncio import (  # type: ignore
        CommunityData as AsyncCommunityData,
        ContextData as AsyncContextData,
        ObjectIdentity as AsyncObjectIdentity,
        ObjectType as AsyncObjectType,
        SnmpEngine as AsyncSnmpEngine,
        UdpTransportTarget as AsyncUdpTransportTarget,
        get_cmd as async_get_cmd,
        next_cmd as async_next_cmd,
    )
    _SNMP_ASYNC_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _SNMP_ASYNC_AVAILABLE = False

_SNMP_AVAILABLE = _SNMP_LEGACY_AVAILABLE or _SNMP_ASYNC_AVAILABLE

_snmp_engines_local = threading.local()

def _get_legacy_engine() -> Any:
    if not hasattr(_snmp_engines_local, "engine"):
        _snmp_engines_local.engine = LegacySnmpEngine()
    return _snmp_engines_local.engine

def _get_async_engine() -> Any:
    if not hasattr(_snmp_engines_local, "async_engine"):
        _snmp_engines_local.async_engine = AsyncSnmpEngine()
    return _snmp_engines_local.async_engine

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_bool(value: Any, default: bool) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on", "y"}


class MfuRuntimeMonitor:
    """Background probe service with conservative network usage."""

    _RUNTIME_TABLE = "mfu_runtime_state"
    _PAGE_SNAPSHOT_TABLE = "mfu_page_snapshots"
    _PAGE_BASELINE_TABLE = "mfu_page_baseline"

    def __init__(self) -> None:
        self.ping_interval_sec = max(20, int(os.getenv("MFU_PING_INTERVAL_SEC", "60")))
        self.snmp_interval_sec = max(60, int(os.getenv("MFU_SNMP_INTERVAL_SEC", "300")))
        self.ping_timeout_ms = max(300, int(os.getenv("MFU_PING_TIMEOUT_MS", "900")))
        self.ping_concurrency = max(2, int(os.getenv("MFU_PING_CONCURRENCY", "16")))
        self.snmp_concurrency = max(1, int(os.getenv("MFU_SNMP_CONCURRENCY", "12")))
        self.snmp_community = str(os.getenv("MFU_SNMP_COMMUNITY", "public") or "public").strip() or "public"
        self.snmp_retries = max(0, int(os.getenv("MFU_SNMP_RETRIES", "0")))
        self.snmp_timeout_sec = max(0.5, float(os.getenv("MFU_SNMP_TIMEOUT_SEC", "0.8")))
        self.snmp_probe_timeout_sec = max(3.0, float(os.getenv("MFU_SNMP_PROBE_TIMEOUT_SEC", "20")))
        self.snmp_enabled = _to_bool(os.getenv("MFU_SNMP_ENABLED", "true"), True)
        self.snmp_max_supplies = max(1, int(os.getenv("MFU_SNMP_MAX_SUPPLIES", "16")))
        self.snmp_max_trays = max(1, int(os.getenv("MFU_SNMP_MAX_TRAYS", "5")))
        self.snmp_marker_scan_max = max(1, int(os.getenv("MFU_SNMP_MARKER_SCAN_MAX", "4")))
        self.snmp_index_refresh_sec = max(300, int(os.getenv("MFU_SNMP_INDEX_REFRESH_SEC", "3600")))
        self.snmp_walk_budget_sec = max(2.0, float(os.getenv("MFU_SNMP_WALK_BUDGET_SEC", "8")))
        self.snmp_walk_max_rows = max(8, int(os.getenv("MFU_SNMP_WALK_MAX_ROWS", "24")))
        self.snmp_walk_retries = max(0, int(os.getenv("MFU_SNMP_WALK_RETRIES", "0")))
        self.snmp_backoff_base_sec = max(5, int(os.getenv("MFU_SNMP_BACKOFF_BASE_SEC", "60")))
        self.snmp_backoff_max_sec = max(self.snmp_backoff_base_sec, int(os.getenv("MFU_SNMP_BACKOFF_MAX_SEC", "900")))
        self.persist_runtime_state = _to_bool(os.getenv("MFU_RUNTIME_PERSIST_ENABLED", "true"), True)
        self.runtime_state_ttl_days = max(1, int(os.getenv("MFU_RUNTIME_STATE_TTL_DAYS", "30")))
        self.page_snapshot_ttl_days = max(30, int(os.getenv("MFU_PAGE_SNAPSHOT_TTL_DAYS", "400")))
        self.page_monthly_default_months = max(1, int(os.getenv("MFU_PAGE_MONTHS_DEFAULT", "12")))
        self.page_snapshot_cleanup_interval_sec = max(300, int(os.getenv("MFU_PAGE_SNAPSHOT_CLEANUP_INTERVAL_SEC", "21600")))

        self._custom_providers = self._load_custom_snmp_config()

        self._known_devices: Dict[str, Dict[str, Any]] = {}
        self._runtime_cache: Dict[str, Dict[str, Any]] = {}
        self._snmp_index_cache: Dict[str, Dict[str, Any]] = {}
        self._runtime_state_seed: Dict[str, Dict[str, Any]] = {}
        self._restored_runtime_keys: set[str] = set()
        self._lock = asyncio.Lock()
        self._running = False
        self._ping_task: Optional[asyncio.Task] = None
        self._snmp_task: Optional[asyncio.Task] = None
        self._runtime_db_path: Optional[Path] = None
        self._last_page_snapshot_cleanup_ts = 0.0

        if self.persist_runtime_state:
            self._init_runtime_persistence()
            self._runtime_state_seed = self._load_runtime_state_seed()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._snmp_index_cache.clear()
        self._ping_task = asyncio.create_task(self._ping_loop(), name="mfu-ping-loop")
        self._snmp_task = asyncio.create_task(self._snmp_loop(), name="mfu-snmp-loop")
        logger.info(
            "MFU runtime monitor started: ping=%ss, snmp=%ss, snmp_enabled=%s, snmp_available=%s",
            self.ping_interval_sec,
            self.snmp_interval_sec,
            self.snmp_enabled,
            _SNMP_AVAILABLE,
        )

    @staticmethod
    def _get_best_percent(supplies: List[Dict[str, Any]]) -> Optional[int]:
        if not supplies:
            return None
        
        known_percents = []
        for s in supplies:
            pct = s.get("percent")
            if isinstance(pct, int):
                known_percents.append(pct)
                
        if known_percents:
            return min(known_percents)
        return None

    async def stop(self) -> None:
        self._running = False
        for task in (self._ping_task, self._snmp_task):
            if task:
                task.cancel()
        for task in (self._ping_task, self._snmp_task):
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:  # pragma: no cover
                    logger.warning("MFU monitor task stop warning: %s", exc)
        self._ping_task = None
        self._last_snapshot_cleanup = time.monotonic()

    def _load_custom_snmp_config(self) -> List[Dict[str, Any]]:
        try:
            paths_to_try = [
                Path("C:/Project/Image_scan/data/custom_snmp.json"),
                Path(__file__).parent.parent.parent.parent / "data" / "custom_snmp.json",
                Path(__file__).parent.parent / "custom_snmp.json"
            ]
            for cfg_path in paths_to_try:
                if cfg_path.exists():
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return data.get("providers", [])
        except Exception as exc:
            logger.error("Failed to load custom_snmp.json: %s", exc)
        return []

    def _connect_runtime_db(self) -> Optional[sqlite3.Connection]:
        if not self._runtime_db_path:
            return None
        conn = sqlite3.connect(str(self._runtime_db_path), timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_runtime_persistence(self) -> None:
        conn: Optional[sqlite3.Connection] = None
        try:
            store = get_local_store()
            self._runtime_db_path = Path(store.db_path)
            conn = self._connect_runtime_db()
            if conn is None:
                return
            with conn:
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._RUNTIME_TABLE} (
                        device_key TEXT PRIMARY KEY,
                        ip_address TEXT NULL,
                        timeout_total INTEGER NOT NULL DEFAULT 0,
                        timeout_streak INTEGER NOT NULL DEFAULT 0,
                        next_retry_at TEXT NULL,
                        runtime_json TEXT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                columns = {
                    str(row["name"] or "").strip().lower()
                    for row in conn.execute(f"PRAGMA table_info({self._RUNTIME_TABLE})").fetchall()
                }
                if "runtime_json" not in columns:
                    conn.execute(f"ALTER TABLE {self._RUNTIME_TABLE} ADD COLUMN runtime_json TEXT NULL")
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{self._RUNTIME_TABLE}_updated_at ON {self._RUNTIME_TABLE}(updated_at);"
                )
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._PAGE_SNAPSHOT_TABLE} (
                        device_key TEXT NOT NULL,
                        snapshot_date TEXT NOT NULL,
                        page_total INTEGER NOT NULL,
                        page_oid TEXT NULL,
                        snmp_checked_at TEXT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (device_key, snapshot_date)
                    );
                    """
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{self._PAGE_SNAPSHOT_TABLE}_snapshot_date ON {self._PAGE_SNAPSHOT_TABLE}(snapshot_date);"
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{self._PAGE_SNAPSHOT_TABLE}_device_date ON {self._PAGE_SNAPSHOT_TABLE}(device_key, snapshot_date);"
                )
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._PAGE_BASELINE_TABLE} (
                        device_key TEXT PRIMARY KEY,
                        baseline_date TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{self._PAGE_BASELINE_TABLE}_baseline_date ON {self._PAGE_BASELINE_TABLE}(baseline_date);"
                )
                conn.commit()
                self._cleanup_old_page_snapshots(conn=conn, force=True)
        except Exception as exc:
            logger.warning("MFU runtime persistence init failed: %s", exc)
            self._runtime_db_path = None
            self.persist_runtime_state = False
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _runtime_ttl_cutoff_iso(self) -> str:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.runtime_state_ttl_days)
        return cutoff.isoformat()

    def _load_runtime_state_seed(self) -> Dict[str, Dict[str, Any]]:
        if not self.persist_runtime_state:
            return {}
        conn = self._connect_runtime_db()
        if conn is None:
            return {}
        cutoff = self._runtime_ttl_cutoff_iso()
        out: Dict[str, Dict[str, Any]] = {}
        try:
            with conn:
                conn.execute(
                    f"DELETE FROM {self._RUNTIME_TABLE} WHERE updated_at < ?",
                    (cutoff,),
                )
                rows = conn.execute(
                    f"""
                    SELECT device_key, ip_address, timeout_total, timeout_streak, next_retry_at, runtime_json, updated_at
                    FROM {self._RUNTIME_TABLE}
                    """,
                ).fetchall()
            for row in rows:
                key = str(row["device_key"] or "").strip()
                if not key:
                    continue
                runtime_payload: Optional[Dict[str, Any]] = None
                runtime_raw = str(row["runtime_json"] or "").strip()
                if runtime_raw:
                    try:
                        parsed = json.loads(runtime_raw)
                        if isinstance(parsed, dict):
                            runtime_payload = parsed
                    except Exception:
                        runtime_payload = None
                out[key] = {
                    "ip_address": str(row["ip_address"] or "").strip(),
                    "timeout_total": int(row["timeout_total"] or 0),
                    "timeout_streak": int(row["timeout_streak"] or 0),
                    "next_retry_at": str(row["next_retry_at"] or "").strip() or None,
                    "runtime": runtime_payload,
                    "updated_at": str(row["updated_at"] or "").strip() or None,
                }
        except Exception as exc:
            logger.warning("MFU runtime seed load failed: %s", exc)
            return {}
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return out

    @staticmethod
    def _parse_iso_utc(value: Any) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _parse_iso_date(value: Any) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _month_start(dt: datetime) -> datetime:
        normalized = dt.astimezone(timezone.utc)
        return normalized.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _shift_month(dt: datetime, delta: int) -> datetime:
        year = dt.year
        month = dt.month + int(delta)
        while month > 12:
            month -= 12
            year += 1
        while month < 1:
            month += 12
            year -= 1
        return dt.replace(year=year, month=month, day=1)

    def _snapshot_date_from_checked_at(self, checked_at: Optional[str]) -> str:
        checked_dt = self._parse_iso_utc(checked_at)
        if checked_dt is None:
            checked_dt = datetime.now(timezone.utc)
        return checked_dt.date().isoformat()

    def _cleanup_old_page_snapshots(self, conn: Optional[sqlite3.Connection] = None, force: bool = False) -> None:
        if not self.persist_runtime_state:
            return
        now_ts = time.monotonic()
        if not force and (now_ts - self._last_page_snapshot_cleanup_ts) < self.page_snapshot_cleanup_interval_sec:
            return

        close_conn = False
        db_conn = conn
        if db_conn is None:
            db_conn = self._connect_runtime_db()
            close_conn = True
        if db_conn is None:
            return

        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=self.page_snapshot_ttl_days)).date().isoformat()
        try:
            with db_conn:
                db_conn.execute(
                    f"DELETE FROM {self._PAGE_SNAPSHOT_TABLE} WHERE snapshot_date < ?",
                    (cutoff_date,),
                )
            self._last_page_snapshot_cleanup_ts = now_ts
        except Exception as exc:
            logger.warning("MFU page snapshots cleanup failed: %s", exc)
        finally:
            if close_conn:
                try:
                    db_conn.close()
                except Exception:
                    pass

    def _upsert_page_snapshot(
        self,
        *,
        device_key: str,
        page_total: Optional[int],
        page_oid: Optional[str],
        snmp_checked_at: Optional[str],
    ) -> None:
        if not self.persist_runtime_state:
            return
        normalized_key = str(device_key or "").strip()
        if not normalized_key:
            return
        if page_total is None or int(page_total) < 0:
            return

        snapshot_date = self._snapshot_date_from_checked_at(snmp_checked_at)
        now_iso = _utc_now_iso()
        conn = self._connect_runtime_db()
        if conn is None:
            return
        try:
            self._cleanup_old_page_snapshots(conn=conn)
            with conn:
                conn.execute(
                    f"""
                    INSERT INTO {self._PAGE_SNAPSHOT_TABLE}
                    (device_key, snapshot_date, page_total, page_oid, snmp_checked_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_key, snapshot_date) DO UPDATE SET
                        page_total=CASE
                            WHEN excluded.page_total > page_total THEN excluded.page_total
                            ELSE page_total
                        END,
                        page_oid=COALESCE(excluded.page_oid, page_oid),
                        snmp_checked_at=COALESCE(excluded.snmp_checked_at, snmp_checked_at),
                        updated_at=excluded.updated_at
                    """,
                    (
                        normalized_key,
                        snapshot_date,
                        int(page_total),
                        str(page_oid or "").strip() or None,
                        str(snmp_checked_at or "").strip() or None,
                        now_iso,
                        now_iso,
                    ),
                )
        except Exception as exc:
            logger.warning("MFU page snapshot upsert failed for %s: %s", normalized_key, exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _get_or_create_page_baseline(self, device_key: str) -> str:
        normalized_key = str(device_key or "").strip()
        today_iso = datetime.now(timezone.utc).date().isoformat()
        if not normalized_key:
            return today_iso
        if not self.persist_runtime_state:
            return today_iso

        conn = self._connect_runtime_db()
        if conn is None:
            return today_iso
        now_iso = _utc_now_iso()
        try:
            with conn:
                row = conn.execute(
                    f"SELECT baseline_date FROM {self._PAGE_BASELINE_TABLE} WHERE device_key = ?",
                    (normalized_key,),
                ).fetchone()
                if row is not None:
                    existing = str(row["baseline_date"] or "").strip()
                    if self._parse_iso_date(existing) is not None:
                        return existing

                conn.execute(
                    f"""
                    INSERT INTO {self._PAGE_BASELINE_TABLE}(device_key, baseline_date, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(device_key) DO UPDATE SET
                        baseline_date=COALESCE(NULLIF(excluded.baseline_date, ''), baseline_date),
                        updated_at=excluded.updated_at
                    """,
                    (normalized_key, today_iso, now_iso, now_iso),
                )
                return today_iso
        except Exception as exc:
            logger.warning("MFU page baseline read/create failed for %s: %s", normalized_key, exc)
            return today_iso
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def get_page_snapshots(
        self,
        *,
        device_key: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 3000,
    ) -> List[Dict[str, Any]]:
        normalized_key = str(device_key or "").strip()
        if not normalized_key:
            return []
        if not self.persist_runtime_state:
            return []

        conn = self._connect_runtime_db()
        if conn is None:
            return []
        query = (
            f"SELECT device_key, snapshot_date, page_total, page_oid, snmp_checked_at "
            f"FROM {self._PAGE_SNAPSHOT_TABLE} WHERE device_key = ?"
        )
        params: List[Any] = [normalized_key]
        from_norm = str(from_date or "").strip()
        to_norm = str(to_date or "").strip()
        if from_norm:
            query += " AND snapshot_date >= ?"
            params.append(from_norm)
        if to_norm:
            query += " AND snapshot_date <= ?"
            params.append(to_norm)
        query += " ORDER BY snapshot_date ASC LIMIT ?"
        params.append(max(100, int(limit)))

        rows: List[Dict[str, Any]] = []
        try:
            with conn:
                db_rows = conn.execute(query, tuple(params)).fetchall()
            for row in db_rows:
                rows.append(
                    {
                        "device_key": str(row["device_key"] or "").strip(),
                        "snapshot_date": str(row["snapshot_date"] or "").strip(),
                        "page_total": int(row["page_total"] or 0),
                        "page_oid": str(row["page_oid"] or "").strip() or None,
                        "snmp_checked_at": str(row["snmp_checked_at"] or "").strip() or None,
                    }
                )
        except Exception as exc:
            logger.warning("MFU page snapshots query failed for %s: %s", normalized_key, exc)
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return rows

    def get_monthly_page_summary(self, *, device_key: str, months: int = 12) -> Dict[str, Any]:
        normalized_key = str(device_key or "").strip()
        if not normalized_key:
            today_iso = datetime.now(timezone.utc).date().isoformat()
            return {
                "device_key": "",
                "months": [],
                "current_total_pages": None,
                "current_checked_at": None,
                "tracking_start_date": today_iso,
            }

        total_months = max(1, min(36, int(months)))
        now_utc = datetime.now(timezone.utc)
        now_date = now_utc.date()
        tracking_start_date = self._get_or_create_page_baseline(normalized_key)
        tracking_start_dt = self._parse_iso_date(tracking_start_date) or now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        current_month_start = self._month_start(now_utc)
        tracking_month_start = self._month_start(tracking_start_dt)
        limit_month_start = self._shift_month(current_month_start, -(total_months - 1))
        
        first_month_start = max(tracking_month_start, limit_month_start)
        
        actual_months_count = 0
        temp_month = first_month_start
        while temp_month <= current_month_start:
            actual_months_count += 1
            temp_month = self._shift_month(temp_month, 1)

        from_date = tracking_start_dt.date().isoformat()
        to_date = now_date.isoformat()
        snapshots = self.get_page_snapshots(
            device_key=normalized_key,
            from_date=from_date,
            to_date=to_date,
            limit=5000,
        )

        normalized_rows: List[Dict[str, Any]] = []
        for row in snapshots:
            snapshot_dt = self._parse_iso_date(row.get("snapshot_date"))
            if snapshot_dt is None:
                continue
            page_total = int(row.get("page_total") or 0)
            normalized_rows.append(
                {
                    "snapshot_dt": snapshot_dt,
                    "snapshot_date": snapshot_dt.date().isoformat(),
                    "page_total": page_total,
                    "snmp_checked_at": row.get("snmp_checked_at"),
                }
            )
        normalized_rows.sort(key=lambda item: item["snapshot_dt"])

        current_total_pages: Optional[int] = None
        current_checked_at: Optional[str] = None
        if normalized_rows:
            latest = normalized_rows[-1]
            current_total_pages = int(latest.get("page_total") or 0)
            current_checked_at = str(latest.get("snmp_checked_at") or "").strip() or None

        month_rows: List[Dict[str, Any]] = []
        for index in range(actual_months_count):
            month_start = self._shift_month(first_month_start, index)
            month_end = self._shift_month(month_start, 1)
            month_key = month_start.strftime("%Y-%m")

            rows_in_month = [
                row for row in normalized_rows
                if month_start.date() <= row["snapshot_dt"].date() < month_end.date()
            ]
            rows_before_month = [
                row for row in normalized_rows
                if row["snapshot_dt"].date() < month_start.date()
            ]

            start_counter = int(rows_before_month[-1]["page_total"]) if rows_before_month else None
            end_counter = max((int(row["page_total"]) for row in rows_in_month), default=None)
            month_start_min = min((int(row["page_total"]) for row in rows_in_month), default=None)

            printed_pages = 0
            reset_detected = False
            if end_counter is not None:
                baseline = start_counter if start_counter is not None else month_start_min
                if baseline is not None:
                    delta = int(end_counter) - int(baseline)
                    if delta < 0:
                        printed_pages = int(end_counter)
                        reset_detected = True
                    else:
                        printed_pages = int(delta)

            month_rows.append(
                {
                    "month": month_key,
                    "printed_pages": max(0, int(printed_pages)),
                    "start_counter": start_counter,
                    "end_counter": end_counter,
                    "reset_detected": bool(reset_detected),
                }
            )

        return {
            "device_key": normalized_key,
            "months": month_rows,
            "current_total_pages": current_total_pages,
            "current_checked_at": current_checked_at,
            "tracking_start_date": tracking_start_dt.date().isoformat(),
        }

    @staticmethod
    def _sanitize_runtime_snapshot(runtime_snapshot: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(runtime_snapshot, dict):
            return None

        ping_src = runtime_snapshot.get("ping") if isinstance(runtime_snapshot.get("ping"), dict) else {}
        snmp_src = runtime_snapshot.get("snmp") if isinstance(runtime_snapshot.get("snmp"), dict) else {}

        ping = {
            "status": str(ping_src.get("status") or "unknown").strip() or "unknown",
            "latency_ms": ping_src.get("latency_ms"),
            "checked_at": ping_src.get("checked_at"),
            "last_online_at": ping_src.get("last_online_at"),
        }

        raw_supplies = snmp_src.get("supplies")
        supplies: List[Dict[str, Any]] = []
        if isinstance(raw_supplies, list):
            for item in raw_supplies[:32]:
                if isinstance(item, dict):
                    supplies.append(item)

        raw_trays = snmp_src.get("trays")
        trays: List[Dict[str, Any]] = []
        if isinstance(raw_trays, list):
            for item in raw_trays[:16]:
                if isinstance(item, dict):
                    trays.append(item)

        device_info = snmp_src.get("device_info") if isinstance(snmp_src.get("device_info"), dict) else None

        snmp = {
            "status": str(snmp_src.get("status") or "unknown").strip() or "unknown",
            "checked_at": snmp_src.get("checked_at"),
            "last_success_at": snmp_src.get("last_success_at"),
            "best_percent": snmp_src.get("best_percent"),
            "page_total": snmp_src.get("page_total"),
            "page_checked_at": snmp_src.get("page_checked_at"),
            "page_oid": snmp_src.get("page_oid"),
            "supplies": supplies,
            "trays": trays,
            "device_info": device_info,
            "used_community": snmp_src.get("used_community"),
            "version": snmp_src.get("version"),
            "error": snmp_src.get("error"),
            "query_mode": snmp_src.get("query_mode"),
            "timeout_total": int(snmp_src.get("timeout_total") or 0),
            "timeout_streak": int(snmp_src.get("timeout_streak") or 0),
            "next_retry_at": snmp_src.get("next_retry_at"),
        }
        return {"ping": ping, "snmp": snmp}

    def _restore_runtime_state_for_key(self, key: str, ip_address: str) -> None:
        if key in self._restored_runtime_keys:
            return
        self._restored_runtime_keys.add(key)
        if not self.persist_runtime_state:
            return

        seeded = self._runtime_state_seed.get(key)
        if not isinstance(seeded, dict):
            return

        seeded_ip = str(seeded.get("ip_address") or "").strip()
        if seeded_ip and ip_address and seeded_ip != ip_address:
            return

        timeout_total = max(0, int(seeded.get("timeout_total") or 0))
        timeout_streak = max(0, int(seeded.get("timeout_streak") or 0))
        next_retry_at = str(seeded.get("next_retry_at") or "").strip() or None
        original_next_retry_at = next_retry_at
        original_timeout_streak = timeout_streak
        retry_dt = self._parse_iso_utc(next_retry_at)
        if retry_dt and retry_dt <= datetime.now(timezone.utc):
            next_retry_at = None
            timeout_streak = 0

        device_meta = self._known_devices.setdefault(key, {})
        device_meta["snmp_timeout_total"] = timeout_total
        device_meta["snmp_timeout_streak"] = timeout_streak
        device_meta["snmp_backoff_until"] = next_retry_at

        runtime = self._runtime_cache.setdefault(key, {})
        restored_runtime = self._sanitize_runtime_snapshot(seeded.get("runtime"))
        if restored_runtime:
            runtime["ping"] = restored_runtime.get("ping", runtime.get("ping", {}))
            runtime["snmp"] = restored_runtime.get("snmp", runtime.get("snmp", {}))
        snmp_state = runtime.setdefault("snmp", {})
        snmp_state["timeout_total"] = timeout_total
        snmp_state["timeout_streak"] = timeout_streak
        snmp_state["next_retry_at"] = next_retry_at
        if original_next_retry_at != next_retry_at or original_timeout_streak != timeout_streak:
            self._persist_runtime_state_for_key(
                key=key,
                ip_address=ip_address,
                timeout_total=timeout_total,
                timeout_streak=timeout_streak,
                next_retry_at=next_retry_at,
                runtime_snapshot=runtime,
            )

    def _persist_runtime_state_for_key(
        self,
        key: str,
        ip_address: str,
        timeout_total: int,
        timeout_streak: int,
        next_retry_at: Optional[str],
        runtime_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.persist_runtime_state:
            return
        conn = self._connect_runtime_db()
        if conn is None:
            return
        runtime_json: Optional[str] = None
        sanitized_runtime = self._sanitize_runtime_snapshot(runtime_snapshot)
        if sanitized_runtime is not None:
            try:
                runtime_json = json.dumps(
                    sanitized_runtime,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            except Exception:
                runtime_json = None
        try:
            with conn:
                conn.execute(
                    f"""
                    INSERT INTO {self._RUNTIME_TABLE}
                    (device_key, ip_address, timeout_total, timeout_streak, next_retry_at, runtime_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_key) DO UPDATE SET
                        ip_address=excluded.ip_address,
                        timeout_total=excluded.timeout_total,
                        timeout_streak=excluded.timeout_streak,
                        next_retry_at=excluded.next_retry_at,
                        runtime_json=COALESCE(excluded.runtime_json, runtime_json),
                        updated_at=excluded.updated_at
                    """,
                    (
                        key,
                        ip_address or None,
                        max(0, int(timeout_total)),
                        max(0, int(timeout_streak)),
                        str(next_retry_at or "").strip() or None,
                        runtime_json,
                        _utc_now_iso(),
                    ),
                )
        except Exception as exc:
            logger.warning("MFU runtime persist failed for %s: %s", key, exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _clear_persisted_runtime_state(self, key: str) -> None:
        if not self.persist_runtime_state:
            return
        conn = self._connect_runtime_db()
        if conn is None:
            return
        try:
            with conn:
                conn.execute(f"DELETE FROM {self._RUNTIME_TABLE} WHERE device_key = ?", (key,))
        except Exception as exc:
            logger.warning("MFU runtime cleanup failed for %s: %s", key, exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    async def register_devices(self, devices: List[Dict[str, Any]]) -> None:
        """
        Register known devices for background probing.
        Device item: {key: str, ip: str}
        """
        now = _utc_now_iso()
        async with self._lock:
            for item in devices or []:
                key = str(item.get("key") or "").strip()
                ip_address = str(item.get("ip") or "").strip()
                if not key:
                    continue
                existing = self._known_devices.get(key, {})
                previous_ip = str(existing.get("ip") or "").strip()
                existing["ip"] = ip_address
                existing["updated_at"] = now
                self._known_devices[key] = existing
                if previous_ip and ip_address and previous_ip != ip_address:
                    self._snmp_index_cache.pop(key, None)
                    existing["snmp_timeout_total"] = 0
                    existing["snmp_timeout_streak"] = 0
                    existing["snmp_backoff_until"] = None
                    self._clear_persisted_runtime_state(key)
                if key not in self._runtime_cache:
                    self._runtime_cache[key] = {
                        "ping": {
                            "status": "unknown",
                            "latency_ms": None,
                            "checked_at": None,
                            "last_online_at": None,
                        },
                        "snmp": {
                            "status": "disabled" if not self.snmp_enabled else ("unsupported" if not _SNMP_AVAILABLE else "unknown"),
                            "checked_at": None,
                            "last_success_at": None,
                            "best_percent": None,
                            "page_total": None,
                            "page_checked_at": None,
                            "page_oid": None,
                            "supplies": [],
                            "trays": [],
                            "device_info": None,
                            "custom_metrics": {},
                            "used_community": None,
                            "version": None,
                            "error": None,
                            "query_mode": None,
                            "timeout_total": 0,
                            "timeout_streak": 0,
                            "next_retry_at": None,
                        },
                    }
                self._restore_runtime_state_for_key(key, ip_address)

    async def get_snapshot(self, key: str) -> Dict[str, Any]:
        device_key = str(key or "").strip()
        if not device_key:
            return {
                "ping": {"status": "unknown", "latency_ms": None, "checked_at": None, "last_online_at": None},
                "snmp": {
                    "status": "unknown",
                    "checked_at": None,
                    "last_success_at": None,
                    "best_percent": None,
                    "page_total": None,
                    "page_checked_at": None,
                    "page_oid": None,
                    "supplies": [],
                    "trays": [],
                    "device_info": None,
                    "custom_metrics": {},
                    "used_community": None,
                    "version": None,
                    "error": None,
                    "query_mode": None,
                    "timeout_total": 0,
                    "timeout_streak": 0,
                    "next_retry_at": None,
                },
            }
        async with self._lock:
            current = self._runtime_cache.get(device_key)
            if not isinstance(current, dict):
                return {
                    "ping": {"status": "unknown", "latency_ms": None, "checked_at": None, "last_online_at": None},
                    "snmp": {
                        "status": "unknown",
                        "checked_at": None,
                        "last_success_at": None,
                        "best_percent": None,
                        "page_total": None,
                        "page_checked_at": None,
                        "page_oid": None,
                        "supplies": [],
                        "trays": [],
                        "device_info": None,
                        "custom_metrics": {},
                        "used_community": None,
                        "version": None,
                        "error": None,
                        "query_mode": None,
                        "timeout_total": 0,
                        "timeout_streak": 0,
                        "next_retry_at": None,
                    },
                }
            return copy.deepcopy(current)

    async def _ping_loop(self) -> None:
        while self._running:
            try:
                await self._run_ping_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("MFU ping cycle failed: %s", exc)
            await asyncio.sleep(self.ping_interval_sec)

    async def _snmp_loop(self) -> None:
        while self._running:
            try:
                await self._run_snmp_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("MFU SNMP cycle failed: %s", exc)
            await asyncio.sleep(self.snmp_interval_sec)

    async def _run_ping_cycle(self) -> None:
        async with self._lock:
            candidates: List[Tuple[str, str]] = [
                (key, str(meta.get("ip") or "").strip())
                for key, meta in self._known_devices.items()
                if str(meta.get("ip") or "").strip()
            ]
        if not candidates:
            return

        semaphore = asyncio.Semaphore(self.ping_concurrency)

        async def worker(key: str, ip_address: str) -> None:
            async with semaphore:
                result = await self._probe_ping(ip_address)
                await self._apply_ping_result(key, result)

        await asyncio.gather(*(worker(key, ip) for key, ip in candidates), return_exceptions=True)

    async def _run_snmp_cycle(self) -> None:
        if not self.snmp_enabled:
            return
        if not _SNMP_AVAILABLE:
            await self._mark_snmp_unsupported()
            return

        # ── Hot-reload custom_snmp.json if modified ───────────────────────
        try:
            cfg_paths = [
                Path("C:/Project/Image_scan/data/custom_snmp.json"),
                Path(__file__).parent.parent.parent.parent / "data" / "custom_snmp.json",
                Path(__file__).parent.parent / "custom_snmp.json",
            ]
            for cfg_path in cfg_paths:
                if cfg_path.exists():
                    mtime = cfg_path.stat().st_mtime
                    if mtime != getattr(self, "_custom_snmp_mtime", None):
                        self._custom_providers = self._load_custom_snmp_config()
                        self._custom_snmp_mtime = mtime
                        # Clear version cache so new snmp_version rules apply immediately
                        for key in list(self._runtime_cache.keys()):
                            self._runtime_cache[key].pop("snmp_detected_version", None)
                        logger.info("custom_snmp.json reloaded (%d providers)", len(self._custom_providers))
                    break
        except Exception as _exc:
            logger.debug("custom_snmp.json hot-reload check failed: %s", _exc)


        async with self._lock:
            candidates: List[Tuple[str, str, str]] = []
            now_utc = datetime.now(timezone.utc)
            for key, meta in self._known_devices.items():
                ip_address = str(meta.get("ip") or "").strip()
                if not ip_address:
                    continue
                ping_status = str(self._runtime_cache.get(key, {}).get("ping", {}).get("status") or "").lower()
                if ping_status and ping_status != "online":
                    continue

                backoff_until_raw = str(meta.get("snmp_backoff_until") or "").strip()
                if backoff_until_raw:
                    try:
                        backoff_until = datetime.fromisoformat(backoff_until_raw.replace("Z", "+00:00"))
                        if backoff_until.tzinfo is None:
                            backoff_until = backoff_until.replace(tzinfo=timezone.utc)
                        if backoff_until.astimezone(timezone.utc) > now_utc:
                            continue
                    except ValueError:
                        pass
                candidates.append((key, ip_address, ping_status))
        if not candidates:
            return

        semaphore = asyncio.Semaphore(self.snmp_concurrency)

        async def worker(key: str, ip_address: str) -> None:
            async with semaphore:
                async with self._lock:
                    cached_snmp = self._runtime_cache.get(key, {}).get("snmp", {})
                    device_info = cached_snmp.get("device_info") or {}
                    device_model = device_info.get("device_model")

                search_model = str(device_model or "")
                if not search_model or len(search_model) < 3:
                    try:
                        info = await self._probe_device_info_async(ip_address, time.monotonic() + 4.0)
                        if info:
                            dm = info.get("device_model")
                            sd = info.get("sys_descr")
                            sn = info.get("sys_name")
                            search_model = " ".join(filter(None, [dm, sd, sn]))
                    except Exception:
                        pass

                try:
                    result = await asyncio.wait_for(
                        self._probe_snmp_async(ip_address, key, search_model),
                        timeout=self.snmp_probe_timeout_sec,
                    )
                except asyncio.TimeoutError:
                    result = {
                        "status": "error",
                        "error": "probe_timeout",
                        "supplies": [],
                        "best_percent": None,
                        "page_total": None,
                        "page_oid": None,
                        "used_community": self.snmp_community,
                        "version": "v2c",
                    }
                # Enrich with device info and trays on successful probe
                if str(result.get("status") or "").lower() in {"ok", "no_data"}:
                    resolved_version = 0 if result.get("version") == "v1" else 1
                    try:
                        device_info = await self._probe_device_info_async(
                            ip_address,
                            time.monotonic() + 6.0,
                            snmp_version=resolved_version,
                        )
                        if device_info:
                            result["device_info"] = device_info
                    except Exception:
                        pass
                    try:
                        trays = await self._probe_trays_async(
                            ip_address,
                            time.monotonic() + 6.0,
                            snmp_version=resolved_version,
                        )
                        if trays:
                            result["trays"] = trays
                    except Exception:
                        pass
                    try:
                        if search_model:
                            custom_metrics = await self._probe_custom_metrics_async(
                                ip_address,
                                search_model,
                                time.monotonic() + 5.0,
                                snmp_version=resolved_version,
                            )
                            if custom_metrics:
                                result["custom_metrics"] = custom_metrics
                    except Exception:
                        pass
                await self._apply_snmp_result(key, result)

        await asyncio.gather(*(worker(key, ip) for key, ip, _ in candidates), return_exceptions=True)

    async def _mark_snmp_unsupported(self) -> None:
        async with self._lock:
            checked_at = _utc_now_iso()
            for key, runtime in self._runtime_cache.items():
                snmp = runtime.setdefault("snmp", {})
                if str(snmp.get("status") or "").lower() in {"ok", "no_data"}:
                    continue
                snmp["status"] = "unsupported"
                snmp["checked_at"] = checked_at

    async def _apply_ping_result(self, key: str, result: Dict[str, Any]) -> None:
        checked_at = _utc_now_iso()
        async with self._lock:
            runtime = self._runtime_cache.setdefault(
                key,
                {
                    "ping": {"status": "unknown", "latency_ms": None, "checked_at": None, "last_online_at": None},
                    "snmp": {
                        "status": "unknown",
                        "checked_at": None,
                        "last_success_at": None,
                        "best_percent": None,
                        "page_total": None,
                        "page_checked_at": None,
                        "page_oid": None,
                        "supplies": [],
                        "trays": [],
                        "device_info": None,
                        "custom_metrics": {},
                        "used_community": None,
                        "version": None,
                        "error": None,
                        "query_mode": None,
                        "timeout_total": 0,
                        "timeout_streak": 0,
                        "next_retry_at": None,
                    },
                },
            )
            ping_state = runtime.setdefault("ping", {})
            prev_last_online = ping_state.get("last_online_at")

            is_online = bool(result.get("online"))
            ping_state["status"] = "online" if is_online else "offline"
            ping_state["latency_ms"] = result.get("latency_ms")
            ping_state["checked_at"] = checked_at
            ping_state["last_online_at"] = checked_at if is_online else prev_last_online
            snmp_state = runtime.setdefault("snmp", {})
            device_meta = self._known_devices.setdefault(key, {})
            self._persist_runtime_state_for_key(
                key=key,
                ip_address=str(device_meta.get("ip") or "").strip(),
                timeout_total=int(device_meta.get("snmp_timeout_total") or snmp_state.get("timeout_total") or 0),
                timeout_streak=int(device_meta.get("snmp_timeout_streak") or snmp_state.get("timeout_streak") or 0),
                next_retry_at=str(device_meta.get("snmp_backoff_until") or snmp_state.get("next_retry_at") or "").strip() or None,
                runtime_snapshot=runtime,
            )

    async def _apply_snmp_result(self, key: str, result: Dict[str, Any]) -> None:
        checked_at = _utc_now_iso()
        async with self._lock:
            runtime = self._runtime_cache.setdefault(
                key,
                {
                    "ping": {"status": "unknown", "latency_ms": None, "checked_at": None, "last_online_at": None},
                    "snmp": {
                        "status": "unknown",
                        "checked_at": None,
                        "last_success_at": None,
                        "best_percent": None,
                        "page_total": None,
                        "page_checked_at": None,
                        "page_oid": None,
                        "supplies": [],
                        "trays": [],
                        "device_info": None,
                        "custom_metrics": {},
                        "used_community": None,
                        "version": None,
                        "error": None,
                        "query_mode": None,
                        "timeout_total": 0,
                        "timeout_streak": 0,
                        "next_retry_at": None,
                    },
                },
            )
            snmp_state = runtime.setdefault("snmp", {})
            previous_supplies = snmp_state.get("supplies") if isinstance(snmp_state.get("supplies"), list) else []
            previous_success_at = snmp_state.get("last_success_at")
            previous_best = snmp_state.get("best_percent")
            previous_page_total = self._to_int(snmp_state.get("page_total"))
            previous_page_checked_at = snmp_state.get("page_checked_at")
            previous_page_oid = snmp_state.get("page_oid")
            previous_community = snmp_state.get("used_community")
            previous_version = snmp_state.get("version")
            previous_timeout_total = int(snmp_state.get("timeout_total") or 0)
            previous_timeout_streak = int(snmp_state.get("timeout_streak") or 0)

            status = str(result.get("status") or "error").lower()
            snmp_state["status"] = status
            snmp_state["checked_at"] = checked_at
            snmp_state["used_community"] = result.get("used_community") or previous_community
            snmp_state["version"] = result.get("version") or previous_version
            snmp_state["query_mode"] = result.get("query_mode") or snmp_state.get("query_mode")

            device_meta = self._known_devices.setdefault(key, {})
            timeout_total = int(device_meta.get("snmp_timeout_total") or previous_timeout_total or 0)
            timeout_streak = int(device_meta.get("snmp_timeout_streak") or previous_timeout_streak or 0)

            if status in {"ok", "no_data"}:
                snmp_state["last_success_at"] = checked_at
                snmp_state["supplies"] = result.get("supplies") if isinstance(result.get("supplies"), list) else []
                snmp_state["best_percent"] = result.get("best_percent")
                snmp_state["trays"] = result.get("trays") if isinstance(result.get("trays"), list) else snmp_state.get("trays", [])
                if isinstance(result.get("custom_metrics"), dict):
                    snmp_state["custom_metrics"] = result["custom_metrics"]
                if isinstance(result.get("device_info"), dict):
                    snmp_state["device_info"] = result["device_info"]
                result_page_total = self._to_int(result.get("page_total"))
                snmp_state["page_total"] = result_page_total if result_page_total is not None else previous_page_total
                snmp_state["page_checked_at"] = checked_at if result_page_total is not None else previous_page_checked_at
                snmp_state["page_oid"] = str(result.get("page_oid") or "").strip() or previous_page_oid
                snmp_state["error"] = None
                timeout_streak = 0
                device_meta["snmp_backoff_until"] = None
                if result_page_total is not None:
                    self._upsert_page_snapshot(
                        device_key=key,
                        page_total=result_page_total,
                        page_oid=snmp_state.get("page_oid"),
                        snmp_checked_at=checked_at,
                    )
            else:
                snmp_state["last_success_at"] = previous_success_at
                snmp_state["supplies"] = previous_supplies
                snmp_state["best_percent"] = previous_best
                snmp_state["page_total"] = previous_page_total
                snmp_state["page_checked_at"] = previous_page_checked_at
                snmp_state["page_oid"] = previous_page_oid
                error_text = str(result.get("error") or "").strip()
                if error_text:
                    snmp_state["error"] = error_text
                    if error_text == "probe_timeout":
                        timeout_total += 1
                        timeout_streak += 1
                        delay_sec = min(
                            self.snmp_backoff_max_sec,
                            self.snmp_backoff_base_sec * (2 ** max(0, timeout_streak - 1)),
                        )
                        device_meta["snmp_backoff_until"] = (datetime.now(timezone.utc) + timedelta(seconds=delay_sec)).isoformat()
                    else:
                        timeout_streak = 0
                        device_meta["snmp_backoff_until"] = None
                else:
                    timeout_streak = 0
                    device_meta["snmp_backoff_until"] = None

            device_meta["snmp_timeout_total"] = timeout_total
            device_meta["snmp_timeout_streak"] = timeout_streak
            snmp_state["timeout_total"] = timeout_total
            snmp_state["timeout_streak"] = timeout_streak
            snmp_state["next_retry_at"] = device_meta.get("snmp_backoff_until")
            self._persist_runtime_state_for_key(
                key=key,
                ip_address=str(device_meta.get("ip") or "").strip(),
                timeout_total=timeout_total,
                timeout_streak=timeout_streak,
                next_retry_at=snmp_state.get("next_retry_at"),
                runtime_snapshot=runtime,
            )

    async def _probe_ping(self, ip_address: str) -> Dict[str, Any]:
        """
        Probe ICMP with one packet.
        Returns: {online: bool, latency_ms: Optional[int]}
        """
        return await asyncio.to_thread(self._probe_ping_sync, ip_address)

    def _probe_ping_sync(self, ip_address: str) -> Dict[str, Any]:
        """
        Windows-safe ping probe without PIPE handles.
        Status is determined by process return code.
        """
        system_name = platform.system().lower()
        timeout_sec = max(1, int(round(self.ping_timeout_ms / 1000)))
        if "windows" in system_name:
            args = ["ping", "-n", "1", "-w", str(self.ping_timeout_ms), ip_address]
        else:
            args = ["ping", "-c", "1", "-W", str(timeout_sec), ip_address]

        try:
            run_timeout = max(2.0, (self.ping_timeout_ms / 1000.0) + 1.5)
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if "windows" in system_name else 0
            completed = subprocess.run(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=run_timeout,
                check=False,
                creationflags=creationflags,
            )
            return {"online": completed.returncode == 0, "latency_ms": None}
        except subprocess.TimeoutExpired:
            return {"online": False, "latency_ms": None}
        except Exception as exc:
            logger.debug("Ping probe error for %s: %s", ip_address, exc)
            return {"online": False, "latency_ms": None}

    async def _probe_snmp_async(self, ip_address: str, device_key: Optional[str] = None, search_model: Optional[str] = None) -> Dict[str, Any]:
        """
        Read printer supplies via standard Printer-MIB or custom overrides.
        OIDs:
          - description: 1.3.6.1.2.1.43.11.1.1.6.<marker>.<idx>
          - max level:   1.3.6.1.2.1.43.11.1.1.8.<marker>.<idx>
          - cur level:   1.3.6.1.2.1.43.11.1.1.9.<marker>.<idx>
        """
        if not self.snmp_enabled:
            return {
                "status": "disabled",
                "supplies": [],
                "best_percent": None,
                "page_total": None,
                "page_oid": None,
                "used_community": None,
                "version": None,
                "query_mode": "disabled",
            }
        if not _SNMP_AVAILABLE:
            return {
                "status": "unsupported",
                "supplies": [],
                "best_percent": None,
                "page_total": None,
                "page_oid": None,
                "used_community": self.snmp_community,
                "version": "v2c",
                "query_mode": "unsupported",
            }

        descr_base = "1.3.6.1.2.1.43.11.1.1.6"
        max_base = "1.3.6.1.2.1.43.11.1.1.8"
        level_base = "1.3.6.1.2.1.43.11.1.1.9"
        normalized_key = str(device_key or "").strip()
        deadline = time.monotonic() + max(2.0, self.snmp_probe_timeout_sec - 1.0)
        logger.info(
            "SNMP probe start: ip=%s key=%s probe_timeout=%.1fs deadline_budget=%.1fs",
            ip_address, device_key, self.snmp_probe_timeout_sec, max(2.0, self.snmp_probe_timeout_sec - 1.0),
        )
        page_probe_done = False
        page_total: Optional[int] = None
        page_oid: Optional[str] = None

        async def ensure_page_probe(version=1) -> Tuple[Optional[int], Optional[str]]:
            nonlocal page_probe_done, page_total, page_oid
            if not page_probe_done:
                page_total, page_oid = await self._probe_total_pages_async(ip_address=ip_address, deadline=deadline, snmp_version=version)
                page_probe_done = True
            return page_total, page_oid

        try:
            provider_override = None
            provider_version = None
            if search_model:
                search_lower = str(search_model).lower()
                best_match_tokens = 0
                for prov in self._custom_providers:
                    match_val = str(prov.get("match_model", "")).lower()
                    if match_val and match_val != "*":
                        tokens = match_val.split()
                        if all(t in search_lower for t in tokens):
                            if len(tokens) > best_match_tokens:
                                best_match_tokens = len(tokens)
                                provider_override = prov.get("overrides")
                                provider_version = prov.get("snmp_version")
            
            # allow match_ip
            if not provider_override:
                for prov in self._custom_providers:
                    match_ip = str(prov.get("match_ip", "")).lower()
                    if match_ip and match_ip == ip_address.lower():
                        if "overrides" in prov:
                            provider_override = prov["overrides"]
                        provider_version = prov.get("snmp_version")
                        break

            # Let fallback '*' activate if no regular match
            if not provider_override:
                for prov in self._custom_providers:
                    if str(prov.get("match_model", "")) == "*":
                        if "overrides" in prov:
                            provider_override = prov["overrides"]
                        provider_version = prov.get("snmp_version")
                        break

            # AUTO FALLBACK LOGIC
            req_version = 1 if provider_version is None else int(provider_version)
            if provider_version is None:
                cached_ver = self._runtime_cache.get(device_key, {}).get("snmp", {}).get("version") if device_key else None
                if cached_ver == "v1":
                    req_version = 0
                elif cached_ver == "v2c":
                    req_version = 1
                else:
                    probe_v2 = await self._snmp_get_async(ip_address, "1.3.6.1.2.1.1.1.0", deadline=time.monotonic()+1.0, snmp_version=1, timeout_override=1.0)
                    if probe_v2 is None:
                        probe_v1 = await self._snmp_get_async(ip_address, "1.3.6.1.2.1.1.1.0", deadline=time.monotonic()+1.0, snmp_version=0, timeout_override=1.0)
                        if probe_v1 is not None:
                            req_version = 0
                            logger.info("Auto-fallback to SNMPv1 selected for %s", ip_address)

            if provider_override:
                # Apply JSON Overrides directly
                supplies = []
                override_supplies = provider_override.get("supplies", [])
                
                idx = 1
                for s_def in override_supplies:
                    lvl_raw = await self._snmp_get_async(ip_address, s_def.get("level", ""), deadline=deadline, snmp_version=req_version)
                    max_raw = await self._snmp_get_async(ip_address, s_def.get("max", ""), deadline=deadline, snmp_version=req_version)
                    lvl = self._to_int(lvl_raw)
                    mx = self._to_int(max_raw)
                    pct = None
                    if lvl is not None and mx is not None and mx > 0 and lvl >= 0:
                        pct = max(0, min(100, int(round((lvl / mx) * 100))))
                    supplies.append({
                        "index": idx,
                        "marker_index": 1,
                        "supply_index": idx,
                        "name": str(s_def.get("name", "Override Supply")),
                        "level": lvl,
                        "max": mx,
                        "percent": pct
                    })
                    idx += 1
                
                best_percent = self._get_best_percent(supplies)
                
                page_total = None
                page_oid_override = str(provider_override.get("page_total", "")).strip()
                if page_oid_override:
                    pt_raw = await self._snmp_get_async(ip_address, page_oid_override, deadline=deadline, snmp_version=req_version)
                    if pt_raw:
                        page_total = self._to_int(pt_raw)
                        page_oid = page_oid_override
                
                # If page total was not in override, try regular
                if page_total is None:
                    page_total, page_oid = await ensure_page_probe(version=req_version)

                return {
                    "status": "ok",
                    "supplies": supplies,
                    "best_percent": best_percent,
                    "page_total": page_total,
                    "page_oid": page_oid,
                    "used_community": self.snmp_community,
                    "version": "v1" if req_version == 0 else "v2c",
                    "query_mode": "custom_override",
                }

            # Use cached index pairs if available (cleared on startup, TTL=1h)
            # This reduces GETs from 48 to 24 per printer on repeat cycles
            cached_pairs = self._get_cached_index_pairs(normalized_key, ip_address)
            if cached_pairs:
                supplies = await self._collect_supplies_for_pairs_async(
                    ip_address=ip_address,
                    cached_pairs=cached_pairs,
                    max_base=max_base,
                    level_base=level_base,
                    deadline=deadline,
                    snmp_version=req_version,
                )
                if supplies:
                    supplies.sort(
                        key=lambda item: (
                            item.get("percent") is None,
                            item.get("percent") if item.get("percent") is not None else 101,
                            str(item.get("name") or ""),
                        )
                    )
                    best_percent = self._get_best_percent(supplies)
                    page_total, page_oid = await ensure_page_probe(version=req_version)
                    return {
                        "status": "ok",
                        "supplies": supplies,
                        "best_percent": best_percent,
                        "page_total": page_total,
                        "page_oid": page_oid,
                        "used_community": self.snmp_community,
                        "version": "v1" if req_version == 0 else "v2c",
                        "query_mode": "cached_indexes",
                    }
                # Cache stale — invalidate and do full scan
                if normalized_key:
                    self._snmp_index_cache.pop(normalized_key, None)

            supplies = await self._collect_supplies_for_marker_async(
                ip_address=ip_address,
                marker_index=1,
                descr_base=descr_base,
                max_base=max_base,
                level_base=level_base,
                max_supplies=self.snmp_max_supplies,
                deadline=deadline,
                snmp_version=req_version,
            )

            if not supplies:
                for marker_index in range(2, self.snmp_marker_scan_max + 1):
                    if self._deadline_expired(deadline):
                        break
                    if not await self._marker_has_data_async(
                        ip_address=ip_address,
                        marker_index=marker_index,
                        descr_base=descr_base,
                        max_base=max_base,
                        level_base=level_base,
                        deadline=deadline,
                        snmp_version=req_version,
                    ):
                        continue
                    marker_supplies = await self._collect_supplies_for_marker_async(
                        ip_address=ip_address,
                        marker_index=marker_index,
                        descr_base=descr_base,
                        max_base=max_base,
                        level_base=level_base,
                        max_supplies=max(self.snmp_max_supplies, 12),
                        deadline=deadline,
                        snmp_version=req_version,
                    )
                    if marker_supplies:
                        supplies.extend(marker_supplies)
                        break

            if supplies:
                self._set_cached_index_pairs(normalized_key, ip_address, supplies)
                supplies.sort(key=lambda item: (item.get("percent") is None, item.get("percent") if item.get("percent") is not None else 101, str(item.get("name") or "")))
                best_percent = self._get_best_percent(supplies)
                page_total, page_oid = await ensure_page_probe(version=req_version)
                return {
                    "status": "ok",
                    "supplies": supplies,
                    "best_percent": best_percent,
                    "page_total": page_total,
                    "page_oid": page_oid,
                    "used_community": self.snmp_community,
                    "version": "v1" if req_version == 0 else "v2c",
                    "query_mode": "marker_scan",
                }

            if self._deadline_expired(deadline):
                page_total, page_oid = await ensure_page_probe(version=req_version)
                return {
                    "status": "no_data",
                    "supplies": [],
                    "best_percent": None,
                    "page_total": page_total,
                    "page_oid": page_oid,
                    "used_community": self.snmp_community,
                    "version": "v1" if req_version == 0 else "v2c",
                    "query_mode": "budget_exhausted",
                }

            # Fallback path: bounded walk to discover non-standard marker/supply indexes.
            walk_deadline = min(deadline, time.monotonic() + self.snmp_walk_budget_sec)
            supplies = await self._collect_supplies_via_walk_async(
                ip_address=ip_address,
                descr_base=descr_base,
                max_base=max_base,
                level_base=level_base,
                deadline=walk_deadline,
                max_rows=self.snmp_walk_max_rows,
                snmp_version=req_version,
            )

            if supplies:
                self._set_cached_index_pairs(normalized_key, ip_address, supplies)
                supplies.sort(
                    key=lambda item: (
                        item.get("percent") is None,
                        item.get("percent") if item.get("percent") is not None else 101,
                        str(item.get("name") or ""),
                    )
                )
                best_percent = self._get_best_percent(supplies)
                page_total, page_oid = await ensure_page_probe(version=req_version)
                return {
                    "status": "ok",
                    "supplies": supplies,
                    "best_percent": best_percent,
                    "page_total": page_total,
                    "page_oid": page_oid,
                    "used_community": self.snmp_community,
                    "version": "v1" if req_version == 0 else "v2c",
                    "query_mode": "walk",
                }

            page_total, page_oid = await ensure_page_probe(version=req_version)
            return {
                "status": "no_data",
                "supplies": [],
                "best_percent": None,
                "page_total": page_total,
                "page_oid": page_oid,
                "used_community": self.snmp_community,
                "version": "v1" if req_version == 0 else "v2c",
                "query_mode": "no_data",
            }
        except Exception as exc:
            logger.debug("SNMP probe error for %s: %s", ip_address, exc)
            return {
                "status": "error",
                "error": str(exc),
                "supplies": [],
                "best_percent": None,
                "page_total": None,
                "page_oid": None,
                "used_community": self.snmp_community,
                "version": "v2c",
                "query_mode": "error",
            }

    async def _collect_supplies_for_marker_async(
        self,
        ip_address: str,
        marker_index: int,
        descr_base: str,
        max_base: str,
        level_base: str,
        max_supplies: int,
        deadline: Optional[float] = None,
        snmp_version: int = 1,
    ) -> List[Dict[str, Any]]:
        supplies: List[Dict[str, Any]] = []
        empty_streak = 0
        _scan_start = time.monotonic()
        logger.info(
            "Supply scan start: ip=%s marker=%s max_supplies=%s deadline_remaining=%.1fs",
            ip_address, marker_index, max_supplies,
            (deadline - time.monotonic()) if deadline else -1,
        )

        for supply_index in range(1, max(1, int(max_supplies)) + 1):
            if self._deadline_expired(deadline):
                logger.warning(
                    "Supply scan DEADLINE EXPIRED at index %s for %s (elapsed=%.1fs, found=%s so far)",
                    supply_index, ip_address, time.monotonic() - _scan_start, len(supplies),
                )
                break
            _t0 = time.monotonic()
            oid_suffix = f"{marker_index}.{supply_index}"
            per_oid_timeout = min(self.snmp_timeout_sec, 1.0)

            # Fetch all 3 OIDs in parallel — reduces 3×0.8s → ~0.8s per supply index
            descr, max_level_raw, level_raw = await asyncio.gather(
                self._snmp_get_async(
                    ip_address,
                    f"{descr_base}.{oid_suffix}",
                    deadline=deadline,
                    timeout_override=per_oid_timeout,
                    snmp_version=snmp_version,
                ),
                self._snmp_get_async(
                    ip_address,
                    f"{max_base}.{oid_suffix}",
                    deadline=deadline,
                    timeout_override=per_oid_timeout,
                    snmp_version=snmp_version,
                ),
                self._snmp_get_async(
                    ip_address,
                    f"{level_base}.{oid_suffix}",
                    deadline=deadline,
                    timeout_override=per_oid_timeout,
                    snmp_version=snmp_version,
                ),
            )

            if descr is None and max_level_raw is None and level_raw is None:
                empty_streak += 1
                logger.debug("Supply idx %s for %s: empty (streak=%s, elapsed=%.2fs)", supply_index, ip_address, empty_streak, time.monotonic() - _t0)
                if supplies and empty_streak >= 5:
                    break
                continue

            empty_streak = 0
            max_level = self._to_int(max_level_raw)
            level = self._to_int(level_raw)
            percent = None
            if level is not None and level == -3:
                percent = 100  # sufficient
            elif max_level is not None and level is not None and max_level > 0 and level >= 0:
                percent = max(0, min(100, int(round((level / max_level) * 100))))

            name = str(descr or "").strip() or f"Расходник {supply_index}"
            supplies.append(
                {
                    "index": marker_index * 1000 + supply_index,
                    "marker_index": marker_index,
                    "supply_index": supply_index,
                    "name": name,
                    "level": level,
                    "max": max_level,
                    "percent": percent,
                }
            )

        return supplies

    def _decode_snmp_string(self, val: Any) -> str:
        text = str(val or "").strip()
        if text.startswith("0x") and len(text) > 2:
            try:
                return bytes.fromhex(text[2:]).decode("utf-8", errors="replace").strip()
            except (ValueError, UnicodeDecodeError):
                pass
        return text

    def _decode_snmp_string(self, val: Any) -> str:
        text = str(val or "").strip()
        if text.startswith("0x") and len(text) > 2:
            try:
                return bytes.fromhex(text[2:]).decode("utf-8", errors="replace").strip()
            except (ValueError, UnicodeDecodeError):
                pass
        return text

    async def _probe_device_info_async(
        self,
        ip_address: str,
        deadline: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Probe standard MIB OIDs for device identification info:
        - Serial number (Printer-MIB prtGeneralSerialNumber)
        - Device model (HR-MIB hrDeviceDescr)
        - sysName, sysDescr, sysLocation, sysUpTime
        """
        oids = {
            "sys_descr": "1.3.6.1.2.1.1.1.0",
            "sys_name": "1.3.6.1.2.1.1.5.0",
            "device_model": "1.3.6.1.2.1.25.3.2.1.3.1",
            "serial_number": "1.3.6.1.2.1.43.5.1.1.17.1",
            "sys_location": "1.3.6.1.2.1.1.6.0",
            "sys_uptime_ticks": "1.3.6.1.2.1.1.3.0",
        }
        info: Dict[str, Any] = {}
        got_any = False
        working_version = None
        
        for field_name, oid in oids.items():
            if self._deadline_expired(deadline):
                break
            
            versions_to_try = [working_version] if working_version is not None else [1, 0]
            raw = None
            for v in versions_to_try:
                raw = await self._snmp_get_async(
                    ip_address,
                    oid,
                    deadline=deadline,
                    timeout_override=min(self.snmp_timeout_sec, 1.0),
                    snmp_version=v
                )
                if raw is not None:
                    working_version = v
                    break

            if raw is None:
                continue
            val = str(raw or "").strip()
            if not val:
                continue
            val = self._decode_snmp_string(val)
            if field_name == "sys_uptime_ticks":
                parsed = self._to_int(raw)
                if parsed is not None and parsed >= 0:
                    info["uptime_seconds"] = int(parsed) // 100
                    got_any = True
            else:
                info[field_name] = val
                got_any = True
        return info if got_any else None

    async def _probe_custom_metrics_async(
        self,
        ip_address: str,
        search_model: str,
        deadline: Optional[float] = None,
        snmp_version: int = 1,
    ) -> Dict[str, Any]:
        """Query additional generic string OIDs based on custom_snmp.json providers"""
        metrics = {}
        target_prov = None
        best_match_tokens = 0

        for prov in self._custom_providers:
            match_val = str(prov.get("match_model", "")).lower()
            if match_val and match_val != "*":
                tokens = match_val.split()
                if all(t in str(search_model).lower() for t in tokens):
                    if len(tokens) > best_match_tokens:
                        best_match_tokens = len(tokens)
                        target_prov = prov
        
        if not target_prov:
            for prov in self._custom_providers:
                if str(prov.get("match_model", "")) == "*":
                    target_prov = prov
                    break
        
        if not target_prov or "custom_metrics" not in target_prov:
            return metrics
            
        for name, oid in target_prov["custom_metrics"].items():
            if self._deadline_expired(deadline):
                break
            raw = await self._snmp_get_async(ip_address, str(oid).strip(), deadline=deadline, timeout_override=min(self.snmp_timeout_sec, 0.8), snmp_version=snmp_version)
            if raw is not None:
                val = self._decode_snmp_string(raw)
                if val:
                    metrics[name] = val
        return metrics

    async def _probe_trays_async(
        self,
        ip_address: str,
        deadline: Optional[float] = None,
        snmp_version: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Probe Printer-MIB input (tray) info: name, media, max capacity, current level.
        OIDs under 1.3.6.1.2.1.43.8.2.1
        """
        trays: List[Dict[str, Any]] = []
        for tray_idx in range(1, self.snmp_max_trays + 1):
            if self._deadline_expired(deadline):
                break
            # prtInputName
            name_raw = await self._snmp_get_async(
                ip_address,
                f"1.3.6.1.2.1.43.8.2.1.18.1.{tray_idx}",
                deadline=deadline,
                timeout_override=min(self.snmp_timeout_sec, 0.8),
                snmp_version=snmp_version,
            )
            # prtInputMaxCapacity
            max_raw = await self._snmp_get_async(
                ip_address,
                f"1.3.6.1.2.1.43.8.2.1.9.1.{tray_idx}",
                deadline=deadline,
                timeout_override=min(self.snmp_timeout_sec, 0.8),
                snmp_version=snmp_version,
            )
            # prtInputCurrentLevel
            level_raw = await self._snmp_get_async(
                ip_address,
                f"1.3.6.1.2.1.43.8.2.1.10.1.{tray_idx}",
                deadline=deadline,
                timeout_override=min(self.snmp_timeout_sec, 0.8),
                snmp_version=snmp_version,
            )

            name_val = self._decode_snmp_string(name_raw) if name_raw is not None else None
            max_val = self._to_int(max_raw)
            level_val = self._to_int(level_raw)

            if name_val is None and max_val is None and level_val is None:
                continue

            tray_name = str(name_val).strip() if name_val else f"Tray {tray_idx}"

            # prtInputMediaName
            media_raw = await self._snmp_get_async(
                ip_address,
                f"1.3.6.1.2.1.43.8.2.1.12.1.{tray_idx}",
                deadline=deadline,
                timeout_override=min(self.snmp_timeout_sec, 0.8),
                snmp_version=snmp_version,
            )
            media_val = self._decode_snmp_string(media_raw) if media_raw is not None else None
            media_name = media_val if media_val else None

            percent = None
            if max_val is not None and max_val > 0 and level_val is not None and level_val >= 0:
                percent = max(0, min(100, int(round(100.0 * level_val / max_val))))

            trays.append({
                "index": tray_idx,
                "name": tray_name,
                "media_name": media_name,
                "max_capacity": max_val,
                "current_level": level_val,
                "percent": percent,
            })
        return trays

    async def _probe_total_pages_async(
        self,
        ip_address: str,
        deadline: Optional[float] = None,
        snmp_version: int = 1,
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Probe Printer-MIB total printed pages.
        Base OID: 1.3.6.1.2.1.43.10.2.1.4 (prtMarkerLifeCount)
        """
        base_oid = "1.3.6.1.2.1.43.10.2.1.4"
        if self._deadline_expired(deadline):
            return None, None

        candidates: List[Tuple[str, int]] = []
        walk_rows = await self._snmp_walk_async(
            ip_address,
            base_oid,
            max_rows=16,
            deadline=deadline,
            snmp_version=snmp_version,
        )
        for oid, value in walk_rows:
            parsed = self._to_int(value)
            if parsed is None or parsed < 0:
                continue
            candidates.append((str(oid).strip(), int(parsed)))

        if not candidates:
            for suffix in ("1.1", "1.2", "1.3", "1.4", "2.1", "2.2", "3.1", "1", "2", "3", "4"):
                if self._deadline_expired(deadline):
                    break
                oid = f"{base_oid}.{suffix}"
                value = await self._snmp_get_async(
                    ip_address,
                    oid,
                    deadline=deadline,
                    timeout_override=min(self.snmp_timeout_sec, 0.9),
                    snmp_version=snmp_version,
                )
                parsed = self._to_int(value)
                if parsed is None or parsed < 0:
                    continue
                candidates.append((oid, int(parsed)))

        if not candidates:
            return None, None

        best_oid, best_value = max(candidates, key=lambda item: item[1])
        return int(best_value), str(best_oid).strip() or None

    def _get_cached_index_pairs(self, device_key: str, ip_address: str) -> List[Dict[str, Any]]:
        if not device_key:
            return []
        entry = self._snmp_index_cache.get(device_key)
        if not isinstance(entry, dict):
            return []

        cached_ip = str(entry.get("ip") or "").strip()
        if cached_ip and cached_ip != ip_address:
            self._snmp_index_cache.pop(device_key, None)
            return []

        updated_raw = str(entry.get("updated_at") or "").strip()
        if updated_raw:
            try:
                dt = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_sec = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
                if age_sec > self.snmp_index_refresh_sec:
                    return []
            except ValueError:
                return []

        pairs = entry.get("pairs")
        if not isinstance(pairs, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for pair in pairs:
            if not isinstance(pair, dict):
                continue
            marker_index = self._to_int(pair.get("marker_index"))
            supply_index = self._to_int(pair.get("supply_index"))
            if marker_index is None or supply_index is None:
                continue
            if marker_index <= 0 or supply_index <= 0:
                continue
            normalized.append(
                {
                    "marker_index": marker_index,
                    "supply_index": supply_index,
                    "name": str(pair.get("name") or "").strip(),
                }
            )
        return normalized

    def _set_cached_index_pairs(self, device_key: str, ip_address: str, supplies: List[Dict[str, Any]]) -> None:
        if not device_key:
            return
        indexed: Dict[Tuple[int, int], str] = {}
        for entry in supplies or []:
            if not isinstance(entry, dict):
                continue
            marker_index = self._to_int(entry.get("marker_index"))
            supply_index = self._to_int(entry.get("supply_index"))
            if marker_index is None or supply_index is None:
                continue
            if marker_index <= 0 or supply_index <= 0:
                continue
            indexed[(marker_index, supply_index)] = str(entry.get("name") or "").strip()

        if not indexed:
            return

        pairs = [
            {
                "marker_index": marker_index,
                "supply_index": supply_index,
                "name": indexed[(marker_index, supply_index)],
            }
            for marker_index, supply_index in sorted(indexed.keys())
        ]
        self._snmp_index_cache[device_key] = {
            "ip": ip_address,
            "updated_at": _utc_now_iso(),
            "pairs": pairs[:128],
        }

    async def _collect_supplies_for_pairs_async(
        self,
        ip_address: str,
        cached_pairs: List[Dict[str, Any]],
        max_base: str,
        level_base: str,
        deadline: Optional[float] = None,
        snmp_version: int = 1,
    ) -> List[Dict[str, Any]]:
        supplies: List[Dict[str, Any]] = []
        for pair in cached_pairs or []:
            if self._deadline_expired(deadline):
                break
            marker_index = self._to_int(pair.get("marker_index"))
            supply_index = self._to_int(pair.get("supply_index"))
            if marker_index is None or supply_index is None:
                continue

            suffix = f"{marker_index}.{supply_index}"
            max_level_raw = await self._snmp_get_async(
                ip_address,
                f"{max_base}.{suffix}",
                deadline=deadline,
                timeout_override=min(self.snmp_timeout_sec, 1.0),
                snmp_version=snmp_version,
            )
            level_raw = await self._snmp_get_async(
                ip_address,
                f"{level_base}.{suffix}",
                deadline=deadline,
                timeout_override=min(self.snmp_timeout_sec, 1.0),
                snmp_version=snmp_version,
            )
            if max_level_raw is None and level_raw is None:
                continue

            max_level = self._to_int(max_level_raw)
            level = self._to_int(level_raw)
            percent = None
            if max_level is not None and level is not None and max_level > 0 and level >= 0:
                percent = max(0, min(100, int(round((level / max_level) * 100))))

            display_name = str(pair.get("name") or "").strip() or f"Расходник {supply_index}"
            supplies.append(
                {
                    "index": marker_index * 1000 + supply_index,
                    "marker_index": marker_index,
                    "supply_index": supply_index,
                    "name": display_name,
                    "level": level,
                    "max": max_level,
                    "percent": percent,
                }
            )

        return supplies

    async def _collect_supplies_via_walk_async(
        self,
        ip_address: str,
        descr_base: str,
        max_base: str,
        level_base: str,
        deadline: Optional[float] = None,
        max_rows: Optional[int] = None,
        snmp_version: int = 1,
    ) -> List[Dict[str, Any]]:
        walk_rows_limit = int(max_rows) if max_rows is not None else max(self.snmp_max_supplies * 8, 48)
        rows = await self._snmp_walk_async(ip_address, descr_base, max_rows=walk_rows_limit, deadline=deadline, snmp_version=snmp_version)
        if not rows:
            return []

        indexed_names: Dict[Tuple[int, int], str] = {}
        for oid, value in rows:
            pair = self._extract_two_level_index(oid, descr_base)
            if not pair:
                continue
            marker_index, supply_index = pair
            name = str(value or "").strip()
            if name:
                indexed_names[(marker_index, supply_index)] = name

        if not indexed_names:
            return []

        supplies: List[Dict[str, Any]] = []
        for (marker_index, supply_index), name in indexed_names.items():
            if self._deadline_expired(deadline):
                break
            suffix = f"{marker_index}.{supply_index}"
            max_level_raw = await self._snmp_get_async(
                ip_address,
                f"{max_base}.{suffix}",
                deadline=deadline,
                timeout_override=min(self.snmp_timeout_sec, 1.2),
                snmp_version=snmp_version,
            )
            level_raw = await self._snmp_get_async(
                ip_address,
                f"{level_base}.{suffix}",
                deadline=deadline,
                timeout_override=min(self.snmp_timeout_sec, 1.2),
                snmp_version=snmp_version,
            )

            max_level = self._to_int(max_level_raw)
            level = self._to_int(level_raw)
            percent = None
            if max_level is not None and level is not None and max_level > 0 and level >= 0:
                percent = max(0, min(100, int(round((level / max_level) * 100))))

            supplies.append(
                {
                    "index": marker_index * 1000 + supply_index,
                    "marker_index": marker_index,
                    "supply_index": supply_index,
                    "name": name or f"Расходник {supply_index}",
                    "level": level,
                    "max": max_level,
                    "percent": percent,
                }
            )

        return supplies

    @staticmethod
    def _extract_two_level_index(oid: str, base_oid: str) -> Optional[Tuple[int, int]]:
        oid_text = str(oid or "").strip()
        root = f"{str(base_oid).strip()}."
        if not oid_text.startswith(root):
            return None

        suffix = oid_text[len(root):]
        parts = [part for part in suffix.split(".") if part]
        if len(parts) < 2:
            return None
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None

    def _snmp_walk(
        self,
        ip_address: str,
        oid_root: str,
        max_rows: int = 64,
        deadline: Optional[float] = None,
        snmp_version: int = 1,
    ) -> List[Tuple[str, str]]:
        if self._deadline_expired(deadline):
            return []

        walk_timeout = self._resolve_snmp_timeout(
            deadline=deadline,
            timeout_override=min(self.snmp_timeout_sec, self.snmp_walk_budget_sec),
        )
        if walk_timeout is None:
            return []

        root = f"{str(oid_root).strip()}."

        # ── Legacy synchronous path (pysnmp ≤ 6) ─────────────────────────────
        if _SNMP_LEGACY_AVAILABLE:
            result: List[Tuple[str, str]] = []
            iterator = legacy_next_cmd(
                _get_legacy_engine(),
                LegacyCommunityData(self.snmp_community, mpModel=snmp_version),
                LegacyUdpTransportTarget((ip_address, 161), timeout=walk_timeout, retries=self.snmp_walk_retries),
                LegacyContextData(),
                LegacyObjectType(LegacyObjectIdentity(oid_root)),
                lexicographicMode=False,
                ignoreNonIncreasingOid=True,
            )
            for error_indication, error_status, _error_index, var_binds in iterator:
                if self._deadline_expired(deadline):
                    break
                if error_indication or error_status:
                    break
                stop = False
                for name, value in var_binds:
                    if self._deadline_expired(deadline):
                        stop = True
                        break
                    name_text = str(name)
                    if not name_text.startswith(root):
                        stop = True
                        break
                    rendered = str(value.prettyPrint())
                    if "no such" in rendered.lower():
                        continue
                    result.append((name_text, rendered))
                    if len(result) >= max_rows:
                        stop = True
                        break
                if stop:
                    break
            return result

        # ── Async path (pysnmp 7.x) ───────────────────────────────────────────
        if not _SNMP_ASYNC_AVAILABLE:
            return []

        async def _walk_async() -> List[Tuple[str, str]]:
            rows: List[Tuple[str, str]] = []
            target = await AsyncUdpTransportTarget.create(
                (ip_address, 161),
                timeout=walk_timeout,
                retries=self.snmp_walk_retries,
            )
            engine = _get_async_engine()
            community = AsyncCommunityData(self.snmp_community, mpModel=snmp_version)
            ctx = AsyncContextData()
            obj = AsyncObjectType(AsyncObjectIdentity(oid_root))

            # In pysnmp > 7.0, async_next_cmd returns an awaitable tuple, not an async generator.
            # We must await it in a loop and pass the new object identity to advance.
            while len(rows) < max_rows:
                if self._deadline_expired(deadline):
                    break
                    
                result = await async_next_cmd(
                    engine, community, target, ctx, obj, lexicographicMode=False
                )
                err_ind, err_status, _, var_binds = result
                
                if err_ind or err_status:
                    break
                if not var_binds:
                    break
                    
                stop = False
                for name, value in var_binds:
                    if self._deadline_expired(deadline):
                        stop = True
                        break
                    name_text = str(name)
                    if not name_text.startswith(root):
                        stop = True
                        break
                    rendered = str(value.prettyPrint())
                    if "no such" in rendered.lower():
                        continue
                    rows.append((name_text, rendered))
                    
                    # Update 'obj' with the last OID retrieved to advance the walk
                    obj = AsyncObjectType(AsyncObjectIdentity(name_text))
                    
                    if len(rows) >= max_rows:
                        stop = True
                        break
                        
                if stop:
                    break
            return rows

        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_walk_async())
        except Exception as exc:
            logger.debug("Async SNMP walk failed for %s: %s", ip_address, exc)
            return []

    async def _snmp_walk_async(
        self,
        ip_address: str,
        oid_root: str,
        max_rows: int = 64,
        deadline: Optional[float] = None,
        snmp_version: int = 1,
    ) -> List[Tuple[str, str]]:
        if self._deadline_expired(deadline):
            return []

        walk_timeout = self._resolve_snmp_timeout(
            deadline=deadline,
            timeout_override=min(self.snmp_timeout_sec, self.snmp_walk_budget_sec),
        )
        if walk_timeout is None:
            return []

        root = f"{str(oid_root).strip()}."

        if _SNMP_LEGACY_AVAILABLE:
            def _legacy_walk():
                result: List[Tuple[str, str]] = []
                iterator = legacy_next_cmd(
                    _get_legacy_engine(),
                    LegacyCommunityData(self.snmp_community, mpModel=snmp_version),
                    LegacyUdpTransportTarget((ip_address, 161), timeout=walk_timeout, retries=self.snmp_walk_retries),
                    LegacyContextData(),
                    LegacyObjectType(LegacyObjectIdentity(oid_root)),
                    lexicographicMode=False,
                    ignoreNonIncreasingOid=True,
                )
                for err_ind, err_status, _, var_binds in iterator:
                    if self._deadline_expired(deadline) or err_ind or err_status:
                        break
                    stop = False
                    for name, value in var_binds:
                        if self._deadline_expired(deadline):
                            stop = True
                            break
                        name_text = str(name)
                        if not name_text.startswith(root):
                            stop = True
                            break
                        rendered = str(value.prettyPrint())
                        if "no such" in rendered.lower():
                            continue
                        result.append((name_text, rendered))
                        if len(result) >= max_rows:
                            stop = True
                            break
                    if stop:
                        break
                return result
            try:
                return await asyncio.to_thread(_legacy_walk)
            except Exception:
                return []

        if not _SNMP_ASYNC_AVAILABLE:
            return []

        rows: List[Tuple[str, str]] = []
        try:
            target = await AsyncUdpTransportTarget.create(
                (ip_address, 161),
                timeout=walk_timeout,
                retries=self.snmp_walk_retries,
            )
            engine = _get_async_engine()
            community = AsyncCommunityData(self.snmp_community, mpModel=snmp_version)
            ctx = AsyncContextData()
            obj = AsyncObjectType(AsyncObjectIdentity(oid_root))

            while len(rows) < max_rows:
                if self._deadline_expired(deadline):
                    break
                
                result = await async_next_cmd(
                    engine, community, target, ctx, obj, lexicographicMode=False
                )
                err_ind, err_status, _, var_binds = result
                
                if err_ind or err_status or not var_binds:
                    break
                    
                stop = False
                for name, value in var_binds:
                    if self._deadline_expired(deadline):
                        stop = True
                        break
                    name_text = str(name)
                    if not name_text.startswith(root):
                        stop = True
                        break
                    rendered = str(value.prettyPrint())
                    if "no such" in rendered.lower():
                        continue
                    rows.append((name_text, rendered))
                    
                    obj = AsyncObjectType(AsyncObjectIdentity(name_text))
                    
                    if len(rows) >= max_rows:
                        stop = True
                        break
                        
                if stop:
                    break
        except Exception:
            pass
            
        return rows

    async def _marker_has_data_async(
        self,
        ip_address: str,
        marker_index: int,
        descr_base: str,
        max_base: str,
        level_base: str,
        deadline: Optional[float] = None,
        snmp_version: int = 1,
    ) -> bool:
        # Fast probe to avoid expensive full scans on devices without this marker.
        for supply_index in (1, 2):
            if self._deadline_expired(deadline):
                return False
            oid_suffix = f"{marker_index}.{supply_index}"
            for base in (descr_base, max_base, level_base):
                value = await self._snmp_get_async(
                    ip_address,
                    f"{base}.{oid_suffix}",
                    deadline=deadline,
                    timeout_override=min(self.snmp_timeout_sec, 0.8),
                    snmp_version=snmp_version,
                )
                if value is not None:
                    return True
        return False

    @staticmethod
    def _deadline_expired(deadline: Optional[float]) -> bool:
        return deadline is not None and time.monotonic() >= deadline

    def _resolve_snmp_timeout(self, deadline: Optional[float], timeout_override: Optional[float] = None) -> Optional[float]:
        configured = self.snmp_timeout_sec if timeout_override is None else float(timeout_override)
        if deadline is None:
            return max(0.2, configured)
        remaining = deadline - time.monotonic()
        if remaining <= 0.2:
            return None
        return max(0.2, min(configured, remaining))

    def _snmp_get(
        self,
        ip_address: str,
        oid: str,
        *,
        deadline: Optional[float] = None,
        timeout_override: Optional[float] = None,
        snmp_version: int = 1,
    ) -> Optional[str]:
        if not _SNMP_AVAILABLE:
            return None
        if self._deadline_expired(deadline):
            return None

        request_timeout = self._resolve_snmp_timeout(deadline=deadline, timeout_override=timeout_override)
        if request_timeout is None:
            return None

        if _SNMP_LEGACY_AVAILABLE:
            iterator = legacy_get_cmd(
                _get_legacy_engine(),
                LegacyCommunityData(self.snmp_community, mpModel=snmp_version),
                LegacyUdpTransportTarget((ip_address, 161), timeout=request_timeout, retries=self.snmp_retries),
                LegacyContextData(),
                LegacyObjectType(LegacyObjectIdentity(oid)),
            )
            error_indication, error_status, _error_index, var_binds = next(iterator)
        else:
            async def _query():
                async_timeout = self._resolve_snmp_timeout(deadline=deadline, timeout_override=timeout_override)
                if async_timeout is None:
                    return "deadline_expired", None, None, []
                target = await AsyncUdpTransportTarget.create(
                    (ip_address, 161),
                    timeout=async_timeout,
                    retries=self.snmp_retries,
                )
                return await async_get_cmd(
                    _get_async_engine(),
                    AsyncCommunityData(self.snmp_community, mpModel=snmp_version),
                    target,
                    AsyncContextData(),
                    AsyncObjectType(AsyncObjectIdentity(oid)),
                )

            # Reuse event loop within the same thread to avoid asyncio.run() overhead
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            error_indication, error_status, _error_index, var_binds = loop.run_until_complete(_query())
        if error_indication:
            return None
        if error_status:
            return None
        for _name, value in var_binds:
            rendered = str(value.prettyPrint())
            lowered = rendered.lower()
            if "no such" in lowered:
                return None
            return rendered
        return None

    async def _snmp_get_async(
        self,
        ip_address: str,
        oid: str,
        *,
        deadline: Optional[float] = None,
        timeout_override: Optional[float] = None,
        snmp_version: int = 1,
    ) -> Optional[str]:
        if not _SNMP_AVAILABLE:
            return None
        if self._deadline_expired(deadline):
            return None

        request_timeout = self._resolve_snmp_timeout(deadline=deadline, timeout_override=timeout_override)
        if request_timeout is None:
            return None

        if _SNMP_LEGACY_AVAILABLE:
            def _legacy_query():
                iterator = legacy_get_cmd(
                    _get_legacy_engine(),
                    LegacyCommunityData(self.snmp_community, mpModel=snmp_version),
                    LegacyUdpTransportTarget((ip_address, 161), timeout=request_timeout, retries=self.snmp_retries),
                    LegacyContextData(),
                    LegacyObjectType(LegacyObjectIdentity(oid)),
                )
                return next(iterator)
            try:
                error_indication, error_status, _error_index, var_binds = await asyncio.to_thread(_legacy_query)
            except Exception:
                return None
        else:
            async_timeout = self._resolve_snmp_timeout(deadline=deadline, timeout_override=timeout_override)
            if async_timeout is None:
                return None
            try:
                target = await AsyncUdpTransportTarget.create(
                    (ip_address, 161),
                    timeout=async_timeout,
                    retries=self.snmp_retries,
                )
                error_indication, error_status, _error_index, var_binds = await async_get_cmd(
                    _get_async_engine(),
                    AsyncCommunityData(self.snmp_community, mpModel=snmp_version),
                    target,
                    AsyncContextData(),
                    AsyncObjectType(AsyncObjectIdentity(oid)),
                )
            except Exception:
                return None

        if error_indication or error_status:
            return None
        for _name, value in var_binds:
            rendered = str(value.prettyPrint())
            if "no such" in rendered.lower():
                return None
            return rendered
        return None

    @staticmethod
    def _to_int(value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None


mfu_runtime_monitor = MfuRuntimeMonitor()
