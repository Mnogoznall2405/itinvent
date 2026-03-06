from __future__ import annotations

import base64
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeoutError
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import ScanServerConfig
from .database import ScanStore
from .ocr import is_tesseract_available, ocr_pdf_bytes
from .patterns import allowed_pattern_ids, classify_severity, scan_text

logger = logging.getLogger(__name__)

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None


def _safe_b64decode(value: str) -> bytes:
    try:
        return base64.b64decode(str(value or ""), validate=False)
    except Exception:
        return b""


def _extract_pdf_text(pdf_bytes: bytes, max_pages: int = 3) -> str:
    if not pdf_bytes or fitz is None:
        return ""
    text_parts: List[str] = []
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            pages = min(max_pages, len(doc))
            for idx in range(pages):
                text_parts.append(doc.load_page(idx).get_text("text") or "")
    except Exception as exc:
        logger.debug("PDF text extraction failed: %s", exc)
    return "\n".join(text_parts).strip()


def _looks_gibberish(text: str) -> bool:
    content = str(text or "")
    if len(content.strip()) < 120:
        return True
    printable = sum(1 for ch in content if ch.isprintable())
    letters = sum(1 for ch in content if ch.isalpha())
    if printable == 0:
        return True
    return (letters / max(1, printable)) < 0.35


def _ocr_pdf_job(pdf_bytes: bytes, lang: str, tesseract_cmd: str, timeout_sec: int, dpi: int) -> str:
    return ocr_pdf_bytes(
        pdf_bytes,
        lang=lang,
        tesseract_cmd=tesseract_cmd,
        timeout_sec=timeout_sec,
        dpi=dpi,
        max_pages=3,
    )


