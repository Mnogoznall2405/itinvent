from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import random
import re
import socket
import sys
import threading
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests
import yaml

try:
    import fitz  # type: ignore
except Exception:
    fitz = None

try:
    from watchdog.events import FileSystemEventHandler  # type: ignore
    from watchdog.observers import Observer  # type: ignore
except Exception:
    FileSystemEventHandler = object  # type: ignore
    Observer = None  # type: ignore


DEFAULT_SERVER_BASE = "https://hubit.zsgp.ru/api/v1/scan"
DEFAULT_API_KEY = "itinvent_agent_secure_token_v1"
DEFAULT_POLL_INTERVAL = 60
DEFAULT_HTTP_TIMEOUT = 20
DEFAULT_MAX_FILE_SIZE_MB = 50
DEFAULT_OUTBOX_MAX_ITEMS = 5000
DEFAULT_OUTBOX_MAX_AGE_DAYS = 14
DEFAULT_OUTBOX_MAX_TOTAL_MB = 512
STATE_RETENTION_DAYS = 90
MAX_HASH_ENTRIES = 120_000

USER_SUBDIRS = ("Desktop", "Documents", "Downloads")
IGNORED_USER_DIRS = {
    "all users",
    "default",
    "default user",
    "public",
    "defaultappspool",
}

TEXT_EXTENSIONS = {
    ".txt",
    ".csv",
    ".log",
    ".json",
    ".xml",
    ".ini",
    ".conf",
    ".md",
    ".rtf",
}

PROGRAM_DATA = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "IT-Invent" / "ScanAgent"
TEMP_DIR = Path(os.environ.get("TEMP", r"C:\Windows\Temp"))

LOG_FILE = "scan_agent.log"
STATE_FILE = "scan_agent_state.json"
OUTBOX_DIR = "outbox"
OUTBOX_PENDING_DIR = "pending"
OUTBOX_DEAD_DIR = "dead_letter"
STATUS_FILE = "scan_agent_status.json"
STATUS_UPDATE_INTERVAL_SEC = 30
ENV_FILE_NAME = ".env"


def _setup_paths() -> Tuple[Path, Path, Path, Path, Path]:
    root = PROGRAM_DATA
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        root = TEMP_DIR
        root.mkdir(parents=True, exist_ok=True)
    outbox_root = root / OUTBOX_DIR
    pending_dir = outbox_root / OUTBOX_PENDING_DIR
    dead_dir = outbox_root / OUTBOX_DEAD_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    dead_dir.mkdir(parents=True, exist_ok=True)
    return root / LOG_FILE, root / STATE_FILE, pending_dir, dead_dir, root / STATUS_FILE


LOG_PATH, STATE_PATH, OUTBOX_PENDING_PATH, OUTBOX_DEAD_PATH, STATUS_PATH = _setup_paths()


def _strip_env_value(raw: str) -> str:
    value = str(raw or "").strip()
    if len(value) >= 2 and ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
        return value[1:-1]
    return value


def _read_env_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return ""


def bootstrap_env_from_files() -> List[str]:
    loaded: List[str] = []
    seen = set()
    candidates: List[Path] = []
    explicit = str(os.getenv("SCAN_AGENT_ENV_FILE", "")).strip()
    if explicit:
        candidates.append(Path(explicit))
    current = Path(__file__).resolve()
    candidates.append(current.parent / ENV_FILE_NAME)
    for parent in list(current.parents)[:4]:
        candidates.append(parent / ENV_FILE_NAME)
    candidates.append(Path.cwd() / ENV_FILE_NAME)
    candidates.append(PROGRAM_DATA.parent / ENV_FILE_NAME)

    for raw_path in candidates:
        try:
            path = raw_path.expanduser().resolve()
        except Exception:
            path = raw_path
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if not path.exists() or not path.is_file():
            continue
        text = _read_env_text(path)
        if not text:
            continue
        count = 0
        for line in text.splitlines():
            row = line.strip()
            if not row or row.startswith("#") or "=" not in row:
                continue
            k, v = row.split("=", 1)
            k = k.strip()
            if not k or k in os.environ:
                continue
            os.environ[k] = _strip_env_value(v)
            count += 1
        if count > 0:
            loaded.append(f"{path} ({count})")
    return loaded


def setup_logging() -> None:
    handlers: List[logging.Handler] = [
        RotatingFileHandler(LOG_PATH, maxBytes=8 * 1024 * 1024, backupCount=3, encoding="utf-8")
    ]
    if hasattr(os.sys.stdout, "isatty") and os.sys.stdout.isatty():
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp.{uuid.uuid4().hex}")
    temp_path.write_text(content, encoding=encoding)
    os.replace(str(temp_path), str(path))


