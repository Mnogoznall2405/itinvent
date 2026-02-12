"""
Сервисный слой IT-invent Bot

Бизнес-логика, независимая от Telegram API.
"""

from .validation import (
    validate_serial_number,
    validate_employee_name,
    validate_ip_address,
    validate_inventory_number,
    sanitize_input
)
from .ocr_service import (
    analyze_image,
    extract_serial_number,
    extract_serial_from_image,
    extract_model,
    clean_serial_number
)
from .excel_service import (
    BaseExcelExporter,
    GroupedExcelExporter,
    DatabaseExcelExporter,
    SimpleExcelExporter,
    ExcelStyles,
    ColumnWidth,
    filter_data_by_period,
    count_excel_records
)

__all__ = [
    # Validation
    'validate_serial_number',
    'validate_employee_name',
    'validate_ip_address',
    'validate_inventory_number',
    'sanitize_input',
    # OCR
    'analyze_image',
    'extract_serial_number',
    'extract_serial_from_image',
    'extract_model',
    'clean_serial_number',
    # Excel Export
    'BaseExcelExporter',
    'GroupedExcelExporter',
    'DatabaseExcelExporter',
    'ExcelStyles',
    'ColumnWidth',
    'filter_data_by_period',
    'count_excel_records',
]
