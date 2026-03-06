#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис распознавания QR и извлечения данных оборудования.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _decode_qr_with_detector(detector, image) -> Optional[str]:
    """Один проход декодирования QR с OpenCV QRCodeDetector."""
    data, _, _ = detector.detectAndDecode(image)
    if data and str(data).strip():
        return str(data).strip()

    # Для изогнутых/неидеальных поверхностей (если доступно в текущей сборке)
    try:
        curved_data, _ = detector.detectAndDecodeCurved(image)
        if curved_data and str(curved_data).strip():
            return str(curved_data).strip()
    except Exception:
        pass

    ok, decoded_info, _, _ = detector.detectAndDecodeMulti(image)
    if ok and decoded_info:
        for value in decoded_info:
            if value and str(value).strip():
                return str(value).strip()
    return None


def _decode_with_barcode_detector(cv2_module, image) -> Optional[str]:
    """Резервный декодер через OpenCV BarcodeDetector."""
    try:
        if not hasattr(cv2_module, "barcode_BarcodeDetector"):
            return None
        detector = cv2_module.barcode_BarcodeDetector()
        ok, decoded_info, _, _ = detector.detectAndDecode(image)
        if ok and decoded_info:
            for value in decoded_info:
                if value and str(value).strip():
                    return str(value).strip()
    except Exception:
        return None
    return None


def _append_contour_region_attempts(cv2_module, image, attempts: list[tuple[str, Any]]) -> None:
    """
    Добавляет попытки декодирования из потенциальных ROI с QR.
    Это повышает шанс чтения с фото, где QR маленький или на сложном фоне.
    """
    try:
        h, w = image.shape[:2]
        if h <= 0 or w <= 0:
            return

        gray = cv2_module.cvtColor(image, cv2_module.COLOR_BGR2GRAY)
        blur = cv2_module.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2_module.adaptiveThreshold(
            blur,
            255,
            cv2_module.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2_module.THRESH_BINARY_INV,
            51,
            7,
        )

        contours, _ = cv2_module.findContours(
            thresh,
            cv2_module.RETR_LIST,
            cv2_module.CHAIN_APPROX_SIMPLE,
        )
        if not contours:
            return

        min_area = max(900, (h * w) // 450)
        seen_boxes: set[tuple[int, int, int, int]] = set()
        roi_count = 0

        for cnt in sorted(contours, key=cv2_module.contourArea, reverse=True):
            area = cv2_module.contourArea(cnt)
            if area < min_area:
                continue

            x, y, bw, bh = cv2_module.boundingRect(cnt)
            if bw < 24 or bh < 24:
                continue

            ratio = bw / float(bh)
            if ratio < 0.55 or ratio > 1.8:
                continue

            box_key = (x // 12, y // 12, bw // 12, bh // 12)
            if box_key in seen_boxes:
                continue
            seen_boxes.add(box_key)

            margin = max(8, int(max(bw, bh) * 0.25))
            x0 = max(0, x - margin)
            y0 = max(0, y - margin)
            x1 = min(w, x + bw + margin)
            y1 = min(h, y + bh + margin)
            roi = image[y0:y1, x0:x1]
            if roi is None or roi.size == 0:
                continue

            roi_count += 1
            attempts.append((f"roi_{roi_count}", roi))

            rh, rw = roi.shape[:2]
            attempts.append(
                (
                    f"roi_{roi_count}_x3",
                    cv2_module.resize(roi, (rw * 3, rh * 3), interpolation=cv2_module.INTER_CUBIC),
                )
            )
            roi_gray = cv2_module.cvtColor(roi, cv2_module.COLOR_BGR2GRAY)
            attempts.append((f"roi_{roi_count}_gray", roi_gray))

            if roi_count >= 12:
                break
    except Exception:
        return


def extract_qr_payload_from_image(file_path: str) -> Optional[str]:
    """
    Пытается декодировать QR из изображения.
    Возвращает текст QR или None, если не удалось декодировать.
    """
    try:
        import cv2  # type: ignore
    except Exception:
        logger.info("OpenCV не установлен, декодирование QR из фото пропущено")
        return None

    try:
        image = cv2.imread(file_path)
        if image is None:
            logger.info("[QR] image_read_failed file=%s", file_path)
            return None

        qr_detector = cv2.QRCodeDetector()
        attempts = []

        def add_attempt(name: str, img) -> None:
            if img is not None:
                attempts.append((name, img))

        # Базовые попытки
        add_attempt("original", image)
        add_attempt("rotate_90", cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE))
        add_attempt("rotate_180", cv2.rotate(image, cv2.ROTATE_180))
        add_attempt("rotate_270", cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE))

        h, w = image.shape[:2]
        if h > 0 and w > 0:
            add_attempt("scale_x2", cv2.resize(image, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC))
            add_attempt("scale_x3", cv2.resize(image, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC))
            add_attempt("scale_x4", cv2.resize(image, (w * 4, h * 4), interpolation=cv2.INTER_CUBIC))

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        add_attempt("gray", gray)
        add_attempt("gray_equalized", cv2.equalizeHist(gray))

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        add_attempt("gray_clahe", clahe.apply(gray))

        add_attempt(
            "adaptive_threshold",
            cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                31,
                5,
            ),
        )

        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        add_attempt("otsu_threshold", otsu)

        morph_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        add_attempt("dilate", cv2.dilate(gray, morph_kernel, iterations=1))
        add_attempt("erode", cv2.erode(gray, morph_kernel, iterations=1))
        add_attempt("laplacian", cv2.Laplacian(gray, cv2.CV_8U))
        add_attempt("channel_b", image[:, :, 0])
        add_attempt("channel_g", image[:, :, 1])
        add_attempt("channel_r", image[:, :, 2])
        _append_contour_region_attempts(cv2, image, attempts)

        for attempt_name, attempt_image in attempts:
            decoded = _decode_qr_with_detector(qr_detector, attempt_image)
            if not decoded:
                decoded = _decode_with_barcode_detector(cv2, attempt_image)
            if decoded:
                logger.info("[QR] decoded attempt=%s file=%s", attempt_name, file_path)
                return decoded

        logger.info("[QR] decode_failed file=%s attempts=%s", file_path, len(attempts))
        return None
    except Exception as exc:
        logger.warning("Ошибка декодирования QR: %s", exc)
        return None