def _read_env() -> Dict[str, Any]:
    poll = max(30, _to_int(os.getenv("SCAN_AGENT_POLL_INTERVAL_SEC", str(DEFAULT_POLL_INTERVAL)), DEFAULT_POLL_INTERVAL))
    max_size_mb = max(1, _to_int(os.getenv("SCAN_AGENT_MAX_FILE_MB", str(DEFAULT_MAX_FILE_SIZE_MB)), DEFAULT_MAX_FILE_SIZE_MB))
    allow_default_key = _to_bool(os.getenv("ITINV_AGENT_ALLOW_DEFAULT_KEY", "1"), default=True)
    api_key = str(os.getenv("SCAN_AGENT_API_KEY", "")).strip()
    if not api_key:
        if allow_default_key:
            api_key = DEFAULT_API_KEY
            logging.warning("SCAN_AGENT_API_KEY is empty; using legacy default key because ITINV_AGENT_ALLOW_DEFAULT_KEY=1")
        else:
            logging.error("SCAN_AGENT_API_KEY is empty and ITINV_AGENT_ALLOW_DEFAULT_KEY=0")

    return {
        "server_base": str(os.getenv("SCAN_AGENT_SERVER_BASE", DEFAULT_SERVER_BASE)).strip().rstrip("/"),
        "api_key": api_key,
        "poll_interval": poll,
        "timeout": max(5, _to_int(os.getenv("SCAN_AGENT_HTTP_TIMEOUT_SEC", str(DEFAULT_HTTP_TIMEOUT)), DEFAULT_HTTP_TIMEOUT)),
        "max_file_bytes": max_size_mb * 1024 * 1024,
        "run_scan_on_start": str(os.getenv("SCAN_AGENT_SCAN_ON_START", "1")).strip() not in {"0", "false", "False"},
        "watchdog_enabled": str(os.getenv("SCAN_AGENT_WATCHDOG_ENABLED", "1")).strip() not in {"0", "false", "False"},
        "watchdog_batch_size": max(10, _to_int(os.getenv("SCAN_AGENT_WATCHDOG_BATCH_SIZE", "200"), 200)),
        "roots_refresh_sec": max(60, _to_int(os.getenv("SCAN_AGENT_ROOTS_REFRESH_SEC", "300"), 300)),
        "branch": str(os.getenv("SCAN_AGENT_BRANCH", "")).strip(),
        "patterns_file": str(os.getenv("SCAN_AGENT_PATTERNS_FILE", "")).strip(),
        "outbox_max_items": max(100, _to_int(os.getenv("SCAN_AGENT_OUTBOX_MAX_ITEMS", str(DEFAULT_OUTBOX_MAX_ITEMS)), DEFAULT_OUTBOX_MAX_ITEMS)),
        "outbox_max_age_days": max(1, _to_int(os.getenv("SCAN_AGENT_OUTBOX_MAX_AGE_DAYS", str(DEFAULT_OUTBOX_MAX_AGE_DAYS)), DEFAULT_OUTBOX_MAX_AGE_DAYS)),
        "outbox_max_total_mb": max(32, _to_int(os.getenv("SCAN_AGENT_OUTBOX_MAX_TOTAL_MB", str(DEFAULT_OUTBOX_MAX_TOTAL_MB)), DEFAULT_OUTBOX_MAX_TOTAL_MB)),
    }


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"hashes": {}, "files": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        hashes = data.get("hashes") if isinstance(data, dict) else {}
        files = data.get("files") if isinstance(data, dict) else {}
        if not isinstance(hashes, dict):
            hashes = {}
        if not isinstance(files, dict):
            files = {}
        return {"hashes": hashes, "files": files}
    except Exception:
        return {"hashes": {}, "files": {}}


def _save_state(state: Dict[str, Any]) -> None:
    try:
        _atomic_write_text(STATE_PATH, json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logging.warning("Failed to save state: %s", exc)


def _prune_state(state: Dict[str, Any]) -> None:
    now_ts = int(time.time())
    min_ts = now_ts - STATE_RETENTION_DAYS * 24 * 60 * 60
    hashes = state.get("hashes") if isinstance(state.get("hashes"), dict) else {}
    files = state.get("files") if isinstance(state.get("files"), dict) else {}

    stale_hashes = [key for key, ts in hashes.items() if _to_int(ts, 0) < min_ts]
    for key in stale_hashes:
        hashes.pop(key, None)

    stale_files = [key for key, meta in files.items() if _to_int((meta or {}).get("ts"), 0) < min_ts]
    for key in stale_files:
        files.pop(key, None)

    if len(hashes) > MAX_HASH_ENTRIES:
        ordered = sorted(hashes.items(), key=lambda item: _to_int(item[1], 0), reverse=True)
        keep = dict(ordered[:MAX_HASH_ENTRIES])
        hashes.clear()
        hashes.update(keep)

    state["hashes"] = hashes
    state["files"] = files


def _norm_path(path: Path) -> str:
    return str(path).lower()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _snippet(text: str, start: int, end: int, radius: int = 30) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right].replace("\n", " ").strip()


