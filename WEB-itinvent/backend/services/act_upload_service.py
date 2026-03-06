"""
Uploaded signed act service:
- parse uploaded PDF via OpenRouter into a draft,
- validate/edit draft,
- commit draft into DOCS + DOCS_LIST + FILES.
"""
from __future__ import annotations

import json
import logging
import os
import re
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from dotenv import dotenv_values

from backend.database import queries

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional runtime dependency
    OpenAI = None


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ROOT_ENV_PATH = PROJECT_ROOT / ".env"
ROOT_ENV = dotenv_values(str(ROOT_ENV_PATH)) if ROOT_ENV_PATH.exists() else {}

_ACT_DRAFTS: dict[str, dict[str, Any]] = {}
logger = logging.getLogger(__name__)


class DraftNotFoundError(RuntimeError):
    """Draft not found or expired."""


class DraftValidationError(RuntimeError):
    """Draft cannot be committed due to validation errors."""


class DuplicateActError(RuntimeError):
    """Duplicate act/document detected."""


def _read_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value not in (None, ""):
        return str(value).strip()
    root_value = ROOT_ENV.get(name)
    if root_value not in (None, ""):
        return str(root_value).strip()
    return default


def _cleanup_expired_drafts() -> None:
    now = datetime.now()
    expired = [
        draft_id
        for draft_id, payload in _ACT_DRAFTS.items()
        if payload.get("expires_at") and payload["expires_at"] < now
    ]
    for draft_id in expired:
        _ACT_DRAFTS.pop(draft_id, None)


def _extract_json_payload(raw_text: str) -> Optional[dict]:
    text = str(raw_text or "").strip()
    if not text:
        return None

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except Exception:
            return None
    return None


def _extract_pdf_text(file_bytes: bytes) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not file_bytes:
        return "", ["Файл пустой."]

    def _extract_with_pymupdf(raw_bytes: bytes) -> tuple[str, Optional[str]]:
        try:
            import fitz  # type: ignore
        except Exception:
            return "", "Модуль PyMuPDF недоступен для fallback-извлечения текста."

        try:
            doc = fitz.open(stream=raw_bytes, filetype="pdf")
            chunks: list[str] = []
            for page in doc:
                page_text = str(page.get_text("text") or "").strip()
                if page_text:
                    chunks.append(page_text)
            doc.close()
            return "\n\n".join(chunks).strip(), None
        except Exception as exc:
            return "", f"Ошибка fallback-извлечения текста PyMuPDF: {exc}"

    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        warnings.append("Модуль pypdf не установлен, пробую fallback через PyMuPDF.")
        text, fallback_warning = _extract_with_pymupdf(file_bytes)
        if fallback_warning:
            warnings.append(fallback_warning)
        if not text:
            logger.info("Uploaded act parse: PDF text layer not found after fallback extraction.")
        return text, warnings

    try:
        import io

        reader = PdfReader(io.BytesIO(file_bytes))
        chunks: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                chunks.append(page_text.strip())
        text = "\n\n".join(chunks).strip()
        if text:
            return text, warnings

        fallback_text, fallback_warning = _extract_with_pymupdf(file_bytes)
        if fallback_warning:
            warnings.append(fallback_warning)
        if fallback_text:
            warnings.append("Текст PDF извлечен через fallback PyMuPDF.")
            return fallback_text, warnings

        logger.info("Uploaded act parse: PDF text layer not found after pypdf and PyMuPDF extraction.")
        return text, warnings
    except Exception as exc:
        warnings.append(f"Ошибка извлечения текста PDF (pypdf): {exc}")
        fallback_text, fallback_warning = _extract_with_pymupdf(file_bytes)
        if fallback_warning:
            warnings.append(fallback_warning)
        if fallback_text:
            warnings.append("Текст PDF извлечен через fallback PyMuPDF.")
            return fallback_text, warnings
        return "", warnings


def _extract_pdf_images_for_llm(file_bytes: bytes, max_pages: int = 3) -> tuple[list[str], list[str]]:
    """
    Render first PDF pages into PNG data URLs for multimodal LLM OCR fallback.
    """
    warnings: list[str] = []
    if not file_bytes:
        return [], warnings

    try:
        import fitz  # type: ignore
    except Exception:
        warnings.append("PyMuPDF недоступен для OCR fallback по изображениям PDF.")
        return [], warnings

    images: list[str] = []
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages_limit = min(max(len(doc), 0), max(1, int(max_pages)))
        zoom = 2.0
        matrix = fitz.Matrix(zoom, zoom)
        for page_index in range(pages_limit):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png_bytes = pix.tobytes("png")
            encoded = base64.b64encode(png_bytes).decode("ascii")
            images.append(f"data:image/png;base64,{encoded}")
        doc.close()
    except Exception as exc:
        warnings.append(f"Не удалось подготовить изображения PDF для OCR fallback: {exc}")

    return images, warnings


