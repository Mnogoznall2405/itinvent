import argparse
import ctypes
import getpass
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import random
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse, urlunparse

import psutil
import requests

try:
    import wmi  # type: ignore
except Exception:
    wmi = None

try:
    import winreg  # type: ignore
except Exception:
    winreg = None


DEFAULT_SERVER_URL = "https://hubit.zsgp.ru/api/v1/inventory"
DEFAULT_API_KEY = "itinvent_agent_secure_token_v1"
DEFAULT_FULL_SNAPSHOT_INTERVAL = 3600
DEFAULT_HEARTBEAT_INTERVAL = 300
DEFAULT_HEARTBEAT_JITTER = 60
DEFAULT_OUTLOOK_REFRESH_SEC = 300
DEFAULT_RUN_CMD_TIMEOUT_SEC = 20
DEFAULT_INVENTORY_QUEUE_BATCH = 50
DEFAULT_INVENTORY_QUEUE_MAX_ITEMS = 1000
DEFAULT_INVENTORY_QUEUE_MAX_AGE_DAYS = 14
DEFAULT_INVENTORY_QUEUE_MAX_TOTAL_MB = 256
DEFAULT_REBOOT_REMINDER_DAYS = 7
DEFAULT_REBOOT_REMINDER_INTERVAL_HOURS = 24
DEFAULT_REBOOT_REMINDER_TIMEOUT_SEC = 120
DEFAULT_REBOOT_REMINDER_WORK_START_HOUR = 9
DEFAULT_REBOOT_REMINDER_WORK_END_HOUR = 18
DEFAULT_OUTLOOK_SCAN_STATE_MAX_AGE_SEC = 30 * 24 * 60 * 60
OUTLOOK_WARNING_THRESHOLD_BYTES = 45 * (1024 ** 3)
OUTLOOK_CRITICAL_THRESHOLD_BYTES = 49 * (1024 ** 3)
TIMEOUT = 10
STATUS_WRITE_INTERVAL_SEC = 30
AGENT_VERSION = "1.2.0"

PROGRAM_DATA_ROOT = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "IT-Invent"
PROGRAM_DATA_DIR = PROGRAM_DATA_ROOT / "Logs"
PROGRAM_DATA_SPOOL_DIR = PROGRAM_DATA_ROOT / "Spool"
TEMP_DIR = Path(os.environ.get("TEMP", r"C:\Windows\Temp"))
LOG_FILE_NAME = "itinvent_agent.log"
INVENTORY_QUEUE_DIR_NAME = "inventory"
INVENTORY_QUEUE_PENDING_DIR_NAME = "pending"
INVENTORY_QUEUE_DEAD_DIR_NAME = "dead_letter"
REBOOT_REMINDER_STATE_FILE_NAME = "reboot_reminder_state.json"
AGENT_STATUS_FILE_NAME = "agent_status.json"
OUTLOOK_SCAN_STATE_FILE_NAME = "outlook_scan_state.json"
ENV_FILE_NAME = ".env"
REBOOT_REMINDER_MESSAGE = (
    "Компьютер работает более 7 дней без перезагрузки. "
    "Рекомендуется перезагрузить его для стабильной работы и установки обновлений."
)

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SERVICE_USERS = {
    "system",
    "nt authority\\system",
    "local service",
    "nt authority\\local service",
    "network service",
    "nt authority\\network service",
}

ACTIVE_SESSION_MARKERS = {"active", "активно"}
WINDOWS_SID_RE = re.compile(r"^S-\d-\d+(?:-\d+)+$")
OUTLOOK_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
OUTLOOK_ARCHIVE_NAME_RE = re.compile(r"^(archive|архив)(?:$|[ _.\-].*)", re.IGNORECASE)

VIRTUAL_BUS_MARKERS = (
    "virtual",
    "file backed",
    "storage spaces",
    "spaces",
    "ram",
)

VIRTUAL_MODEL_MARKERS = (
    "virtual",
    "vmware",
    "vbox",
    "virtualbox",
    "hyper-v",
    "qemu",
    "msft virtual",
)

LOGICAL_MOUNT_SKIP_MARKERS = (
    "\\windows\\containers\\",
    "\\programdata\\docker\\",
    "\\docker\\windowsfilter\\",
    "\\containerstorage\\",
)

GENERIC_DISK_NAME_VALUES = {
    "disk",
    "disk drive",
    "fixed hard disk media",
    "physical disk",
    "physicaldisk",
    "scsi disk device",
    "unknown",
}

GENERIC_DISK_NAME_SUFFIXES = (
    "scsi disk device",
    "ata device",
)

BUS_TYPE_LABELS = {
    "nvme": "NVMe",
    "sata": "SATA",
    "sas": "SAS",
    "scsi": "SCSI",
    "raid": "RAID",
    "usb": "USB",
    "sd": "SD",
}


@dataclass(frozen=True)
class AgentConfig:
    server_url: str
    api_key: str
    full_snapshot_interval: int
    heartbeat_interval: int
    heartbeat_jitter_sec: int
    outlook_refresh_sec: int = DEFAULT_OUTLOOK_REFRESH_SEC
    run_cmd_timeout_sec: int = DEFAULT_RUN_CMD_TIMEOUT_SEC
    inventory_queue_batch: int = DEFAULT_INVENTORY_QUEUE_BATCH
    inventory_queue_max_items: int = DEFAULT_INVENTORY_QUEUE_MAX_ITEMS
    inventory_queue_max_age_days: int = DEFAULT_INVENTORY_QUEUE_MAX_AGE_DAYS
    inventory_queue_max_total_mb: int = DEFAULT_INVENTORY_QUEUE_MAX_TOTAL_MB
    reboot_reminder_enabled: bool = True
    reboot_reminder_days: int = DEFAULT_REBOOT_REMINDER_DAYS
    reboot_reminder_interval_hours: int = DEFAULT_REBOOT_REMINDER_INTERVAL_HOURS
    reboot_reminder_timeout_sec: int = DEFAULT_REBOOT_REMINDER_TIMEOUT_SEC
    reboot_reminder_work_start_hour: int = DEFAULT_REBOOT_REMINDER_WORK_START_HOUR
    reboot_reminder_work_end_hour: int = DEFAULT_REBOOT_REMINDER_WORK_END_HOUR
    reboot_reminder_weekdays_only: bool = True
    ca_bundle: Optional[str] = None
    timeout: int = TIMEOUT


INVENTORY_QUEUE_PENDING_PATH: Optional[Path] = None
INVENTORY_QUEUE_DEAD_PATH: Optional[Path] = None
REBOOT_REMINDER_STATE_PATH: Optional[Path] = None
AGENT_STATUS_PATH: Optional[Path] = None
OUTLOOK_SCAN_STATE_PATH: Optional[Path] = None
LOADED_ENV_FILES: List[str] = []
RUN_CMD_TIMEOUT_SEC = DEFAULT_RUN_CMD_TIMEOUT_SEC
OUTLOOK_SCAN_CACHE_TTL_SEC = DEFAULT_OUTLOOK_REFRESH_SEC
OUTLOOK_RUNTIME_CACHE: Dict[str, Any] = {"user": "", "collected_at": 0, "payload": None}