class ScanWorker(threading.Thread):
    def __init__(self, *, store: ScanStore, config: ScanServerConfig, stop_event: threading.Event) -> None:
        super().__init__(daemon=True, name="scan-worker")
        self.store = store
        self.config = config
        self.stop_event = stop_event
        self._last_cleanup_ts = 0
        self._ocr_pool: Optional[ProcessPoolExecutor] = None
        self._ocr_available = False

    def run(self) -> None:
        logger.info("Scan worker started")
        if self.config.ocr_enabled:
            available = is_tesseract_available(self.config.ocr_tesseract_cmd)
            self._ocr_available = available
            logger.info(
                "OCR status: enabled=%s available=%s lang=%s max_processes=%s tesseract=%s",
                self.config.ocr_enabled,
                available,
                self.config.ocr_lang,
                self.config.ocr_max_processes,
                self.config.ocr_tesseract_cmd,
            )
        while not self.stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.exception("Scan worker tick failed: %s", exc)
            self.stop_event.wait(self.config.worker_interval_sec)
        self._shutdown_ocr_pool()
        logger.info("Scan worker stopped")

    def _tick(self) -> None:
        now_ts = int(time.time())
        if now_ts - self._last_cleanup_ts > 3600:
            self.store.cleanup_retention(retention_days=self.config.retention_days)
            self._last_cleanup_ts = now_ts

        job = self.store.claim_next_job()
        if not job:
            return
        self._process_job(job)

    def _save_artifact_if_present(self, job_id: str, payload: Dict[str, Any]) -> Optional[Path]:
        raw_b64 = str(payload.get("pdf_slice_b64") or "").strip()
        if not raw_b64:
            return None
        data = _safe_b64decode(raw_b64)
        if not data:
            return None
        now = time.gmtime()
        day_dir = self.config.archive_dir / f"{now.tm_year:04d}" / f"{now.tm_mon:02d}" / f"{now.tm_mday:02d}"
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"{job_id}.pdf"
        path.write_bytes(data)
        self.store.add_artifact(
            job_id=job_id,
            artifact_type="pdf_slice",
            storage_path=str(path),
            size_bytes=len(data),
        )
        return path

    def _coerce_matches(self, raw_items: Any) -> List[Dict[str, str]]:
        items = raw_items if isinstance(raw_items, list) else []
        allowed = allowed_pattern_ids()
        out: List[Dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            pattern_id = str(item.get("pattern") or "unknown")
            if pattern_id not in allowed:
                continue
            out.append(
                {
                    "pattern": pattern_id,
                    "pattern_name": str(item.get("pattern_name") or pattern_id),
                    "weight": str(item.get("weight") or ""),
                    "value": str(item.get("value") or ""),
                    "snippet": str(item.get("snippet") or ""),
                }
            )
            if len(out) >= 100:
                break
        return out

    def _dedupe_matches(self, matches: List[Dict[str, str]]) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        seen = set()
        for item in matches:
            key = (
                str(item.get("pattern") or ""),
                str(item.get("value") or ""),
                str(item.get("snippet") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _get_ocr_pool(self) -> Optional[ProcessPoolExecutor]:
        if not self.config.ocr_enabled or not self._ocr_available:
            return None
        if self._ocr_pool is None:
            self._ocr_pool = ProcessPoolExecutor(max_workers=self.config.ocr_max_processes)
        return self._ocr_pool

    def _shutdown_ocr_pool(self) -> None:
        if self._ocr_pool is None:
            return
        try:
            self._ocr_pool.shutdown(wait=True, cancel_futures=True)
        except Exception:
            pass
        self._ocr_pool = None

    def _extract_from_pdf_artifact(self, artifact_path: Path) -> str:
        pdf_bytes = artifact_path.read_bytes()
        text_layer = _extract_pdf_text(pdf_bytes, max_pages=3)
        if text_layer and (not self.config.ocr_only_if_no_text or not _looks_gibberish(text_layer)):
            return text_layer
        if not self.config.ocr_enabled:
            return ""

        pool = self._get_ocr_pool()
        if pool is None:
            return ""
        try:
            future = pool.submit(
                _ocr_pdf_job,
                pdf_bytes,
                self.config.ocr_lang,
                self.config.ocr_tesseract_cmd,
                self.config.ocr_timeout_sec,
                self.config.ocr_dpi,
            )
            return str(
                future.result(timeout=max(5, int(self.config.ocr_timeout_sec) + 15)) or ""
            ).strip()
        except FuturesTimeoutError:
            logger.warning("OCR timeout for artifact=%s", artifact_path)
            return ""
        except Exception as exc:
            logger.warning("OCR failed for artifact=%s: %s", artifact_path, exc)
            return ""

    def _process_job(self, job: Dict[str, Any]) -> None:
        job_id = str(job.get("id") or "")
        payload = {}
        try:
            payload = json.loads(str(job.get("payload_json") or "{}"))
        except Exception:
            payload = {}

        try:
            artifact_path = self._save_artifact_if_present(job_id, payload)
            matches = self._coerce_matches(payload.get("local_pattern_hits"))

            text_excerpt = str(payload.get("text_excerpt") or "")
            if text_excerpt:
                matches.extend(scan_text(text_excerpt))

            if not matches and artifact_path is not None:
                pdf_text = self._extract_from_pdf_artifact(artifact_path)
                if pdf_text:
                    matches.extend(scan_text(pdf_text))
            matches = self._dedupe_matches(matches)

            if matches:
                severity = classify_severity(matches)
                unique_patterns = sorted({str(row.get("pattern") or "unknown") for row in matches})
                short_reason = ", ".join(unique_patterns[:5])
                self.store.create_finding_and_incident(
                    job=job,
                    severity=severity,
                    category="policy_match",
                    matched_patterns=matches,
                    short_reason=short_reason,
                )
                self.store.finalize_job(
                    job_id=job_id,
                    status="done_with_incident",
                    summary=f"Matches found: {len(matches)}",
                )
            else:
                self.store.finalize_job(job_id=job_id, status="done_clean", summary="No matches")
        except Exception as exc:
            self.store.finalize_job(job_id=job_id, status="failed", error_text=str(exc))
            logger.exception("Job processing failed job_id=%s: %s", job_id, exc)