def _normalize_date(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    text = str(value or "").strip()
    if not text:
        return None

    # Common direct ISO-like values (with time).
    iso_candidate = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_candidate)
    except Exception:
        pass

    # Extract date token from noisy text, e.g. "16.02.2026 г." / "Дата: 2026-02-16 10:22".
    token_patterns = [
        r"(\d{4}[./-]\d{1,2}[./-]\d{1,2})",
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2})",
    ]
    candidates: list[str] = [text]
    for pattern in token_patterns:
        match = re.search(pattern, text)
        if match:
            token = str(match.group(1) or "").strip()
            if token and token not in candidates:
                candidates.append(token)

    formats = [
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%y",
        "%d-%m-%y",
        "%d/%m/%y",
    ]
    for candidate in candidates:
        cleaned = candidate.strip().replace("Рі.", "").replace("Рі", "").strip()
        for fmt in formats:
            try:
                parsed = datetime.strptime(cleaned, fmt)
                # Normalize 2-digit year into 2000+ window if parser returned 19xx unexpectedly.
                if parsed.year < 2000 and "%y" in fmt:
                    parsed = parsed.replace(year=parsed.year + 100)
                return parsed
            except Exception:
                continue

    return None


def _extract_doc_date_from_text(pdf_text: str) -> Optional[datetime]:
    """
    Best-effort extraction of document date from PDF text.
    Priority:
      1) contextual patterns (акт ... от ..., дата документа ...),
      2) first generic date token.
    """
    text = str(pdf_text or "").strip()
    if not text:
        return None

    contextual_patterns = [
        r"(?is)\bакт\b.{0,120}?\bот\b\s*([0-3]?\d[./-][01]?\d[./-](?:\d{2}|\d{4}))",
        r"(?is)\bдата(?:\s+документа|\s+составления)?\b\s*[:№]?\s*([0-3]?\d[./-][01]?\d[./-](?:\d{2}|\d{4}))",
    ]
    for pattern in contextual_patterns:
        for raw in re.findall(pattern, text):
            parsed = _normalize_date(raw)
            if parsed:
                return parsed

    generic_matches = re.findall(r"\b([0-3]?\d[./-][01]?\d[./-](?:\d{2}|\d{4}))\b", text)
    for raw in generic_matches:
        parsed = _normalize_date(raw)
        if parsed:
            return parsed

    return None


def _extract_doc_date_from_payload(parsed_payload: dict) -> Optional[datetime]:
    """
    Read document date from various LLM keys.
    """
    if not isinstance(parsed_payload, dict):
        return None

    for key in ("doc_date", "document_date", "act_date", "date"):
        parsed = _normalize_date(parsed_payload.get(key))
        if parsed:
            return parsed

    return None


def _normalize_item_ids_legacy(raw_ids: Any) -> list[int]:
    """Legacy fallback when model returns ITEMS.ID instead of INV_NO."""
    source = raw_ids if isinstance(raw_ids, list) else [raw_ids]
    result: list[int] = []
    for raw in source:
        if raw in (None, "", "null"):
            continue
        try:
            value = int(str(raw).strip())
        except Exception:
            continue
        if value > 0 and value not in result:
            result.append(value)
    return result


def _normalize_inv_no_token(raw: Any) -> Optional[str]:
    text = str(raw or "").strip()
    if not text:
        return None
    text = re.sub(r"\s+", "", text)
    text = text.replace("№", "")
    text = text.strip(".,;:|")
    if not text:
        return None
    if re.fullmatch(r"\d+[.,]0+", text):
        text = re.split(r"[.,]", text, maxsplit=1)[0]
    if re.fullmatch(r"\d+", text):
        text = str(int(text))
    return text


def _normalize_inv_nos(raw_values: Any) -> list[str]:
    source = raw_values if isinstance(raw_values, list) else [raw_values]
    result: list[str] = []
    for raw in source:
        if raw in (None, "", "null"):
            continue
        token = _normalize_inv_no_token(raw)
        if token and token not in result:
            result.append(token)
    return result


def _normalized_inv_key(raw: Any) -> Optional[str]:
    token = _normalize_inv_no_token(raw)
    return token.lower() if token else None


def _parse_inv_nos_from_text(pdf_text: str) -> list[str]:
    result: list[str] = []
    if not pdf_text:
        return result

    patterns = [
        r"(?iu)\binv(?:_?no|\.?\s*no|#)?\s*[:=#-]?\s*([\w\-/\.]{2,32})",
        r"(?iu)\bинв(?:ентарный)?\.?\s*№?\s*[:=#-]?\s*([\w\-/\.]{2,32})",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, pdf_text, flags=re.IGNORECASE):
            token = _normalize_inv_no_token(match)
            if token and token not in result:
                result.append(token)
    return result


