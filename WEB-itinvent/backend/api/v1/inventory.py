import logging
import re
import sqlite3
import time
import os
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.api.deps import ensure_user_permission, get_current_database_id, require_permission
from backend.api.v1.database import get_all_db_configs
from backend.config import config
from backend.models.auth import User
from backend.services import user_db_selection_service
from backend.services.authorization_service import PERM_COMPUTERS_READ, PERM_COMPUTERS_READ_ALL
from local_store import get_local_store

router = APIRouter()
logger = logging.getLogger(__name__)

# Legacy token for transitional compatibility.
LEGACY_DEFAULT_API_KEY = "itinvent_agent_secure_token_v1"
_LEGACY_KEY_WARNED = False

INVENTORY_FILE = "agent_inventory_cache.json"
CHANGES_FILE = "agent_inventory_changes.json"
HISTORY_RETENTION_DAYS = 90
CHANGES_WINDOW_DAYS = 30

ONLINE_MAX_AGE_SECONDS = 12 * 60
STALE_MAX_AGE_SECONDS = 60 * 60
OUTLOOK_ALLOWED_STATUS = {"ok", "warning", "critical", "unknown"}
OUTLOOK_ALLOWED_CONFIDENCE = {"high", "medium", "low"}
OUTLOOK_ALLOWED_SOURCE = {"user_helper_com", "system_scan", "none"}


