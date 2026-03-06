#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Excel export service for statistics tabs."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, Dict, List, Tuple

from openpyxl import Workbook
from openpyxl.styles import Font


TAB_TO_FILENAME_PREFIX = {
    "pc": "pc_cleaning",
    "mfu": "mfu_replacements",
    "battery": "battery_replacements",
    "pc_components": "pc_components",
}


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _filter_by_period(records: List[Dict[str, Any]], period_days: int) -> List[Dict[str, Any]]:
    start_dt = datetime.now() - timedelta(days=max(1, int(period_days or 90)))
    filtered = []
    for record in records:
        timestamp = _parse_timestamp(record.get("timestamp"))
        if timestamp is None:
            continue
        if timestamp >= start_dt:
            filtered.append(record)
    filtered.sort(key=lambda row: str(row.get("timestamp") or ""), reverse=True)
    return filtered


def _rows_for_tab(manager, tab: str, period_days: int, db_name: str | None) -> List[Dict[str, Any]]:
    if tab == "pc":
        records = _filter_by_period(manager.get_pc_cleanings(db_name=db_name), period_days)
        return [
            {
                "Дата": row.get("timestamp", ""),
                "Филиал": row.get("branch", ""),
                "Локация": row.get("location", ""),
                "Сотрудник": row.get("employee", ""),
                "Модель": row.get("model_name", ""),
                "Производитель": row.get("manufacturer", ""),
                "Серийный номер": row.get("serial_no") or row.get("serial_number", ""),
                "Инвентарный номер": row.get("inv_no", ""),
                "База данных": row.get("db_name", ""),
            }
            for row in records
        ]

    if tab == "mfu":
        stats = manager.get_mfu_statistics(period_days=period_days, db_name=db_name, max_recent=None)
        rows = stats.get("recent_replacements", [])
        return [
            {
                "Дата": row.get("timestamp", ""),
                "Филиал": row.get("branch", ""),
                "Локация": row.get("location", ""),
                "Модель принтера": row.get("printer_model", ""),
                "Тип замены": row.get("component_type", ""),
                "Позиция": row.get("replacement_item", ""),
                "Сотрудник": row.get("employee", ""),
                "Серийный номер": row.get("serial_no", ""),
                "Инвентарный номер": row.get("inv_no", ""),
                "База данных": row.get("db_name", ""),
            }
            for row in rows
        ]

    if tab == "battery":
        stats = manager.get_battery_statistics(period_days=period_days, db_name=db_name, max_recent=None)
        rows = stats.get("recent_replacements", [])
        return [
            {
                "Дата": row.get("timestamp", ""),
                "Филиал": row.get("branch", ""),
                "Локация": row.get("location", ""),
                "Модель ИБП": row.get("model_name", ""),
                "Производитель": row.get("manufacturer", ""),
                "Позиция": row.get("replacement_item", ""),
                "Сотрудник": row.get("employee", ""),
                "Серийный номер": row.get("serial_no", ""),
                "Инвентарный номер": row.get("inv_no", ""),
                "База данных": row.get("db_name", ""),
            }
            for row in rows
        ]

    if tab == "pc_components":
        stats = manager.get_pc_components_statistics(period_days=period_days, db_name=db_name, max_recent=None)
        rows = stats.get("recent_replacements", [])
        return [
            {
                "Дата": row.get("timestamp", ""),
                "Филиал": row.get("branch", ""),
                "Локация": row.get("location", ""),
                "Модель ПК": row.get("model_name", ""),
                "Производитель": row.get("manufacturer", ""),
                "Компонент": row.get("component_name", ""),
                "Позиция": row.get("replacement_item", ""),
                "Сотрудник": row.get("employee", ""),
                "Серийный номер": row.get("serial_no", ""),
                "Инвентарный номер": row.get("inv_no", ""),
                "База данных": row.get("db_name", ""),
            }
            for row in rows
        ]

    raise ValueError(f"Unsupported tab: {tab}")


def _fit_columns(worksheet) -> None:
    for column_cells in worksheet.columns:
        max_length = 0
        column_letter = column_cells[0].column_letter
        for cell in column_cells:
            try:
                value = str(cell.value or "")
            except Exception:
                value = ""
            max_length = max(max_length, len(value))
        worksheet.column_dimensions[column_letter].width = min(max(max_length + 2, 12), 60)


def _write_rows(worksheet, headers: List[str], rows: List[Dict[str, Any]]) -> None:
    worksheet.append(headers)
    for cell in worksheet[1]:
        cell.font = Font(bold=True)

    if rows:
        for row in rows:
            worksheet.append([row.get(column, "") for column in headers])
    else:
        worksheet.append(["За выбранный период записей нет"])

    _fit_columns(worksheet)


def _detect_branch_column(headers: List[str]) -> str | None:
    for header in headers:
        lower = str(header).strip().lower()
        if "branch" in lower or "филиал" in lower or "р¤рёр»рёр°р»" in lower:
            return header
    return None


def _sanitize_sheet_name(raw_name: str, used_names: set[str]) -> str:
    name = str(raw_name or "").strip() or "Не указано"
    name = re.sub(r'[\\/*?:\[\]]+', "_", name).strip(" .")
    if not name:
        name = "Лист"

    base = name[:31]
    candidate = base
    counter = 1
    while candidate in used_names:
        suffix = f"_{counter}"
        max_base_len = max(1, 31 - len(suffix))
        candidate = f"{base[:max_base_len]}{suffix}"
        counter += 1

    used_names.add(candidate)
    return candidate


def build_statistics_excel(manager, tab: str, period_days: int, db_name: str | None = None) -> Tuple[bytes, str]:
    """
    Build statistics Excel:
    - sheet `Сводка` with all records
    - one sheet per branch
    """
    rows = _rows_for_tab(manager=manager, tab=tab, period_days=period_days, db_name=db_name)

    workbook = Workbook()
    summary_sheet = workbook.active
    summary_sheet.title = "Сводка"

    headers = list(rows[0].keys()) if rows else ["Данные"]
    _write_rows(summary_sheet, headers, rows)

    branch_column = _detect_branch_column(headers)
    if branch_column and rows:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            branch = str(row.get(branch_column) or "").strip() or "Не указано"
            groups.setdefault(branch, []).append(row)

        used_sheet_names = {summary_sheet.title}
        for branch in sorted(groups.keys()):
            sheet_name = _sanitize_sheet_name(branch, used_sheet_names)
            worksheet = workbook.create_sheet(title=sheet_name)
            _write_rows(worksheet, headers, groups[branch])

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    prefix = TAB_TO_FILENAME_PREFIX.get(tab, "statistics")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{period_days}d_{timestamp}.xlsx"
    return output.read(), filename
