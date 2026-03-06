from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import List

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None

try:
    import pytesseract  # type: ignore
except Exception:  # pragma: no cover
    pytesseract = None

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None


def is_tesseract_available(tesseract_cmd: str) -> bool:
    if pytesseract is None:
        return False
    cmd = str(tesseract_cmd or "").strip()
    if cmd:
        if not Path(cmd).exists():
            return False
        pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        _ = pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _render_pdf_pages(pdf_bytes: bytes, max_pages: int, dpi: int) -> List[bytes]:
    if not pdf_bytes or fitz is None:
        return []
    out: List[bytes] = []
    zoom = max(1.0, float(dpi) / 72.0)
    matrix = fitz.Matrix(zoom, zoom)
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            total = min(max(1, int(max_pages)), len(doc))
            for idx in range(total):
                pix = doc.load_page(idx).get_pixmap(matrix=matrix, alpha=False)
                out.append(pix.tobytes("png"))
    except Exception:
        return []
    return out


def ocr_pdf_bytes(
    pdf_bytes: bytes,
    *,
    lang: str,
    tesseract_cmd: str,
    timeout_sec: int = 45,
    dpi: int = 300,
    max_pages: int = 3,
) -> str:
    if not pdf_bytes or pytesseract is None or Image is None:
        return ""

    cmd = str(tesseract_cmd or "").strip()
    if cmd:
        if not Path(cmd).exists():
            return ""
        pytesseract.pytesseract.tesseract_cmd = cmd

    page_images = _render_pdf_pages(pdf_bytes, max_pages=max_pages, dpi=dpi)
    if not page_images:
        return ""

    text_parts: List[str] = []
    for raw in page_images:
        try:
            with Image.open(BytesIO(raw)) as image:
                rgb_image = image.convert("RGB")
                try:
                    text = pytesseract.image_to_string(
                        rgb_image,
                        lang=str(lang or "rus"),
                        timeout=max(1, int(timeout_sec)),
                    )
                except TypeError:
                    text = pytesseract.image_to_string(
                        rgb_image,
                        lang=str(lang or "rus"),
                    )
                if text:
                    text_parts.append(str(text))
        except Exception:
            continue
    return "\n".join(text_parts).strip()