def _derive_title_from_filename(file_name: str) -> str:
    base = os.path.splitext(os.path.basename(str(file_name or "")))[0]
    base = re.sub(r"\s+", " ", base).strip()
    return base or "Перемещение оборудования"


def _to_short_fio(value: str) -> str:
    """Convert full name to 'Фамилия И.О.'."""
    text = str(value or "").strip()
    if not text:
        return ""

    parts = re.findall(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", text, flags=re.UNICODE)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]

    surname = parts[0]
    initials = "".join(f"{part[0].upper()}." for part in parts[1:3] if part)
    if initials:
        return f"{surname} {initials}"
    return surname


def _build_transfer_title(from_employee: str, to_employee: str, fallback: str) -> str:
    """
    Build transfer title in required format:
    'Акт, Фамилия И.О. передал Фамилия И.О.'
    """
    from_short = _to_short_fio(from_employee)
    to_short = _to_short_fio(to_employee)
    if from_short and to_short:
        return f"Акт, {from_short} передал {to_short}"
    return str(fallback or "").strip() or "Акт перемещения оборудования"


def _resolve_cyrillic_ttf_path() -> Optional[str]:
    """
    Return path to a TTF font with Cyrillic glyphs for PDF stamps.
    Priority: env override -> common Windows fonts.
    """
    env_candidates = [
        _read_env("ACT_ANNULLED_FONT_PATH"),
        _read_env("PDF_CYRILLIC_FONT_PATH"),
    ]
    for raw in env_candidates:
        path = str(raw or "").strip()
        if path and Path(path).exists():
            return path

    win_dir = os.environ.get("WINDIR") or r"C:\Windows"
    fonts_dir = Path(win_dir) / "Fonts"
    font_candidates = [
        fonts_dir / "arial.ttf",
        fonts_dir / "arialbd.ttf",
        fonts_dir / "calibri.ttf",
        fonts_dir / "times.ttf",
        fonts_dir / "tahoma.ttf",
        fonts_dir / "verdana.ttf",
    ]
    for path in font_candidates:
        if path.exists():
            return str(path)
    return None


def _stamp_pdf_doc_no(file_bytes: bytes, doc_no: int) -> bytes:
    """
    Put visible document number in the top-left corner of first PDF page.
    Returns original bytes on any non-critical failure.
    """
    if not file_bytes or not bytes(file_bytes).startswith(b"%PDF-"):
        return bytes(file_bytes or b"")

    try:
        import io
        from pypdf import PdfReader, PdfWriter  # type: ignore
        from reportlab.pdfbase import pdfmetrics  # type: ignore
        from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
    except Exception as exc:
        logger.warning("DOC_NO stamp skipped: PDF libs unavailable (%s)", exc)
        return bytes(file_bytes)

    try:
        source = io.BytesIO(bytes(file_bytes))
        reader = PdfReader(source)
        if not reader.pages:
            return bytes(file_bytes)

        writer = PdfWriter()
        font_name = "Helvetica-Bold"
        font_size = 10
        stamp_text = f"\u2116{int(doc_no)}"

        cyr_font_path = _resolve_cyrillic_ttf_path()
        if cyr_font_path:
            try:
                cyr_font_name = "StampCyrFontDocNo"
                if cyr_font_name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(cyr_font_name, cyr_font_path))
                font_name = cyr_font_name
            except Exception as exc:
                logger.warning("DOC_NO stamp: failed to load Cyrillic font (%s)", exc)
        else:
            logger.warning("DOC_NO stamp: Cyrillic font not found")

        for index, page in enumerate(reader.pages):
            if index == 0:
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
                overlay_stream = io.BytesIO()
                overlay = canvas.Canvas(overlay_stream, pagesize=(width, height))
                overlay.setFont(font_name, font_size)
                text_width = overlay.stringWidth(stamp_text, font_name, font_size)
                margin = 18
                x = margin
                y = max(margin, height - margin - font_size)
                overlay.drawString(x, y, stamp_text)
                overlay.save()
                overlay_stream.seek(0)

                overlay_reader = PdfReader(overlay_stream)
                page.merge_page(overlay_reader.pages[0])

            writer.add_page(page)

        out = io.BytesIO()
        writer.write(out)
        stamped = out.getvalue()
        return stamped or bytes(file_bytes)
    except Exception as exc:
        logger.warning("DOC_NO stamp failed for doc_no=%s: %s", doc_no, exc)
        return bytes(file_bytes)