def _normalize_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text == "-":
        return ""
    return text


def parse_qr_equipment_payload(payload_text: str) -> Dict[str, str]:
    """
    Извлекает поля оборудования из текста QR.
    Поддерживаются:
    - INV_NO
    - SERIAL_NO
    - MODEL
    - PART_NO
    """
    text = str(payload_text or "").strip()
    if not text:
        return {}

    result: Dict[str, str] = {}

    # 1) Попытка JSON-формата
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            inv_no = _normalize_value(parsed.get("INV_NO") or parsed.get("inv_no"))
            serial_no = _normalize_value(parsed.get("SERIAL_NO") or parsed.get("serial_no"))
            model = _normalize_value(parsed.get("MODEL") or parsed.get("MODEL_NAME") or parsed.get("model_name"))
            part_no = _normalize_value(parsed.get("PART_NO") or parsed.get("part_no"))
            if inv_no:
                result["inv_no"] = inv_no
            if serial_no:
                result["serial_no"] = serial_no
            if model:
                result["model"] = model
            if part_no:
                result["part_no"] = part_no
    except Exception:
        pass

    # 2) Построчный формат KEY: VALUE
    for raw_line in text.splitlines():
        line = str(raw_line or "").strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key_norm = key.strip().lower().replace(" ", "").replace("-", "_")
        value_norm = _normalize_value(value)
        if not value_norm:
            continue

        if key_norm in {"inv_no", "inv", "inventory", "inventory_no", "инв", "инв_номер"}:
            result.setdefault("inv_no", value_norm)
        elif key_norm in {"serial_no", "serial", "s/n", "sn", "серийный", "серийный_номер"}:
            result.setdefault("serial_no", value_norm)
        elif key_norm in {"model", "model_name", "модель"}:
            result.setdefault("model", value_norm)
        elif key_norm in {"part_no", "part", "p/n", "pn", "парт", "парт_номер"}:
            result.setdefault("part_no", value_norm)

    # 3) Fallback: в QR только "INV_NO:123..." без переносов
    if "inv_no" not in result:
        inv_match = re.search(
            r"(?i)\b(?:INV(?:_?NO)?|ИНВ(?:ЕНТАРНЫЙ)?\.?\s*№?)\s*[:=#-]?\s*([A-Z0-9\-/\.]+)",
            text,
        )
        if inv_match:
            result["inv_no"] = _normalize_value(inv_match.group(1))
    if "serial_no" not in result:
        serial_match = re.search(
            r"(?i)\b(?:SERIAL(?:_?NO)?|S/?N|СЕРИЙНЫЙ)\s*[:=#-]?\s*([A-Z0-9\-/\.]+)",
            text,
        )
        if serial_match:
            result["serial_no"] = _normalize_value(serial_match.group(1))

    if result:
        result["raw"] = text

    return result
