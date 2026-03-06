from __future__ import annotations

import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Tuple

import yaml

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _patterns_file() -> Path:
    raw = str(os.getenv("SCAN_PATTERNS_FILE", "")).strip()
    if raw:
        return Path(raw)
    return _repo_root() / "patterns_strict.yaml"


def _read_text_with_fallback(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return ""


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


def _load_defs() -> Tuple[List[Dict[str, Any]], Dict[str, float], Dict[str, float]]:
    default_thresholds = {"dsp": 1.0, "review": 0.8}
    path = _patterns_file()
    if not path.exists():
        logger.error("patterns file not found: %s", path)
        return [], {}, default_thresholds

    text = _read_text_with_fallback(path)
    if not text.strip():
        logger.error("patterns file is empty: %s", path)
        return [], {}, default_thresholds

    try:
        payload = yaml.safe_load(text) or {}
    except Exception as exc:
        logger.error("patterns file parse failed: %s", exc)
        return [], {}, default_thresholds

    rows = payload.get("patterns") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []

    defs: List[Dict[str, Any]] = []
    weights: Dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "regex").strip().lower() != "regex":
            continue
        pattern_id = str(row.get("id") or "").strip()
        pattern_raw = str(row.get("pattern") or "")
        if not pattern_id or not pattern_raw:
            continue
        weight = float(row.get("weight") or 1.0)
        flags = _re_flags(row.get("flags"))
        try:
            regex = re.compile(pattern_raw, flags)
        except Exception as exc:
            logger.warning("pattern compile failed id=%s: %s", pattern_id, exc)
            continue
        defs.append(
            {
                "id": pattern_id,
                "name": str(row.get("name") or pattern_id),
                "weight": weight,
                "regex": regex,
            }
        )
        weights[pattern_id] = weight

    if not defs:
        logger.warning("No regex patterns loaded from %s", path)

    scoring = payload.get("scoring") if isinstance(payload, dict) else {}
    thresholds = scoring.get("thresholds") if isinstance(scoring, dict) else {}
    dsp_threshold = float((thresholds or {}).get("dsp") or 1.0)
    review_threshold = float((thresholds or {}).get("review") or 0.8)

    logger.info("Loaded strict patterns: count=%s file=%s", len(defs), path)
    return defs, weights, {"dsp": dsp_threshold, "review": review_threshold}


PATTERN_DEFS, PATTERN_WEIGHTS, THRESHOLDS = _load_defs()
ALLOWED_PATTERN_IDS = set(PATTERN_WEIGHTS.keys())


def allowed_pattern_ids() -> set[str]:
    return set(ALLOWED_PATTERN_IDS)


def _snippet(text: str, start: int, end: int, radius: int = 36) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right].replace("\n", " ").strip()


def scan_text(text: str) -> List[Dict[str, str]]:
    source = str(text or "")
    if not source.strip():
        return []
    out: List[Dict[str, str]] = []
    for item in PATTERN_DEFS:
        pattern_id = str(item.get("id") or "")
        name = str(item.get("name") or pattern_id)
        weight = float(item.get("weight") or 1.0)
        regex = item.get("regex")
        if not pattern_id or regex is None:
            continue
        for match in regex.finditer(source):
            out.append(
                {
                    "pattern": pattern_id,
                    "pattern_name": name,
                    "weight": str(weight),
                    "value": match.group(0),
                    "snippet": _snippet(source, match.start(), match.end()),
                }
            )
            if len(out) >= 200:
                return out
    return out


def classify_severity(matches: List[Dict[str, str]]) -> str:
    if not matches:
        return "none"
    total_score = 0.0
    for item in matches:
        pattern_id = str(item.get("pattern") or "")
        total_score += float(PATTERN_WEIGHTS.get(pattern_id, 0.0))

    if total_score >= float(THRESHOLDS.get("dsp") or 1.0):
        return "high"
    if total_score >= float(THRESHOLDS.get("review") or 0.8):
        return "medium"
    return "low"