def _stamp_pdf_annulled(file_bytes: bytes, doc_no: int) -> bytes:
    """
    Put visible annulled stamp on first PDF page.
    Returns original bytes on any non-critical failure.
    """
    if not file_bytes or not bytes(file_bytes).startswith(b"%PDF-"):
        return bytes(file_bytes or b"")

    try:
        import io
        from pypdf import PdfReader, PdfWriter  # type: ignore
        from reportlab.pdfbase import pdfmetrics  # type: ignore
        from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
    except Exception as exc:
        logger.warning("ANNULLED stamp skipped: PDF libs unavailable (%s)", exc)
        return bytes(file_bytes)

    try:
        source = io.BytesIO(bytes(file_bytes))
        reader = PdfReader(source)
        if not reader.pages:
            return bytes(file_bytes)

        writer = PdfWriter()
        font_name = "Helvetica-Bold"
        font_size = 36
        stamp_text = f"\u0410\u041d\u041d\u0423\u041b\u0418\u0420\u041e\u0412\u0410\u041d\u041e DOC_NO: {int(doc_no)}"
        cyr_font_path = _resolve_cyrillic_ttf_path()
        if cyr_font_path:
            try:
                cyr_font_name = "StampCyrFont"
                if cyr_font_name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(cyr_font_name, cyr_font_path))
                font_name = cyr_font_name
            except Exception as exc:
                logger.warning("ANNULLED stamp: failed to load Cyrillic font (%s)", exc)
        else:
            logger.warning("ANNULLED stamp: Cyrillic font not found")

        for index, page in enumerate(reader.pages):
            if index == 0:
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
                overlay_stream = io.BytesIO()
                overlay = canvas.Canvas(overlay_stream, pagesize=(width, height))
                overlay.setFillColorRGB(0.75, 0.0, 0.0)
                overlay.setFont(font_name, font_size)
                overlay.saveState()
                overlay.translate(width / 2.0, height / 2.0)
                overlay.rotate(27)
                text_width = overlay.stringWidth(stamp_text, font_name, font_size)
                overlay.drawString(-text_width / 2.0, 0, stamp_text)
                overlay.restoreState()
                overlay.save()
                overlay_stream.seek(0)

                overlay_reader = PdfReader(overlay_stream)
                page.merge_page(overlay_reader.pages[0])

            writer.add_page(page)

        out = io.BytesIO()
        writer.write(out)
        stamped = out.getvalue()
        return stamped or bytes(file_bytes)
    except Exception as exc:
        logger.warning("ANNULLED stamp failed for doc_no=%s: %s", doc_no, exc)
        return bytes(file_bytes)


def _normalize_openrouter_base_url(raw_value: Any, default_base_url: str) -> str:
    """
    Normalize OpenRouter base URL to API root:
    https://openrouter.ai/api/v1
    """
    raw = str(raw_value or "").strip()
    if not raw:
        return default_base_url

    value = raw.rstrip("/")
    lower = value.lower()

    if lower.endswith("/chat/completions"):
        value = value[: -len("/chat/completions")]
        lower = value.lower()
    elif lower.endswith("/completions"):
        value = value[: -len("/completions")]
        lower = value.lower()

    if lower.endswith("/api"):
        value = f"{value}/v1"
        lower = value.lower()

    if lower.endswith("/v1") and not lower.endswith("/api/v1"):
        value = re.sub(r"/v1$", "", value, flags=re.IGNORECASE)
        value = f"{value}/api/v1"
        lower = value.lower()

    if not lower.endswith("/api/v1"):
        value = f"{value}/api/v1"

    return value


