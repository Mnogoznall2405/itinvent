from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple


def _to_int(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _to_bool(value: str, default: bool) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ScanServerConfig:
    host: str
    port: int
    api_keys: Tuple[str, ...]
    data_dir: Path
    db_path: Path
    archive_dir: Path
    retention_days: int
    task_ttl_days: int
    poll_limit: int
    task_ack_timeout_sec: int
    worker_interval_sec: int
    ocr_enabled: bool
    ocr_tesseract_cmd: str
    ocr_lang: str
    ocr_max_processes: int
    ocr_timeout_sec: int
    ocr_dpi: int
    ocr_only_if_no_text: bool

    @classmethod
    def from_env(cls) -> "ScanServerConfig":
        root = Path(__file__).resolve().parent.parent
        data_dir = Path(
            os.getenv("SCAN_SERVER_DATA_DIR", str(root / "data" / "scan_server"))
        )
        db_path = Path(
            os.getenv("SCAN_SERVER_DB_PATH", str(data_dir / "scan_server.db"))
        )
        archive_dir = Path(
            os.getenv("SCAN_SERVER_ARCHIVE_DIR", str(data_dir / "archive"))
        )
        keys: list[str] = []
        ring_raw = str(os.getenv("SCAN_SERVER_API_KEYS", "") or "").strip()
        if ring_raw:
            for row in ring_raw.split(","):
                key = str(row or "").strip()
                if key and key not in keys:
                    keys.append(key)
        legacy_key = str(os.getenv("SCAN_SERVER_API_KEY", "") or "").strip()
        if legacy_key and legacy_key not in keys:
            keys.append(legacy_key)
        if not keys:
            keys.append("itinvent_agent_secure_token_v1")

        return cls(
            host=str(os.getenv("SCAN_SERVER_HOST", "127.0.0.1")).strip() or "127.0.0.1",
            port=max(1, _to_int(os.getenv("SCAN_SERVER_PORT", "8011"), 8011)),
            api_keys=tuple(keys),
            data_dir=data_dir,
            db_path=db_path,
            archive_dir=archive_dir,
            retention_days=max(7, _to_int(os.getenv("SCAN_RETENTION_DAYS", "90"), 90)),
            task_ttl_days=max(1, _to_int(os.getenv("SCAN_TASK_TTL_DAYS", "7"), 7)),
            poll_limit=max(1, min(50, _to_int(os.getenv("SCAN_POLL_LIMIT", "10"), 10))),
            task_ack_timeout_sec=max(
                30, _to_int(os.getenv("SCAN_TASK_ACK_TIMEOUT_SEC", "300"), 300)
            ),
            worker_interval_sec=max(
                1, _to_int(os.getenv("SCAN_WORKER_INTERVAL_SEC", "3"), 3)
            ),
            ocr_enabled=_to_bool(os.getenv("SCAN_OCR_ENABLED", "1"), True),
            ocr_tesseract_cmd=str(
                os.getenv("SCAN_OCR_TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
            ).strip(),
            ocr_lang=str(os.getenv("SCAN_OCR_LANG", "rus")).strip() or "rus",
            ocr_max_processes=max(1, min(16, _to_int(os.getenv("SCAN_OCR_MAX_PROCESSES", "4"), 4))),
            ocr_timeout_sec=max(5, min(300, _to_int(os.getenv("SCAN_OCR_TIMEOUT_SEC", "45"), 45))),
            ocr_dpi=max(100, min(600, _to_int(os.getenv("SCAN_OCR_DPI", "300"), 300))),
            ocr_only_if_no_text=_to_bool(os.getenv("SCAN_OCR_ONLY_IF_NO_TEXT", "1"), True),
        )


config = ScanServerConfig.from_env()