def _read_text_with_fallback(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return ""


def _agent_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _resolve_patterns_file(raw: str) -> Path:
    text = str(raw or "").strip()
    if text:
        explicit = Path(text)
        if explicit.is_absolute():
            return explicit
        return (Path.cwd() / explicit).resolve()
    return (_agent_base_dir() / "patterns_strict.yaml").resolve()


def _re_flags(flags: Any) -> int:
    out = 0
    if not isinstance(flags, list):
        return out
    for item in flags:
        token = str(item or "").strip().lower()
        if token in {"ignorecase", "i"}:
            out |= re.IGNORECASE
        elif token in {"dotall", "s"}:
            out |= re.DOTALL
        elif token in {"multiline", "m"}:
            out |= re.MULTILINE
    return out


def _load_pattern_defs(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        logging.error("Strict patterns file not found: %s", path)
        return []
    text = _read_text_with_fallback(path)
    if not text.strip():
        logging.error("Strict patterns file is empty: %s", path)
        return []
    try:
        payload = yaml.safe_load(text) or {}
    except Exception as exc:
        logging.error("Strict patterns parse failed: %s", exc)
        return []

    rows = payload.get("patterns") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []

    defs: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "regex").strip().lower() != "regex":
            continue
        pattern_id = str(row.get("id") or "").strip()
        pattern_raw = str(row.get("pattern") or "")
        if not pattern_id or not pattern_raw:
            continue
        name = str(row.get("name") or pattern_id)
        weight = float(row.get("weight") or 1.0)
        try:
            regex = re.compile(pattern_raw, _re_flags(row.get("flags")))
        except Exception as exc:
            logging.warning("Pattern compile failed id=%s: %s", pattern_id, exc)
            continue
        defs.append(
            {
                "id": pattern_id,
                "name": name,
                "weight": weight,
                "regex": regex,
            }
        )
    if not defs:
        logging.error("No strict regex patterns loaded from %s", path)
        return []
    logging.info("Loaded strict patterns for agent: file=%s count=%s", path, len(defs))
    return defs


def scan_text(text: str, pattern_defs: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    source = str(text or "")
    if not source.strip() or not pattern_defs:
        return []
    out: List[Dict[str, str]] = []
    for item in pattern_defs:
        pattern = str(item.get("id") or "")
        name = str(item.get("name") or pattern)
        weight = float(item.get("weight") or 1.0)
        regex = item.get("regex")
        if not pattern or regex is None:
            continue
        for match in regex.finditer(source):
            out.append(
                {
                    "pattern": pattern,
                    "pattern_name": name,
                    "weight": str(weight),
                    "value": match.group(0),
                    "snippet": _snippet(source, match.start(), match.end()),
                }
            )
            if len(out) >= 100:
                return out
    return out


def _looks_gibberish(text: str) -> bool:
    content = str(text or "")
    if len(content.strip()) < 120:
        return True
    printable = sum(1 for ch in content if ch.isprintable())
    letters = sum(1 for ch in content if ch.isalpha())
    if printable == 0:
        return True
    letter_ratio = letters / max(1, printable)
    return letter_ratio < 0.35


def _extract_pdf_text(path: Path, max_pages: int = 10) -> str:
    if fitz is None:
        return ""
    text_parts: List[str] = []
    try:
        with fitz.open(path) as doc:
            total = min(max_pages, len(doc))
            for idx in range(total):
                text_parts.append(doc.load_page(idx).get_text("text") or "")
    except Exception as exc:
        logging.debug("PDF text extraction failed for %s: %s", path, exc)
    return "\n".join(text_parts).strip()


def _first_pdf_pages_b64(path: Path, pages: int = 3) -> str:
    if fitz is None:
        return ""
    try:
        with fitz.open(path) as src:
            out = fitz.open()
            total = min(pages, len(src))
            for idx in range(total):
                out.insert_pdf(src, from_page=idx, to_page=idx)
            data = out.tobytes()
        return base64.b64encode(data).decode("ascii")
    except Exception as exc:
        logging.warning("Failed to build PDF slice for %s: %s", path, exc)
        return ""


def _read_text_file(path: Path, max_bytes: int = 2 * 1024 * 1024) -> str:
    try:
        with path.open("rb") as f:
            raw = f.read(max_bytes)
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _iter_target_roots() -> Iterable[Path]:
    users_root = Path(r"C:\Users")
    if not users_root.exists():
        return []
    roots: List[Path] = []
    for user_dir in users_root.iterdir():
        if not user_dir.is_dir():
            continue
        name = user_dir.name.strip().lower()
        if name in IGNORED_USER_DIRS:
            continue
        for sub in USER_SUBDIRS:
            target = user_dir / sub
            if target.exists() and target.is_dir():
                roots.append(target)
    return roots


def _iter_files(roots: Iterable[Path], max_file_bytes: int) -> Iterable[Path]:
    for root in roots:
        for dirpath, _, filenames in os.walk(root):
            for file_name in filenames:
                path = Path(dirpath) / file_name
                try:
                    stat_result = path.stat()
                except Exception:
                    continue
                if stat_result.st_size <= 0 or stat_result.st_size > max_file_bytes:
                    continue
                yield path


def _extract_user_from_path(path: Path) -> str:
    parts = [part for part in path.parts if part]
    for idx, part in enumerate(parts):
        if part.lower() == "users" and idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def _mac_address() -> str:
    mac = uuid.getnode()
    raw = f"{mac:012X}"
    return ":".join(raw[i:i + 2] for i in range(0, 12, 2))


def _hostname() -> str:
    return str(socket.gethostname() or "unknown-host")


def _primary_ip() -> str:
    try:
        return socket.gethostbyname(_hostname())
    except Exception:
        return ""


class _PathEventHandler(FileSystemEventHandler):
    def __init__(self, agent: "ScanAgent") -> None:
        super().__init__()
        self.agent = agent

    def on_created(self, event: Any) -> None:
        if not getattr(event, "is_directory", False):
            self.agent.enqueue_path(Path(str(getattr(event, "src_path", ""))))

    def on_modified(self, event: Any) -> None:
        if not getattr(event, "is_directory", False):
            self.agent.enqueue_path(Path(str(getattr(event, "src_path", ""))))

    def on_moved(self, event: Any) -> None:
        if not getattr(event, "is_directory", False):
            self.agent.enqueue_path(Path(str(getattr(event, "dest_path", ""))))


class ScanAgent:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.patterns_path = _resolve_patterns_file(self.config.get("patterns_file", ""))
        self.pattern_defs = _load_pattern_defs(self.patterns_path)
        self.state = _load_state()
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": self.config["api_key"]})
        self.agent_id = _hostname().lower()

        self._lock = threading.RLock()
        self._pending_paths: Set[str] = set()
        self._roots: List[Path] = list(_iter_target_roots())
        self._observer: Optional[Any] = None
        self._state_dirty = False
        self._last_ingest_ok_at: Optional[int] = None
        self._last_error: str = ""
        self._last_status_write_at: int = 0

    def _url(self, suffix: str) -> str:
        return f"{self.config['server_base']}/{suffix.lstrip('/')}"

    def _send(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.config["timeout"])
        return self.session.request(method=method, url=url, **kwargs)

    def _write_status(self, force: bool = False) -> None:
        now_ts = int(time.time())
        if not force and (now_ts - self._last_status_write_at) < STATUS_UPDATE_INTERVAL_SEC:
            return
        payload = {
            "last_ingest_ok_at": self._last_ingest_ok_at,
            "outbox_depth": self._outbox_depth(),
            "pending_paths": len(self._pending_paths),
            "last_error": self._last_error,
            "agent_id": self.agent_id,
            "updated_at": now_ts,
        }
        try:
            _atomic_write_text(STATUS_PATH, json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            self._last_status_write_at = now_ts
        except Exception as exc:
            logging.debug("Scan status write failed: %s", exc)

    def _outbox_paths(self) -> List[Path]:
        if not OUTBOX_PENDING_PATH.exists():
            return []
        return sorted([row for row in OUTBOX_PENDING_PATH.glob("*.json") if row.is_file()], key=lambda row: row.name)

    def _outbox_depth(self) -> int:
        return len(self._outbox_paths())

    def _outbox_read(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logging.warning("Outbox read failed (%s): %s", path, exc)
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
        data["event_id"] = str(data.get("event_id") or payload.get("event_id") or "")
        data["last_error"] = str(data.get("last_error") or "")
        return data

    def _outbox_write(self, path: Path, item: Dict[str, Any]) -> None:
        _atomic_write_text(path, json.dumps(item, ensure_ascii=False), encoding="utf-8")

    def _outbox_move_to_dead(self, path: Path, item: Optional[Dict[str, Any]], reason: str) -> None:
        payload = item or {}
        payload["dropped_reason"] = str(reason or "unknown")
        payload["dropped_at"] = int(time.time())
        dead_path = OUTBOX_DEAD_PATH / path.name
        try:
            self._outbox_write(dead_path, payload)
        except Exception as exc:
            logging.warning("Outbox dead-letter write failed (%s): %s", dead_path, exc)
        try:
            path.unlink(missing_ok=True)
        except Exception as exc:
            logging.warning("Outbox delete failed (%s): %s", path, exc)

    def _outbox_has_event(self, event_id: str) -> bool:
        check_id = str(event_id or "").strip()
        if not check_id:
            return False
        for path in self._outbox_paths():
            item = self._outbox_read(path)
            if not item:
                continue
            if str(item.get("event_id") or "") == check_id:
                return True
        return False

    def _outbox_enqueue(self, payload: Dict[str, Any]) -> Optional[Path]:
        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            return None
        if self._outbox_has_event(event_id):
            return None
        now_ts = int(time.time())
        item_id = uuid.uuid4().hex
        path = OUTBOX_PENDING_PATH / f"{now_ts:010d}_{item_id}.json"
        item = {
            "id": item_id,
            "event_id": event_id,
            "created_at": now_ts,
            "payload": payload,
            "attempts": 0,
            "next_attempt_at": 0,
            "last_error": "",
        }
        try:
            self._outbox_write(path, item)
            return path
        except Exception as exc:
            logging.warning("Outbox enqueue failed: %s", exc)
            return None

    def _outbox_backoff_seconds(self, attempts: int) -> int:
        attempts_count = max(1, attempts)
        base = min(3600, 5 * (2 ** min(attempts_count - 1, 10)))
        jitter = random.uniform(0.85, 1.25)
        return max(5, int(base * jitter))

    def _outbox_prune_limits(self) -> None:
        now_ts = int(time.time())
        max_age_seconds = int(self.config["outbox_max_age_days"]) * 24 * 60 * 60
        max_total_size = int(self.config["outbox_max_total_mb"]) * 1024 * 1024
        entries: List[Tuple[Path, Dict[str, Any], int]] = []
        for path in self._outbox_paths():
            try:
                size_bytes = int(path.stat().st_size)
            except Exception:
                size_bytes = 0
            item = self._outbox_read(path)
            if not item:
                self._outbox_move_to_dead(path, None, "OUTBOX_CORRUPT")
                continue
            if max_age_seconds > 0 and (now_ts - _to_int(item.get("created_at"), now_ts)) > max_age_seconds:
                self._outbox_move_to_dead(path, item, "OUTBOX_MAX_AGE")
                continue
            entries.append((path, item, size_bytes))

        while len(entries) > int(self.config["outbox_max_items"]):
            path, item, _ = entries.pop(0)
            logging.warning("Outbox full by count, moving oldest to dead-letter: %s", path.name)
            self._outbox_move_to_dead(path, item, "OUTBOX_FULL_COUNT")

        total_size = sum(max(0, size_bytes) for _, _, size_bytes in entries)
        while entries and total_size > max_total_size:
            path, item, size_bytes = entries.pop(0)
            logging.warning("Outbox full by size, moving oldest to dead-letter: %s", path.name)
            self._outbox_move_to_dead(path, item, "OUTBOX_FULL_SIZE")
            total_size -= max(0, size_bytes)

    def _register_scanned(self, path: Path, file_hash: str, stat_result: os.stat_result) -> None:
        now_ts = int(time.time())
        files = self.state.setdefault("files", {})
        hashes = self.state.setdefault("hashes", {})
        files[_norm_path(path)] = {
            "hash": file_hash,
            "mtime": int(stat_result.st_mtime),
            "size": int(stat_result.st_size),
            "ts": now_ts,
        }
        hashes[file_hash] = now_ts
        self._state_dirty = True

    def _register_scanned_from_payload(self, payload: Dict[str, Any]) -> None:
        file_path = str(payload.get("file_path") or "").strip()
        file_hash = str(payload.get("file_hash") or "").strip()
        if not file_path or not file_hash:
            return
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        mtime = _to_int(metadata.get("mtime"), int(time.time()))
        size_value = _to_int(payload.get("file_size"), 0)
        now_ts = int(time.time())
        files = self.state.setdefault("files", {})
        hashes = self.state.setdefault("hashes", {})
        files[_norm_path(Path(file_path))] = {
            "hash": file_hash,
            "mtime": mtime,
            "size": size_value,
            "ts": now_ts,
        }
        hashes[file_hash] = now_ts
        self._state_dirty = True

    def _already_scanned(self, path: Path, stat_result: os.stat_result) -> bool:
        record = (self.state.get("files") or {}).get(_norm_path(path))
        if not isinstance(record, dict):
            return False
        same_mtime = _to_int(record.get("mtime"), -1) == int(stat_result.st_mtime)
        same_size = _to_int(record.get("size"), -1) == int(stat_result.st_size)
        if not (same_mtime and same_size):
            return False
        old_hash = str(record.get("hash") or "")
        if not old_hash:
            return False
        return old_hash in (self.state.get("hashes") or {})

    def _build_event_id(self, path: Path, file_hash: str, stat_result: os.stat_result) -> str:
        source = "|".join(
            [
                self.agent_id,
                _norm_path(path),
                str(file_hash or "").strip().lower(),
                str(int(stat_result.st_mtime)),
                str(int(stat_result.st_size)),
            ]
        )
        return hashlib.sha256(source.encode("utf-8", errors="ignore")).hexdigest()

    def _analyze_file(self, path: Path, file_hash: str, stat_result: os.stat_result) -> Optional[Dict[str, Any]]:
        ext = path.suffix.lower()
        matches: List[Dict[str, str]] = []
        text_excerpt = ""
        pdf_slice_b64 = ""
        source_kind = "metadata"

        if ext == ".pdf":
            source_kind = "pdf"
            text = _extract_pdf_text(path, max_pages=10)
            if text and not _looks_gibberish(text):
                matches = scan_text(text, self.pattern_defs)
                text_excerpt = text[:4000]
            else:
                pdf_slice_b64 = _first_pdf_pages_b64(path, pages=3)
                source_kind = "pdf_slice"
        elif ext in TEXT_EXTENSIONS:
            source_kind = "text"
            text = _read_text_file(path)
            if text:
                matches = scan_text(text, self.pattern_defs)
                text_excerpt = text[:4000]

        if not matches and not pdf_slice_b64:
            return None

        return {
            "agent_id": self.agent_id,
            "hostname": _hostname(),
            "branch": self.config["branch"],
            "user_login": _extract_user_from_path(path),
            "user_full_name": "",
            "file_path": str(path),
            "file_name": path.name,
            "file_hash": file_hash,
            "file_size": int(stat_result.st_size),
            "source_kind": source_kind,
            "text_excerpt": text_excerpt,
            "pdf_slice_b64": pdf_slice_b64,
            "local_pattern_hits": matches,
            "metadata": {
                "mtime": int(stat_result.st_mtime),
                "ext": ext,
            },
        }

    def _send_ingest(self, payload: Dict[str, Any]) -> bool:
        try:
            response = self._send("POST", self._url("ingest"), json=payload)
            if response.status_code >= 300:
                logging.warning("Ingest failed status=%s body=%s", response.status_code, response.text[:300])
                self._last_error = f"INGEST_HTTP_{response.status_code}"
                return False
            self._last_ingest_ok_at = int(time.time())
            self._last_error = ""
            return True
        except Exception as exc:
            logging.warning("Ingest request error: %s", exc)
            self._last_error = f"INGEST_ERR:{type(exc).__name__}"
            return False

    def _drain_outbox(self, max_items: int = 100) -> int:
        now_ts = int(time.time())
        sent_count = 0
        for path in self._outbox_paths()[: max(1, max_items)]:
            item = self._outbox_read(path)
            if not item:
                self._outbox_move_to_dead(path, None, "OUTBOX_CORRUPT")
                continue
            if _to_int(item.get("next_attempt_at"), 0) > now_ts:
                continue
            payload = item.get("payload")
            if not isinstance(payload, dict):
                self._outbox_move_to_dead(path, item, "OUTBOX_INVALID_PAYLOAD")
                continue
            if self._send_ingest(payload):
                self._register_scanned_from_payload(payload)
                try:
                    path.unlink(missing_ok=True)
                except Exception as exc:
                    logging.warning("Outbox delete after ACK failed (%s): %s", path, exc)
                sent_count += 1
                continue
            attempts = _to_int(item.get("attempts"), 0) + 1
            item["attempts"] = attempts
            item["next_attempt_at"] = now_ts + self._outbox_backoff_seconds(attempts)
            item["last_error"] = self._last_error or "INGEST_FAILED"
            try:
                self._outbox_write(path, item)
            except Exception as exc:
                logging.warning("Outbox rewrite failed (%s): %s", path, exc)
        return sent_count

    def _is_under_roots(self, path: Path) -> bool:
        test_path = _norm_path(path)
        for root in self._roots:
            if test_path.startswith(_norm_path(root) + os.sep) or test_path == _norm_path(root):
                return True
        return False

    def enqueue_path(self, path: Path) -> None:
        if not path:
            return
        normalized = _norm_path(path)
        with self._lock:
            if not self._is_under_roots(path):
                return
            self._pending_paths.add(normalized)

    def _scan_path(self, path: Path) -> Dict[str, int]:
        result = {"scanned": 0, "queued": 0, "skipped": 0}
        try:
            stat_result = path.stat()
        except Exception:
            result["skipped"] += 1
            return result
        if not path.is_file():
            result["skipped"] += 1
            return result
        if stat_result.st_size <= 0 or stat_result.st_size > self.config["max_file_bytes"]:
            result["skipped"] += 1
            return result

        if self._already_scanned(path, stat_result):
            result["skipped"] += 1
            return result

        try:
            file_hash = _sha256_file(path)
        except Exception:
            result["skipped"] += 1
            return result

        if file_hash in (self.state.get("hashes") or {}):
            self._register_scanned(path, file_hash, stat_result)
            result["skipped"] += 1
            return result

        result["scanned"] += 1
        payload = self._analyze_file(path, file_hash, stat_result)
        if not payload:
            result["skipped"] += 1
            return result

        payload["event_id"] = self._build_event_id(path, file_hash, stat_result)
        if self._send_ingest(payload):
            self._register_scanned(path, file_hash, stat_result)
            result["queued"] += 1
            return result

        self._outbox_enqueue(payload)
        self._outbox_prune_limits()
        self._drain_outbox(max_items=20)
        return result

    def run_scan_once(self) -> Dict[str, int]:
        self.refresh_roots(force=True)
        self._outbox_prune_limits()
        summary = {"scanned": 0, "queued": 0, "skipped": 0}
        for path in _iter_files(self._roots, self.config["max_file_bytes"]):
            stats = self._scan_path(path)
            summary["scanned"] += stats["scanned"]
            summary["queued"] += stats["queued"]
            summary["skipped"] += stats["skipped"]
        drained = self._drain_outbox(max_items=200)
        if drained:
            logging.info("Outbox drained after scan_once: sent=%s", drained)
        self._persist_state()
        self._write_status(force=True)
        logging.info("Scan completed: scanned=%s queued=%s skipped=%s", summary["scanned"], summary["queued"], summary["skipped"])
        return summary

    def process_watchdog_queue(self, max_items: int) -> Dict[str, int]:
        batch: List[str] = []
        with self._lock:
            while self._pending_paths and len(batch) < max_items:
                batch.append(self._pending_paths.pop())

        summary = {"scanned": 0, "queued": 0, "skipped": 0}
        for raw in batch:
            stats = self._scan_path(Path(raw))
            summary["scanned"] += stats["scanned"]
            summary["queued"] += stats["queued"]
            summary["skipped"] += stats["skipped"]

        if batch:
            self._persist_state()
        return summary

    def _persist_state(self) -> None:
        _prune_state(self.state)
        if self._state_dirty:
            _save_state(self.state)
            self._state_dirty = False
        self._write_status(force=False)

    def heartbeat(self) -> None:
        payload = {
            "agent_id": self.agent_id,
            "hostname": _hostname(),
            "branch": self.config["branch"],
            "ip_address": _primary_ip(),
            "version": "1.1.0",
            "status": "online",
            "queue_pending": len(self._pending_paths) + self._outbox_depth(),
            "last_seen_at": int(time.time()),
            "metadata": {
                "mac_address": _mac_address(),
                "watchdog_enabled": bool(self._observer is not None),
            },
        }
        try:
            response = self._send("POST", self._url("heartbeat"), json=payload)
            if response.status_code >= 300:
                logging.warning("Heartbeat failed status=%s", response.status_code)
        except Exception as exc:
            logging.warning("Heartbeat error: %s", exc)

    def _task_result(self, task_id: str, status_value: str, result: Optional[Dict[str, Any]] = None, error_text: str = "") -> None:
        payload = {
            "agent_id": self.agent_id,
            "status": status_value,
            "result": result or {},
            "error_text": error_text,
        }
        try:
            self._send("POST", self._url(f"tasks/{task_id}/result"), json=payload)
        except Exception as exc:
            logging.warning("Task result send error: %s", exc)

    def poll_tasks(self) -> None:
        try:
            response = self._send("GET", self._url("tasks/poll"), params={"agent_id": self.agent_id, "limit": 10})
            if response.status_code >= 300:
                logging.warning("Task poll failed status=%s", response.status_code)
                return
            data = response.json() if response.content else {}
        except Exception as exc:
            logging.warning("Task poll error: %s", exc)
            return

        tasks = data.get("tasks") if isinstance(data, dict) else []
        if not isinstance(tasks, list):
            return

        for task in tasks:
            task_id = str(task.get("task_id") or "").strip()
            command = str(task.get("command") or "").strip().lower()
            if not task_id:
                continue
            self._task_result(task_id, "acknowledged", result={"received": True})
            try:
                if command == "ping":
                    self._task_result(task_id, "completed", result={"pong": int(time.time())})
                elif command == "scan_now":
                    stats = self.run_scan_once()
                    self._task_result(task_id, "completed", result=stats)
                else:
                    self._task_result(task_id, "failed", error_text=f"Unsupported command: {command}")
            except Exception as exc:
                self._task_result(task_id, "failed", error_text=str(exc))

    def refresh_roots(self, force: bool = False) -> None:
        new_roots = list(_iter_target_roots())
        if force or {_norm_path(path) for path in new_roots} != {_norm_path(path) for path in self._roots}:
            self._roots = new_roots
            if self._observer is not None:
                self._restart_watchdog()

    def _stop_watchdog(self) -> None:
        if self._observer is None:
            return
        try:
            self._observer.stop()
            self._observer.join(timeout=5)
        except Exception as exc:
            logging.warning("Watchdog stop failed: %s", exc)
        self._observer = None

    def _restart_watchdog(self) -> None:
        self._stop_watchdog()
        self._start_watchdog()

    def _start_watchdog(self) -> None:
        if not self.config.get("watchdog_enabled", True):
            return
        if Observer is None:
            logging.warning("watchdog is not installed; real-time mode disabled")
            return
        if not self._roots:
            return

        observer = Observer()
        handler = _PathEventHandler(self)
        watched = 0
        for root in self._roots:
            try:
                observer.schedule(handler, str(root), recursive=True)
                watched += 1
            except Exception as exc:
                logging.warning("Watchdog schedule failed for %s: %s", root, exc)
        if watched == 0:
            return
        observer.start()
        self._observer = observer
        logging.info("Watchdog started for %s roots", watched)

    def run_forever(self) -> None:
        self.refresh_roots(force=True)
        if self.config["run_scan_on_start"]:
            self.run_scan_once()
        self._start_watchdog()

        next_poll_ts = 0.0
        next_roots_refresh_ts = 0.0

        try:
            while True:
                now = time.time()

                if now >= next_poll_ts:
                    self.heartbeat()
                    self.poll_tasks()
                    self._outbox_prune_limits()
                    drained = self._drain_outbox(max_items=200)
                    if drained:
                        logging.info("Outbox drained on heartbeat cycle: sent=%s", drained)
                    next_poll_ts = now + self.config["poll_interval"]

                if now >= next_roots_refresh_ts:
                    self.refresh_roots(force=False)
                    next_roots_refresh_ts = now + self.config["roots_refresh_sec"]

                summary = self.process_watchdog_queue(max_items=self.config["watchdog_batch_size"])
                if summary["scanned"] or summary["queued"]:
                    logging.info(
                        "Watchdog batch: scanned=%s queued=%s skipped=%s",
                        summary["scanned"],
                        summary["queued"],
                        summary["skipped"],
                    )

                if self._state_dirty and int(now) % 15 == 0:
                    self._persist_state()
                else:
                    self._write_status(force=False)

                time.sleep(1)
        finally:
            self._persist_state()
            self._write_status(force=True)
            self._stop_watchdog()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IT-Invent Scan Agent")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    parser.add_argument("--heartbeat", action="store_true", help="Send heartbeat and exit")
    parser.add_argument("--no-watchdog", action="store_true", help="Disable watchdog for current run")
    return parser.parse_args()


def main() -> int:
    loaded_env_sources = bootstrap_env_from_files()
    setup_logging()
    args = parse_args()
    config = _read_env()
    if args.no_watchdog:
        config["watchdog_enabled"] = False
    logging.info(
        "Scan agent started, server=%s outbox_max_items=%s outbox_max_age_days=%s outbox_max_total_mb=%s",
        config["server_base"],
        config["outbox_max_items"],
        config["outbox_max_age_days"],
        config["outbox_max_total_mb"],
    )
    if loaded_env_sources:
        logging.info("Loaded .env sources for scan agent: %s", "; ".join(loaded_env_sources))

    if not str(config.get("api_key") or "").strip():
        logging.error("Scan agent API key is not configured. Set SCAN_AGENT_API_KEY or allow legacy key explicitly.")
        return 1

    agent = ScanAgent(config)
    if not agent.pattern_defs:
        logging.warning("No strict patterns loaded; text/pdf-text files will be skipped until patterns file is fixed")
    if args.heartbeat:
        agent.heartbeat()
        return 0
    if args.once:
        stats = agent.run_scan_once()
        logging.info("One-shot scan done: %s", stats)
        return 0

    agent.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