def _is_truthy(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    return text not in {"0", "false", "no", "off"}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp.{uuid.uuid4().hex}")
    temp_path.write_text(content, encoding=encoding)
    os.replace(str(temp_path), str(path))


def _strip_env_value(raw: str) -> str:
    value = str(raw or "").strip()
    if len(value) >= 2 and ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
        return value[1:-1]
    return value


def _read_text_with_fallback(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return ""


def _load_env_file(path: Path) -> int:
    if not path.exists() or not path.is_file():
        return 0
    text = _read_text_with_fallback(path)
    if not text:
        return 0

    loaded = 0
    for line in text.splitlines():
        row = line.strip()
        if not row or row.startswith("#"):
            continue
        if row.lower().startswith("export "):
            row = row[7:].strip()
        if "=" not in row:
            continue
        key, value = row.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if key in os.environ:
            continue
        os.environ[key] = _strip_env_value(value)
        loaded += 1
    return loaded


def _candidate_env_paths() -> List[Path]:
    candidates: List[Path] = []
    explicit_path = str(os.getenv("ITINV_AGENT_ENV_FILE", "")).strip()
    if explicit_path:
        candidates.append(Path(explicit_path))

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / ENV_FILE_NAME)
    else:
        current_file = Path(__file__).resolve()
        candidates.append(current_file.parent / ENV_FILE_NAME)
        for parent in list(current_file.parents)[:4]:
            candidates.append(parent / ENV_FILE_NAME)
    candidates.append(Path.cwd() / ENV_FILE_NAME)
    candidates.append(PROGRAM_DATA_ROOT / ENV_FILE_NAME)
    return candidates


def bootstrap_env_from_files() -> List[str]:
    loaded: List[str] = []
    seen = set()
    for raw_path in _candidate_env_paths():
        try:
            resolved = raw_path.expanduser().resolve()
        except Exception:
            resolved = raw_path
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        count = _load_env_file(resolved)
        if count > 0:
            loaded.append(f"{resolved} ({count})")
    return loaded


def _run_scan_sidecar(run_once: bool = False) -> None:
    if not _is_truthy(os.getenv("ITINV_SCAN_ENABLED", "1"), default=True):
        logging.info("Scan sidecar is disabled by ITINV_SCAN_ENABLED")
        return
    try:
        from scan_agent import agent as scan_agent_module  # type: ignore
    except Exception as exc:
        logging.warning("Scan sidecar import failed: %s", exc)
        return

    try:
        scan_config = scan_agent_module._read_env()
        if not str(scan_config.get("api_key") or "").strip():
            logging.error("Scan sidecar is disabled: SCAN_AGENT_API_KEY is not configured")
            return
        scan_agent = scan_agent_module.ScanAgent(scan_config)
        if run_once:
            stats = scan_agent.run_scan_once()
            logging.info("Scan sidecar one-shot done: %s", stats)
            return
        scan_agent.run_forever()
    except Exception as exc:
        logging.exception("Scan sidecar crashed: %s", exc)


def setup_logging() -> Path:
    """Configure file logging in ProgramData with fallback to TEMP."""
    global INVENTORY_QUEUE_PENDING_PATH, INVENTORY_QUEUE_DEAD_PATH, REBOOT_REMINDER_STATE_PATH, AGENT_STATUS_PATH, OUTLOOK_SCAN_STATE_PATH
    log_dir = PROGRAM_DATA_DIR
    spool_dir = PROGRAM_DATA_SPOOL_DIR
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        spool_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        log_dir = TEMP_DIR
        spool_dir = TEMP_DIR
        log_dir.mkdir(parents=True, exist_ok=True)
        spool_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / LOG_FILE_NAME
    handlers: List[logging.Handler] = [
        RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    ]

    if sys.stdout and hasattr(sys.stdout, "isatty"):
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
    queue_root = spool_dir / INVENTORY_QUEUE_DIR_NAME
    INVENTORY_QUEUE_PENDING_PATH = queue_root / INVENTORY_QUEUE_PENDING_DIR_NAME
    INVENTORY_QUEUE_DEAD_PATH = queue_root / INVENTORY_QUEUE_DEAD_DIR_NAME
    INVENTORY_QUEUE_PENDING_PATH.mkdir(parents=True, exist_ok=True)
    INVENTORY_QUEUE_DEAD_PATH.mkdir(parents=True, exist_ok=True)
    REBOOT_REMINDER_STATE_PATH = log_dir / REBOOT_REMINDER_STATE_FILE_NAME
    AGENT_STATUS_PATH = log_dir / AGENT_STATUS_FILE_NAME
    OUTLOOK_SCAN_STATE_PATH = log_dir / OUTLOOK_SCAN_STATE_FILE_NAME
    return log_path


def get_inventory_queue_pending_dir() -> Path:
    if INVENTORY_QUEUE_PENDING_PATH is not None:
        return INVENTORY_QUEUE_PENDING_PATH
    return TEMP_DIR / INVENTORY_QUEUE_DIR_NAME / INVENTORY_QUEUE_PENDING_DIR_NAME


def get_inventory_queue_dead_dir() -> Path:
    if INVENTORY_QUEUE_DEAD_PATH is not None:
        return INVENTORY_QUEUE_DEAD_PATH
    return TEMP_DIR / INVENTORY_QUEUE_DIR_NAME / INVENTORY_QUEUE_DEAD_DIR_NAME


def get_reboot_reminder_state_path() -> Path:
    if REBOOT_REMINDER_STATE_PATH is not None:
        return REBOOT_REMINDER_STATE_PATH
    return TEMP_DIR / REBOOT_REMINDER_STATE_FILE_NAME


def get_agent_status_path() -> Path:
    if AGENT_STATUS_PATH is not None:
        return AGENT_STATUS_PATH
    return TEMP_DIR / AGENT_STATUS_FILE_NAME


def get_outlook_scan_state_path() -> Path:
    if OUTLOOK_SCAN_STATE_PATH is not None:
        return OUTLOOK_SCAN_STATE_PATH
    return TEMP_DIR / OUTLOOK_SCAN_STATE_FILE_NAME


def _empty_outlook_payload() -> Dict[str, Any]:
    return {
        "collected_at": int(time.time()),
        "source": "none",
        "confidence": "low",
        "status": "unknown",
        "threshold_warning_bytes": OUTLOOK_WARNING_THRESHOLD_BYTES,
        "threshold_critical_bytes": OUTLOOK_CRITICAL_THRESHOLD_BYTES,
        "active_store": None,
        "active_stores": [],
        "active_candidate": None,
        "archives": [],
        "largest_file_path": "",
        "largest_file_size_bytes": 0,
        "total_outlook_size_bytes": 0,
    }


def _normalize_outlook_store(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    path = sanitize_text(value.get("path"))
    if not path:
        return None
    store_type = sanitize_text(value.get("type")).lower()
    if not store_type:
        suffix = Path(path).suffix.lower()
        if suffix == ".ost":
            store_type = "ost"
        elif suffix == ".pst":
            store_type = "pst"
        else:
            store_type = suffix.lstrip(".")
    return {
        "path": path,
        "type": store_type,
        "size_bytes": max(0, _to_int(value.get("size_bytes"), 0)),
        "last_modified_at": max(0, _to_int(value.get("last_modified_at"), 0)),
    }


def _normalize_outlook_payload(raw: Any) -> Dict[str, Any]:
    base = _empty_outlook_payload()
    if not isinstance(raw, dict):
        return base

    warning_threshold = max(1, _to_int(raw.get("threshold_warning_bytes"), OUTLOOK_WARNING_THRESHOLD_BYTES))
    critical_threshold = max(warning_threshold, _to_int(raw.get("threshold_critical_bytes"), OUTLOOK_CRITICAL_THRESHOLD_BYTES))
    source = sanitize_text(raw.get("source")).lower()
    if source not in {"system_scan", "none"}:
        source = "none"
    confidence = sanitize_text(raw.get("confidence")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"

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
        seen_active_paths = set()
        for row in active_stores:
            row_path = sanitize_text(row.get("path")).lower()
            if not row_path or row_path in seen_active_paths:
                continue
            seen_active_paths.add(row_path)
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

    largest_path = sanitize_text(raw.get("largest_file_path"))
    largest_size = max(0, _to_int(raw.get("largest_file_size_bytes"), 0))
    total_size = max(0, _to_int(raw.get("total_outlook_size_bytes"), 0))
    collected_at = max(0, _to_int(raw.get("collected_at"), int(time.time())))

    active_size = 0
    if active_stores:
        active_size = max(max(0, _to_int(row.get("size_bytes"), 0)) for row in active_stores)
    if active_size > 0 and confidence in {"high", "medium"}:
        if active_size >= critical_threshold:
            status = "critical"
        elif active_size >= warning_threshold:
            status = "warning"
        else:
            status = "ok"
    else:
        status = "unknown"

    return {
        "collected_at": collected_at,
        "source": source,
        "confidence": confidence,
        "status": status,
        "threshold_warning_bytes": warning_threshold,
        "threshold_critical_bytes": critical_threshold,
        "active_store": active_store,
        "active_stores": active_stores,
        "active_candidate": active_candidate,
        "archives": archives,
        "largest_file_path": largest_path,
        "largest_file_size_bytes": largest_size,
        "total_outlook_size_bytes": total_size,
    }


def _collect_outlook_via_fallback_scan() -> List[Dict[str, Any]]:
    users_root = Path(r"C:\Users")
    patterns = (
        Path(r"AppData\Local\Microsoft\Outlook\*.ost"),
        Path(r"AppData\Roaming\Microsoft\Outlook\*.pst"),
        Path(r"Documents\Outlook Files\*.pst"),
        Path(r"Documents\Файлы Outlook\*.pst"),
        Path(r"Документы\Outlook Files\*.pst"),
        Path(r"Документы\Файлы Outlook\*.pst"),
    )
    stores: List[Dict[str, Any]] = []
    seen_paths: set = set()

    if not users_root.exists():
        return stores

    for user_dir in users_root.iterdir():
        if not user_dir.is_dir():
            continue
        profile_name = sanitize_text(user_dir.name)
        if not profile_name:
            continue
        for pattern in patterns:
            for path in user_dir.glob(str(pattern)):
                try:
                    if not path.is_file():
                        continue
                    full_path = str(path.resolve())
                    dedupe_key = full_path.lower()
                    if dedupe_key in seen_paths:
                        continue
                    seen_paths.add(dedupe_key)
                    stat = path.stat()
                    suffix = path.suffix.lower()
                    stores.append(
                        {
                            "path": full_path,
                            "type": "ost" if suffix == ".ost" else "pst" if suffix == ".pst" else suffix.lstrip("."),
                            "size_bytes": max(0, int(stat.st_size)),
                            "last_modified_at": max(0, int(stat.st_mtime)),
                            "profile_name": profile_name,
                        }
                    )
                except Exception:
                    continue
    return stores


def _load_outlook_scan_state() -> Dict[str, Any]:
    path = get_outlook_scan_state_path()
    empty_state: Dict[str, Any] = {"updated_at": 0, "files": {}}
    try:
        if not path.exists():
            return empty_state
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return empty_state
        rows = raw.get("files")
        if not isinstance(rows, dict):
            return empty_state
        files: Dict[str, Dict[str, int]] = {}
        for key, value in rows.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            path_key = key.strip().lower()
            if not path_key:
                continue
            files[path_key] = {
                "size_bytes": max(0, _to_int(value.get("size_bytes"), 0)),
                "last_seen_at": max(0, _to_int(value.get("last_seen_at"), 0)),
            }
        return {"updated_at": max(0, _to_int(raw.get("updated_at"), 0)), "files": files}
    except Exception:
        return empty_state


def _save_outlook_scan_state(state: Dict[str, Any]) -> None:
    path = get_outlook_scan_state_path()
    try:
        _atomic_write_text(path, json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logging.warning("Failed to save Outlook scan state (%s): %s", path, exc)


def _select_outlook_stores_for_user(stores: List[Dict[str, Any]], user_login: str) -> List[Dict[str, Any]]:
    if not stores:
        return []
    login = extract_login_name(user_login).lower()
    if not login:
        return list(stores)
    marker = f"\\users\\{login}\\"
    selected = [row for row in stores if marker in sanitize_text(row.get("path")).lower()]
    if selected:
        return selected
    selected = [row for row in stores if sanitize_text(row.get("profile_name")).lower() == login]
    if selected:
        return selected
    return list(stores)


def _normalize_outlook_profile_email(value: Any) -> str:
    email = sanitize_text(value).lower()
    if not email:
        return ""
    while email.endswith(".pst") or email.endswith(".ost"):
        email = email[:-4].rstrip(".")
    if not OUTLOOK_EMAIL_RE.fullmatch(email):
        return ""
    return email


def _extract_outlook_emails_from_text(value: Any) -> List[str]:
    text = sanitize_text(value)
    if not text:
        return []
    emails: List[str] = []
    for match in OUTLOOK_EMAIL_RE.findall(text):
        normalized = _normalize_outlook_profile_email(match)
        if normalized:
            emails.append(normalized)
    return _dedupe_preserve_order(emails)


def _decode_registry_value_texts(value: Any) -> List[str]:
    texts: List[str] = []
    if isinstance(value, str):
        texts.append(value)
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str):
                texts.append(item)
    elif isinstance(value, (bytes, bytearray)):
        data = bytes(value)
        for encoding in ("utf-16-le", "utf-16-be", "utf-8", "cp1251", "cp866", "ascii"):
            try:
                decoded = data.decode(encoding, errors="ignore")
            except Exception:
                continue
            cleaned = sanitize_text(decoded.replace("\x00", " "))
            if cleaned:
                texts.append(cleaned)
    elif value is not None:
        texts.append(str(value))
    return _dedupe_preserve_order([sanitize_text(item.replace("\x00", " ")) for item in texts if sanitize_text(item)])


def _enumerate_hku_user_sids() -> List[str]:
    if winreg is None:
        return []
    sids: List[str] = []
    index = 0
    while True:
        try:
            sid = sanitize_text(winreg.EnumKey(winreg.HKEY_USERS, index))
        except OSError:
            break
        index += 1
        if not sid or sid.endswith("_Classes"):
            continue
        if WINDOWS_SID_RE.fullmatch(sid):
            sids.append(sid)
    return sids


def _resolve_user_sid_candidates(user_login: str) -> List[str]:
    if winreg is None:
        return []
    login = extract_login_name(user_login).lower()
    if not login:
        return []

    matched: List[str] = []
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList",
        ) as profile_list_key:
            index = 0
            while True:
                try:
                    sid = sanitize_text(winreg.EnumKey(profile_list_key, index))
                except OSError:
                    break
                index += 1
                if not sid or sid.endswith("_Classes") or not WINDOWS_SID_RE.fullmatch(sid):
                    continue
                try:
                    with winreg.OpenKey(profile_list_key, sid) as sid_key:
                        profile_path_raw, _ = winreg.QueryValueEx(sid_key, "ProfileImagePath")
                except Exception:
                    continue
                profile_path = os.path.expandvars(sanitize_text(profile_path_raw))
                profile_name = sanitize_text(Path(profile_path).name).lower()
                if profile_name == login:
                    matched.append(sid)
    except Exception:
        pass

    loaded_sids = set(_enumerate_hku_user_sids())
    matched_loaded = [sid for sid in matched if sid in loaded_sids]
    if matched_loaded:
        return _dedupe_preserve_order(matched_loaded)
    if matched:
        return _dedupe_preserve_order(matched)
    if len(loaded_sids) == 1:
        return sorted(loaded_sids)
    return []


def _collect_emails_from_registry_tree(root: Any, base_path: str) -> List[str]:
    if winreg is None:
        return []
    emails: List[str] = []
    stack: List[str] = [base_path]
    while stack:
        path = stack.pop()
        try:
            with winreg.OpenKey(root, path) as key:
                value_index = 0
                while True:
                    try:
                        _, raw_value, _ = winreg.EnumValue(key, value_index)
                    except OSError:
                        break
                    value_index += 1
                    for text_value in _decode_registry_value_texts(raw_value):
                        emails.extend(_extract_outlook_emails_from_text(text_value))

                subkey_index = 0
                while True:
                    try:
                        subkey_name = sanitize_text(winreg.EnumKey(key, subkey_index))
                    except OSError:
                        break
                    subkey_index += 1
                    if subkey_name:
                        stack.append(f"{path}\\{subkey_name}")
        except Exception:
            continue
    return _dedupe_preserve_order(emails)


def _collect_outlook_profile_emails(user_login: str) -> List[str]:
    if winreg is None:
        return []
    sid_candidates = _resolve_user_sid_candidates(user_login)
    if not sid_candidates:
        return []

    profile_paths = (
        r"Software\Microsoft\Office\16.0\Outlook\Profiles",
        r"Software\Microsoft\Windows NT\CurrentVersion\Windows Messaging Subsystem\Profiles",
    )
    for sid in sid_candidates:
        sid_emails: List[str] = []
        for rel_path in profile_paths:
            sid_emails.extend(_collect_emails_from_registry_tree(winreg.HKEY_USERS, f"{sid}\\{rel_path}"))
        sid_emails = _dedupe_preserve_order(sid_emails)
        if sid_emails:
            logging.debug("Outlook profile emails loaded: user=%s sid=%s count=%s", user_login, sid, len(sid_emails))
            return sid_emails
    return []


def _outlook_store_stem(path: Any) -> str:
    raw_path = sanitize_text(path)
    if not raw_path:
        return ""
    try:
        return sanitize_text(Path(raw_path).stem).lower()
    except Exception:
        return sanitize_text(raw_path).lower()


def _is_forced_archive_store(path: Any) -> bool:
    stem = _outlook_store_stem(path)
    if not stem:
        return False
    return bool(OUTLOOK_ARCHIVE_NAME_RE.fullmatch(stem))


def _build_outlook_match_tokens(user_login: str, profile_emails: List[str]) -> Dict[str, set]:
    email_full: set = set()
    email_local: set = set()
    login_variants: set = set()

    login = extract_login_name(user_login).lower()
    if login:
        login_variants.add(login)
        login_variants.add(login.replace("_", "."))
        login_variants.add(login.replace(".", "_"))

    for raw_email in profile_emails:
        email = _normalize_outlook_profile_email(raw_email)
        if not email:
            continue
        email_full.add(email)
        local_part = email.split("@", 1)[0]
        if local_part:
            email_local.add(local_part)
            email_local.add(local_part.replace("_", "."))
            email_local.add(local_part.replace(".", "_"))

    return {
        "email_full": {item for item in email_full if item},
        "email_local": {item for item in email_local if item},
        "login": {item for item in login_variants if item},
    }


def _outlook_store_match_priority(path: Any, match_tokens: Dict[str, set]) -> int:
    stem = _outlook_store_stem(path)
    if not stem:
        return 0
    if stem in match_tokens.get("email_full", set()):
        return 3
    if stem in match_tokens.get("email_local", set()):
        return 2
    if stem in match_tokens.get("login", set()):
        return 1
    return 0


def _outlook_store_name_class(path: Any, user_login: str, profile_emails: Optional[List[str]] = None) -> str:
    if _is_forced_archive_store(path):
        return "archive"
    match_tokens = _build_outlook_match_tokens(user_login, profile_emails or [])
    if _outlook_store_match_priority(path, match_tokens) > 0:
        return "primary"
    return "neutral"


def _outlook_store_name_score(
    path: Any,
    user_login: str,
    profile_emails: Optional[List[str]] = None,
    match_tokens: Optional[Dict[str, set]] = None,
) -> int:
    if _is_forced_archive_store(path):
        return 0
    tokens = match_tokens if match_tokens is not None else _build_outlook_match_tokens(user_login, profile_emails or [])
    priority = _outlook_store_match_priority(path, tokens)
    if priority >= 3:
        return 4
    if priority == 2:
        return 3
    if priority == 1:
        return 2
    return 1


def _choose_outlook_active_stores(
    stores: List[Dict[str, Any]],
    state_files: Dict[str, Dict[str, int]],
    user_login: str,
    profile_emails: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]], str]:
    if not stores:
        return [], None, "low"
    profile_emails = profile_emails or []
    match_tokens = _build_outlook_match_tokens(user_login, profile_emails)
    non_archive_rows = [row for row in stores if not _is_forced_archive_store(row.get("path"))]
    if not non_archive_rows:
        return [], None, "low"

    profile_match_rows: List[Tuple[int, int, int, Dict[str, Any]]] = []
    for row in non_archive_rows:
        path = sanitize_text(row.get("path"))
        if not path:
            continue
        match_priority = _outlook_store_match_priority(path, match_tokens)
        if match_priority < 2:
            continue
        key = path.lower()
        previous = state_files.get(key) if isinstance(state_files.get(key), dict) else None
        previous_size = _to_int(previous.get("size_bytes"), -1) if previous else -1
        current_size = max(0, _to_int(row.get("size_bytes"), 0))
        delta = abs(current_size - previous_size) if previous_size >= 0 else 0
        mtime = max(0, _to_int(row.get("last_modified_at"), 0))
        profile_match_rows.append((match_priority, delta, mtime, row))

    if profile_match_rows:
        profile_match_rows.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        active_stores = [row for _, __, ___, row in profile_match_rows[:10]]
        return active_stores, None, "medium"

    changed_rows: List[Tuple[int, int, int, Dict[str, Any]]] = []
    for row in non_archive_rows:
        path = sanitize_text(row.get("path"))
        if not path:
            continue
        key = path.lower()
        previous = state_files.get(key) if isinstance(state_files.get(key), dict) else None
        previous_size = _to_int(previous.get("size_bytes"), -1) if previous else -1
        current_size = max(0, _to_int(row.get("size_bytes"), 0))
        if previous_size < 0:
            continue
        delta = abs(current_size - previous_size)
        if delta <= 0:
            continue
        mtime = max(0, _to_int(row.get("last_modified_at"), 0))
        name_score = _outlook_store_name_score(
            path,
            user_login,
            profile_emails=profile_emails,
            match_tokens=match_tokens,
        )
        changed_rows.append((name_score, delta, mtime, row))

    if changed_rows:
        changed_rows.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        active_stores = [row for _, __, ___, row in changed_rows[:10]]
        return active_stores, None, "medium"

    active_candidate = sorted(
        non_archive_rows,
        key=lambda item: (
            _outlook_store_name_score(
                item.get("path"),
                user_login,
                profile_emails=profile_emails,
                match_tokens=match_tokens,
            ),
            _to_int(item.get("last_modified_at"), 0),
            _to_int(item.get("size_bytes"), 0),
        ),
        reverse=True,
    )[0]
    return [], active_candidate, "low"


