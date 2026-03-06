#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Equipment Transfer JSON operations.

Handles operations for equipment transfers between employees.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from backend.json_db.manager import JSONDataManager

logger = logging.getLogger(__name__)


class TransferManager:
    """Manager for equipment transfer operations."""

    TRANSFERS_FILE = "equipment_transfers.json"

    def __init__(self, data_manager: Optional[JSONDataManager] = None):
        """
        Initialize the transfer manager.

        Args:
            data_manager: Optional JSONDataManager instance
        """
        self.data_manager = data_manager or JSONDataManager()

    def add_transfer(
        self,
        serial_number: str,
        new_employee: str,
        old_employee: Optional[str] = None,
        inv_no: Optional[str] = None,
        branch: Optional[str] = None,
        location: Optional[str] = None,
        db_name: Optional[str] = None,
        act_pdf_path: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add a new equipment transfer record.

        Args:
            serial_number: Serial number of the equipment
            new_employee: Name of the new employee (recipient)
            old_employee: Name of the old employee (sender)
            inv_no: Inventory number
            branch: Branch name
            location: Location code
            db_name: Database name
            act_pdf_path: Path to PDF act document
            additional_data: Additional metadata

        Returns:
            Created transfer record
        """
        # Clean serial number
        serial_number = self._extract_serial_value(serial_number or "")
        if not serial_number:
            raise ValueError("Serial number is required")

        if not new_employee or not new_employee.strip():
            raise ValueError("New employee name is required")

        # Merge additional_data with location/branch info
        merged_additional = additional_data.copy() if additional_data else {}
        if branch:
            merged_additional['branch'] = branch
        if location:
            merged_additional['location'] = location

        # Create new record
        new_record = {
            'serial_number': serial_number,
            'inv_no': (inv_no or "").strip(),
            'new_employee': new_employee.strip(),
            'old_employee': (old_employee or "").strip() if old_employee else None,
            'timestamp': datetime.now().isoformat(),
            'db_name': (db_name or "").strip(),
            'act_pdf_path': act_pdf_path,
            'additional_data': merged_additional,
        }

        # Save to JSON
        self.data_manager.append_to_json(self.TRANSFERS_FILE, new_record)
        logger.info(f"Added transfer: {serial_number} -> {new_employee}")

        return new_record

    def get_transfers(
        self,
        db_name: Optional[str] = None,
        branch: Optional[str] = None,
        employee: Optional[str] = None,
        serial_number: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get transfer records with optional filtering.

        Args:
            db_name: Filter by database name
            branch: Filter by branch
            employee: Filter by employee (matches both new_employee and old_employee)
            serial_number: Filter by serial number
            from_date: Filter transfers after this ISO date
            to_date: Filter transfers before this ISO date
            limit: Maximum number of records to return

        Returns:
            List of transfer records
        """
        data = self.data_manager.load_json(self.TRANSFERS_FILE, default_content=[])
        if not isinstance(data, list):
            return []

        # Apply filters
        filtered = data

        if db_name:
            filtered = [r for r in filtered if r.get('db_name') == db_name]

        if branch:
            filtered = [
                r for r in filtered
                if branch.lower() in (r.get('additional_data', {}).get('branch') or '').lower()
            ]

        if employee:
            filtered = [
                r for r in filtered
                if employee.lower() in (r.get('new_employee') or '').lower()
                or employee.lower() in (r.get('old_employee') or '').lower()
            ]

        if serial_number:
            serial_number = self._extract_serial_value(serial_number)
            filtered = [
                r for r in filtered
                if r.get('serial_number') == serial_number
            ]

        if from_date:
            filtered = [r for r in filtered if r.get('timestamp', '') >= from_date]

        if to_date:
            filtered = [r for r in filtered if r.get('timestamp', '') <= to_date]

        # Apply limit (most recent first)
        if limit and limit > 0:
            filtered = filtered[-limit:]

        return filtered

    def get_transfer_by_serial(self, serial_number: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get transfer history for a specific serial number.

        Args:
            serial_number: Serial number to search for
            limit: Maximum number of records to return (most recent)

        Returns:
            List of transfer records
        """
        return self.get_transfers(serial_number=serial_number, limit=limit)

    def get_transfers_by_employee(
        self, employee: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get transfer history for a specific employee.

        Args:
            employee: Employee name to search for
            limit: Maximum number of records to return

        Returns:
            List of transfer records
        """
        return self.get_transfers(employee=employee, limit=limit)

    def get_transfer_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about equipment transfers.

        Returns:
            Statistics dictionary
        """
        records = self.get_transfers()

        # Count by employee (both new and old)
        employee_counts: Dict[str, int] = {}

        for record in records:
            new_emp = record.get('new_employee', '')
            old_emp = record.get('old_employee')

            if new_emp:
                employee_counts[new_emp] = employee_counts.get(new_emp, 0) + 1

            if old_emp:
                employee_counts[old_emp] = employee_counts.get(old_emp, 0) + 1

        return {
            'total': len(records),
            'unique_employees': len(employee_counts),
            'top_employees': dict(sorted(
                employee_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]),
        }

    @staticmethod
    def _extract_serial_value(serial_input: str) -> str:
        """
        Extract clean serial number from input.

        Removes common prefixes like "Serial Number:", "S/N:", etc.

        Args:
            serial_input: Raw serial number input

        Returns:
            Cleaned serial number
        """
        import re

        if not serial_input or not isinstance(serial_input, str):
            return ""

        s = serial_input.strip()

        # Remove common prefixes
        prefix_re = re.compile(
            r'^\s*(?:serial\s*number|serial\s*no\.?|serial\s*#|s/?n|sn|service\s*tag|серийный\s*номер|серийный)\s*[:#\-]?\s*',
            re.IGNORECASE
        )

        s = prefix_re.sub('', s)
        return s.strip()
