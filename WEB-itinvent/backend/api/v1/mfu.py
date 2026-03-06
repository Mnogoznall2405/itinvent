"""
MFU/printer dashboard endpoints.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from backend.api.deps import get_current_database_id, require_permission
from backend.database.equipment_db import get_all_equipment_flat, get_equipment_grouped
from backend.json_db.works import WorksManager
from backend.models.auth import User
from backend.services.authorization_service import PERM_DATABASE_READ
from backend.services.mfu_monitor_service import mfu_runtime_monitor

router = APIRouter()
works_manager = WorksManager()
SNMP_ACTIVE_TTL_SEC = max(60, int(os.getenv("MFU_SNMP_ACTIVE_TTL_SEC", "600")))

# Simple TTL cache for the heavy events-index query (works history)
_events_cache: Dict[str, Any] = {}  # keyed by "db_id|period_days"
_EVENTS_CACHE_TTL_SEC = int(os.getenv("MFU_EVENTS_CACHE_TTL_SEC", "300"))  # 5 minutes
MFU_FALLBACK_KEYWORDS = (
    "принтер",
    "мфу",
    "printer",
    "mfp",
    "mfc",
    "laserjet",
    "officejet",
    "deskjet",
    "workcentre",
    "versalink",
    "i-sensys",
    "imageprograf",
    "imagerunner",
    "plotter",
    "designjet",
    "plotwave",
    "surecolor",
)
MFU_VENDOR_HINTS = (
    "xerox",
    "canon",
    "hp",
    "kyocera",
    "ricoh",
    "brother",
    "epson",
    "lexmark",
    "oki",
    "sharp",
    "pantum",
    "toshiba",
    "konica",
    "minolta",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_first(row: Dict[str, Any], keys: List[str], default: Any = "") -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return default


def _normalize_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _to_int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _parse_utc_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_snmp_recent(last_success_at: Any, now_utc: datetime, ttl_sec: int) -> bool:
    dt = _parse_utc_datetime(last_success_at)
    if dt is None:
        return False
    age_sec = (now_utc - dt).total_seconds()
    return 0 <= age_sec <= max(60, int(ttl_sec))


def _is_mfu_device(device: Dict[str, Any]) -> bool:
    payload = {
        "type_name": device.get("type_name"),
        "model_name": device.get("model_name"),
        "vendor_name": device.get("manufacturer"),
    }
    if works_manager._is_printer_mfu_record(payload):  # noqa: SLF001
        return True
    if works_manager._is_pc_record(payload):  # noqa: SLF001
        return False

    type_name = _normalize_text(device.get("type_name")).lower()
    
    if "сервер" in type_name or "server" in type_name:
        return False
    model_name = _normalize_text(device.get("model_name")).lower()
    manufacturer = _normalize_text(device.get("manufacturer")).lower()
    full_text = f"{type_name} {model_name} {manufacturer}".strip()
    if any(keyword in full_text for keyword in MFU_FALLBACK_KEYWORDS):
        return True

    has_network_identity = bool(_normalize_text(device.get("ip_address")) or _normalize_text(device.get("mac_address")))
    if has_network_identity and any(hint in manufacturer for hint in MFU_VENDOR_HINTS):
        return True
    return False


def _normalize_identifier(value: Any) -> str:
    text = _normalize_text(value).upper()
    if not text:
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _flatten_grouped(grouped: Dict[str, Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for locations in (grouped or {}).values():
        if not isinstance(locations, dict):
            continue
        for items in locations.values():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    result.append(item)
    return result


def _normalize_device_row(row: Dict[str, Any], db_id: Optional[str]) -> Dict[str, Any]:
    item_id = _normalize_text(_read_first(row, ["ID", "id"]))
    inv_no = _normalize_text(_read_first(row, ["INV_NO", "inv_no"]))
    serial_no = _normalize_text(_read_first(row, ["SERIAL_NO", "serial_no"]))
    hw_serial_no = _normalize_text(_read_first(row, ["HW_SERIAL_NO", "hw_serial_no"]))
    type_name = _normalize_text(_read_first(row, ["TYPE_NAME", "type_name"]), "Не указано")
    model_name = _normalize_text(_read_first(row, ["MODEL_NAME", "model_name"]), "Не указано")
    manufacturer = _normalize_text(_read_first(row, ["MANUFACTURER", "manufacturer", "VENDOR_NAME", "vendor_name"]), "Не указано")
    branch_name = _normalize_text(_read_first(row, ["BRANCH_NAME", "branch_name"]), "Не указано")
    location_name = _normalize_text(_read_first(row, ["LOCATION_NAME", "location_name", "LOCATION", "location"]), "Не указано")
    status = _normalize_text(_read_first(row, ["STATUS", "status"]), "Не указано")
    ip_address = _normalize_text(_read_first(row, ["IP_ADDRESS", "ip_address"]))
    mac_address = _normalize_text(_read_first(row, ["MAC_ADDRESS", "mac_address"]))
    employee_name = _normalize_text(_read_first(row, ["EMPLOYEE_NAME", "employee_name"]))
    employee_dept = _normalize_text(_read_first(row, ["EMPLOYEE_DEPT", "employee_dept"]))

    unique_key_parts = [
        _normalize_text(db_id or "default", "default"),
        item_id or inv_no or serial_no or hw_serial_no or "unknown",
    ]
    unique_key = "|".join(unique_key_parts)

    return {
        "key": unique_key,
        "id": item_id,
        "inv_no": inv_no,
        "serial_no": serial_no,
        "hw_serial_no": hw_serial_no,
        "type_name": type_name,
        "model_name": model_name,
        "manufacturer": manufacturer,
        "branch_name": branch_name,
        "location_name": location_name,
        "status": status,
        "ip_address": ip_address,
        "mac_address": mac_address,
        "employee_name": employee_name,
        "employee_dept": employee_dept,
    }


def _build_mfu_events_index(db_id: Optional[str], period_days: int) -> Dict[str, List[Dict[str, Any]]]:
    cache_key = f"{db_id or ''}|{period_days}"
    cached = _events_cache.get(cache_key)
    if cached and time.monotonic() - cached["ts"] < _EVENTS_CACHE_TTL_SEC:
        return cached["data"]

    stats = works_manager.get_mfu_statistics(
        period_days=period_days,
        db_name=db_id,
        max_recent=None,
    )
    events = stats.get("recent_replacements") if isinstance(stats, dict) else []
    if not isinstance(events, list):
        return {}

    by_identifier: Dict[str, List[Dict[str, Any]]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        candidates = [
            _normalize_identifier(event.get("inv_no")),
            _normalize_identifier(event.get("serial_no")),
        ]
        for identifier in candidates:
            if not identifier:
                continue
            by_identifier.setdefault(identifier, []).append(event)

    for identifier in list(by_identifier.keys()):
        by_identifier[identifier].sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)

    _events_cache[cache_key] = {"data": by_identifier, "ts": time.monotonic()}
    return by_identifier


def _collect_device_maintenance(
    device: Dict[str, Any],
    events_by_identifier: Dict[str, List[Dict[str, Any]]],
    recent_limit: int,
) -> Dict[str, Any]:
    identifiers = [
        _normalize_identifier(device.get("inv_no")),
        _normalize_identifier(device.get("serial_no")),
        _normalize_identifier(device.get("hw_serial_no")),
    ]
    identifiers = [item for item in identifiers if item]

    merged: List[Dict[str, Any]] = []
    seen = set()
    for identifier in identifiers:
        for event in events_by_identifier.get(identifier, []):
            signature = (
                str(event.get("timestamp") or ""),
                str(event.get("component_type") or ""),
                str(event.get("replacement_item") or ""),
                str(event.get("inv_no") or ""),
                str(event.get("serial_no") or ""),
            )
            if signature in seen:
                continue
            seen.add(signature)
            merged.append(event)

    merged.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    recent = merged[:recent_limit] if recent_limit > 0 else []
    return {
        "total_operations": len(merged),
        "last_operation_at": _normalize_text(merged[0].get("timestamp")) if merged else None,
        "recent": recent,
    }


@router.get("/devices")
async def get_mfu_devices(
    period_days: int = Query(365, ge=1, le=3650),
    recent_limit: int = Query(5, ge=0, le=50),
    limit: int = Query(5000, ge=1, le=10000),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(require_permission(PERM_DATABASE_READ)),
):
    """
    MFU/Printer/Plotter inventory with runtime status and maintenance history.
    """
    rows = get_all_equipment_flat(db_id=db_id, limit=max(1, limit))

    normalized_devices: List[Dict[str, Any]] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        device = _normalize_device_row(row, db_id)
        if not _is_mfu_device(device):
            continue
        normalized_devices.append(device)

    await mfu_runtime_monitor.register_devices(
        [{"key": device["key"], "ip": device.get("ip_address")} for device in normalized_devices]
    )

    events_index = _build_mfu_events_index(db_id=db_id, period_days=period_days)

    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    totals = {
        "devices": 0,
        "online": 0,
        "offline": 0,
        "unknown": 0,
        "snmp_ok": 0,
        "snmp_fresh": 0,
        "snmp_cached_active": 0,
        "snmp_error": 0,
        "snmp_unknown": 0,
        "snmp_probe_timeout_count": 0,
        "snmp_devices_in_backoff": 0,
        "snmp_active_ttl_sec": SNMP_ACTIVE_TTL_SEC,
    }
    now_utc = datetime.now(timezone.utc)
    slow_devices: List[Dict[str, Any]] = []

    for device in normalized_devices:
        runtime = await mfu_runtime_monitor.get_snapshot(device["key"])
        maintenance = _collect_device_maintenance(device, events_index, recent_limit=recent_limit)

        payload = dict(device)
        payload["runtime"] = runtime
        payload["maintenance"] = maintenance

        branch_name = _normalize_text(device.get("branch_name"), "Не указано")
        location_name = _normalize_text(device.get("location_name"), "Не указано")
        grouped.setdefault(branch_name, {}).setdefault(location_name, []).append(payload)

        totals["devices"] += 1
        ping_status = _normalize_text(runtime.get("ping", {}).get("status")).lower()
        if ping_status == "online":
            totals["online"] += 1
        elif ping_status == "offline":
            totals["offline"] += 1
        else:
            totals["unknown"] += 1

        snmp_state = runtime.get("snmp", {}) if isinstance(runtime.get("snmp"), dict) else {}
        snmp_status = _normalize_text(snmp_state.get("status")).lower()
        has_recent_success = _is_snmp_recent(snmp_state.get("last_success_at"), now_utc=now_utc, ttl_sec=SNMP_ACTIVE_TTL_SEC)

        if snmp_status in {"ok", "no_data"}:
            totals["snmp_fresh"] += 1
            totals["snmp_ok"] += 1
        elif has_recent_success:
            totals["snmp_cached_active"] += 1
            totals["snmp_ok"] += 1

        if snmp_status == "error":
            totals["snmp_error"] += 1
            if _normalize_text(snmp_state.get("error")).lower() == "probe_timeout":
                totals["snmp_probe_timeout_count"] += 1
        elif snmp_status not in {"ok", "no_data"}:
            totals["snmp_unknown"] += 1

        timeout_total = int(snmp_state.get("timeout_total") or 0)
        timeout_streak = int(snmp_state.get("timeout_streak") or 0)
        next_retry_at = _normalize_text(snmp_state.get("next_retry_at"))
        if next_retry_at:
            next_retry_dt = _parse_utc_datetime(next_retry_at)
            if next_retry_dt and next_retry_dt > now_utc:
                totals["snmp_devices_in_backoff"] += 1
        if timeout_total > 0 or timeout_streak > 0:
            slow_devices.append(
                {
                    "key": device.get("key"),
                    "host": device.get("inv_no") or device.get("serial_no") or device.get("model_name"),
                    "ip_address": device.get("ip_address"),
                    "model_name": device.get("model_name"),
                    "timeout_total": timeout_total,
                    "timeout_streak": timeout_streak,
                    "next_retry_at": next_retry_at or None,
                }
            )

    slow_devices.sort(
        key=lambda item: (
            -int(item.get("timeout_total") or 0),
            -int(item.get("timeout_streak") or 0),
            str(item.get("model_name") or ""),
        )
    )

    return {
        "generated_at": _utc_now_iso(),
        "db_id": db_id,
        "totals": totals,
        "grouped": grouped,
        "debug": {
            "raw_rows_count": len(rows),
            "matched_mfu_count": len(normalized_devices),
            "dropped_count": max(0, len(rows) - len(normalized_devices)),
            "snmp_slow_devices": slow_devices[:10],
        },
    }


@router.get("/pages/monthly")
async def get_mfu_pages_monthly(
    device_key: str = Query(..., min_length=3, max_length=255),
    months: int = Query(12, ge=1, le=36),
    _: User = Depends(require_permission(PERM_DATABASE_READ)),
):
    """
    Monthly printed pages summary for one MFU device key.
    """
    normalized_key = _normalize_text(device_key)
    summary = mfu_runtime_monitor.get_monthly_page_summary(
        device_key=normalized_key,
        months=months,
    )
    runtime = await mfu_runtime_monitor.get_snapshot(normalized_key)
    snmp_state = runtime.get("snmp", {}) if isinstance(runtime.get("snmp"), dict) else {}
    runtime_total = _to_int_or_none(snmp_state.get("page_total"))
    runtime_checked_at = _normalize_text(snmp_state.get("page_checked_at"))
    runtime_oid = _normalize_text(snmp_state.get("page_oid"))

    current_total = summary.get("current_total_pages")
    if current_total is None and runtime_total is not None:
        current_total = runtime_total
    current_checked_at = _normalize_text(summary.get("current_checked_at"))
    if not current_checked_at and runtime_checked_at:
        current_checked_at = runtime_checked_at

    return {
        "generated_at": _utc_now_iso(),
        "device_key": normalized_key,
        "months_requested": max(1, min(36, int(months))),
        "months": summary.get("months") if isinstance(summary.get("months"), list) else [],
        "current_total_pages": current_total,
        "current_checked_at": current_checked_at or None,
        "tracking_start_date": _normalize_text(summary.get("tracking_start_date")) or None,
        "page_oid": runtime_oid or None,
    }
