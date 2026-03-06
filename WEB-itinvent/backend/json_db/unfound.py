#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unfound Equipment JSON operations.

Handles operations for equipment not found in the main SQL database.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from backend.json_db.manager import JSONDataManager

logger = logging.getLogger(__name__)


class UnfoundEquipmentManager:
    """Manager for unfound equipment operations."""

    UNFOUND_FILE = "unfound_equipment.json"

    def __init__(self, data_manager: Optional[JSONDataManager] = None):
        """
        Initialize the unfound equipment manager.

        Args:
            data_manager: Optional JSONDataManager instance
        """
        self.data_manager = data_manager or JSONDataManager()

    def add_unfound_equipment(
        self,
        serial_number: str,
        model_name: str,
        employee_name: str,
        brand_name: Optional[str] = None,
        location: Optional[str] = None,
        equipment_type: Optional[str] = None,
        description: Optional[str] = None,
        inventory_number: Optional[str] = None,
        batch_number: Optional[str] = None,
        ip_address: Optional[str] = None,
        status: Optional[str] = None,
        branch: Optional[str] = None,
        company: Optional[str] = None,
        db_name: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add a new unfound equipment record.

        Args:
            serial_number: Serial number of the equipment
            model_name: Model name
            employee_name: Employee name
            brand_name: Brand/manufacturer name
            location: Location code
            equipment_type: Type of equipment
            description: Description
            inventory_number: Inventory number
            batch_number: Batch number
            ip_address: IP address
            status: Equipment status
            branch: Branch name
            company: Company name
            db_name: Database name
            additional_data: Additional metadata

        Returns:
            Created record
        """
        # Clean and validate serial number
        serial_number = self._extract_serial_value(serial_number or "")
        if not serial_number:
            raise ValueError("Serial number is required")

        # Check if record already exists
        existing = self.get_unfound_equipment()
        for record in existing:
            if record.get('serial_number') == serial_number:
                raise ValueError(f"Equipment with serial {serial_number} already exists")

        # Create new record
        new_record = {
            'serial_number': serial_number,
            'model_name': (model_name or "").strip(),
            'employee_name': (employee_name or "").strip(),
            'brand_name': (brand_name or "").strip(),
            'location': (location or "").strip(),
            'equipment_type': (equipment_type or "").strip(),
            'description': (description or "").strip(),
            'inventory_number': (inventory_number or "").strip(),
            'batch_number': (batch_number or "").strip(),
            'ip_address': (ip_address or "").strip(),
            'status': (status or "").strip(),
            'branch': (branch or "").strip(),
            'company': (company or 'ООО "Запсибгазпром-Газификация"').strip(),
            'timestamp': datetime.now().isoformat(),
            'additional_data': additional_data or {},
            'db_name': (db_name or "").strip(),
        }

        # Save to JSON
        self.data_manager.append_to_json(self.UNFOUND_FILE, new_record)
        logger.info(f"Added unfound equipment: {serial_number} -> {employee_name}")

        return new_record

    def get_unfound_equipment(
        self,
        db_name: Optional[str] = None,
        branch: Optional[str] = None,
        employee: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get unfound equipment records with optional filtering.

        Args:
            db_name: Filter by database name
            branch: Filter by branch
            employee: Filter by employee name
            limit: Maximum number of records to return

        Returns:
            List of unfound equipment records
        """
        data = self.data_manager.load_json(self.UNFOUND_FILE, default_content=[])
        if not isinstance(data, list):
            return []

        # Apply filters
        filtered = data

        if db_name:
            filtered = [r for r in filtered if r.get('db_name') == db_name]

        if branch:
            filtered = [r for r in filtered if branch.lower() in (r.get('branch') or '').lower()]

        if employee:
            filtered = [r for r in filtered if employee.lower() in (r.get('employee_name') or '').lower()]

        # Apply limit
        if limit and limit > 0:
            filtered = filtered[-limit:]

        return filtered

    def get_unfound_by_serial(self, serial_number: str) -> Optional[Dict[str, Any]]:
        """
        Get unfound equipment by serial number.

        Args:
            serial_number: Serial number to search for

        Returns:
            Equipment record or None if not found
        """
        serial_number = self._extract_serial_value(serial_number or "")
        if not serial_number:
            return None

        records = self.get_unfound_equipment()
        for record in records:
            if record.get('serial_number') == serial_number:
                return record

        return None

    def update_unfound_equipment(
        self,
        serial_number: str,
        **updates
    ) -> Optional[Dict[str, Any]]:
        """
        Update unfound equipment record.

        Args:
            serial_number: Serial number of the equipment to update
            **updates: Fields to update

        Returns:
            Updated record or None if not found
        """
        serial_number = self._extract_serial_value(serial_number or "")

        def predicate(record):
            return record.get('serial_number') == serial_number

        def updater(record):
            updated = record.copy()
            for key, value in updates.items():
                if value is not None:
                    updated[key] = value
            return updated

        count = self.data_manager.update_json_array(
            self.UNFOUND_FILE, predicate, updater
        )

        if count > 0:
            return self.get_unfound_by_serial(serial_number)

        return None

    def delete_unfound_equipment(self, serial_number: str) -> bool:
        """
        Delete unfound equipment record.

        Args:
            serial_number: Serial number of the equipment to delete

        Returns:
            True if deleted, False if not found
        """
        serial_number = self._extract_serial_value(serial_number or "")

        data = self.data_manager.load_json(self.UNFOUND_FILE, default_content=[])
        if not isinstance(data, list):
            return False

        original_length = len(data)
        data = [r for r in data if r.get('serial_number') != serial_number]

        if len(data) < original_length:
            self.data_manager.save_json(self.UNFOUND_FILE, data)
            logger.info(f"Deleted unfound equipment: {serial_number}")
            return True

        return False

    def get_unfound_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about unfound equipment.

        Returns:
            Statistics dictionary
        """
        records = self.get_unfound_equipment()

        # Count by type
        type_counts: Dict[str, int] = {}
        # Count by branch
        branch_counts: Dict[str, int] = {}

        for record in records:
            eq_type = record.get('equipment_type', 'Неизвестно')
            type_counts[eq_type] = type_counts.get(eq_type, 0) + 1

            branch = record.get('branch', 'Неизвестно')
            branch_counts[branch] = branch_counts.get(branch, 0) + 1

        return {
            'total': len(records),
            'by_type': type_counts,
            'by_branch': branch_counts,
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