def _call_openrouter_act_parser(
    *,
    file_name: str,
    pdf_text: str,
    file_bytes: Optional[bytes] = None,
) -> tuple[Optional[dict], list[str]]:
    warnings: list[str] = []

    model_candidates: list[tuple[str, str]] = []
    for source, value in (
        ("root/.env:ACT_PARSE_MODEL", ROOT_ENV.get("ACT_PARSE_MODEL")),
        ("os.getenv:ACT_PARSE_MODEL", os.getenv("ACT_PARSE_MODEL")),
        ("root/.env:OCR_MODEL", ROOT_ENV.get("OCR_MODEL")),
        ("os.getenv:OCR_MODEL", os.getenv("OCR_MODEL")),
    ):
        model_name = str(value or "").strip()
        if not model_name:
            continue
        if model_name not in [m for _, m in model_candidates]:
            model_candidates.append((source, model_name))
    default_base_url = "https://openrouter.ai/api/v1"

    key_candidates: list[tuple[str, str]] = []
    for source, value in (
        ("root/.env:OPENROUTER_API_KEY", ROOT_ENV.get("OPENROUTER_API_KEY")),
        ("os.getenv:OPENROUTER_API_KEY", os.getenv("OPENROUTER_API_KEY")),
        # Fallback for environments where OpenRouter token is stored in OPENAI_API_KEY.
        ("root/.env:OPENAI_API_KEY", ROOT_ENV.get("OPENAI_API_KEY")),
        ("os.getenv:OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")),
    ):
        token = str(value or "").strip()
        if not token:
            continue
        if token not in [v for _, v in key_candidates]:
            key_candidates.append((source, token))

    base_candidates: list[tuple[str, str]] = []
    for source, value in (
        ("root/.env", ROOT_ENV.get("OPENROUTER_BASE_URL")),
        ("os.getenv", os.getenv("OPENROUTER_BASE_URL")),
        ("default", default_base_url),
    ):
        base = _normalize_openrouter_base_url(value, default_base_url)
        if base not in [v for _, v in base_candidates]:
            base_candidates.append((source, base))

    if not key_candidates:
        warnings.append("OPENROUTER_API_KEY (или OPENAI_API_KEY) не задан, распознавание через модель пропущено.")
        return None, warnings
    if not model_candidates:
        warnings.append("ACT_PARSE_MODEL/OCR_MODEL не заданы, распознавание через модель пропущено.")
        return None, warnings
    if OpenAI is None:
        warnings.append("Пакет openai недоступен, распознавание через модель пропущено.")
        return None, warnings

    text_for_model = pdf_text[:50000]
    image_urls: list[str] = []
    if not text_for_model.strip() and file_bytes:
        rendered_images, image_warnings = _extract_pdf_images_for_llm(file_bytes=file_bytes, max_pages=3)
        warnings.extend(image_warnings)
        image_urls = rendered_images

    if not text_for_model.strip() and not image_urls:
        warnings.append(
            "Текст PDF пустой и изображения для OCR fallback недоступны. "
            "Для сканов включите OCR или введите данные вручную."
        )
        text_for_model = "[PDF_TEXT_EMPTY]"

    user_prompt_header = (
        "Return JSON object only (without markdown) in format:\n"
        "{\n"
        '  "document_title": "string",\n'
        '  "from_employee": "string",\n'
        '  "to_employee": "string",\n'
        '  "doc_date": "YYYY-MM-DD or empty",\n'
        '  "equipment_inv_nos": ["100887", "100888"]\n'
        "}\n"
        "Rules:\n"
        "- equipment_inv_nos must contain inventory numbers (INV_NO), not internal IDs.\n"
        "- doc_date must be extracted from the act date in the document text and normalized to YYYY-MM-DD.\n"
        "- if data is not found, return empty string or empty array.\n\n"
        f"File name: {file_name}\n\n"
    )

    def _build_user_content(use_images: bool) -> Any:
        if use_images and image_urls:
            content: Any = [{"type": "text", "text": user_prompt_header + "Document is provided as images below."}]
            for url in image_urls:
                content.append({"type": "image_url", "image_url": {"url": url}})
            return content
        return user_prompt_header + f"Document text:\n{text_for_model}"

    completion = None
    last_exc: Optional[Exception] = None
    logger.info(
        "Uploaded act parse: model candidates=%s",
        [f"{src}:{name}" for src, name in model_candidates],
    )

    for model_source, model in model_candidates:
        attempt_modes = [True, False] if image_urls else [False]
        for use_images in attempt_modes:
            if use_images and not image_urls:
                continue
            if (not use_images) and (not text_for_model.strip()):
                continue

            image_input_unsupported = False
            for key_source, api_key in key_candidates:
                for base_source, base_url in base_candidates:
                    client = OpenAI(
                        api_key=api_key,
                        base_url=base_url,
                    )
                    try:
                        logger.info(
                            "Uploaded act parse: sending request to OpenRouter (file=%s, model=%s, model_source=%s, text_len=%s, images=%s, key_source=%s, base_source=%s)",
                            file_name,
                            model,
                            model_source,
                            len(text_for_model),
                            len(image_urls) if use_images else 0,
                            key_source,
                            base_source,
                        )
                        completion = client.chat.completions.create(
                            model=model,
                            temperature=0.1,
                            response_format={"type": "json_object"},
                            messages=[
                                {
                                    "role": "system",
                                    "content": (
                                        "Extract structured data from signed transfer act and return strict JSON."
                                    ),
                                },
                                {
                                    "role": "user",
                                    "content": _build_user_content(use_images),
                                },
                            ],
                            max_tokens=900,
                        )
                        logger.info(
                            "Uploaded act parse: OpenRouter response received (file=%s, model=%s, model_source=%s, use_images=%s)",
                            file_name,
                            model,
                            model_source,
                            use_images,
                        )
                        last_exc = None
                        break
                    except Exception as exc:
                        last_exc = exc
                        message = str(exc or "")
                        if use_images and ("support image input" in message.lower()):
                            image_input_unsupported = True
                        logger.warning(
                            "Uploaded act parse: OpenRouter call failed (file=%s, model=%s, model_source=%s, use_images=%s, key_source=%s, base_source=%s): %s",
                            file_name,
                            model,
                            model_source,
                            use_images,
                            key_source,
                            base_source,
                            exc,
                        )
                        if image_input_unsupported:
                            break
                if completion is not None or image_input_unsupported:
                    break

            if completion is not None:
                break

            if image_input_unsupported:
                warnings.append(
                    f"Модель {model} не поддерживает image input, пробую следующий режим/модель."
                )
        if completion is not None:
            break

    if completion is None:
        warnings.append(f"Ошибка OpenRouter: {last_exc}" if last_exc else "Ошибка OpenRouter: пустой ответ.")
        return None, warnings

    content = ""
    if completion and getattr(completion, "choices", None):
        content = str(completion.choices[0].message.content or "").strip()

    payload = _extract_json_payload(content)
    if payload is None:
        warnings.append("OpenRouter вернул невалидный JSON.")
        logger.warning("Uploaded act parse: OpenRouter returned invalid JSON (file=%s)", file_name)
        return None, warnings
    logger.info("Uploaded act parse: OpenRouter JSON parsed successfully (file=%s)", file_name)
    return payload, warnings


