#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Единый сервис определения идентификаторов оборудования из изображения или текста.
Используется в сценариях поиска и перемещения для одинакового поведения.
"""

from __future__ import annotations

from typing import Dict, Optional

from bot.services.ocr_service import extract_serial_from_image
from bot.services.qr_service import extract_qr_payload_from_image, parse_qr_equipment_payload


def _normalize(value: object) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def detect_identifiers_from_text(text_input: str) -> Dict[str, Optional[str]]:
    """
    Определяет идентификаторы из текстового ввода.
    Возвращает:
      detector: qr | manual | none
      inv_no: str | None
      serial_no: str | None
      qr_payload_text: str | None
    """
    text = str(text_input or "").strip()
    if not text:
        return {
            "detector": "none",
            "inv_no": None,
            "serial_no": None,
            "qr_payload_text": None,
        }

    qr_data = parse_qr_equipment_payload(text)
    inv_no = _normalize(qr_data.get("inv_no"))
    serial_no = _normalize(qr_data.get("serial_no"))

    if inv_no or serial_no:
        return {
            "detector": "qr",
            "inv_no": inv_no,
            "serial_no": serial_no,
            "qr_payload_text": text,
        }

    return {
        "detector": "manual",
        "inv_no": None,
        "serial_no": text,
        "qr_payload_text": None,
    }


async def detect_identifiers_from_image(file_path: str) -> Dict[str, Optional[str]]:
    """
    Определяет идентификаторы из изображения.
    Порядок: QR -> OCR fallback.
    Возвращает:
      detector: qr | ocr | none
      inv_no: str | None
      serial_no: str | None
      qr_payload_text: str | None
    """
    qr_payload_text = extract_qr_payload_from_image(file_path)
    if qr_payload_text:
        qr_data = parse_qr_equipment_payload(qr_payload_text)
        inv_no = _normalize(qr_data.get("inv_no"))
        serial_no = _normalize(qr_data.get("serial_no"))
        if inv_no or serial_no:
            return {
                "detector": "qr",
                "inv_no": inv_no,
                "serial_no": serial_no,
                "qr_payload_text": qr_payload_text,
            }

    serial_from_ocr = _normalize(await extract_serial_from_image(file_path))
    if serial_from_ocr:
        return {
            "detector": "ocr",
            "inv_no": None,
            "serial_no": serial_from_ocr,
            "qr_payload_text": qr_payload_text if qr_payload_text else None,
        }

    return {
        "detector": "none",
        "inv_no": None,
        "serial_no": None,
        "qr_payload_text": qr_payload_text if qr_payload_text else None,
    }