def _api_key_fingerprint(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "none"
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()
    return digest[:12]


def _load_agent_api_keys() -> List[str]:
    global _LEGACY_KEY_WARNED
    keys: List[str] = []
    ring_raw = str(os.getenv("ITINV_AGENT_API_KEYS", "") or "").strip()
    if ring_raw:
        for row in ring_raw.split(","):
            key = str(row or "").strip()
            if key and key not in keys:
                keys.append(key)

    legacy_key = str(os.getenv("ITINV_AGENT_API_KEY", "") or "").strip()
    if legacy_key and legacy_key not in keys:
        keys.append(legacy_key)
    elif not keys:
        keys.append(LEGACY_DEFAULT_API_KEY)
        if not _LEGACY_KEY_WARNED:
            logger.warning(
                "Inventory API is using legacy built-in key fallback. Configure ITINV_AGENT_API_KEYS for key rotation."
            )
            _LEGACY_KEY_WARNED = True
    return keys


def _is_valid_agent_api_key(candidate: Optional[str]) -> bool:
    token = str(candidate or "").strip()
    if not token:
        return False
    keys = _load_agent_api_keys()
    return token in keys


class InventoryPayload(BaseModel):
    hostname: str
    system_serial: Optional[str] = "Unknown"
    mac_address: str
    current_user: Optional[str] = ""
    user_login: Optional[str] = ""
    user_full_name: Optional[str] = ""
    ip_primary: Optional[str] = ""
    ip_list: Optional[List[str]] = None
    cpu_model: Optional[str] = "Unknown"
    ram_gb: Optional[float] = None
    monitors: Optional[List[Dict[str, Any]]] = None
    logical_disks: Optional[List[Dict[str, Any]]] = None
    storage: Optional[List[Dict[str, Any]]] = None
    report_type: Optional[str] = "full_snapshot"
    last_seen_at: Optional[int] = None
    last_full_snapshot_at: Optional[int] = None
    os_info: Optional[Dict[str, Any]] = None
    network: Optional[Dict[str, Any]] = None
    health: Optional[Dict[str, Any]] = None
    uptime_seconds: Optional[int] = None
    cpu_load_percent: Optional[float] = None
    ram_used_percent: Optional[float] = None
    last_reboot_at: Optional[int] = None
    security: Optional[Dict[str, Any]] = None
    updates: Optional[Dict[str, Any]] = None
    outlook: Optional[Dict[str, Any]] = None
    timestamp: int


def _normalize_report_type(value: Optional[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "heartbeat":
        return "heartbeat"
    return "full_snapshot"


def _model_dump(payload: InventoryPayload) -> Dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=True)
    return payload.dict(exclude_unset=True)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _cyrillic_score(value: str) -> int:
    text = _normalize_text(value)
    cyr_count = len(re.findall(r"[А-Яа-яЁё]", text))
    mojibake_count = len(re.findall(r"[ЉЊЋЌЍЎџ®§«»ўЄЁ©…†‡‰™‹›№]", text))
    return cyr_count - (mojibake_count * 2)


def _repair_cp866_mojibake(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    if not re.search(r"[ЉЊЋЌЍЎџ®§«»ўЄЁ©…†‡‰™‹›№]", text):
        return text
    try:
        candidate = text.encode("cp1251").decode("cp866")
    except Exception:
        return text
    if _cyrillic_score(candidate) >= _cyrillic_score(text) + 3:
        return candidate
    return text


def _normalize_person_name(value: Any) -> str:
    return _repair_cp866_mojibake(value)


def _normalize_mac(value: Any) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", _normalize_text(value)).upper()


def _normalize_login(value: Any) -> str:
    return _normalize_text(value)


def _extract_mac_candidates(value: Any) -> List[str]:
    text = _normalize_text(value)
    if not text:
        return []
    matches = re.findall(
        r"(?:[0-9A-Fa-f]{2}(?:[:-])){5}[0-9A-Fa-f]{2}|[0-9A-Fa-f]{12}|[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}",
        text,
    )
    out: List[str] = []
    for raw in matches:
        normalized = _normalize_mac(raw)
        if len(normalized) != 12:
            continue
        if normalized not in out:
            out.append(normalized)
    return out


def _extract_first_ipv4(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    match = re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text)
    return match.group(0) if match else ""


def _dedupe_strings(values: List[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in values or []:
        value = _normalize_text(raw)
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _extract_ip_fields(record: Dict[str, Any]) -> Tuple[str, List[str]]:
    candidate_list = record.get("ip_list")
    if not isinstance(candidate_list, list):
        candidate_list = []

    if not candidate_list:
        network = record.get("network") if isinstance(record.get("network"), dict) else {}
        network_ipv4 = network.get("active_ipv4") if isinstance(network.get("active_ipv4"), list) else []
        candidate_list = list(network_ipv4)

    ip_list = _dedupe_strings(candidate_list)
    ip_primary = _normalize_text(record.get("ip_primary"))
    if not ip_primary and ip_list:
        ip_primary = ip_list[0]
    if ip_primary and ip_primary not in ip_list:
        ip_list.insert(0, ip_primary)
    return ip_primary, ip_list


def _network_link_payload(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "branch_id": row["branch_id"],
        "branch_name": row["branch_name"],
        "site_name": row["site_name"],
        "device_code": row["device_code"],
        "device_model": row["device_model"],
        "port_name": row["port_name"],
        "socket_code": row["socket_code"],
        "endpoint_ip_raw": row["endpoint_ip_raw"],
        "endpoint_mac_raw": row["endpoint_mac_raw"],
    }


def _ensure_identity_fields(record: Dict[str, Any]) -> None:
    user_login = _normalize_login(record.get("user_login") or record.get("current_user"))
    user_full_name = _normalize_person_name(record.get("user_full_name"))
    record["user_login"] = user_login
    record["current_user"] = user_login
    record["user_full_name"] = user_full_name

    ip_primary, ip_list = _extract_ip_fields(record)
    record["ip_primary"] = ip_primary
    record["ip_list"] = ip_list


def _ensure_runtime_fields(record: Dict[str, Any]) -> None:
    health = record.get("health") if isinstance(record.get("health"), dict) else {}

    cpu_value = _to_float(record.get("cpu_load_percent"), default=None)
    if cpu_value is None:
        cpu_value = _to_float(health.get("cpu_load_percent"), default=None)
    if cpu_value is not None:
        cpu_value = round(cpu_value, 1)
        record["cpu_load_percent"] = cpu_value
        health["cpu_load_percent"] = cpu_value

    ram_value = _to_float(record.get("ram_used_percent"), default=None)
    if ram_value is None:
        ram_value = _to_float(health.get("ram_used_percent"), default=None)
    if ram_value is not None:
        ram_value = round(ram_value, 1)
        record["ram_used_percent"] = ram_value
        health["ram_used_percent"] = ram_value

    uptime_value = _to_int(record.get("uptime_seconds"), default=-1)
    if uptime_value < 0:
        uptime_value = _to_int(health.get("uptime_seconds"), default=-1)
    if uptime_value >= 0:
        record["uptime_seconds"] = uptime_value
        health["uptime_seconds"] = uptime_value

    last_reboot_at = _to_int(
        record.get("last_reboot_at") or health.get("last_reboot_at") or health.get("boot_time"),
        default=0,
    )
    if last_reboot_at > 0:
        record["last_reboot_at"] = last_reboot_at
        health["boot_time"] = last_reboot_at
        health["last_reboot_at"] = last_reboot_at
        if not _normalize_text(health.get("last_reboot_iso")):
            health["last_reboot_iso"] = datetime.fromtimestamp(last_reboot_at).isoformat()

    record["health"] = health


def _normalize_outlook_store(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    path = _normalize_text(raw.get("path"))
    if not path:
        return None
    store_type = _normalize_text(raw.get("type")).lower()
    if not store_type:
        suffix = os.path.splitext(path)[1].lower()
        if suffix == ".ost":
            store_type = "ost"
        elif suffix == ".pst":
            store_type = "pst"
        else:
            store_type = suffix.lstrip(".")
    return {
        "path": path,
        "type": store_type,
        "size_bytes": max(0, _to_int(raw.get("size_bytes"), 0)),
        "last_modified_at": max(0, _to_int(raw.get("last_modified_at"), 0)),
    }


def _normalize_outlook_payload(raw: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "collected_at": _to_int(time.time(), 0),
        "source": "none",
        "confidence": "low",
        "status": "unknown",
        "threshold_warning_bytes": 45 * (1024 ** 3),
        "threshold_critical_bytes": 49 * (1024 ** 3),
        "active_store": None,
        "active_stores": [],
        "active_candidate": None,
        "archives": [],
        "largest_file_path": "",
        "largest_file_size_bytes": 0,
        "total_outlook_size_bytes": 0,
    }
    if not isinstance(raw, dict):
        return base

    source = _normalize_text(raw.get("source")).lower()
    confidence = _normalize_text(raw.get("confidence")).lower()
    status = _normalize_text(raw.get("status")).lower()
    if source not in OUTLOOK_ALLOWED_SOURCE:
        source = "none"
    if confidence not in OUTLOOK_ALLOWED_CONFIDENCE:
        confidence = "low"
    if status not in OUTLOOK_ALLOWED_STATUS:
        status = "unknown"

    warning_bytes = max(1, _to_int(raw.get("threshold_warning_bytes"), base["threshold_warning_bytes"]))
    critical_bytes = max(warning_bytes, _to_int(raw.get("threshold_critical_bytes"), base["threshold_critical_bytes"]))

    active_store = _normalize_outlook_store(raw.get("active_store"))
    active_stores: List[Dict[str, Any]] = []
    active_stores_raw = raw.get("active_stores")
    if isinstance(active_stores_raw, list):
        for row in active_stores_raw:
            normalized = _normalize_outlook_store(row)
            if normalized:
                active_stores.append(normalized)
    if active_store:
        active_stores.insert(0, active_store)
    if active_stores:
        deduped_active_stores: List[Dict[str, Any]] = []
        seen_paths = set()
        for row in active_stores:
            row_path = _normalize_text(row.get("path")).lower()
            if not row_path or row_path in seen_paths:
                continue
            seen_paths.add(row_path)
            deduped_active_stores.append(row)
        active_stores = deduped_active_stores
    active_store = active_stores[0] if active_stores else None
    active_candidate = _normalize_outlook_store(raw.get("active_candidate"))

    archives: List[Dict[str, Any]] = []
    archives_raw = raw.get("archives")
    if isinstance(archives_raw, list):
        for row in archives_raw:
            normalized = _normalize_outlook_store(row)
            if normalized:
                archives.append(normalized)

    active_size = 0
    if active_stores:
        active_size = max(max(0, _to_int(row.get("size_bytes"), 0)) for row in active_stores)
    if confidence in {"high", "medium"} and active_size > 0:
        if active_size >= critical_bytes:
            status = "critical"
        elif active_size >= warning_bytes:
            status = "warning"
        else:
            status = "ok"
    else:
        status = "unknown"

    return {
        "collected_at": max(0, _to_int(raw.get("collected_at"), base["collected_at"])),
        "source": source,
        "confidence": confidence,
        "status": status,
        "threshold_warning_bytes": warning_bytes,
        "threshold_critical_bytes": critical_bytes,
        "active_store": active_store,
        "active_stores": active_stores,
        "active_candidate": active_candidate,
        "archives": archives,
        "largest_file_path": _normalize_text(raw.get("largest_file_path")),
        "largest_file_size_bytes": max(0, _to_int(raw.get("largest_file_size_bytes"), 0)),
        "total_outlook_size_bytes": max(0, _to_int(raw.get("total_outlook_size_bytes"), 0)),
    }


def _enrich_outlook_fields(record: Dict[str, Any]) -> None:
    outlook = _normalize_outlook_payload(record.get("outlook"))
    active_stores = outlook.get("active_stores") if isinstance(outlook.get("active_stores"), list) else []
    active_store = outlook.get("active_store") if isinstance(outlook.get("active_store"), dict) else None
    if not active_store and active_stores:
        first_active = active_stores[0]
        if isinstance(first_active, dict):
            active_store = first_active
    archives = outlook.get("archives") if isinstance(outlook.get("archives"), list) else []
    active_size_bytes = max(0, _to_int((active_store or {}).get("size_bytes"), 0))
    if active_stores:
        active_size_bytes = max(active_size_bytes, max(max(0, _to_int(row.get("size_bytes"), 0)) for row in active_stores if isinstance(row, dict)))
    record["outlook"] = outlook
    record["outlook_status"] = _normalize_text(outlook.get("status")).lower() or "unknown"
    record["outlook_confidence"] = _normalize_text(outlook.get("confidence")).lower() or "low"
    record["outlook_active_size_bytes"] = active_size_bytes
    record["outlook_active_path"] = _normalize_text((active_store or {}).get("path"))
    record["outlook_active_stores_count"] = len([row for row in active_stores if isinstance(row, dict)])
    record["outlook_total_size_bytes"] = max(0, _to_int(outlook.get("total_outlook_size_bytes"), 0))
    record["outlook_archives_count"] = len([row for row in archives if isinstance(row, dict)])


def _merge_payload(previous: Any, incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(previous) if isinstance(previous, dict) else {}
    for key, value in incoming.items():
        if value is not None:
            merged[key] = value
    if "outlook" in incoming:
        merged["outlook"] = _normalize_outlook_payload(incoming.get("outlook"))
    _ensure_identity_fields(merged)
    _ensure_runtime_fields(merged)
    _enrich_outlook_fields(merged)
    return merged


def _enrich_status(record: Dict[str, Any], now_ts: int) -> Dict[str, Any]:
    result = dict(record)
    last_seen_raw = result.get("last_seen_at") or result.get("timestamp")
    last_seen_at = _to_int(last_seen_raw, default=0)

    if last_seen_at <= 0:
        result["status"] = "unknown"
        result["age_seconds"] = None
        result["last_seen_at"] = None
        return result

    age_seconds = max(0, now_ts - last_seen_at)
    if age_seconds <= ONLINE_MAX_AGE_SECONDS:
        status_value = "online"
    elif age_seconds <= STALE_MAX_AGE_SECONDS:
        status_value = "stale"
    else:
        status_value = "offline"

    result["status"] = status_value
    result["age_seconds"] = age_seconds
    result["last_seen_at"] = last_seen_at
    return result


def _signature_monitors(record: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    rows = record.get("monitors") if isinstance(record.get("monitors"), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        serial = _normalize_text(row.get("serial_number"))
        manufacturer = _normalize_text(row.get("manufacturer")).lower()
        product = _normalize_text(row.get("product_code")).lower()
        token = f"{serial.lower()}|{manufacturer}|{product}"
        if token.strip("|"):
            values.append(token)
    return sorted(set(values))


def _signature_storage(record: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    rows = record.get("storage") if isinstance(record.get("storage"), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        serial = _normalize_text(row.get("serial_number"))
        model = _normalize_text(row.get("model")).lower()
        bus = _normalize_text(row.get("bus_type")).lower()
        token = f"{serial.lower()}|{model}|{bus}"
        if token.strip("|"):
            values.append(token)
    return sorted(set(values))


def _signature_system(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "system_serial": _normalize_text(record.get("system_serial")),
        "cpu_model": _normalize_text(record.get("cpu_model")),
        "ram_gb": float(record.get("ram_gb") or 0),
    }


def _build_hardware_signature(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "system": _signature_system(record),
        "monitors": _signature_monitors(record),
        "storage": _signature_storage(record),
    }


def _build_signature_diff(before_sig: Dict[str, Any], after_sig: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    diff: Dict[str, Dict[str, Any]] = {}
    for key in ("system", "monitors", "storage"):
        before_value = before_sig.get(key)
        after_value = after_sig.get(key)
        if before_value != after_value:
            diff[key] = {"before": before_value, "after": after_value}
    return diff


def _load_changes(store: Any) -> List[Dict[str, Any]]:
    payload = store.load_json(CHANGES_FILE, default_content=[])
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def _prune_old_changes(rows: List[Dict[str, Any]], now_ts: int) -> List[Dict[str, Any]]:
    cutoff = now_ts - HISTORY_RETENTION_DAYS * 24 * 60 * 60
    out = []
    for row in rows:
        ts = _to_int(row.get("detected_at"), default=0)
        if ts <= 0:
            continue
        if ts >= cutoff:
            out.append(row)
    return out


def _event_host_key(mac_address: str, hostname: str) -> str:
    normalized_mac = _normalize_mac(mac_address)
    if normalized_mac:
        return f"mac:{normalized_mac}"
    normalized_host = _normalize_text(hostname).lower()
    return f"host:{normalized_host}"


def _add_hardware_change_event(
    changes: List[Dict[str, Any]],
    previous_record: Optional[Dict[str, Any]],
    merged_record: Dict[str, Any],
    current_ts: int,
) -> None:
    if not isinstance(previous_record, dict):
        merged_record["_hardware_signature"] = _build_hardware_signature(merged_record)
        return

    previous_sig = previous_record.get("_hardware_signature")
    if not isinstance(previous_sig, dict):
        previous_sig = _build_hardware_signature(previous_record)

    current_sig = _build_hardware_signature(merged_record)
    merged_record["_hardware_signature"] = current_sig

    diff = _build_signature_diff(previous_sig, current_sig)
    if not diff:
        return

    mac_address = _normalize_text(merged_record.get("mac_address"))
    hostname = _normalize_text(merged_record.get("hostname"))
    change_types = sorted(diff.keys())

    event = {
        "event_id": f"{_event_host_key(mac_address, hostname)}:{current_ts}",
        "detected_at": current_ts,
        "mac_address": mac_address,
        "hostname": hostname,
        "change_types": change_types,
        "diff": diff,
        "report_type": _normalize_text(merged_record.get("report_type")) or "full_snapshot",
    }
    changes.append(event)


def _build_changes_index(changes: List[Dict[str, Any]], now_ts: int) -> Dict[str, Dict[str, Any]]:
    since_30d = now_ts - CHANGES_WINDOW_DAYS * 24 * 60 * 60
    index: Dict[str, Dict[str, Any]] = {}

    sorted_changes = sorted(changes, key=lambda item: _to_int(item.get("detected_at"), 0), reverse=True)
    for event in sorted_changes:
        ts = _to_int(event.get("detected_at"), 0)
        if ts <= 0:
            continue
        key = _event_host_key(_normalize_text(event.get("mac_address")), _normalize_text(event.get("hostname")))
        entry = index.setdefault(
            key,
            {
                "last_change_at": None,
                "changes_count_30d": 0,
                "recent_changes": [],
            },
        )
        if entry["last_change_at"] is None:
            entry["last_change_at"] = ts
        if ts >= since_30d:
            entry["changes_count_30d"] += 1
        if len(entry["recent_changes"]) < 5:
            entry["recent_changes"].append(event)

    return index


def _resolve_sql_context(mac_address: str, hostname: str, db_id: Optional[str]) -> Optional[Dict[str, Any]]:
    try:
        from backend.database import queries

        return queries.resolve_pc_context_by_mac_or_hostname(
            mac_address=mac_address,
            hostname=hostname,
            db_id=db_id,
        )
    except Exception as exc:
        logger.debug("SQL context resolution skipped: %s", exc)
        return None


def _normalize_scope(value: Any) -> Literal["selected", "all"]:
    scope = _normalize_text(value).lower()
    if scope == "all":
        return "all"
    return "selected"


def _get_available_db_ids() -> List[str]:
    ids: List[str] = []
    try:
        for item in get_all_db_configs():
            db_id = _normalize_text(item.get("id"))
            if db_id and db_id not in ids:
                ids.append(db_id)
    except Exception:
        pass
    default_db_id = _normalize_text(config.database.database)
    if default_db_id and default_db_id not in ids:
        ids.append(default_db_id)
    return ids


def _get_database_name_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    try:
        for item in get_all_db_configs():
            db_id = _normalize_text(item.get("id"))
            if not db_id:
                continue
            mapping[db_id] = _normalize_text(item.get("name")) or db_id
    except Exception:
        pass
    default_db_id = _normalize_text(config.database.database)
    if default_db_id and default_db_id not in mapping:
        mapping[default_db_id] = default_db_id
    return mapping


def _get_accessible_db_ids(current_user: User) -> List[str]:
    all_db_ids = _get_available_db_ids()
    assigned_database = _normalize_text(getattr(current_user, "assigned_database", ""))
    if not assigned_database:
        assigned_database = _normalize_text(
            user_db_selection_service.get_assigned_database(getattr(current_user, "telegram_id", None))
        )
    is_admin = _normalize_text(getattr(current_user, "role", "")).lower() == "admin"
    if assigned_database and not is_admin:
        return [assigned_database]
    return all_db_ids


def _resolve_network_link(
    conn: Optional[sqlite3.Connection],
    mac_address: str,
    ip_list: List[str],
) -> Optional[Dict[str, Any]]:
    if conn is None:
        return None

    normalized_mac = _normalize_mac(mac_address)
    normalized_ips = _dedupe_strings(ip_list)
    conditions: List[str] = []
    params: List[Any] = []

    if normalized_mac:
        conditions.append(
            "UPPER(REPLACE(REPLACE(COALESCE(ns.mac_address, p.endpoint_mac_raw, ''), ':', ''), '-', '')) = ?"
        )
        params.append(normalized_mac)

    for ip in normalized_ips:
        conditions.append("COALESCE(p.endpoint_ip_raw, '') LIKE ?")
        params.append(f"%{ip}%")

    if not conditions:
        return None

    mac_case_expr = "1"
    if normalized_mac:
        mac_case_expr = (
            "CASE WHEN UPPER(REPLACE(REPLACE(COALESCE(ns.mac_address, p.endpoint_mac_raw, ''), ':', ''), '-', '')) = ? "
            "THEN 0 ELSE 1 END"
        )
        params.append(normalized_mac)

    query = f"""
        SELECT
            b.id as branch_id,
            b.name as branch_name,
            s.name as site_name,
            d.device_code,
            d.model as device_model,
            p.port_name,
            COALESCE(ns.socket_code, p.patch_panel_port) as socket_code,
            p.endpoint_ip_raw,
            COALESCE(ns.mac_address, p.endpoint_mac_raw) as endpoint_mac_raw
        FROM network_ports p
        JOIN network_devices d ON d.id = p.device_id
        LEFT JOIN network_branches b ON b.id = d.branch_id
        LEFT JOIN network_sites s ON s.id = d.site_id
        LEFT JOIN network_sockets ns ON ns.port_id = p.id
        WHERE {' OR '.join(conditions)}
        ORDER BY {mac_case_expr}, p.is_occupied DESC, p.updated_at DESC
        LIMIT 1
    """

    try:
        row = conn.execute(query, params).fetchone()
    except Exception:
        return None

    if row is not None:
        return _network_link_payload(row)

    # Fallback for rows where multiple MAC addresses are stored in one endpoint_mac_raw cell.
    if normalized_mac:
        try:
            fallback_rows = conn.execute(
                """
                SELECT
                    b.id as branch_id,
                    b.name as branch_name,
                    s.name as site_name,
                    d.device_code,
                    d.model as device_model,
                    p.port_name,
                    COALESCE(ns.socket_code, p.patch_panel_port) as socket_code,
                    p.endpoint_ip_raw,
                    COALESCE(ns.mac_address, p.endpoint_mac_raw) as endpoint_mac_raw,
                    ns.mac_address as socket_mac_raw,
                    p.endpoint_mac_raw as port_mac_raw
                FROM network_ports p
                JOIN network_devices d ON d.id = p.device_id
                LEFT JOIN network_branches b ON b.id = d.branch_id
                LEFT JOIN network_sites s ON s.id = d.site_id
                LEFT JOIN network_sockets ns ON ns.port_id = p.id
                WHERE COALESCE(ns.mac_address, '') <> '' OR COALESCE(p.endpoint_mac_raw, '') <> ''
                ORDER BY p.is_occupied DESC, p.updated_at DESC
                LIMIT 4000
                """
            ).fetchall()
        except Exception:
            fallback_rows = []

        for candidate in fallback_rows:
            mac_tokens = _extract_mac_candidates(candidate["socket_mac_raw"]) + _extract_mac_candidates(candidate["port_mac_raw"])
            if normalized_mac in mac_tokens:
                return _network_link_payload(candidate)

    return None


def _apply_search_filter(records: List[Dict[str, Any]], query_text: str) -> List[Dict[str, Any]]:
    needle = _normalize_text(query_text).lower()
    if not needle:
        return records

    out: List[Dict[str, Any]] = []
    for item in records:
        network_link = item.get("network_link") if isinstance(item.get("network_link"), dict) else {}
        haystack = " ".join(
            [
                _normalize_text(item.get("hostname")),
                _normalize_text(item.get("user_full_name")),
                _normalize_text(item.get("user_login")),
                _normalize_text(item.get("mac_address")),
                _normalize_text(item.get("ip_primary")),
                _normalize_text(item.get("branch_name")),
                _normalize_text(item.get("location_name")),
                _normalize_text(item.get("database_name")),
                _normalize_text(item.get("database_id")),
                _normalize_text(item.get("outlook_active_path")),
                _normalize_text((item.get("outlook") or {}).get("largest_file_path") if isinstance(item.get("outlook"), dict) else ""),
                _normalize_text(network_link.get("device_code")),
                _normalize_text(network_link.get("port_name")),
                _normalize_text(network_link.get("socket_code")),
            ]
        ).lower()
        if needle in haystack:
            out.append(item)
    return out


@router.post("")
async def receive_inventory(
    payload: InventoryPayload,
    x_api_key: Optional[str] = Header(None),
):
    """
    Receive inventory data from PC agents.
    """
    if not _is_valid_agent_api_key(x_api_key):
        logger.warning("Inventory rejected unknown agent key fingerprint=%s", _api_key_fingerprint(x_api_key))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    store = get_local_store()
    current_data = store.load_json(INVENTORY_FILE, default_content={})
    if not isinstance(current_data, dict):
        current_data = {}

    incoming_payload = _model_dump(payload)
    _ensure_identity_fields(incoming_payload)

    report_type = _normalize_report_type(incoming_payload.get("report_type"))
    current_ts = _to_int(incoming_payload.get("timestamp") or time.time(), default=int(time.time()))
    last_seen_at = _to_int(incoming_payload.get("last_seen_at") or current_ts, default=current_ts)

    mac_key = _normalize_text(incoming_payload.get("mac_address"))
    if not mac_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mac_address is required",
        )

    previous_record = current_data.get(mac_key)
    merged = _merge_payload(previous_record, incoming_payload)
    merged["report_type"] = report_type
    merged["timestamp"] = current_ts
    merged["last_seen_at"] = last_seen_at

    changes = _load_changes(store)
    changes = _prune_old_changes(changes, current_ts)

    if report_type == "full_snapshot":
        merged["last_full_snapshot_at"] = current_ts
        _add_hardware_change_event(changes, previous_record, merged, current_ts)
    elif not merged.get("last_full_snapshot_at"):
        merged["last_full_snapshot_at"] = current_ts

    current_data[mac_key] = merged

    if not store.save_json(INVENTORY_FILE, current_data):
        logger.error("Failed to save inventory to local store")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save data",
        )

    if not store.save_json(CHANGES_FILE, changes):
        logger.warning("Failed to save inventory change history")

    return {"success": True, "message": "Inventory updated successfully"}


@router.get("/changes")
async def get_inventory_changes(
    limit: int = Query(50, ge=1, le=200),
):
    store = get_local_store()
    now_ts = int(time.time())
    changes = _prune_old_changes(_load_changes(store), now_ts)
    sorted_changes = sorted(changes, key=lambda item: _to_int(item.get("detected_at"), 0), reverse=True)

    def _unique_hosts_since(seconds_back: int) -> int:
        threshold = now_ts - seconds_back
        keys = {
            _event_host_key(_normalize_text(item.get("mac_address")), _normalize_text(item.get("hostname")))
            for item in sorted_changes
            if _to_int(item.get("detected_at"), 0) >= threshold
        }
        return len(keys)

    daily_map: Dict[str, int] = {}
    for item in sorted_changes:
        ts = _to_int(item.get("detected_at"), 0)
        if ts <= 0:
            continue
        if ts < now_ts - CHANGES_WINDOW_DAYS * 24 * 60 * 60:
            continue
        day_key = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        daily_map[day_key] = daily_map.get(day_key, 0) + 1

    daily_rows: List[Dict[str, Any]] = []
    start_day = datetime.fromtimestamp(now_ts, tz=timezone.utc).date() - timedelta(days=CHANGES_WINDOW_DAYS - 1)
    for offset in range(CHANGES_WINDOW_DAYS):
        current_day = start_day + timedelta(days=offset)
        day_key = current_day.strftime("%Y-%m-%d")
        daily_rows.append({"date": day_key, "count": int(daily_map.get(day_key, 0))})

    return {
        "totals": {
            "changed_24h": _unique_hosts_since(24 * 60 * 60),
            "changed_7d": _unique_hosts_since(7 * 24 * 60 * 60),
            "changed_30d": _unique_hosts_since(30 * 24 * 60 * 60),
        },
        "daily": daily_rows,
        "latest_events": sorted_changes[: int(limit)],
    }


@router.get("/computers")
async def get_computers(
    current_user: User = Depends(require_permission(PERM_COMPUTERS_READ)),
    db_id_selected: Optional[str] = Depends(get_current_database_id),
    scope: str = Query("selected"),
    branch: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    outlook_status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sort_by: str = Query("hostname"),
    sort_dir: str = Query("asc"),
    changed_only: bool = Query(False),
):
    """
    Return all collected computers from local store.
    """
    store = get_local_store()
    current_data = store.load_json(INVENTORY_FILE, default_content={})
    if not isinstance(current_data, dict):
        return []

    now_ts = int(time.time())
    changes = _prune_old_changes(_load_changes(store), now_ts)
    changes_index = _build_changes_index(changes, now_ts)

    requested_scope = _normalize_scope(scope)
    if requested_scope == "all":
        ensure_user_permission(current_user, PERM_COMPUTERS_READ_ALL)

    database_name_map = _get_database_name_map()
    accessible_db_ids = _get_accessible_db_ids(current_user)
    if requested_scope == "all":
        db_candidates = list(accessible_db_ids)
    else:
        selected_db = _normalize_text(db_id_selected) or _normalize_text(config.database.database)
        db_candidates = [selected_db]

    db_candidates = [_normalize_text(item) for item in db_candidates if _normalize_text(item)]
    if not db_candidates:
        fallback_db = _normalize_text(config.database.database)
        if fallback_db:
            db_candidates = [fallback_db]

    sql_cache: Dict[str, Optional[Dict[str, Any]]] = {}
    network_cache: Dict[str, Optional[Dict[str, Any]]] = {}
    network_conn: Optional[sqlite3.Connection] = None
    try:
        network_conn = sqlite3.connect(str(store.db_path), timeout=5)
        network_conn.row_factory = sqlite3.Row
    except Exception:
        network_conn = None

    records: List[Dict[str, Any]] = []

    try:
        for item in current_data.values():
            if not isinstance(item, dict):
                continue

            record = _enrich_status(item, now_ts)
            _ensure_identity_fields(record)
            _ensure_runtime_fields(record)
            _enrich_outlook_fields(record)

            mac_address = _normalize_text(record.get("mac_address"))
            hostname = _normalize_text(record.get("hostname"))
            cache_key = f"{_normalize_mac(mac_address)}|{hostname.lower()}|{','.join(db_candidates)}"
            if cache_key not in sql_cache:
                resolved_context: Optional[Dict[str, Any]] = None
                for candidate_db in db_candidates:
                    context = _resolve_sql_context(mac_address, hostname, candidate_db)
                    if not isinstance(context, dict):
                        continue
                    resolved_context = dict(context)
                    resolved_context["database_id"] = candidate_db
                    resolved_context["database_name"] = database_name_map.get(candidate_db, candidate_db)
                    break
                sql_cache[cache_key] = resolved_context

            sql_context = sql_cache.get(cache_key)
            if not isinstance(sql_context, dict):
                # Strict DB filtering: show PCs only when they exist in selected/allowed DB scope.
                continue

            record["branch_no"] = sql_context.get("branch_no")
            record["branch_name"] = _normalize_text(sql_context.get("branch_name"))
            record["location_name"] = _normalize_text(sql_context.get("location_name"))
            record["branch_source"] = "sql"
            record["database_id"] = _normalize_text(sql_context.get("database_id"))
            record["database_name"] = _normalize_text(sql_context.get("database_name")) or record["database_id"]
            if not record.get("user_full_name"):
                record["user_full_name"] = _normalize_person_name(sql_context.get("employee_name"))

            record_ip_list = record.get("ip_list") if isinstance(record.get("ip_list"), list) else []
            network_key = f"{_normalize_mac(mac_address)}|{','.join(_dedupe_strings(record_ip_list))}"
            if network_key not in network_cache:
                network_cache[network_key] = _resolve_network_link(
                    network_conn,
                    mac_address=mac_address,
                    ip_list=record_ip_list,
                )
            record["network_link"] = network_cache.get(network_key)

            ip_primary = _normalize_text(record.get("ip_primary"))
            ip_list = record.get("ip_list") if isinstance(record.get("ip_list"), list) else []
            if not ip_primary and isinstance(sql_context, dict):
                ip_primary = _extract_first_ipv4(sql_context.get("ip_address"))
            if not ip_primary and isinstance(record.get("network_link"), dict):
                ip_primary = _extract_first_ipv4(record["network_link"].get("endpoint_ip_raw"))
            if ip_primary and ip_primary not in ip_list:
                ip_list = [ip_primary] + [item for item in ip_list if _normalize_text(item) and _normalize_text(item) != ip_primary]
            record["ip_primary"] = ip_primary
            record["ip_list"] = _dedupe_strings(ip_list)

            change_key = _event_host_key(mac_address, hostname)
            change_meta = changes_index.get(change_key, {})
            last_change_at = change_meta.get("last_change_at")
            changes_count_30d = int(change_meta.get("changes_count_30d") or 0)
            record["last_change_at"] = last_change_at
            record["changes_count_30d"] = changes_count_30d
            record["has_hardware_changes"] = changes_count_30d > 0
            record["recent_changes"] = change_meta.get("recent_changes") or []

            record.pop("_hardware_signature", None)
            records.append(record)
    finally:
        if network_conn is not None:
            try:
                network_conn.close()
            except Exception:
                pass

    if branch:
        branch_lower = _normalize_text(branch).lower()
        records = [
            item for item in records if branch_lower in _normalize_text(item.get("branch_name")).lower()
        ]

    if status_filter:
        target_status = _normalize_text(status_filter).lower()
        records = [
            item for item in records if _normalize_text(item.get("status")).lower() == target_status
        ]

    if outlook_status:
        target_outlook_status = _normalize_text(outlook_status).lower()
        if target_outlook_status in OUTLOOK_ALLOWED_STATUS:
            records = [
                item for item in records if _normalize_text(item.get("outlook_status")).lower() == target_outlook_status
            ]

    if changed_only:
        records = [item for item in records if bool(item.get("has_hardware_changes"))]

    if q:
        records = _apply_search_filter(records, q)

    reverse = _normalize_text(sort_dir).lower() == "desc"
    normalized_sort_by = _normalize_text(sort_by).lower() or "hostname"

    def _sort_key(item: Dict[str, Any]) -> Any:
        if normalized_sort_by in {
            "age",
            "age_seconds",
            "last_seen_at",
            "last_change_at",
            "changes_count_30d",
            "outlook_active_size_bytes",
            "outlook_total_size_bytes",
            "outlook_archives_count",
        }:
            return _to_int(item.get(normalized_sort_by), default=0)
        if normalized_sort_by == "status":
            order = {"online": 0, "stale": 1, "offline": 2, "unknown": 3}
            return order.get(_normalize_text(item.get("status")).lower(), 9)
        if normalized_sort_by == "outlook_status":
            order = {"critical": 0, "warning": 1, "unknown": 2, "ok": 3}
            return order.get(_normalize_text(item.get("outlook_status")).lower(), 9)
        if normalized_sort_by == "branch":
            return _normalize_text(item.get("branch_name")).lower()
        if normalized_sort_by == "user":
            return (
                _normalize_text(item.get("user_full_name")).lower(),
                _normalize_text(item.get("user_login")).lower(),
            )
        return _normalize_text(item.get(normalized_sort_by)).lower()

    records.sort(key=_sort_key, reverse=reverse)
    return records