def _build_resolved_items(rows: list[dict]) -> list[dict]:
    return [
        {
            "item_id": int(row.get("item_id") or row.get("ITEM_ID")),
            "inv_no": str(row.get("inv_no") or row.get("INV_NO") or "").strip() or None,
            "serial_no": str(row.get("serial_no") or row.get("SERIAL_NO") or "").strip() or None,
            "model_name": str(row.get("model_name") or row.get("MODEL_NAME") or "").strip() or None,
            "employee_name": str(row.get("employee_name") or row.get("EMPLOYEE_NAME") or "").strip() or None,
            "branch_name": str(row.get("branch_name") or row.get("BRANCH_NAME") or "").strip() or None,
            "location_name": str(row.get("location_name") or row.get("LOCATION_NAME") or "").strip() or None,
        }
        for row in rows
        if (row.get("item_id") is not None or row.get("ITEM_ID") is not None)
    ]


def _resolve_rows_for_inv_nos(inv_nos: list[str], db_id: Optional[str]) -> tuple[list[dict], list[str], dict[str, list[int]]]:
    rows = queries.get_equipment_items_by_inv_nos(inv_nos, db_id)

    by_key: dict[str, list[dict]] = {}
    for row in rows:
        key = _normalized_inv_key(row.get("inv_no") or row.get("INV_NO"))
        if not key:
            continue
        by_key.setdefault(key, []).append(row)

    ordered_rows: list[dict] = []
    missing: list[str] = []
    duplicate_matches: dict[str, list[int]] = {}
    seen_item_ids: set[int] = set()

    for raw_inv in inv_nos:
        key = _normalized_inv_key(raw_inv)
        if not key:
            continue
        matches = by_key.get(key) or []
        if not matches:
            missing.append(raw_inv)
            continue
        if len(matches) > 1:
            duplicate_matches[raw_inv] = [
                int(row.get("item_id") or row.get("ITEM_ID"))
                for row in matches
                if row.get("item_id") is not None or row.get("ITEM_ID") is not None
            ]
        row = matches[0]
        item_id = int(row.get("item_id") or row.get("ITEM_ID"))
        if item_id in seen_item_ids:
            continue
        seen_item_ids.add(item_id)
        ordered_rows.append(row)

    return ordered_rows, missing, duplicate_matches


def _build_draft_response_payload(draft: dict) -> dict:
    return {
        "draft_id": draft["draft_id"],
        "file_name": draft["file_name"],
        "document_title": draft.get("document_title") or "",
        "from_employee": draft.get("from_employee") or "",
        "to_employee": draft.get("to_employee") or "",
        "doc_date": draft.get("doc_date"),
        "equipment_inv_nos": list(draft.get("equipment_inv_nos") or []),
        "resolved_items": list(draft.get("resolved_items") or []),
        "warnings": list(draft.get("warnings") or []),
    }