def _build_outlook_payload_from_scan(
    user_login: str,
    user_stores: List[Dict[str, Any]],
    previous_state: Dict[str, Any],
    profile_emails: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not user_stores:
        return _normalize_outlook_payload(_empty_outlook_payload())

    state_files = previous_state.get("files") if isinstance(previous_state, dict) else {}
    if not isinstance(state_files, dict):
        state_files = {}

    profile_emails = profile_emails or []
    active_stores, active_candidate, confidence = _choose_outlook_active_stores(
        user_stores,
        state_files,
        user_login,
        profile_emails=profile_emails,
    )
    active_store = active_stores[0] if active_stores else None
    active_paths = {sanitize_text(row.get("path")).lower() for row in active_stores if sanitize_text(row.get("path"))}

    archives: List[Dict[str, Any]] = []
    for row in user_stores:
        row_path = sanitize_text(row.get("path"))
        if row_path and row_path.lower() in active_paths:
            continue
        archives.append(row)

    largest_file_path = ""
    largest_file_size_bytes = 0
    total_size_bytes = 0
    for row in user_stores:
        row_size = max(0, _to_int(row.get("size_bytes"), 0))
        total_size_bytes += row_size
        if row_size > largest_file_size_bytes:
            largest_file_size_bytes = row_size
            largest_file_path = sanitize_text(row.get("path"))

    payload = {
        "collected_at": int(time.time()),
        "source": "system_scan",
        "confidence": confidence,
        "threshold_warning_bytes": OUTLOOK_WARNING_THRESHOLD_BYTES,
        "threshold_critical_bytes": OUTLOOK_CRITICAL_THRESHOLD_BYTES,
        "active_store": active_store,
        "active_stores": active_stores,
        "active_candidate": active_candidate,
        "archives": archives,
        "largest_file_path": largest_file_path,
        "largest_file_size_bytes": largest_file_size_bytes,
        "total_outlook_size_bytes": total_size_bytes,
        "collector": "scan_profile_email_first",
        "user": user_login,
    }
    return _normalize_outlook_payload(payload)


def collect_outlook_info(user_login: str, force_refresh: bool = False) -> Dict[str, Any]:
    normalized_user = extract_login_name(user_login).lower()
    now_ts = int(time.time())
    cached_payload = OUTLOOK_RUNTIME_CACHE.get("payload")
    cached_user = sanitize_text(OUTLOOK_RUNTIME_CACHE.get("user")).lower()
    cached_ts = _to_int(OUTLOOK_RUNTIME_CACHE.get("collected_at"), 0)
    if (
        not force_refresh
        and isinstance(cached_payload, dict)
        and cached_user == normalized_user
        and (now_ts - cached_ts) <= OUTLOOK_SCAN_CACHE_TTL_SEC
    ):
        return dict(cached_payload)

    all_stores = _collect_outlook_via_fallback_scan()
    user_stores = _select_outlook_stores_for_user(all_stores, user_login)
    profile_emails = _collect_outlook_profile_emails(user_login)
    previous_state = _load_outlook_scan_state()
    payload = _build_outlook_payload_from_scan(
        user_login,
        user_stores,
        previous_state,
        profile_emails=profile_emails,
    )

    files_state: Dict[str, Dict[str, int]] = {}
    old_files = previous_state.get("files") if isinstance(previous_state, dict) else {}
    if isinstance(old_files, dict):
        for key, row in old_files.items():
            if not isinstance(key, str) or not isinstance(row, dict):
                continue
            seen_at = max(0, _to_int(row.get("last_seen_at"), 0))
            if seen_at and (now_ts - seen_at) > DEFAULT_OUTLOOK_SCAN_STATE_MAX_AGE_SEC:
                continue
            files_state[key.lower()] = {
                "size_bytes": max(0, _to_int(row.get("size_bytes"), 0)),
                "last_seen_at": seen_at,
            }

    for row in all_stores:
        path = sanitize_text(row.get("path"))
        if not path:
            continue
        files_state[path.lower()] = {
            "size_bytes": max(0, _to_int(row.get("size_bytes"), 0)),
            "last_seen_at": now_ts,
        }

    _save_outlook_scan_state({"updated_at": now_ts, "files": files_state})

    OUTLOOK_RUNTIME_CACHE["user"] = normalized_user
    OUTLOOK_RUNTIME_CACHE["collected_at"] = now_ts
    OUTLOOK_RUNTIME_CACHE["payload"] = dict(payload)
    return payload


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IT-Invent inventory agent")
    parser.add_argument("--once", action="store_true", help="Collect and send one report, then exit")
    parser.add_argument("--check", action="store_true", help="Validate config and endpoint reachability, then exit")
    return parser.parse_args(argv)


def load_config() -> AgentConfig:
    server_url = str(os.getenv("ITINV_AGENT_SERVER_URL", DEFAULT_SERVER_URL)).strip() or DEFAULT_SERVER_URL
    allow_default_key = _to_bool(os.getenv("ITINV_AGENT_ALLOW_DEFAULT_KEY", "1"), default=True)
    api_key = str(os.getenv("ITINV_AGENT_API_KEY", "")).strip()
    if not api_key:
        if allow_default_key:
            api_key = DEFAULT_API_KEY
            logging.warning("ITINV_AGENT_API_KEY is empty; using legacy default key because ITINV_AGENT_ALLOW_DEFAULT_KEY=1")
        else:
            logging.error("ITINV_AGENT_API_KEY is empty and ITINV_AGENT_ALLOW_DEFAULT_KEY=0; agent will not send data")

    interval_raw = str(os.getenv("ITINV_AGENT_INTERVAL_SEC", DEFAULT_FULL_SNAPSHOT_INTERVAL)).strip()
    heartbeat_raw = str(os.getenv("ITINV_AGENT_HEARTBEAT_SEC", DEFAULT_HEARTBEAT_INTERVAL)).strip()
    jitter_raw = str(os.getenv("ITINV_AGENT_HEARTBEAT_JITTER_SEC", DEFAULT_HEARTBEAT_JITTER)).strip()
    outlook_refresh_raw = str(os.getenv("ITINV_OUTLOOK_REFRESH_SEC", DEFAULT_OUTLOOK_REFRESH_SEC)).strip()
    run_cmd_timeout_raw = str(os.getenv("ITINV_RUN_CMD_TIMEOUT_SEC", DEFAULT_RUN_CMD_TIMEOUT_SEC)).strip()
    queue_batch_raw = str(os.getenv("ITINV_INVENTORY_QUEUE_BATCH", DEFAULT_INVENTORY_QUEUE_BATCH)).strip()
    queue_max_items_raw = str(os.getenv("ITINV_INVENTORY_QUEUE_MAX_ITEMS", DEFAULT_INVENTORY_QUEUE_MAX_ITEMS)).strip()
    queue_max_age_raw = str(os.getenv("ITINV_INVENTORY_QUEUE_MAX_AGE_DAYS", DEFAULT_INVENTORY_QUEUE_MAX_AGE_DAYS)).strip()
    queue_max_total_mb_raw = str(
        os.getenv("ITINV_INVENTORY_QUEUE_MAX_TOTAL_MB", DEFAULT_INVENTORY_QUEUE_MAX_TOTAL_MB)
    ).strip()
    reminder_enabled_raw = os.getenv("ITINV_REBOOT_REMINDER_ENABLED", "1")
    reminder_days_raw = str(os.getenv("ITINV_REBOOT_REMINDER_DAYS", DEFAULT_REBOOT_REMINDER_DAYS)).strip()
    reminder_interval_raw = str(
        os.getenv("ITINV_REBOOT_REMINDER_INTERVAL_HOURS", DEFAULT_REBOOT_REMINDER_INTERVAL_HOURS)
    ).strip()
    reminder_timeout_raw = str(
        os.getenv("ITINV_REBOOT_REMINDER_TIMEOUT_SEC", DEFAULT_REBOOT_REMINDER_TIMEOUT_SEC)
    ).strip()
    reminder_work_start_raw = str(
        os.getenv("ITINV_REBOOT_REMINDER_WORK_START_HOUR", DEFAULT_REBOOT_REMINDER_WORK_START_HOUR)
    ).strip()
    reminder_work_end_raw = str(
        os.getenv("ITINV_REBOOT_REMINDER_WORK_END_HOUR", DEFAULT_REBOOT_REMINDER_WORK_END_HOUR)
    ).strip()
    reminder_weekdays_only_raw = os.getenv("ITINV_REBOOT_REMINDER_WEEKDAYS_ONLY", "1")
    ca_bundle = str(os.getenv("ITINV_AGENT_CA_BUNDLE", "")).strip() or None
    try:
        full_snapshot_interval = int(interval_raw)
    except ValueError:
        full_snapshot_interval = DEFAULT_FULL_SNAPSHOT_INTERVAL
    try:
        heartbeat_interval = int(heartbeat_raw)
    except ValueError:
        heartbeat_interval = DEFAULT_HEARTBEAT_INTERVAL
    try:
        heartbeat_jitter = int(jitter_raw)
    except ValueError:
        heartbeat_jitter = DEFAULT_HEARTBEAT_JITTER
    outlook_refresh_sec = _to_int(outlook_refresh_raw, DEFAULT_OUTLOOK_REFRESH_SEC)
    run_cmd_timeout_sec = _to_int(run_cmd_timeout_raw, DEFAULT_RUN_CMD_TIMEOUT_SEC)
    queue_batch = _to_int(queue_batch_raw, DEFAULT_INVENTORY_QUEUE_BATCH)
    queue_max_items = _to_int(queue_max_items_raw, DEFAULT_INVENTORY_QUEUE_MAX_ITEMS)
    queue_max_age_days = _to_int(queue_max_age_raw, DEFAULT_INVENTORY_QUEUE_MAX_AGE_DAYS)
    queue_max_total_mb = _to_int(queue_max_total_mb_raw, DEFAULT_INVENTORY_QUEUE_MAX_TOTAL_MB)
    reminder_enabled = _is_truthy(reminder_enabled_raw, default=True)
    reminder_days = _to_int(reminder_days_raw, DEFAULT_REBOOT_REMINDER_DAYS)
    reminder_interval_hours = _to_int(reminder_interval_raw, DEFAULT_REBOOT_REMINDER_INTERVAL_HOURS)
    reminder_timeout_sec = _to_int(reminder_timeout_raw, DEFAULT_REBOOT_REMINDER_TIMEOUT_SEC)
    reminder_work_start_hour = _to_int(reminder_work_start_raw, DEFAULT_REBOOT_REMINDER_WORK_START_HOUR)
    reminder_work_end_hour = _to_int(reminder_work_end_raw, DEFAULT_REBOOT_REMINDER_WORK_END_HOUR)
    reminder_weekdays_only = _is_truthy(reminder_weekdays_only_raw, default=True)

    full_snapshot_interval = max(300, full_snapshot_interval)
    heartbeat_interval = max(60, min(heartbeat_interval, full_snapshot_interval))
    heartbeat_jitter = max(0, min(heartbeat_jitter, 300))
    outlook_refresh_sec = max(60, min(outlook_refresh_sec, 3600))
    run_cmd_timeout_sec = max(5, min(run_cmd_timeout_sec, 300))
    queue_batch = max(1, min(queue_batch, 200))
    queue_max_items = max(50, min(queue_max_items, 10000))
    queue_max_age_days = max(1, min(queue_max_age_days, 90))
    queue_max_total_mb = max(32, min(queue_max_total_mb, 2048))
    reminder_days = max(1, min(reminder_days, 365))
    reminder_interval_hours = max(1, min(reminder_interval_hours, 24 * 30))
    reminder_timeout_sec = max(30, min(reminder_timeout_sec, 600))
    reminder_work_start_hour = max(0, min(reminder_work_start_hour, 23))
    reminder_work_end_hour = max(1, min(reminder_work_end_hour, 24))
    if reminder_work_start_hour >= reminder_work_end_hour:
        logging.warning(
            "Invalid reboot reminder work window %s-%s. Fallback to default %s-%s",
            reminder_work_start_hour,
            reminder_work_end_hour,
            DEFAULT_REBOOT_REMINDER_WORK_START_HOUR,
            DEFAULT_REBOOT_REMINDER_WORK_END_HOUR,
        )
        reminder_work_start_hour = DEFAULT_REBOOT_REMINDER_WORK_START_HOUR
        reminder_work_end_hour = DEFAULT_REBOOT_REMINDER_WORK_END_HOUR
    return AgentConfig(
        server_url=server_url,
        api_key=api_key,
        full_snapshot_interval=full_snapshot_interval,
        heartbeat_interval=heartbeat_interval,
        heartbeat_jitter_sec=heartbeat_jitter,
        outlook_refresh_sec=outlook_refresh_sec,
        run_cmd_timeout_sec=run_cmd_timeout_sec,
        inventory_queue_batch=queue_batch,
        inventory_queue_max_items=queue_max_items,
        inventory_queue_max_age_days=queue_max_age_days,
        inventory_queue_max_total_mb=queue_max_total_mb,
        reboot_reminder_enabled=reminder_enabled,
        reboot_reminder_days=reminder_days,
        reboot_reminder_interval_hours=reminder_interval_hours,
        reboot_reminder_timeout_sec=reminder_timeout_sec,
        reboot_reminder_work_start_hour=reminder_work_start_hour,
        reboot_reminder_work_end_hour=reminder_work_end_hour,
        reboot_reminder_weekdays_only=reminder_weekdays_only,
        ca_bundle=ca_bundle,
    )


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_cmd(args: List[str], timeout_sec: Optional[int] = None) -> subprocess.CompletedProcess:
    effective_timeout = max(1, int(timeout_sec or RUN_CMD_TIMEOUT_SEC))
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=False,
            timeout=effective_timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        stdout = _decode_console_output(result.stdout)
        stderr = _decode_console_output(result.stderr)
        return subprocess.CompletedProcess(args=args, returncode=result.returncode, stdout=stdout, stderr=stderr)
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_console_output(getattr(exc, "stdout", b""))
        stderr_raw = _decode_console_output(getattr(exc, "stderr", b""))
        stderr = (stderr_raw + f"\nCommand timed out after {effective_timeout}s").strip()
        logging.warning("Command timeout after %ss: %s", effective_timeout, " ".join(args))
        return subprocess.CompletedProcess(args=args, returncode=124, stdout=stdout, stderr=stderr)


def _decode_console_output(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    data = bytes(raw)
    if not data:
        return ""

    if b"\x00" in data:
        for enc in ("utf-16", "utf-16-le", "utf-16-be"):
            try:
                return data.decode(enc)
            except Exception:
                continue
    for enc in ("utf-8-sig", "utf-8", "cp866", "cp1251"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", errors="ignore")


def sanitize_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _compact_spaces(value: Any) -> str:
    return re.sub(r"\s+", " ", sanitize_text(value))


def _to_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            return int(value)
        return int(value)
    text = sanitize_text(value).replace(",", ".")
    if not text:
        return None
    try:
        return int(text)
    except Exception:
        try:
            return int(float(text))
        except Exception:
            return None


def _normalize_disk_serial(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", sanitize_text(value)).upper()


def _normalize_disk_model(value: Any) -> str:
    return re.sub(r"\s+", " ", sanitize_text(value)).lower()


def _is_generic_disk_name(value: Any) -> bool:
    text = _normalize_disk_model(value)
    if not text:
        return True
    if text in GENERIC_DISK_NAME_VALUES:
        return True
    return any(text.endswith(suffix) for suffix in GENERIC_DISK_NAME_SUFFIXES)


def _format_size_label(size_bytes: Optional[int]) -> str:
    size_value = _to_int_or_none(size_bytes)
    if not size_value or size_value <= 0:
        return ""
    gib = size_value / float(1024 ** 3)
    if gib >= 1024:
        tib = gib / 1024.0
        return f"{tib:.1f} TB"
    return f"{round(gib)} GB"


def _normalize_bus_label(value: Any) -> str:
    raw = _normalize_disk_model(value)
    if not raw:
        return ""
    return BUS_TYPE_LABELS.get(raw, sanitize_text(value).upper())


def _is_size_close(left: Optional[int], right: Optional[int]) -> bool:
    l_val = _to_int_or_none(left)
    r_val = _to_int_or_none(right)
    if not l_val or not r_val:
        return False
    diff = abs(l_val - r_val)
    tolerance = max(10 * 1024 * 1024, int(max(l_val, r_val) * 0.01))
    return diff <= tolerance


def _match_diskdrive_row(
    *,
    serial_number: str,
    model: str,
    size_bytes: Optional[int],
    rows: List[Dict[str, Any]],
    used_indices: set,
) -> Dict[str, Any]:
    serial_key = _normalize_disk_serial(serial_number)
    if serial_key:
        for idx, row in enumerate(rows):
            if idx in used_indices:
                continue
            row_serial = _normalize_disk_serial(row.get("serial_number"))
            if row_serial and row_serial == serial_key:
                used_indices.add(idx)
                return row

    model_key = _normalize_disk_model(model)
    if model_key:
        for idx, row in enumerate(rows):
            if idx in used_indices:
                continue
            row_model = _normalize_disk_model(row.get("model"))
            if not row_model:
                continue
            if model_key in row_model or row_model in model_key:
                if _is_size_close(size_bytes, row.get("size_bytes")) or not size_bytes or not row.get("size_bytes"):
                    used_indices.add(idx)
                    return row

    if size_bytes:
        for idx, row in enumerate(rows):
            if idx in used_indices:
                continue
            if _is_size_close(size_bytes, row.get("size_bytes")):
                used_indices.add(idx)
                return row

    return {}


def _choose_disk_base_name(
    raw_friendly_name: str,
    raw_caption: str,
    raw_model: str,
) -> str:
    candidates = [
        _compact_spaces(raw_friendly_name),
        _compact_spaces(raw_caption),
        _compact_spaces(raw_model),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if _is_generic_disk_name(candidate):
            continue
        return candidate
    for candidate in candidates:
        if candidate:
            return candidate
    return "Unknown Disk"


def _build_disk_display_name(
    *,
    raw_friendly_name: str,
    raw_caption: str,
    raw_model: str,
    bus_type: str,
    size_bytes: Optional[int],
) -> str:
    base = _choose_disk_base_name(raw_friendly_name, raw_caption, raw_model)
    parts: List[str] = []
    bus_label = _normalize_bus_label(bus_type)
    if bus_label and bus_label != "UNKNOWN":
        parts.append(bus_label)
    size_label = _format_size_label(size_bytes)
    if size_label:
        parts.append(size_label)
    if parts:
        return f"{base} ({', '.join(parts)})"
    return base


def get_diskdrive_metadata() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if wmi is None:
        return rows
    try:
        c = wmi.WMI()
        for item in c.Win32_DiskDrive():
            rows.append(
                {
                    "caption": _compact_spaces(getattr(item, "Caption", "")),
                    "model": _compact_spaces(getattr(item, "Model", "")),
                    "serial_number": _compact_spaces(getattr(item, "SerialNumber", "")),
                    "pnp_device_id": sanitize_text(getattr(item, "PNPDeviceID", "")),
                    "size_bytes": _to_int_or_none(getattr(item, "Size", None)),
                    "index": _to_int_or_none(getattr(item, "Index", None)),
                }
            )
    except Exception as exc:
        logging.debug("Win32_DiskDrive metadata collection failed: %s", exc)
    return rows


def decode_wmi_char_array(value: Any) -> str:
    if value is None:
        return ""
    try:
        chars = []
        for item in value:
            try:
                num = int(item)
            except Exception:
                continue
            if num == 0:
                continue
            chars.append(chr(num))
        return "".join(chars).strip()
    except Exception:
        return ""


def is_service_account(value: str) -> bool:
    normalized = sanitize_text(value).lower()
    return not normalized or normalized in SERVICE_USERS


def normalize_user_name(value: str) -> str:
    normalized = sanitize_text(value).strip().strip('"')
    return normalized


def extract_login_name(value: str) -> str:
    normalized = normalize_user_name(value)
    if "\\" in normalized:
        return normalize_user_name(normalized.split("\\", 1)[1])
    if "@" in normalized:
        return normalize_user_name(normalized.split("@", 1)[0])
    return normalized


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in items:
        value = sanitize_text(item)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _is_af_inet(family: Any) -> bool:
    try:
        return int(family) == int(socket.AF_INET)
    except Exception:
        text = str(family)
        return ".AF_INET" in text and ".AF_INET6" not in text


def _is_af_inet6(family: Any) -> bool:
    try:
        return int(family) == int(socket.AF_INET6)
    except Exception:
        return ".AF_INET6" in str(family)


def get_process_user_name() -> str:
    username = sanitize_text(os.environ.get("USERNAME")) or sanitize_text(getpass.getuser())
    domain = sanitize_text(os.environ.get("USERDOMAIN"))
    if domain and "\\" not in username:
        return f"{domain}\\{username}"
    return username


def get_user_from_win32_computersystem() -> str:
    if wmi is None:
        return ""
    try:
        c = wmi.WMI()
        systems = c.Win32_ComputerSystem()
        if not systems:
            return ""
        username = normalize_user_name(getattr(systems[0], "UserName", ""))
        return "" if is_service_account(username) else username
    except Exception as exc:
        logging.debug("Win32_ComputerSystem.UserName not available: %s", exc)
        return ""


def parse_query_user_output(output: str) -> str:
    lines = [line.rstrip() for line in (output or "").splitlines() if line.strip()]
    if len(lines) <= 1:
        return ""

    first_candidate = ""
    for line in lines[1:]:
        line_clean = line.lstrip(">").strip()
        parts = line_clean.split()
        if not parts:
            continue
        username = normalize_user_name(parts[0])
        if not username or is_service_account(username):
            continue
        if not first_candidate:
            first_candidate = username

        line_lower = line_clean.lower()
        if any(marker in line_lower for marker in ACTIVE_SESSION_MARKERS):
            return username
    return first_candidate


def get_user_from_query_user() -> str:
    for cmd in (["query", "user"], ["quser"]):
        try:
            result = run_cmd(cmd)
            if result.returncode != 0:
                continue
            parsed = parse_query_user_output(result.stdout)
            if parsed and not is_service_account(parsed):
                return parsed
        except Exception as exc:
            logging.debug("query user call failed (%s): %s", " ".join(cmd), exc)
    return ""


def get_last_logged_on_user() -> str:
    if winreg is None:
        return ""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\LogonUI",
        )
        value, _ = winreg.QueryValueEx(key, "LastLoggedOnUser")
        username = normalize_user_name(value)
        return "" if is_service_account(username) else username
    except Exception as exc:
        logging.debug("LastLoggedOnUser not available: %s", exc)
        return ""


def get_active_console_user() -> str:
    candidates = [
        get_user_from_win32_computersystem(),
        get_user_from_query_user(),
        get_last_logged_on_user(),
    ]
    for item in candidates:
        if item and not is_service_account(item):
            return item
    return normalize_user_name(get_process_user_name())


def _load_reboot_reminder_state() -> Dict[str, Any]:
    path = get_reboot_reminder_state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logging.warning("Reboot reminder state read failed (%s): %s", path, exc)
    return {}


def _save_reboot_reminder_state(state: Dict[str, Any]) -> None:
    path = get_reboot_reminder_state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(path, json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logging.warning("Reboot reminder state write failed (%s): %s", path, exc)


def _send_reboot_reminder_message(user_login: str, timeout_sec: int, message: str) -> bool:
    candidates = _dedupe_preserve_order(
        [normalize_user_name(user_login), extract_login_name(user_login)]
    )
    for candidate in candidates:
        if is_service_account(candidate):
            continue
        try:
            result = run_cmd(["msg", candidate, f"/TIME:{timeout_sec}", message])
        except Exception as exc:
            logging.warning("msg.exe execution failed for user=%s: %s", candidate, exc)
            continue
        if result.returncode == 0:
            return True
        stderr = sanitize_text(result.stderr)
        logging.warning(
            "msg.exe returned non-zero code=%s user=%s stderr=%s",
            result.returncode,
            candidate,
            stderr[:200],
        )
    return False


def _is_worktime_allowed(config: AgentConfig, now_dt: datetime) -> bool:
    if config.reboot_reminder_weekdays_only and now_dt.weekday() >= 5:
        logging.info("Reboot reminder skipped: weekend blocked by weekdays policy")
        return False

    hour = int(now_dt.hour)
    if not (config.reboot_reminder_work_start_hour <= hour < config.reboot_reminder_work_end_hour):
        logging.info(
            "Reboot reminder skipped: outside work window (now=%02d:00, allowed=%02d:00-%02d:00)",
            hour,
            config.reboot_reminder_work_start_hour,
            config.reboot_reminder_work_end_hour,
        )
        return False
    return True


def maybe_notify_reboot_required(health_info: Dict[str, Any], config: AgentConfig) -> None:
    if not config.reboot_reminder_enabled:
        return

    uptime_seconds = _to_int(health_info.get("uptime_seconds"), default=-1)
    if uptime_seconds < 0:
        return

    threshold_seconds = config.reboot_reminder_days * 24 * 60 * 60
    if uptime_seconds < threshold_seconds:
        return

    now_ts = int(time.time())
    boot_time = _to_int(
        health_info.get("boot_time") or health_info.get("last_reboot_at"),
        default=max(0, now_ts - uptime_seconds),
    )
    if boot_time <= 0:
        return

    state = _load_reboot_reminder_state()
    last_notified_at = _to_int(state.get("last_notified_at"), default=0)
    last_notified_boot = _to_int(state.get("last_notified_boot_time"), default=0)
    interval_seconds = config.reboot_reminder_interval_hours * 60 * 60
    if (
        last_notified_boot == boot_time
        and last_notified_at > 0
        and (now_ts - last_notified_at) < interval_seconds
    ):
        return

    now_dt = datetime.fromtimestamp(now_ts)
    if not _is_worktime_allowed(config, now_dt):
        return

    active_user = normalize_user_name(get_active_console_user())
    if is_service_account(active_user):
        logging.info("Reboot reminder skipped: active user session was not detected")
        return

    if not _send_reboot_reminder_message(active_user, config.reboot_reminder_timeout_sec, REBOOT_REMINDER_MESSAGE):
        logging.warning("Failed to deliver reboot reminder to user=%s", active_user)
        return

    _save_reboot_reminder_state(
        {
            "last_notified_at": now_ts,
            "last_notified_boot_time": boot_time,
            "last_notified_user": active_user,
        }
    )
    logging.info(
        "Reboot reminder sent to user=%s (uptime_hours=%.1f)",
        active_user,
        uptime_seconds / 3600.0,
    )


def resolve_user_full_name(user_login: str) -> str:
    login = extract_login_name(user_login)
    if not login:
        return ""

    escaped_login = login.replace("'", "''")
    command = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"$login='{escaped_login}'; "
        "if (Get-Command Get-ADUser -ErrorAction SilentlyContinue) { "
        "  $ad = Get-ADUser -Identity $login -Properties DisplayName; "
        "  if ($ad -and $ad.DisplayName) { $ad.DisplayName | ConvertTo-Json -Compress; exit } "
        "} "
        "$wmiUser = Get-CimInstance Win32_UserAccount -Filter \"Name='$login' AND LocalAccount=FALSE\" | "
        "  Select-Object -First 1 -ExpandProperty FullName; "
        "if ($wmiUser) { $wmiUser | ConvertTo-Json -Compress; exit } "
        "$line = net user $login /domain 2>$null | "
        "  Select-String -Pattern '^(Full Name|Полное имя)\\s{2,}(.+)$' | Select-Object -First 1; "
        "if ($line) { $line.Matches[0].Groups[2].Value | ConvertTo-Json -Compress }"
    )
    value = _powershell_json(command)
    if isinstance(value, str):
        return sanitize_text(value)
    return ""


def get_mac_address() -> str:
    try:
        for interface, addrs in psutil.net_if_addrs().items():
            interface_l = interface.lower()
            if "loopback" in interface_l or "virtual" in interface_l:
                continue
            for addr in addrs:
                if addr.family == psutil.AF_LINK:
                    value = sanitize_text(addr.address)
                    if value:
                        return value
    except Exception as exc:
        logging.error("MAC address detection failed: %s", exc)
    return ""


def validate_monitor_serial(value: str) -> str:
    serial = sanitize_text(value).replace("\n", "").replace("\r", "")
    serial = re.sub(r"[^0-9A-Za-z._-]", "", serial)
    if not serial:
        return ""
    if serial in {"0", "00000000", "FFFFFFFF", "ffffffffff"}:
        return ""
    return serial


def parse_edid_serial(edid: bytes) -> str:
    if not edid or len(edid) < 128:
        return ""

    for offset in range(54, 126, 18):
        block = edid[offset:offset + 18]
        if len(block) < 18:
            continue
        if block[0:3] == b"\x00\x00\x00" and block[3] == 0xFF:
            raw = block[5:18]
            text = raw.decode("ascii", errors="ignore").replace("\n", "").strip()
            serial = validate_monitor_serial(text)
            if serial:
                return serial

    numeric = int.from_bytes(edid[12:16], byteorder="little", signed=False)
    if numeric > 0:
        serial = validate_monitor_serial(f"{numeric}")
        if serial:
            return serial
    return ""


def get_registry_edid_for_instance(instance_name: str) -> bytes:
    if winreg is None:
        return b""

    cleaned = sanitize_text(instance_name).replace("/", "\\")
    if not cleaned:
        return b""

    parts = cleaned.split("\\")
    candidates: List[str] = []
    if len(parts) >= 3:
        pnp_id = parts[2]
        candidates.append(f"{parts[0]}\\{parts[1]}\\{pnp_id}")
        if "_" in pnp_id:
            candidates.append(f"{parts[0]}\\{parts[1]}\\{pnp_id.split('_')[0]}")

    for candidate in candidates:
        reg_path = rf"SYSTEM\CurrentControlSet\Enum\{candidate}\Device Parameters"
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
            data, _ = winreg.QueryValueEx(key, "EDID")
            if isinstance(data, bytes) and data:
                return data
        except Exception:
            continue
    return b""


def get_monitor_serial(monitor_obj: Any) -> Tuple[str, str]:
    instance_name = sanitize_text(getattr(monitor_obj, "InstanceName", ""))
    edid = get_registry_edid_for_instance(instance_name)
    if edid:
        serial = parse_edid_serial(edid)
        if serial:
            return serial, "edid"

    serial_wmi = validate_monitor_serial(decode_wmi_char_array(getattr(monitor_obj, "SerialNumberID", [])))
    if serial_wmi:
        return serial_wmi, "wmi_fallback"
    return "", "unknown"


def get_monitors() -> List[Dict[str, Any]]:
    monitors: List[Dict[str, Any]] = []
    if wmi is None:
        return monitors
    try:
        w = wmi.WMI(namespace=r"root\wmi")
        for monitor in w.WmiMonitorID():
            try:
                manufacturer = decode_wmi_char_array(getattr(monitor, "ManufacturerName", []))
                product_code = decode_wmi_char_array(getattr(monitor, "ProductCodeID", []))
                serial_number, serial_source = get_monitor_serial(monitor)
                monitors.append(
                    {
                        "manufacturer": manufacturer,
                        "product_code": product_code,
                        "serial_number": serial_number,
                        "serial_source": serial_source,
                    }
                )
            except Exception as exc:
                logging.warning("Monitor parsing failed: %s", exc)
    except Exception as exc:
        logging.error("WmiMonitorID query failed: %s", exc)
    return monitors


def get_physical_disk_skip_reasons(disk: Dict[str, Any]) -> List[str]:
    model = sanitize_text(disk.get("model")).lower()
    serial = sanitize_text(disk.get("serial_number")).lower()
    bus_type = sanitize_text(disk.get("bus_type")).lower()
    reasons = []

    if not model and not serial:
        reasons.append("empty")
    if any(marker in bus_type for marker in VIRTUAL_BUS_MARKERS):
        reasons.append("virtual_bus")
    if any(marker in model for marker in VIRTUAL_MODEL_MARKERS):
        reasons.append("virtual_model")
    return reasons


def get_storage_info() -> List[Dict[str, Any]]:
    disks: List[Dict[str, Any]] = []
    skipped: Dict[str, int] = {}
    try:
        diskdrive_rows = get_diskdrive_metadata()
        used_diskdrive_indices: set = set()
        ps_cmd = (
            "Get-PhysicalDisk | Select-Object * -ExcludeProperty Cim* | "
            "ConvertTo-Json -Depth 1 -Compress"
        )
        result = run_cmd(["powershell", "-NoProfile", "-Command", ps_cmd])
        if result.returncode != 0 or not result.stdout.strip():
            return disks

        data = json.loads(result.stdout)
        if not isinstance(data, list):
            data = [data]

        for disk in data:
            raw_model = _compact_spaces(disk.get("Model"))
            raw_friendly_name = _compact_spaces(disk.get("FriendlyName"))
            serial = _compact_spaces(disk.get("SerialNumber"))
            bus_type = sanitize_text(disk.get("BusType")) or "Unknown"
            size_bytes = _to_int_or_none(disk.get("Size"))

            matched_diskdrive = _match_diskdrive_row(
                serial_number=serial,
                model=raw_model,
                size_bytes=size_bytes,
                rows=diskdrive_rows,
                used_indices=used_diskdrive_indices,
            )

            raw_caption = _compact_spaces(matched_diskdrive.get("caption"))
            raw_pnp_device_id = sanitize_text(matched_diskdrive.get("pnp_device_id"))
            if not raw_model:
                raw_model = _compact_spaces(matched_diskdrive.get("model"))
            if not serial:
                serial = _compact_spaces(matched_diskdrive.get("serial_number"))
            if size_bytes is None:
                size_bytes = _to_int_or_none(matched_diskdrive.get("size_bytes"))

            display_name = _build_disk_display_name(
                raw_friendly_name=raw_friendly_name,
                raw_caption=raw_caption,
                raw_model=raw_model,
                bus_type=bus_type,
                size_bytes=size_bytes,
            )

            health_status = "Unknown"
            wear_out = None
            temperature = None

            try:
                if serial:
                    serial_ps = serial.replace("'", "''")
                    rel_cmd = (
                        "Get-StorageReliabilityCounter -PhysicalDisk "
                        f"(Get-PhysicalDisk -SerialNumber '{serial_ps}') | "
                        "Select-Object * -ExcludeProperty Cim* | ConvertTo-Json -Depth 1 -Compress"
                    )
                    rel_result = run_cmd(["powershell", "-NoProfile", "-Command", rel_cmd])
                    if rel_result.returncode == 0 and rel_result.stdout.strip():
                        rel_data = json.loads(rel_result.stdout)
                        wear_out = rel_data.get("Wear")
                        temperature = rel_data.get("Temperature")
                        if isinstance(rel_data, dict):
                            disk.update(rel_data)

                    health_cmd = f"(Get-PhysicalDisk -SerialNumber '{serial_ps}').HealthStatus"
                    health_result = run_cmd(["powershell", "-NoProfile", "-Command", health_cmd])
                    if health_result.returncode == 0:
                        health_status = sanitize_text(health_result.stdout) or "Unknown"
            except Exception as exc:
                logging.warning("Storage reliability counters unavailable for %s: %s", serial, exc)

            disk_item = {
                "model": raw_model,
                "serial_number": serial,
                "media_type": disk.get("MediaType"),
                "bus_type": bus_type,
                "size_bytes": size_bytes,
                "display_name": display_name,
                "raw_model": raw_model,
                "raw_friendly_name": raw_friendly_name,
                "raw_caption": raw_caption,
                "raw_pnp_device_id": raw_pnp_device_id,
                "health_status": health_status,
                "wear_out_percentage": wear_out,
                "temperature": temperature,
                "extended_info": disk,
            }
            reasons = get_physical_disk_skip_reasons(disk_item)
            if reasons:
                for reason in reasons:
                    skipped[reason] = skipped.get(reason, 0) + 1
                continue
            disks.append(disk_item)
    except Exception as exc:
        logging.error("Storage collection failed: %s", exc)

    if skipped:
        logging.info(
            "Filtered physical disks: %s",
            ", ".join(f"{key}={value}" for key, value in sorted(skipped.items())),
        )
    return disks


def is_container_mountpoint(value: str) -> bool:
    mount = sanitize_text(value).replace("/", "\\").lower()
    return any(marker in mount for marker in LOGICAL_MOUNT_SKIP_MARKERS)


def mountpoint_rank(mountpoint: str) -> int:
    mount = sanitize_text(mountpoint)
    return 0 if re.match(r"^[A-Za-z]:\\$", mount) else 1


def get_logical_disks() -> List[Dict[str, Any]]:
    selected_by_device: Dict[str, Dict[str, Any]] = {}
    skipped: Dict[str, int] = {}
    try:
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts or not part.fstype:
                skipped["cdrom_or_no_fstype"] = skipped.get("cdrom_or_no_fstype", 0) + 1
                continue
            if is_container_mountpoint(part.mountpoint):
                skipped["container_path"] = skipped.get("container_path", 0) + 1
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except PermissionError:
                skipped["permission"] = skipped.get("permission", 0) + 1
                continue
            except Exception:
                skipped["usage_error"] = skipped.get("usage_error", 0) + 1
                continue

            total_gb = round(usage.total / (1024 ** 3), 2)
            if total_gb <= 0:
                skipped["empty"] = skipped.get("empty", 0) + 1
                continue

            disk = {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total_gb": total_gb,
                "used_gb": round(usage.used / (1024 ** 3), 2),
                "free_gb": round(usage.free / (1024 ** 3), 2),
                "percent": usage.percent,
            }
            key = sanitize_text(part.device).lower() or sanitize_text(part.mountpoint).lower()
            if key not in selected_by_device:
                selected_by_device[key] = disk
                continue

            current = selected_by_device[key]
            if mountpoint_rank(disk["mountpoint"]) < mountpoint_rank(current["mountpoint"]):
                selected_by_device[key] = disk
            else:
                skipped["duplicate"] = skipped.get("duplicate", 0) + 1
    except Exception as exc:
        logging.error("Logical disk collection failed: %s", exc)

    if skipped:
        logging.info(
            "Filtered logical disks: %s",
            ", ".join(f"{key}={value}" for key, value in sorted(skipped.items())),
        )
    return sorted(selected_by_device.values(), key=lambda item: sanitize_text(item.get("mountpoint")))


def get_system_serial() -> str:
    if wmi is None:
        return "Unknown"
    try:
        c = wmi.WMI()
        bios_items = c.Win32_BIOS()
        if not bios_items:
            return "Unknown"
        serial = sanitize_text(getattr(bios_items[0], "SerialNumber", ""))
        return serial or "Unknown"
    except Exception as exc:
        logging.error("System serial detection failed: %s", exc)
        return "Unknown"


def get_cpu_model() -> str:
    if wmi is None:
        return "Unknown"
    try:
        c = wmi.WMI()
        cpus = c.Win32_Processor()
        if not cpus:
            return "Unknown"
        return sanitize_text(getattr(cpus[0], "Name", "")) or "Unknown"
    except Exception as exc:
        logging.error("CPU detection failed: %s", exc)
        return "Unknown"


def _parse_wmi_datetime(value: str) -> str:
    raw = sanitize_text(value)
    if len(raw) < 14:
        return raw
    try:
        return datetime.strptime(raw[:14], "%Y%m%d%H%M%S").isoformat()
    except Exception:
        return raw


def get_os_info() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "platform": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "caption": "",
        "build_number": "",
        "install_date": "",
    }
    if wmi is None:
        return info
    try:
        c = wmi.WMI()
        rows = c.Win32_OperatingSystem()
        if not rows:
            return info
        os_item = rows[0]
        info["caption"] = sanitize_text(getattr(os_item, "Caption", ""))
        info["version"] = sanitize_text(getattr(os_item, "Version", "")) or info["version"]
        info["build_number"] = sanitize_text(getattr(os_item, "BuildNumber", ""))
        info["install_date"] = _parse_wmi_datetime(sanitize_text(getattr(os_item, "InstallDate", "")))
    except Exception as exc:
        logging.warning("OS info collection failed: %s", exc)
    return info


def _powershell_json(command: str) -> Any:
    result = run_cmd(["powershell", "-NoProfile", "-Command", command])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except Exception:
        return None


def get_network_info() -> Dict[str, Any]:
    adapters: List[Dict[str, Any]] = []
    primary_adapter_name = ""
    active_ipv4: List[str] = []
    active_ipv6: List[str] = []
    try:
        stats = psutil.net_if_stats()
        addrs_map = psutil.net_if_addrs()
        for adapter_name, addrs in addrs_map.items():
            state = stats.get(adapter_name)
            if not state or not state.isup:
                continue
            if "loopback" in adapter_name.lower():
                continue

            ipv4 = []
            ipv6 = []
            for addr in addrs:
                value = sanitize_text(getattr(addr, "address", ""))
                if not value:
                    continue
                family_value = getattr(addr, "family", "")
                if _is_af_inet6(family_value):
                    ipv6.append(value)
                    active_ipv6.append(value)
                elif _is_af_inet(family_value):
                    ipv4.append(value)
                    active_ipv4.append(value)

            if not ipv4 and not ipv6:
                continue

            adapters.append(
                {
                    "name": adapter_name,
                    "ipv4": ipv4,
                    "ipv6": ipv6,
                    "speed_mbps": getattr(state, "speed", 0),
                }
            )
            if not primary_adapter_name:
                primary_adapter_name = adapter_name
    except Exception as exc:
        logging.warning("Network adapter enumeration failed: %s", exc)

    default_gateway = ""
    dns_servers: List[str] = []
    gateway_data = _powershell_json(
        "Get-NetRoute -DestinationPrefix '0.0.0.0/0' | "
        "Sort-Object RouteMetric | Select-Object -First 1 -ExpandProperty NextHop | ConvertTo-Json -Compress"
    )
    if isinstance(gateway_data, str):
        default_gateway = sanitize_text(gateway_data)

    dns_data = _powershell_json(
        "Get-DnsClientServerAddress -AddressFamily IPv4 | "
        "Where-Object {$_.ServerAddresses -and $_.InterfaceAlias} | "
        "Select-Object -First 1 -ExpandProperty ServerAddresses | ConvertTo-Json -Compress"
    )
    if isinstance(dns_data, list):
        dns_servers = [sanitize_text(item) for item in dns_data if sanitize_text(item)]
    elif isinstance(dns_data, str):
        value = sanitize_text(dns_data)
        if value:
            dns_servers = [value]

    return {
        "primary_adapter_name": primary_adapter_name,
        "adapters": adapters,
        "active_ipv4": _dedupe_preserve_order(active_ipv4),
        "active_ipv6": _dedupe_preserve_order(active_ipv6),
        "default_gateway": default_gateway,
        "dns_servers": _dedupe_preserve_order(dns_servers),
    }


def get_active_ipv4_addresses() -> List[str]:
    values: List[str] = []
    try:
        stats = psutil.net_if_stats()
        addrs_map = psutil.net_if_addrs()
        for adapter_name, addrs in addrs_map.items():
            state = stats.get(adapter_name)
            if not state or not state.isup:
                continue
            if "loopback" in adapter_name.lower():
                continue
            for addr in addrs:
                family_value = getattr(addr, "family", "")
                if not _is_af_inet(family_value):
                    continue
                value = sanitize_text(getattr(addr, "address", ""))
                if value:
                    values.append(value)
    except Exception as exc:
        logging.warning("Active IPv4 quick scan failed: %s", exc)
    return _dedupe_preserve_order(values)


def get_health_info() -> Dict[str, Any]:
    now_ts = int(time.time())
    boot_time = int(psutil.boot_time())
    vm = psutil.virtual_memory()
    cpu_load = round(float(psutil.cpu_percent(interval=0.2)), 1)
    ram_used = round(float(vm.percent), 1)
    return {
        "uptime_seconds": max(0, now_ts - boot_time),
        "cpu_load_percent": cpu_load,
        "ram_used_percent": ram_used,
        "boot_time": boot_time,
        "last_reboot_at": boot_time,
        "last_reboot_iso": datetime.fromtimestamp(boot_time).isoformat(),
    }


def get_security_info() -> Dict[str, Any]:
    antivirus_items: List[Dict[str, Any]] = []
    if wmi is not None:
        try:
            sc = wmi.WMI(namespace=r"root\SecurityCenter2")
            for item in sc.AntiVirusProduct():
                antivirus_items.append(
                    {
                        "display_name": sanitize_text(getattr(item, "displayName", "")),
                        "product_state": sanitize_text(getattr(item, "productState", "")),
                    }
                )
        except Exception as exc:
            logging.warning("Antivirus data collection failed: %s", exc)

    bitlocker = {"system_drive_protection": "unknown", "system_drive_status": ""}
    bitlocker_data = _powershell_json(
        "Get-BitLockerVolume -MountPoint 'C:' | "
        "Select-Object ProtectionStatus,VolumeStatus | ConvertTo-Json -Compress"
    )
    if isinstance(bitlocker_data, dict):
        bitlocker["system_drive_protection"] = sanitize_text(bitlocker_data.get("ProtectionStatus")) or "unknown"
        bitlocker["system_drive_status"] = sanitize_text(bitlocker_data.get("VolumeStatus"))

    return {"antivirus": antivirus_items, "bitlocker": bitlocker}


def get_updates_info() -> Dict[str, Any]:
    last_hotfix_date = ""
    if wmi is not None:
        try:
            c = wmi.WMI()
            rows = c.Win32_QuickFixEngineering()
            dates = [sanitize_text(getattr(row, "InstalledOn", "")) for row in rows]
            dates = [item for item in dates if item]
            if dates:
                last_hotfix_date = dates[-1]
        except Exception as exc:
            logging.warning("Hotfix data collection failed: %s", exc)
    return {"last_hotfix_date": last_hotfix_date}


def collect_inventory(report_type: str = "full_snapshot", include_full_snapshot: bool = True) -> Dict[str, Any]:
    now_ts = int(time.time())
    user_login = get_active_console_user()
    health_info = get_health_info()
    outlook_info = collect_outlook_info(user_login, force_refresh=include_full_snapshot)
    network_info: Optional[Dict[str, Any]] = get_network_info() if include_full_snapshot else None
    if isinstance(network_info, dict):
        ip_list = _dedupe_preserve_order([sanitize_text(item) for item in network_info.get("active_ipv4", [])])
    else:
        ip_list = get_active_ipv4_addresses()
    ip_list = _dedupe_preserve_order(ip_list)
    ip_primary = ip_list[0] if ip_list else ""

    payload: Dict[str, Any] = {
        "hostname": socket.gethostname(),
        "mac_address": get_mac_address(),
        "current_user": user_login,
        "user_login": user_login,
        "user_full_name": resolve_user_full_name(user_login),
        "ip_primary": ip_primary,
        "ip_list": ip_list,
        "timestamp": now_ts,
        "report_type": report_type,
        "last_seen_at": now_ts,
        "health": health_info,
        "outlook": outlook_info,
        "uptime_seconds": health_info.get("uptime_seconds"),
        "cpu_load_percent": health_info.get("cpu_load_percent"),
        "ram_used_percent": health_info.get("ram_used_percent"),
        "last_reboot_at": health_info.get("last_reboot_at"),
    }

    if include_full_snapshot:
        payload.update(
            {
                "system_serial": get_system_serial(),
                "cpu_model": get_cpu_model(),
                "ram_gb": round(psutil.virtual_memory().total / (1024.0 ** 3), 2),
                "monitors": get_monitors(),
                "logical_disks": get_logical_disks(),
                "storage": get_storage_info(),
                "os_info": get_os_info(),
                "network": network_info or get_network_info(),
                "security": get_security_info(),
                "updates": get_updates_info(),
                "last_full_snapshot_at": now_ts,
            }
        )

    logging.info(
        "Inventory collected for host=%s user=%s type=%s",
        payload.get("hostname"),
        payload.get("current_user"),
        payload.get("report_type"),
    )
    return payload


def _requests_verify_arg(config: AgentConfig) -> Any:
    return config.ca_bundle or True


def _post_payload(payload: Dict[str, Any], config: AgentConfig) -> bool:
    headers = {"Content-Type": "application/json", "X-API-Key": config.api_key}
    verify_arg = _requests_verify_arg(config)
    retry_delays = [0, 2, 5, 15]

    for attempt, delay in enumerate(retry_delays, start=1):
        if delay > 0:
            time.sleep(delay)
        try:
            logging.info("Sending inventory to %s (attempt=%s)", config.server_url, attempt)
            response = requests.post(
                config.server_url,
                json=payload,
                headers=headers,
                timeout=config.timeout,
                verify=verify_arg,
            )
            response.raise_for_status()
            logging.info("Inventory sent successfully, status=%s", response.status_code)
            return True
        except requests.exceptions.RequestException as exc:
            logging.warning("Inventory send failed on attempt=%s: %s", attempt, exc)
    return False


def _inventory_queue_paths() -> List[Path]:
    pending_dir = get_inventory_queue_pending_dir()
    if not pending_dir.exists():
        return []
    return sorted([row for row in pending_dir.glob("*.json") if row.is_file()], key=lambda row: row.name)


def _inventory_queue_read(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.warning("Inventory queue read failed (%s): %s", path, exc)
        return None
    if not isinstance(data, dict):
        return None
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None
    data["id"] = str(data.get("id") or path.stem)
    data["created_at"] = _to_int(data.get("created_at"), int(time.time()))
    data["attempts"] = max(0, _to_int(data.get("attempts"), 0))
    data["next_attempt_at"] = _to_int(data.get("next_attempt_at"), 0)
    data["last_error"] = str(data.get("last_error") or "")
    return data


def _inventory_queue_write(path: Path, item: Dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(item, ensure_ascii=False), encoding="utf-8")


def _inventory_queue_dead_path(path: Path) -> Path:
    return get_inventory_queue_dead_dir() / path.name


def _inventory_queue_move_to_dead(path: Path, item: Optional[Dict[str, Any]], reason: str) -> None:
    payload: Dict[str, Any] = item or {}
    payload["dropped_reason"] = str(reason or "unknown")
    payload["dropped_at"] = int(time.time())
    dead_path = _inventory_queue_dead_path(path)
    try:
        _inventory_queue_write(dead_path, payload)
    except Exception as exc:
        logging.warning("Inventory dead-letter write failed (%s): %s", dead_path, exc)
    try:
        if path.exists():
            path.unlink()
    except Exception as exc:
        logging.warning("Inventory queue delete failed (%s): %s", path, exc)


def _inventory_queue_enqueue(payload: Dict[str, Any]) -> Path:
    now_ts = int(time.time())
    item_id = uuid.uuid4().hex
    filename = f"{now_ts:010d}_{item_id}.json"
    path = get_inventory_queue_pending_dir() / filename
    item = {
        "id": item_id,
        "created_at": now_ts,
        "payload": payload,
        "attempts": 0,
        "next_attempt_at": 0,
        "last_error": "",
    }
    _inventory_queue_write(path, item)
    return path


def _inventory_backoff_seconds(attempts: int) -> int:
    attempts_count = max(1, attempts)
    base = min(3600, 5 * (2 ** min(attempts_count - 1, 10)))
    jitter = random.uniform(0.85, 1.25)
    return max(5, int(base * jitter))


def _inventory_queue_prune_limits(config: AgentConfig) -> None:
    now_ts = int(time.time())
    max_age_seconds = config.inventory_queue_max_age_days * 24 * 60 * 60
    max_total_size = config.inventory_queue_max_total_mb * 1024 * 1024
    entries: List[Tuple[Path, Dict[str, Any], int]] = []

    for path in _inventory_queue_paths():
        try:
            size_bytes = int(path.stat().st_size)
        except Exception:
            size_bytes = 0
        item = _inventory_queue_read(path)
        if item is None:
            _inventory_queue_move_to_dead(path, None, "QUEUE_CORRUPT")
            continue
        if max_age_seconds > 0 and (now_ts - _to_int(item.get("created_at"), now_ts)) > max_age_seconds:
            logging.warning("Inventory queue item expired by age: %s", path.name)
            _inventory_queue_move_to_dead(path, item, "QUEUE_MAX_AGE")
            continue
        entries.append((path, item, size_bytes))

    while len(entries) > config.inventory_queue_max_items:
        path, item, _ = entries.pop(0)
        logging.warning("Inventory queue full by count, moving oldest to dead-letter: %s", path.name)
        _inventory_queue_move_to_dead(path, item, "QUEUE_FULL_COUNT")

    total_size = sum(max(0, size_bytes) for _, _, size_bytes in entries)
    while entries and total_size > max_total_size:
        path, item, size_bytes = entries.pop(0)
        logging.warning("Inventory queue full by size, moving oldest to dead-letter: %s", path.name)
        _inventory_queue_move_to_dead(path, item, "QUEUE_FULL_SIZE")
        total_size -= max(0, size_bytes)


def _inventory_queue_depth() -> int:
    return len(_inventory_queue_paths())


def _scan_outbox_depth() -> int:
    outbox_pending = PROGRAM_DATA_ROOT / "ScanAgent" / "outbox" / "pending"
    if not outbox_pending.exists():
        return 0
    return len([row for row in outbox_pending.glob("*.json") if row.is_file()])


def _read_scan_last_ingest_ok_at() -> Optional[int]:
    path = PROGRAM_DATA_ROOT / "ScanAgent" / "scan_agent_status.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _to_int(data.get("last_ingest_ok_at"), 0) or None


def _write_agent_status(payload: Dict[str, Any]) -> None:
    path = get_agent_status_path()
    try:
        _atomic_write_text(path, json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logging.debug("Agent status write failed (%s): %s", path, exc)


def send_data(payload: Dict[str, Any], config: AgentConfig) -> bool:
    try:
        enqueued_path = _inventory_queue_enqueue(payload)
    except Exception as exc:
        logging.error("Inventory queue enqueue failed: %s", exc)
        return False

    _inventory_queue_prune_limits(config)
    now_ts = int(time.time())
    sent_this_payload = False

    for path in _inventory_queue_paths()[: config.inventory_queue_batch]:
        item = _inventory_queue_read(path)
        if item is None:
            _inventory_queue_move_to_dead(path, None, "QUEUE_CORRUPT")
            continue

        next_attempt_at = _to_int(item.get("next_attempt_at"), 0)
        if next_attempt_at > now_ts:
            continue

        payload_row = item.get("payload")
        if not isinstance(payload_row, dict):
            _inventory_queue_move_to_dead(path, item, "QUEUE_INVALID_PAYLOAD")
            continue

        if _post_payload(payload_row, config):
            try:
                path.unlink(missing_ok=True)
            except Exception as exc:
                logging.warning("Inventory queue delete after ACK failed (%s): %s", path, exc)
            if path == enqueued_path:
                sent_this_payload = True
            continue

        attempts = _to_int(item.get("attempts"), 0) + 1
        item["attempts"] = attempts
        item["next_attempt_at"] = now_ts + _inventory_backoff_seconds(attempts)
        item["last_error"] = "NET_TIMEOUT_OR_HTTP_ERROR"
        try:
            _inventory_queue_write(path, item)
        except Exception as exc:
            logging.warning("Inventory queue rewrite failed (%s): %s", path, exc)

    return sent_this_payload


def build_health_url(server_url: str) -> str:
    parsed = urlparse(server_url)
    return urlunparse((parsed.scheme, parsed.netloc, "/health", "", "", ""))


def check_configuration(config: AgentConfig) -> bool:
    ok = True
    if not config.server_url:
        logging.error("SERVER_URL is empty")
        ok = False
    if not config.api_key:
        logging.error("API_KEY is empty")
        ok = False
    if not ok:
        return False

    parsed = urlparse(config.server_url)
    if parsed.scheme.lower() != "https":
        logging.warning("SERVER_URL is not HTTPS: %s", config.server_url)

    host = parsed.hostname or ""
    port = int(parsed.port or (443 if parsed.scheme.lower() == "https" else 80))
    if host:
        try:
            resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            ips = sorted({str(row[4][0]) for row in resolved if row and len(row) > 4 and row[4]})
            logging.info("DNS resolve host=%s port=%s -> %s", host, port, ", ".join(ips[:6]) or "no-ip")
        except Exception as exc:
            logging.error("DNS resolve failed for %s:%s: %s", host, port, exc)
            return False

    verify_arg = _requests_verify_arg(config)
    health_url = build_health_url(config.server_url)
    try:
        health_response = requests.get(health_url, timeout=config.timeout, verify=verify_arg)
        logging.info("Health check %s -> status=%s", health_url, health_response.status_code)
    except requests.exceptions.RequestException as exc:
        logging.error("Health endpoint is not reachable: %s", exc)
        return False

    try:
        probe_payload = {"timestamp": int(time.time())}
        probe = requests.post(
            config.server_url,
            json=probe_payload,
            headers={"Content-Type": "application/json", "X-API-Key": config.api_key},
            timeout=config.timeout,
            verify=verify_arg,
        )
        logging.info("Inventory auth probe %s -> status=%s", config.server_url, probe.status_code)
        if probe.status_code in (401, 403):
            logging.error("Inventory auth probe failed: invalid API key")
            return False
        if probe.status_code >= 500:
            logging.error("Inventory endpoint returned server error on probe: status=%s", probe.status_code)
            return False
    except requests.exceptions.RequestException as exc:
        logging.error("Inventory endpoint is not reachable: %s", exc)
        return False

    return True


def run_loop(config: AgentConfig, run_once: bool = False) -> int:
    process_started_at = int(time.time())
    if run_once:
        _run_scan_sidecar(run_once=True)
        payload = collect_inventory(report_type="full_snapshot", include_full_snapshot=True)
        health_info = payload.get("health") if isinstance(payload.get("health"), dict) else {}
        try:
            maybe_notify_reboot_required(health_info, config)
        except Exception as exc:
            logging.warning("Reboot reminder check failed: %s", exc)
        sent_now = send_data(payload, config)
        _write_agent_status(
            {
                "last_inventory_ok_at": int(time.time()) if sent_now else None,
                "inventory_queue_depth": _inventory_queue_depth(),
                "scan_outbox_depth": _scan_outbox_depth(),
                "last_scan_ingest_ok_at": _read_scan_last_ingest_ok_at(),
                "last_error": "" if sent_now else "INVENTORY_SEND_FAILED",
                "version": AGENT_VERSION,
                "uptime_sec": max(0, int(time.time()) - process_started_at),
                "updated_at": int(time.time()),
            }
        )
        return 0 if sent_now else 1

    scan_thread: Optional[threading.Thread] = None
    scan_restart_attempt = 0
    next_scan_restart_ts = 0
    last_inventory_ok_at: Optional[int] = None
    last_error = ""
    last_status_write_ts = 0

    def ensure_scan_sidecar_alive(now_ts: int) -> None:
        nonlocal scan_thread, scan_restart_attempt, next_scan_restart_ts
        if scan_thread is not None and scan_thread.is_alive():
            scan_restart_attempt = 0
            return
        if now_ts < next_scan_restart_ts:
            return
        if scan_thread is not None:
            logging.warning("Scan sidecar thread is not alive; restarting")
        scan_thread = threading.Thread(
            target=_run_scan_sidecar,
            kwargs={"run_once": False},
            daemon=True,
            name="scan-sidecar",
        )
        scan_thread.start()
        if scan_thread.is_alive():
            logging.info("Scan sidecar thread started (alive=%s)", scan_thread.is_alive())
            scan_restart_attempt = 0
            next_scan_restart_ts = now_ts
            return
        delays = [10, 30, 60, 300]
        delay = delays[min(scan_restart_attempt, len(delays) - 1)]
        scan_restart_attempt += 1
        next_scan_restart_ts = now_ts + delay
        logging.warning("Scan sidecar failed to start, next retry in %ss", delay)

    next_full_snapshot_ts = 0
    while True:
        now_ts = int(time.time())
        ensure_scan_sidecar_alive(now_ts)
        include_full_snapshot = now_ts >= next_full_snapshot_ts
        report_type = "full_snapshot" if include_full_snapshot else "heartbeat"
        try:
            inventory_data = collect_inventory(report_type=report_type, include_full_snapshot=include_full_snapshot)
            health_info = inventory_data.get("health") if isinstance(inventory_data.get("health"), dict) else {}
            try:
                maybe_notify_reboot_required(health_info, config)
            except Exception as exc:
                logging.warning("Reboot reminder check failed: %s", exc)
            sent = send_data(inventory_data, config)
            if sent:
                last_inventory_ok_at = now_ts
                last_error = ""
            else:
                last_error = "INVENTORY_SEND_FAILED"
            if include_full_snapshot:
                if sent:
                    next_full_snapshot_ts = now_ts + config.full_snapshot_interval
                else:
                    next_full_snapshot_ts = now_ts + min(config.heartbeat_interval, 300)
        except Exception as exc:
            logging.error("Unexpected error in main loop: %s", exc)
            last_error = f"MAIN_LOOP_ERROR:{type(exc).__name__}"
            if include_full_snapshot and next_full_snapshot_ts == 0:
                next_full_snapshot_ts = now_ts + min(config.heartbeat_interval, 300)

        if (now_ts - last_status_write_ts) >= STATUS_WRITE_INTERVAL_SEC:
            _write_agent_status(
                {
                    "last_inventory_ok_at": last_inventory_ok_at,
                    "inventory_queue_depth": _inventory_queue_depth(),
                    "scan_outbox_depth": _scan_outbox_depth(),
                    "last_scan_ingest_ok_at": _read_scan_last_ingest_ok_at(),
                    "last_error": last_error,
                    "version": AGENT_VERSION,
                    "uptime_sec": max(0, int(time.time()) - process_started_at),
                    "updated_at": int(time.time()),
                }
            )
            last_status_write_ts = now_ts

        sleep_seconds = config.heartbeat_interval + random.randint(0, config.heartbeat_jitter_sec)
        logging.info("Sleeping %s seconds before next cycle", sleep_seconds)
        time.sleep(sleep_seconds)


def main(argv: Optional[Sequence[str]] = None) -> int:
    global LOADED_ENV_FILES, RUN_CMD_TIMEOUT_SEC, OUTLOOK_SCAN_CACHE_TTL_SEC
    LOADED_ENV_FILES = bootstrap_env_from_files()
    args = parse_args(argv)
    log_file_path = setup_logging()

    config = load_config()
    RUN_CMD_TIMEOUT_SEC = config.run_cmd_timeout_sec
    OUTLOOK_SCAN_CACHE_TTL_SEC = config.outlook_refresh_sec

    logging.info("=== Starting IT-Invent Agent ===")
    logging.info(
        "Config: server=%s heartbeat=%ss full_snapshot=%ss jitter=%ss outlook_refresh=%ss once=%s check=%s "
        "run_cmd_timeout=%ss inv_queue_batch=%s inv_queue_max_items=%s inv_queue_max_age_days=%s inv_queue_max_total_mb=%s "
        "reminder_enabled=%s reminder_days=%s reminder_interval_h=%s reminder_timeout_s=%s "
        "reminder_work_start_h=%s reminder_work_end_h=%s reminder_weekdays_only=%s "
        "log=%s inv_queue_pending=%s inv_queue_dead=%s reminder_state=%s status_file=%s",
        config.server_url,
        config.heartbeat_interval,
        config.full_snapshot_interval,
        config.heartbeat_jitter_sec,
        config.outlook_refresh_sec,
        args.once,
        args.check,
        config.run_cmd_timeout_sec,
        config.inventory_queue_batch,
        config.inventory_queue_max_items,
        config.inventory_queue_max_age_days,
        config.inventory_queue_max_total_mb,
        config.reboot_reminder_enabled,
        config.reboot_reminder_days,
        config.reboot_reminder_interval_hours,
        config.reboot_reminder_timeout_sec,
        config.reboot_reminder_work_start_hour,
        config.reboot_reminder_work_end_hour,
        config.reboot_reminder_weekdays_only,
        log_file_path,
        get_inventory_queue_pending_dir(),
        get_inventory_queue_dead_dir(),
        get_reboot_reminder_state_path(),
        get_agent_status_path(),
    )
    if LOADED_ENV_FILES:
        logging.info("Loaded .env sources for agent: %s", "; ".join(LOADED_ENV_FILES))
    else:
        logging.info("No .env sources loaded automatically for agent")

    if args.check:
        return 0 if check_configuration(config) else 1

    if not config.api_key:
        logging.error("Agent API key is not configured. Set ITINV_AGENT_API_KEY or allow legacy key explicitly.")
        return 1

    if not is_admin():
        logging.warning(
            "Agent is running without Administrator privileges. "
            "SMART counters may be unavailable for some disks."
        )

    return run_loop(config, run_once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