def create_uploaded_act_draft(
    *,
    file_bytes: bytes,
    file_name: str,
    db_id: Optional[str],
    created_by: str,
    skip_llm: bool = False,
) -> dict:
    _cleanup_expired_drafts()
    warnings: list[str] = []

    pdf_text, text_warnings = _extract_pdf_text(file_bytes)
    warnings.extend(text_warnings)

    if skip_llm:
        parsed_payload = None
        warnings.append(
            "Ручной режим: автоматическое распознавание через API пропущено."
        )
    else:
        parsed_payload, llm_warnings = _call_openrouter_act_parser(
            file_name=file_name,
            pdf_text=pdf_text,
            file_bytes=file_bytes,
        )
        warnings.extend(llm_warnings)

    title = _derive_title_from_filename(file_name)
    from_employee = ""
    to_employee = ""
    parsed_doc_date: Optional[datetime] = None
    inv_nos: list[str] = []

    if isinstance(parsed_payload, dict):
        title = str(parsed_payload.get("document_title") or "").strip() or title
        from_employee = str(parsed_payload.get("from_employee") or "").strip()
        to_employee = str(parsed_payload.get("to_employee") or "").strip()
        parsed_doc_date = _extract_doc_date_from_payload(parsed_payload)
        inv_nos = _normalize_inv_nos(parsed_payload.get("equipment_inv_nos"))

        if not inv_nos:
            legacy_item_ids = _normalize_item_ids_legacy(parsed_payload.get("equipment_item_ids"))
            if legacy_item_ids:
                legacy_rows = queries.get_equipment_items_by_ids(legacy_item_ids, db_id)
                inv_nos = _normalize_inv_nos(
                    [row.get("inv_no") or row.get("INV_NO") for row in legacy_rows]
                )
                if inv_nos:
                    warnings.append("Модель вернула ITEMS.ID, выполнена конвертация в INV_NO.")

    if parsed_doc_date is None:
        parsed_doc_date = _extract_doc_date_from_text(pdf_text)
        if parsed_doc_date:
            warnings.append("Дата акта определена из текста PDF (fallback).")
        else:
            warnings.append("Не удалось автоматически определить дату акта.")

    title = _build_transfer_title(from_employee, to_employee, title)

    if not inv_nos:
        fallback_inv_nos = _parse_inv_nos_from_text(pdf_text)
        if fallback_inv_nos:
            inv_nos = fallback_inv_nos
            warnings.append("INV_NO извлечены по fallback-правилам из текста PDF.")
        else:
            warnings.append("Не удалось автоматически определить инвентарные номера. Укажите их вручную.")

    ordered_rows, missing_inv_nos, duplicate_matches = _resolve_rows_for_inv_nos(inv_nos, db_id)
    if missing_inv_nos:
        warnings.append(f"В текущей БД не найдены INV_NO: {', '.join(missing_inv_nos)}")
    if duplicate_matches:
        details = "; ".join(
            f"{inv_no} -> {', '.join(str(item_id) for item_id in item_ids)}"
            for inv_no, item_ids in duplicate_matches.items()
        )
        warnings.append(f"Найдено несколько ITEMS.ID для одного INV_NO: {details}")

    resolved_items = _build_resolved_items(ordered_rows)

    draft_id = str(uuid4())
    draft_payload = {
        "draft_id": draft_id,
        "db_id": str(db_id or "").strip() or None,
        "created_by": str(created_by or "IT-WEB"),
        "created_at": datetime.now(),
        "expires_at": datetime.now()
        + timedelta(minutes=int(_read_env("ACT_UPLOAD_DRAFT_TTL_MINUTES", "30") or "30")),
        "file_name": str(file_name or "").strip(),
        "file_bytes": bytes(file_bytes),
        "document_title": title,
        "from_employee": from_employee,
        "to_employee": to_employee,
        "doc_date": parsed_doc_date.strftime("%Y-%m-%d") if parsed_doc_date else None,
        "equipment_inv_nos": inv_nos,
        "resolved_items": resolved_items,
        "warnings": warnings,
    }
    _ACT_DRAFTS[draft_id] = draft_payload
    return _build_draft_response_payload(draft_payload)


def get_uploaded_act_draft(
    draft_id: str,
    db_id: Optional[str],
) -> dict:
    _cleanup_expired_drafts()
    key = str(draft_id or "").strip()
    draft = _ACT_DRAFTS.get(key)
    if not draft:
        raise DraftNotFoundError("Черновик не найден или срок его действия истек.")

    draft_db = str(draft.get("db_id") or "").strip() or None
    current_db = str(db_id or "").strip() or None
    if draft_db and current_db and draft_db != current_db:
        raise DraftValidationError("Черновик создан для другой базы данных.")

    return _build_draft_response_payload(draft)


def commit_uploaded_act_draft(
    *,
    draft_id: str,
    payload: dict,
    db_id: Optional[str],
    committed_by: str,
) -> dict:
    _cleanup_expired_drafts()
    key = str(draft_id or "").strip()
    draft = _ACT_DRAFTS.get(key)
    if not draft:
        raise DraftNotFoundError("Черновик не найден или срок его действия истек.")

    draft_db = str(draft.get("db_id") or "").strip() or None
    current_db = str(db_id or "").strip() or None
    if draft_db and current_db and draft_db != current_db:
        raise DraftValidationError("Черновик создан для другой базы данных.")

    final_title = str(payload.get("document_title") or draft.get("document_title") or "").strip()
    if not final_title:
        final_title = _derive_title_from_filename(str(draft.get("file_name") or ""))

    final_from_employee = str(payload.get("from_employee") or draft.get("from_employee") or "").strip()
    final_to_employee = str(payload.get("to_employee") or draft.get("to_employee") or "").strip()
    final_title = _build_transfer_title(final_from_employee, final_to_employee, final_title)

    raw_inv_nos = payload.get("equipment_inv_nos")
    if raw_inv_nos is None:
        raw_inv_nos = draft.get("equipment_inv_nos") or []
    final_inv_nos = _normalize_inv_nos(raw_inv_nos)
    if not final_inv_nos:
        raise DraftValidationError("Список инвентарных номеров пуст. Укажите оборудование для привязки.")

    ordered_rows, missing_inv_nos, duplicate_matches = _resolve_rows_for_inv_nos(final_inv_nos, db_id)
    if missing_inv_nos:
        raise DraftValidationError(
            f"Не найдены INV_NO в текущей БД: {', '.join(missing_inv_nos)}"
        )
    if duplicate_matches:
        details = "; ".join(
            f"{inv_no} -> {', '.join(str(item_id) for item_id in item_ids)}"
            for inv_no, item_ids in duplicate_matches.items()
        )
        raise DraftValidationError(
            f"Для некоторых INV_NO найдено несколько ITEMS.ID. Уточните вручную: {details}"
        )

    final_item_ids: list[int] = []
    linked_inv_nos: list[str] = []
    for row in ordered_rows:
        item_id = int(row.get("item_id") or row.get("ITEM_ID"))
        inv_no = _normalize_inv_no_token(row.get("inv_no") or row.get("INV_NO"))
        if item_id not in final_item_ids:
            final_item_ids.append(item_id)
        if inv_no and inv_no not in linked_inv_nos:
            linked_inv_nos.append(inv_no)

    original_file_bytes = bytes(draft.get("file_bytes") or b"")

    raw_doc_date = payload.get("doc_date")
    if raw_doc_date in (None, ""):
        raw_doc_date = draft.get("doc_date")
    parsed_doc_date = _normalize_date(raw_doc_date)
    if parsed_doc_date is None and original_file_bytes:
        pdf_text_for_date, _ = _extract_pdf_text(original_file_bytes)
        parsed_doc_date = _extract_doc_date_from_text(pdf_text_for_date)
        if parsed_doc_date:
            logger.info(
                "Uploaded act commit: doc_date fallback from PDF text (draft_id=%s, date=%s)",
                key,
                parsed_doc_date.strftime("%Y-%m-%d"),
            )

    result = queries.create_uploaded_transfer_act(
        document_title=final_title,
        from_employee=final_from_employee,
        to_employee=final_to_employee,
        doc_date=parsed_doc_date,
        equipment_item_ids=final_item_ids,
        file_name=str(draft.get("file_name") or ""),
        file_bytes=original_file_bytes,
        created_by=str(committed_by or "IT-WEB"),
        db_id=db_id,
    )
    # Post-process uploaded PDF: add visible DOC_NO mark on first page.
    try:
        doc_no_value = int(result.get("doc_no"))
        file_no_value = int(result.get("file_no"))
        stamped_bytes = _stamp_pdf_doc_no(original_file_bytes, doc_no_value)
        if stamped_bytes and stamped_bytes != original_file_bytes:
            queries.update_uploaded_transfer_act_file(
                file_no=file_no_value,
                file_bytes=stamped_bytes,
                db_id=db_id,
            )
    except Exception as exc:
        logger.warning("DOC_NO stamp update skipped: %s", exc)

    # Post-process old acts: put ANNULLED stamp when act was auto-annulled.
    try:
        raw_annulled = result.get("annulled_doc_nos") or []
        annulled_doc_nos = [int(x) for x in raw_annulled if x not in (None, "")]
    except Exception:
        annulled_doc_nos = []

    for old_doc_no in annulled_doc_nos:
        try:
            payload_old = queries.get_equipment_act_file(doc_no=old_doc_no, db_id=db_id)
            if not payload_old:
                logger.warning("ANNULLED stamp skipped: file not found for doc_no=%s", old_doc_no)
                continue
            if str(payload_old.get("storage") or "").lower() != "blob":
                logger.warning(
                    "ANNULLED stamp skipped: non-blob storage for doc_no=%s (storage=%s)",
                    old_doc_no,
                    payload_old.get("storage"),
                )
                continue
            old_bytes = bytes(payload_old.get("file_bytes") or b"")
            if not old_bytes:
                logger.warning("ANNULLED stamp skipped: empty bytes for doc_no=%s", old_doc_no)
                continue

            stamped_old = _stamp_pdf_annulled(old_bytes, old_doc_no)
            if stamped_old and stamped_old != old_bytes:
                updated_file_no = queries.update_uploaded_transfer_act_file_by_doc_no(
                    doc_no=old_doc_no,
                    file_bytes=stamped_old,
                    db_id=db_id,
                )
                if updated_file_no is None:
                    logger.warning("ANNULLED stamp skipped: FILE_NO not found for doc_no=%s", old_doc_no)
        except Exception as exc:
            logger.warning("ANNULLED stamp update failed for doc_no=%s: %s", old_doc_no, exc)

    result["linked_inv_nos"] = linked_inv_nos

    _ACT_DRAFTS.pop(key, None)
    return result

