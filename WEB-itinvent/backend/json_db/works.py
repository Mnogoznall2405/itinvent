#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Works JSON operations.

Handles operations for equipment maintenance works:
- Cartridge replacements
- Battery replacements
- Component replacements (fuser, drum, etc.)
- PC cleanings
"""

import logging
import re
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime, timedelta

from backend.json_db.manager import JSONDataManager

logger = logging.getLogger(__name__)

# Work type constants
WorkType = Literal['cartridge', 'battery', 'component', 'cleaning']


class WorksManager:
    """Manager for work operations."""

    CARTRIDGE_FILE = "cartridge_replacements.json"
    BATTERY_FILE = "battery_replacements.json"
    COMPONENT_FILE = "component_replacements.json"
    CLEANING_FILE = "pc_cleanings.json"
    NOTE_AUTHOR = "IT-BOT"
    PC_KEYWORDS = (
        "системный блок",
        "системный",
        "пк",
        "pc",
        "system unit",
        "workstation",
        "desktop",
        "prodesk",
        "elitedesk",
        "optiplex",
        "thinkcentre",
        "ноутбук",
        "notebook",
        "laptop",
        "лэптоп",
        "моноблок",
        "all-in-one",
    )
    PRINTER_MFU_KEYWORDS = (
        "принтер",
        "мфу",
        "printer",
        "mfp",
        "mfc",
        "laserjet",
        "officejet",
        "deskjet",
        "workcentre",
        "versalink",
        "i-sensys",
        "imageprograf",
        "imagerunner",
        "plotter",
        "designjet",
        "plotwave",
        "surecolor",
    )
    PRINTER_COMPONENT_TYPES = (
        "fuser",
        "photoconductor",
        "drum",
        "waste_toner",
        "transfer_belt",
    )
    PC_COMPONENT_TYPES = (
        "ram",
        "ssd",
        "hdd",
        "hdd_ssd",
        "gpu",
        "cpu",
        "motherboard",
        "psu",
        "cooler",
        "fan",
    )

    def __init__(self, data_manager: Optional[JSONDataManager] = None):
        """
        Initialize the works manager.

        Args:
            data_manager: Optional JSONDataManager instance
        """
        self.data_manager = data_manager or JSONDataManager()

    # ========== Cartridge Replacements ==========

    def add_cartridge_replacement(
        self,
        printer_model: str,
        cartridge_color: str,
        branch: str,
        location: str,
        serial_number: Optional[str] = None,
        inv_no: Optional[str] = None,
        db_name: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
        component_type: Optional[str] = None,
        component_color: Optional[str] = None,
        cartridge_model: Optional[str] = None,
        detection_source: Optional[str] = None,
        printer_is_color: Optional[bool] = None,
        equipment_id: Optional[int] = None,
        current_description: Optional[str] = None,
        hw_serial_no: Optional[str] = None,
        model_name: Optional[str] = None,
        manufacturer: Optional[str] = None,
        employee: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a cartridge replacement record.

        Args:
            printer_model: Model of the printer
            cartridge_color: Color of the cartridge (Черный, Синий, Желтый, Пурпурный)
            branch: Branch name
            location: Location code
            serial_number: Serial number of the printer (optional)
            inv_no: Inventory number (optional)
            db_name: Database name
            additional_data: Additional metadata

        Returns:
            Created record
        """
        normalized_printer_model = (printer_model or "").strip()
        normalized_serial = (serial_number or "").strip()
        normalized_color = (cartridge_color or "").strip()
        normalized_component_type = (component_type or "cartridge").strip() or "cartridge"
        normalized_component_color = (component_color or normalized_color).strip()

        # Protect against accidental writes of PC/workstation operations into MFU history.
        if self._is_pc_record(
            {
                "type_name": "",
                "model_name": normalized_printer_model,
                "vendor_name": (manufacturer or ""),
            }
        ):
            raise ValueError(
                "Операция картриджа не может быть записана для ПК/рабочей станции."
            )

        resolved_detection_source = (detection_source or "").strip().lower()
        resolved_cartridge_model = (cartridge_model or "").strip()
        resolved_printer_is_color = bool(printer_is_color) if printer_is_color is not None else False

        try:
            from backend.json_db.cartridges import CartridgeDatabase

            cartridge_db = CartridgeDatabase(self.data_manager)
            compatibility = cartridge_db.find_printer_compatibility(normalized_printer_model)
            if compatibility:
                if not resolved_detection_source:
                    resolved_detection_source = "database"
                if printer_is_color is None:
                    resolved_printer_is_color = bool(compatibility.is_color)
                if not resolved_cartridge_model:
                    compatible_models = getattr(compatibility, "compatible_models", []) or []
                    lowered_color = normalized_color.lower()
                    color_matches = [
                        c for c in compatible_models
                        if str(getattr(c, "color", "") or "").strip().lower() == lowered_color
                    ]
                    candidate = color_matches[0] if color_matches else (compatible_models[0] if compatible_models else None)
                    if candidate and getattr(candidate, "model", None):
                        resolved_cartridge_model = str(candidate.model).strip()
                    elif getattr(compatibility, "oem_cartridge", None):
                        resolved_cartridge_model = str(compatibility.oem_cartridge).strip()
            elif not resolved_detection_source:
                resolved_detection_source = "manual"
        except Exception as e:
            logger.warning(f"Could not resolve cartridge metadata from database: {e}")
            if not resolved_detection_source:
                resolved_detection_source = "manual"

        record = {
            'branch': branch.strip(),
            'location': location.strip(),
            'printer_model': normalized_printer_model,
            'component_type': normalized_component_type,
            'component_color': normalized_component_color,
            'cartridge_model': resolved_cartridge_model,
            'detection_source': resolved_detection_source or "manual",
            'printer_is_color': resolved_printer_is_color,
            'cartridge_color': normalized_color,
            'db_name': (db_name or "").strip(),
            'timestamp': datetime.now().isoformat(),
            'serial_no': normalized_serial,
            'serial_number': normalized_serial,  # compatibility with legacy schema
            'hw_serial_no': (hw_serial_no or "").strip(),
            'model_name': (model_name or "").strip(),
            'manufacturer': (manufacturer or "").strip(),
            'employee': (employee or "").strip(),
            'inv_no': (inv_no or "").strip(),
        }
        if additional_data:
            record['additional_data'] = additional_data

        self.data_manager.append_to_json(self.CARTRIDGE_FILE, record)
        logger.info(f"Added cartridge replacement: {normalized_printer_model} - {normalized_color}")

        if equipment_id and db_name:
            color_part = f" ({normalized_color})" if normalized_color else ""
            note_prefix = f"Последняя замена картриджа{color_part}"
            if normalized_color:
                # For old records without color suffix, update that legacy line too.
                note_pattern = (
                    rf'(?:Последняя замена картриджа{re.escape(color_part)}|Последняя замена картриджа)'
                    r':.*?\((?:IT-BOT|IT-WEB)\)'
                )
            else:
                note_pattern = r'Последняя замена картриджа:.*?\((?:IT-BOT|IT-WEB)\)'
            self._update_sql_descr_with_note(
                equipment_id=equipment_id,
                current_description=current_description or '',
                db_name=db_name,
                note_line=self._build_timestamp_note(note_prefix),
                note_pattern=note_pattern,
                operation_label=f"cartridge replacement{color_part}",
            )
        else:
            logger.warning(f"Skipping SQL update for cartridge replacement: equipment_id={equipment_id}, db_name={db_name}")

        return record

    def get_cartridge_replacements(
        self,
        db_name: Optional[str] = None,
        branch: Optional[str] = None,
        location: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get cartridge replacement records with optional filtering."""
        data = self.data_manager.load_json(self.CARTRIDGE_FILE, default_content=[])
        if not isinstance(data, list):
            return []

        filtered = data

        if db_name:
            filtered = [r for r in filtered if r.get('db_name') == db_name]

        if branch:
            filtered = [r for r in filtered if branch.lower() in (r.get('branch') or '').lower()]

        if location:
            filtered = [r for r in filtered if location.lower() in (r.get('location') or '').lower()]

        if from_date:
            filtered = [r for r in filtered if r.get('timestamp', '') >= from_date]

        if to_date:
            filtered = [r for r in filtered if r.get('timestamp', '') <= to_date]

        if limit and limit > 0:
            filtered = filtered[-limit:]

        return filtered

    def get_cartridge_replacement_history(
        self,
        serial_number: Optional[str] = None,
        hw_serial_number: Optional[str] = None,
        inv_no: Optional[str] = None,
        cartridge_color: Optional[str] = None,
        cartridge_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get cartridge replacement history for specific equipment with optional color filter."""
        try:
            data = self.data_manager.load_json(self.CARTRIDGE_FILE, default_content=[])
            if not isinstance(data, list):
                result = self._history_from_records([])
                result.update({'cartridge_color': cartridge_color, 'cartridge_model': cartridge_model})
                return result

            normalized_color = str(cartridge_color or "").strip().lower()
            normalized_model = str(cartridge_model or "").strip().lower()
            matches = [
                rec for rec in data
                if self._record_matches_serial(rec, serial_number, hw_serial_number, inv_no) and (
                    not normalized_color or str(rec.get('cartridge_color') or '').strip().lower() == normalized_color
                ) and (
                    not normalized_model or str(rec.get('cartridge_model') or '').strip().lower() == normalized_model
                )
            ]
            result = self._history_from_records(matches)
            result.update({'cartridge_color': cartridge_color, 'cartridge_model': cartridge_model})
            return result
        except Exception as e:
            logger.error(f"Error getting cartridge replacement history: {e}")
            result = self._history_from_records([])
            result.update({'cartridge_color': cartridge_color, 'cartridge_model': cartridge_model})
            return result

    # ========== Battery Replacements ==========

    def add_battery_replacement(
        self,
        serial_number: str,
        branch: str,
        location: str,
        inv_no: Optional[str] = None,
        db_name: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
        equipment_id: Optional[int] = None,
        current_description: Optional[str] = None,
        hw_serial_no: Optional[str] = None,
        model_name: Optional[str] = None,
        manufacturer: Optional[str] = None,
        employee: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a battery replacement record (motherboard battery).

        Args:
            serial_number: Serial number of the equipment
            branch: Branch name
            location: Location code
            inv_no: Inventory number
            db_name: Database name
            additional_data: Additional metadata

        Returns:
            Created record
        """
        normalized_serial = (serial_number or "").strip()
        record = {
            'serial_no': normalized_serial,
            'serial_number': normalized_serial,  # compatibility with legacy schema
            'hw_serial_no': (hw_serial_no or "").strip(),
            'model_name': (model_name or "").strip(),
            'manufacturer': (manufacturer or "").strip(),
            'inv_no': (inv_no or "").strip(),
            'branch': branch.strip(),
            'location': location.strip(),
            'employee': (employee or "").strip(),
            'timestamp': datetime.now().isoformat(),
            'db_name': (db_name or "").strip(),
            'additional_data': additional_data or {},
        }

        self.data_manager.append_to_json(self.BATTERY_FILE, record)
        logger.info(f"Added battery replacement: {normalized_serial}")

        if equipment_id and db_name:
            self._update_sql_descr_with_note(
                equipment_id=equipment_id,
                current_description=current_description or '',
                db_name=db_name,
                note_line=self._build_timestamp_note("Последняя замена батареи"),
                note_pattern=r'Последняя замена батареи:.*?\((?:IT-BOT|IT-WEB)\)',
                operation_label="battery replacement",
            )
        else:
            logger.warning(f"Skipping SQL update for battery replacement: equipment_id={equipment_id}, db_name={db_name}")

        return record

    def get_battery_replacements(
        self,
        db_name: Optional[str] = None,
        branch: Optional[str] = None,
        serial_number: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get battery replacement records with optional filtering."""
        data = self.data_manager.load_json(self.BATTERY_FILE, default_content=[])
        if not isinstance(data, list):
            return []

        filtered = data

        if db_name:
            filtered = [r for r in filtered if r.get('db_name') == db_name]

        if branch:
            filtered = [r for r in filtered if branch.lower() in (r.get('branch') or '').lower()]

        if serial_number:
            filtered = [
                r for r in filtered
                if r.get('serial_number') == serial_number or r.get('serial_no') == serial_number
            ]

        if from_date:
            filtered = [r for r in filtered if r.get('timestamp', '') >= from_date]

        if to_date:
            filtered = [r for r in filtered if r.get('timestamp', '') <= to_date]

        if limit and limit > 0:
            filtered = filtered[-limit:]

        return filtered

    def get_battery_statistics(
        self,
        period_days: int = 90,
        db_name: Optional[str] = None,
        max_recent: Optional[int] = 300,
    ) -> Dict[str, Any]:
        """
        Build UPS battery replacement statistics from JSON records.

        Output includes:
        - counts by branch/location/model
        - used battery items
        - recent replacement events
        """
        safe_period_days = max(1, int(period_days or 90))
        now = datetime.now()
        start_dt = now - timedelta(days=safe_period_days)

        records = self.get_battery_replacements(db_name=db_name)

        by_branch_period: Dict[str, int] = {}
        by_model_period: Dict[str, int] = {}
        by_manufacturer_period: Dict[str, int] = {}
        by_item_period: Dict[str, int] = {}
        by_location_raw: Dict[str, Dict[str, Any]] = {}
        recent_replacements: List[Dict[str, Any]] = []
        total_operations = 0

        for record in records:
            event_at = self._parse_timestamp(record.get("timestamp"))
            if event_at is None or event_at < start_dt:
                continue

            branch = self._normalize_branch_name(record.get("branch"))
            location = self._normalize_location_name(record.get("location"))
            model_name = str(record.get("model_name") or "Не указано").strip() or "Не указано"
            manufacturer = str(record.get("manufacturer") or "Не указано").strip() or "Не указано"
            battery_item = self._resolve_battery_item_name(record)

            total_operations += 1
            by_branch_period[branch] = by_branch_period.get(branch, 0) + 1
            by_model_period[model_name] = by_model_period.get(model_name, 0) + 1
            by_manufacturer_period[manufacturer] = by_manufacturer_period.get(manufacturer, 0) + 1
            by_item_period[battery_item] = by_item_period.get(battery_item, 0) + 1

            location_key = f"{branch}|{location}"
            location_row = by_location_raw.get(location_key)
            if location_row is None:
                location_row = {
                    "branch": branch,
                    "location": location,
                    "operations": 0,
                    "last_timestamp": "",
                    "top_items": {},
                }
                by_location_raw[location_key] = location_row

            location_row["operations"] += 1
            location_row["top_items"][battery_item] = location_row["top_items"].get(battery_item, 0) + 1

            ts_text = event_at.isoformat()
            if ts_text > str(location_row["last_timestamp"] or ""):
                location_row["last_timestamp"] = ts_text

            recent_replacements.append(
                {
                    "timestamp": ts_text,
                    "branch": branch,
                    "location": location,
                    "model_name": model_name,
                    "manufacturer": manufacturer,
                    "replacement_item": battery_item,
                    "db_name": str(record.get("db_name") or "").strip(),
                    "employee": str(record.get("employee") or "").strip(),
                    "inv_no": str(record.get("inv_no") or "").strip(),
                    "serial_no": str(record.get("serial_no") or record.get("serial_number") or "").strip(),
                }
            )

        by_location_period = []
        for row in by_location_raw.values():
            by_location_period.append(
                {
                    "branch": row["branch"],
                    "location": row["location"],
                    "operations": row["operations"],
                    "last_timestamp": row["last_timestamp"],
                    "top_items": [
                        {"name": name, "count": count}
                        for name, count in sorted(row["top_items"].items(), key=lambda kv: (-kv[1], kv[0]))[:5]
                    ],
                }
            )
        by_location_period.sort(key=lambda x: (-x["operations"], x["branch"], x["location"]))
        recent_replacements.sort(key=lambda x: x["timestamp"], reverse=True)
        recent_limit = max(0, int(max_recent)) if max_recent is not None else None

        return {
            "generated_at": now.isoformat(),
            "period_days": safe_period_days,
            "start_date": start_dt.date().isoformat(),
            "end_date": now.date().isoformat(),
            "totals": {
                "total_operations": total_operations,
                "unique_branches": len(by_branch_period),
                "unique_locations": len(by_location_period),
            },
            "by_branch_period": dict(sorted(by_branch_period.items(), key=lambda kv: (-kv[1], kv[0]))),
            "by_model_period": [
                {"model": model, "count": count}
                for model, count in sorted(by_model_period.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
            ],
            "by_manufacturer_period": dict(sorted(by_manufacturer_period.items(), key=lambda kv: (-kv[1], kv[0]))),
            "by_item_period": dict(sorted(by_item_period.items(), key=lambda kv: (-kv[1], kv[0]))),
            "by_location_period": by_location_period,
            "recent_replacements": recent_replacements[:recent_limit] if recent_limit is not None else recent_replacements,
        }

    # ========== Component Replacements ==========

    def add_component_replacement(
        self,
        serial_number: str,
        component_type: str,
        component_model: str,
        branch: str,
        location: str,
        inv_no: Optional[str] = None,
        db_name: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
        equipment_id: Optional[int] = None,
        current_description: Optional[str] = None,
        hw_serial_no: Optional[str] = None,
        model_name: Optional[str] = None,
        manufacturer: Optional[str] = None,
        employee: Optional[str] = None,
        component_name: Optional[str] = None,
        equipment_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a component replacement record (fuser, drum, etc.).

        Args:
            serial_number: Serial number of the printer/equipment
            component_type: Type of component (фьюзер, фотобарабан, etc.)
            component_model: Model of the replacement component
            branch: Branch name
            location: Location code
            inv_no: Inventory number
            db_name: Database name
            additional_data: Additional metadata

        Returns:
            Created record
        """
        normalized_serial = (serial_number or "").strip()
        normalized_component_type = (component_type or "").strip()
        normalized_component_model = (component_model or "").strip()
        resolved_component_name = self._resolve_component_name(normalized_component_type, component_name)
        normalized_equipment_kind = (equipment_kind or "").strip().lower()
        is_printer_component = (
            normalized_equipment_kind == "printer"
            or normalized_component_type.lower() in self.PRINTER_COMPONENT_TYPES
        )

        record = {
            'serial_no': normalized_serial,
            'serial_number': normalized_serial,  # compatibility with legacy schema
            'hw_serial_no': (hw_serial_no or "").strip(),
            'model_name': (model_name or "").strip(),
            'manufacturer': (manufacturer or "").strip(),
            'employee': (employee or "").strip(),
            'component_type': normalized_component_type,
            'component_name': resolved_component_name,
            'component_model': normalized_component_model,
            'equipment_kind': (equipment_kind or "").strip(),
            'inv_no': (inv_no or "").strip(),
            'branch': branch.strip(),
            'location': location.strip(),
            'timestamp': datetime.now().isoformat(),
            'db_name': (db_name or "").strip(),
            'additional_data': additional_data or {},
        }

        if is_printer_component:
            # Keep printer/MFU component replacements in the same file as cartridges.
            printer_model_name = (model_name or "").strip()
            component_color_value = "Универсальный"
            if normalized_component_type == "cartridge":
                component_color_value = ""

            printer_is_color = False
            try:
                from backend.json_db.cartridges import CartridgeDatabase

                cartridge_db = CartridgeDatabase(self.data_manager)
                printer_is_color = bool(cartridge_db.is_color_printer(printer_model_name))
            except Exception:
                printer_is_color = False

            printer_record = {
                'branch': branch.strip(),
                'location': location.strip(),
                'printer_model': printer_model_name,
                'component_type': normalized_component_type,
                'component_color': component_color_value,
                'cartridge_model': normalized_component_model or resolved_component_name,
                'detection_source': 'manual',
                'printer_is_color': printer_is_color,
                'cartridge_color': component_color_value,
                'db_name': (db_name or "").strip(),
                'timestamp': datetime.now().isoformat(),
                'serial_no': normalized_serial,
                'serial_number': normalized_serial,
                'hw_serial_no': (hw_serial_no or "").strip(),
                'model_name': printer_model_name,
                'manufacturer': (manufacturer or "").strip(),
                'employee': (employee or "").strip(),
                'inv_no': (inv_no or "").strip(),
            }
            self.data_manager.append_to_json(self.CARTRIDGE_FILE, printer_record)
            logger.info(
                "Added printer component replacement to cartridge file: "
                f"{normalized_serial} - {resolved_component_name}"
            )
        else:
            self.data_manager.append_to_json(self.COMPONENT_FILE, record)
            logger.info(f"Added component replacement: {normalized_serial} - {resolved_component_name}")

        if equipment_id and db_name:
            note_line = f"Замена {resolved_component_name}: {datetime.now().strftime('%d.%m.%Y %H:%M')} ({self.NOTE_AUTHOR})"
            note_pattern = rf'Замена {re.escape(resolved_component_name)}:.*?\((?:IT-BOT|IT-WEB)\)'
            self._update_sql_descr_with_note(
                equipment_id=equipment_id,
                current_description=current_description or '',
                db_name=db_name,
                note_line=note_line,
                note_pattern=note_pattern,
                operation_label=f"component replacement ({resolved_component_name})",
            )
        else:
            logger.warning(f"Skipping SQL update for component replacement: equipment_id={equipment_id}, db_name={db_name}")

        return record

    def get_component_replacements(
        self,
        db_name: Optional[str] = None,
        branch: Optional[str] = None,
        component_type: Optional[str] = None,
        serial_number: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get component replacement records with optional filtering."""
        data = self._get_component_records_combined()

        filtered = data

        if db_name:
            filtered = [r for r in filtered if r.get('db_name') == db_name]

        if branch:
            filtered = [r for r in filtered if branch.lower() in (r.get('branch') or '').lower()]

        if component_type:
            filtered = [r for r in filtered if component_type.lower() in (r.get('component_type') or '').lower()]

        if serial_number:
            filtered = [
                r for r in filtered
                if r.get('serial_number') == serial_number or r.get('serial_no') == serial_number
            ]

        if from_date:
            filtered = [r for r in filtered if r.get('timestamp', '') >= from_date]

        if to_date:
            filtered = [r for r in filtered if r.get('timestamp', '') <= to_date]

        if limit and limit > 0:
            filtered = filtered[-limit:]

        return filtered

    def _get_component_records_combined(self) -> List[Dict[str, Any]]:
        """
        Return unified component replacement records:
        - PC components from component_replacements.json
        - Printer/MFU components from cartridge_replacements.json
        """
        component_data = self._get_component_records_from_component_file(db_name=None)

        printer_component_data = self._get_printer_component_records_from_cartridge()
        return component_data + printer_component_data

    def _get_component_records_from_component_file(self, db_name: Optional[str]) -> List[Dict[str, Any]]:
        """Load component records from component_replacements.json only."""
        component_data = self.data_manager.load_json(self.COMPONENT_FILE, default_content=[])
        if not isinstance(component_data, list):
            return []
        if db_name:
            return [r for r in component_data if str(r.get("db_name") or "").strip() == db_name]
        return component_data

    def _get_printer_component_records_from_cartridge(self) -> List[Dict[str, Any]]:
        """Extract printer component replacements that are stored in cartridge file."""
        source = self.data_manager.load_json(self.CARTRIDGE_FILE, default_content=[])
        if not isinstance(source, list):
            return []

        records: List[Dict[str, Any]] = []
        for entry in source:
            component_type = str(entry.get('component_type') or '').strip().lower()
            if not component_type or component_type == 'cartridge':
                continue

            if component_type not in self.PRINTER_COMPONENT_TYPES:
                # Keep only printer-like component operations here.
                continue

            normalized = dict(entry)
            normalized['serial_number'] = str(
                entry.get('serial_number') or entry.get('serial_no') or ''
            ).strip()
            normalized['component_model'] = str(
                entry.get('component_model') or entry.get('cartridge_model') or ''
            ).strip()
            normalized['component_name'] = str(
                entry.get('component_name') or self._resolve_component_name(component_type, None)
            ).strip()
            normalized['equipment_kind'] = str(entry.get('equipment_kind') or 'printer').strip()
            normalized['model_name'] = str(
                entry.get('model_name') or entry.get('printer_model') or ''
            ).strip()
            records.append(normalized)

        return records

    # ========== PC Cleanings ==========

    def add_pc_cleaning(
        self,
        serial_number: str,
        employee: str,
        branch: str,
        location: str,
        inv_no: Optional[str] = None,
        db_name: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
        equipment_id: Optional[int] = None,
        current_description: Optional[str] = None,
        hw_serial_no: Optional[str] = None,
        model_name: Optional[str] = None,
        manufacturer: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a PC cleaning record.

        Args:
            serial_number: Serial number of the PC
            employee: Employee name
            branch: Branch name
            location: Location code
            inv_no: Inventory number
            db_name: Database name
            additional_data: Additional metadata
            equipment_id: Equipment ID for SQL update (optional)
            current_description: Current DESCRIPTION value for SQL update (optional)
            hw_serial_no: Hardware serial number (optional)
            model_name: Model name (optional)
            manufacturer: Manufacturer name (optional)

        Returns:
            Created record
        """
        record = {
            'serial_no': serial_number.strip(),
            'serial_number': serial_number.strip(),  # compatibility with legacy schema
            'hw_serial_no': (hw_serial_no or "").strip(),
            'model_name': (model_name or "").strip(),
            'manufacturer': (manufacturer or "").strip(),
            'branch': branch.strip(),
            'location': location.strip(),
            'employee': employee.strip(),
            'inv_no': (inv_no or "").strip(),
            'db_name': (db_name or "").strip(),
            'timestamp': datetime.now().isoformat(),
        }

        # Save to JSON
        self.data_manager.append_to_json(self.CLEANING_FILE, record)
        logger.info(f"Added PC cleaning: {serial_number} - {employee}")

        # Update SQL DESCR if equipment_id and db_name are provided
        if equipment_id and db_name:
            self._update_sql_descr_with_note(
                equipment_id=equipment_id,
                current_description=current_description or '',
                db_name=db_name,
                note_line=self._build_timestamp_note("Последняя чистка"),
                note_pattern=r'Последняя чистка:.*?\((?:IT-BOT|IT-WEB)\)',
                operation_label="pc cleaning",
            )
        else:
            logger.warning(f"Skipping SQL update: equipment_id={equipment_id}, db_name={db_name}")

        return record

    def _build_timestamp_note(self, prefix: str) -> str:
        """Build timestamped DESCR line for maintenance notes."""
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
        return f"{prefix}: {timestamp} ({self.NOTE_AUTHOR})"

    @staticmethod
    def _merge_description_note(current_description: str, note_line: str, note_pattern: str) -> str:
        """Replace existing note line if present, otherwise append a new line."""
        existing_description = current_description or ""
        if existing_description and re.search(note_pattern, existing_description):
            return re.sub(note_pattern, note_line, existing_description)
        if existing_description:
            separator = "\r\n" if not existing_description.endswith(("\r\n", "\n")) else ""
            return existing_description + separator + note_line
        return note_line

    @staticmethod
    def _resolve_component_name(component_type: str, component_name: Optional[str]) -> str:
        """Resolve human-readable component name for DESCR and JSON."""
        explicit_name = (component_name or "").strip()
        if explicit_name:
            return explicit_name

        fallback_names = {
            "fuser": "фьюзера",
            "photoconductor": "фотобарабана",
            "waste_toner": "контейнера отработанного тонера",
            "transfer_belt": "трансферного ролика",
            "ram": "оперативной памяти",
            "ssd": "SSD",
            "hdd": "HDD",
            "gpu": "видеокарты",
            "cpu": "процессора",
            "motherboard": "материнской платы",
            "psu": "блока питания",
            "cooler": "кулера",
            "fan": "вентилятора",
        }
        normalized_type = (component_type or "").strip().lower()
        return fallback_names.get(normalized_type, normalized_type or "компонента")

    def _update_sql_descr_with_note(
        self,
        equipment_id: int,
        current_description: str,
        db_name: str,
        note_line: str,
        note_pattern: str,
        operation_label: str,
    ) -> None:
        """
        Update the DESCR field in SQL database with a formatted maintenance note.

        Args:
            equipment_id: Equipment ID in the database
            current_description: Current DESCRIPTION value
            db_name: Database name to use for connection
            note_line: Text line to write into DESCR
            note_pattern: Regex pattern to replace existing note
            operation_label: Log label for operation context
        """
        try:
            from backend.database.connection import get_db

            logger.info(
                f"Attempting SQL DESCR update ({operation_label}): "
                f"equipment_id={equipment_id}, db_name={db_name}"
            )

            if not equipment_id:
                logger.warning("No equipment_id provided, skipping SQL update")
                return

            if not db_name:
                logger.warning("No db_name provided, skipping SQL update")
                return

            # Get database connection using backend's connection manager
            db = get_db(db_name)
            if not db:
                logger.warning(f"Could not get database connection for {db_name}")
                return

            new_description = self._merge_description_note(current_description, note_line, note_pattern)

            # Execute UPDATE
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE ITEMS
                    SET DESCR = ?, CH_DATE = GETDATE(), CH_USER = 'IT-BOT'
                    WHERE ID = ?
                """, (new_description, equipment_id))
                conn.commit()
                logger.info(
                    f"Successfully updated DESCR ({operation_label}) for equipment_id={equipment_id}"
                )

        except Exception as e:
            logger.error(
                f"Error updating SQL DESCR ({operation_label}) for equipment_id={equipment_id}: {e}"
            )
            import traceback
            traceback.print_exc()

    @staticmethod
    def _record_matches_serial(
        record: Dict[str, Any],
        serial_number: Optional[str],
        hw_serial_number: Optional[str],
        inv_no: Optional[str] = None,
    ) -> bool:
        """Check whether a record belongs to equipment by serial, hardware serial or inv_no."""
        primary = (serial_number or "").strip()
        secondary = (hw_serial_number or "").strip()
        inventory_number = str(inv_no or "").strip()
        record_inv_no = str(record.get('inv_no') or '').strip()
        record_serials = {
            str(record.get('serial_number') or '').strip(),
            str(record.get('serial_no') or '').strip(),
            str(record.get('hw_serial_no') or '').strip(),
        }
        record_serials.discard("")
        if primary and primary in record_serials:
            return True
        if secondary and secondary in record_serials:
            return True
        if inventory_number and record_inv_no and inventory_number == record_inv_no:
            return True
        return False

    @staticmethod
    def _history_from_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build unified history summary from a list of records."""
        if not records:
            return {
                'last_date': None,
                'count': 0,
                'time_ago_str': None,
            }

        sorted_records = sorted(records, key=lambda x: x.get('timestamp', ''), reverse=True)
        last_timestamp = sorted_records[0].get('timestamp')
        last_date = None
        if last_timestamp:
            try:
                last_date = datetime.fromisoformat(str(last_timestamp).replace('Z', '+00:00'))
            except ValueError:
                last_date = None

        time_ago_str = None
        if last_date:
            now = datetime.now(last_date.tzinfo)
            delta = now - last_date
            days = delta.days
            if days == 0:
                time_ago_str = 'сегодня'
            elif days == 1:
                time_ago_str = 'вчера'
            elif days < 7:
                time_ago_str = f'{days} дн. назад'
            elif days < 30:
                time_ago_str = f'{days // 7} нед. назад'
            elif days < 365:
                time_ago_str = f'{days // 30} мес. назад'
            else:
                time_ago_str = f'{days // 365} г. назад'

        return {
            'last_date': last_date.isoformat() if last_date else None,
            'count': len(records),
            'time_ago_str': time_ago_str,
        }

    def get_battery_replacement_history(
        self,
        serial_number: str,
        hw_serial_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get battery replacement history for specific equipment."""
        try:
            data = self.data_manager.load_json(self.BATTERY_FILE, default_content=[])
            if not isinstance(data, list):
                return self._history_from_records([])
            matches = [
                rec for rec in data
                if self._record_matches_serial(rec, serial_number, hw_serial_number)
            ]
            return self._history_from_records(matches)
        except Exception as e:
            logger.error(f"Error getting battery replacement history: {e}")
            return self._history_from_records([])

    def get_component_replacement_history(
        self,
        serial_number: str,
        hw_serial_number: Optional[str] = None,
        component_type: Optional[str] = None,
        component_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get component replacement history for specific equipment and optional component filter."""
        try:
            data = self._get_component_records_combined()

            normalized_type = str(component_type or '').strip().lower()
            normalized_name = str(component_name or '').strip().lower()

            def component_matches(record: Dict[str, Any]) -> bool:
                if normalized_type:
                    record_type = str(record.get('component_type') or '').strip().lower()
                    if record_type != normalized_type:
                        return False
                if normalized_name:
                    record_name = str(record.get('component_name') or '').strip().lower()
                    if record_name != normalized_name:
                        return False
                return True

            matches = [
                rec for rec in data
                if self._record_matches_serial(rec, serial_number, hw_serial_number) and component_matches(rec)
            ]
            result = self._history_from_records(matches)
            result.update({'component_type': component_type, 'component_name': component_name})
            return result
        except Exception as e:
            logger.error(f"Error getting component replacement history: {e}")
            base = self._history_from_records([])
            base.update({'component_type': component_type, 'component_name': component_name})
            return base

    def get_pc_cleaning_history(
        self,
        serial_number: str,
        hw_serial_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get PC cleaning history for a specific serial number.

        Args:
            serial_number: Serial number to search for
            hw_serial_number: Hardware serial number (optional, for additional search)

        Returns:
            Dictionary with last_date, count, and time_ago_str
        """
        try:
            data = self.data_manager.load_json(self.CLEANING_FILE, default_content=[])
            if not isinstance(data, list):
                return self._history_from_records([])
            pc_cleanings = [
                c for c in data
                if self._record_matches_serial(c, serial_number, hw_serial_number)
            ]
            return self._history_from_records(pc_cleanings)

        except Exception as e:
            logger.error(f"Error getting PC cleaning history: {e}")
            return self._history_from_records([])

    def get_pc_cleanings(
        self,
        db_name: Optional[str] = None,
        branch: Optional[str] = None,
        employee: Optional[str] = None,
        serial_number: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get PC cleaning records with optional filtering."""
        data = self.data_manager.load_json(self.CLEANING_FILE, default_content=[])
        if not isinstance(data, list):
            return []

        filtered = data

        if db_name:
            filtered = [r for r in filtered if r.get('db_name') == db_name]

        if branch:
            filtered = [r for r in filtered if branch.lower() in (r.get('branch') or '').lower()]

        if employee:
            filtered = [r for r in filtered if employee.lower() in (r.get('employee') or '').lower()]

        if serial_number:
            filtered = [r for r in filtered if r.get('serial_number') == serial_number or r.get('serial_no') == serial_number]

        if from_date:
            filtered = [r for r in filtered if r.get('timestamp', '') >= from_date]

        if to_date:
            filtered = [r for r in filtered if r.get('timestamp', '') <= to_date]

        if limit and limit > 0:
            filtered = filtered[-limit:]

        return filtered

    def get_pc_cleaning_statistics(
        self,
        period_days: int = 90,
        db_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build PC cleaning statistics by branch for selected period.

        Logic:
        - total_pc: total number of PCs currently in SQL inventory
        - cleaned_pc: PCs with at least one cleaning in selected period
        - remaining_pc: PCs without cleaning in selected period
        """
        safe_period_days = max(1, int(period_days or 90))
        now = datetime.now()
        start_dt = now - timedelta(days=safe_period_days)

        pc_inventory = self._get_pc_inventory(db_name=db_name)
        cleanings = self.get_pc_cleanings(db_name=db_name)

        latest_cleaning_by_identifier: Dict[str, datetime] = {}
        cleanings_by_branch_total: Dict[str, int] = {}
        cleanings_by_branch_period: Dict[str, int] = {}
        cleanings_total = 0
        cleanings_period = 0

        for record in cleanings:
            cleaned_at = self._parse_timestamp(record.get("timestamp"))
            if cleaned_at is None:
                continue

            cleanings_total += 1
            branch_name = self._normalize_branch_name(record.get("branch"))
            cleanings_by_branch_total[branch_name] = cleanings_by_branch_total.get(branch_name, 0) + 1

            if cleaned_at >= start_dt:
                cleanings_period += 1
                cleanings_by_branch_period[branch_name] = cleanings_by_branch_period.get(branch_name, 0) + 1

            for identifier in self._extract_identifiers(record):
                existing = latest_cleaning_by_identifier.get(identifier)
                if existing is None or cleaned_at > existing:
                    latest_cleaning_by_identifier[identifier] = cleaned_at

        total_pc_by_branch: Dict[str, int] = {}
        cleaned_pc_by_branch: Dict[str, int] = {}

        for item in pc_inventory:
            branch_name = self._normalize_branch_name(item.get("branch_name"))
            total_pc_by_branch[branch_name] = total_pc_by_branch.get(branch_name, 0) + 1

            identifiers = self._extract_identifiers(item)
            latest_for_item = None
            for identifier in identifiers:
                candidate = latest_cleaning_by_identifier.get(identifier)
                if candidate is not None and (latest_for_item is None or candidate > latest_for_item):
                    latest_for_item = candidate

            if latest_for_item is not None and latest_for_item >= start_dt:
                cleaned_pc_by_branch[branch_name] = cleaned_pc_by_branch.get(branch_name, 0) + 1

        all_branches = set(total_pc_by_branch.keys()) | set(cleanings_by_branch_total.keys())
        rows = []

        for branch_name in sorted(all_branches):
            total_pc = total_pc_by_branch.get(branch_name, 0)
            cleaned_pc = cleaned_pc_by_branch.get(branch_name, 0)
            remaining_pc = max(total_pc - cleaned_pc, 0)
            coverage_percent = round((cleaned_pc / total_pc) * 100, 1) if total_pc else 0.0

            rows.append(
                {
                    "branch": branch_name,
                    "total_pc": total_pc,
                    "cleaned_pc": cleaned_pc,
                    "remaining_pc": remaining_pc,
                    "coverage_percent": coverage_percent,
                    "cleanings_total": cleanings_by_branch_total.get(branch_name, 0),
                    "cleanings_period": cleanings_by_branch_period.get(branch_name, 0),
                }
            )

        rows.sort(key=lambda r: (-r["remaining_pc"], r["branch"]))

        total_pc_all = sum(total_pc_by_branch.values())
        cleaned_pc_all = sum(cleaned_pc_by_branch.values())
        remaining_pc_all = max(total_pc_all - cleaned_pc_all, 0)

        return {
            "generated_at": now.isoformat(),
            "period_days": safe_period_days,
            "start_date": start_dt.date().isoformat(),
            "end_date": now.date().isoformat(),
            "totals": {
                "total_pc": total_pc_all,
                "cleaned_pc": cleaned_pc_all,
                "remaining_pc": remaining_pc_all,
                "coverage_percent": round((cleaned_pc_all / total_pc_all) * 100, 1) if total_pc_all else 0.0,
                "cleanings_total": cleanings_total,
                "cleanings_period": cleanings_period,
            },
            "branches": rows,
        }

    def get_mfu_statistics(
        self,
        period_days: int = 90,
        db_name: Optional[str] = None,
        max_recent: Optional[int] = 300,
    ) -> Dict[str, Any]:
        """
        Build MFU/printer maintenance statistics from JSON records.

        Output is event-based:
        - what was replaced
        - where it was replaced
        - how many consumables/components were used
        """
        safe_period_days = max(1, int(period_days or 90))
        now = datetime.now()
        start_dt = now - timedelta(days=safe_period_days)

        cartridges = self.get_cartridge_replacements(db_name=db_name)
        component_file_records = self._get_component_records_from_component_file(db_name=db_name)

        by_type_period: Dict[str, int] = {}
        by_item_period: Dict[str, int] = {}
        by_branch_period: Dict[str, int] = {}
        by_model_period: Dict[str, int] = {}
        by_location_raw: Dict[str, Dict[str, Any]] = {}
        recent_replacements: List[Dict[str, Any]] = []
        total_operations = 0

        def register_record(record: Dict[str, Any], timestamp: datetime) -> None:
            nonlocal total_operations

            branch = self._normalize_branch_name(record.get("branch"))
            location = self._normalize_location_name(record.get("location"))
            component_type_raw = str(record.get("component_type") or "cartridge").strip().lower() or "cartridge"
            component_type_label = self._map_component_type_label(component_type_raw)
            replacement_item = self._resolve_mfu_replacement_item(record, component_type_label)
            printer_model = str(
                record.get("printer_model")
                or record.get("model_name")
                or "Не указано"
            ).strip() or "Не указано"

            total_operations += 1
            by_type_period[component_type_label] = by_type_period.get(component_type_label, 0) + 1
            by_item_period[replacement_item] = by_item_period.get(replacement_item, 0) + 1
            by_branch_period[branch] = by_branch_period.get(branch, 0) + 1
            by_model_period[printer_model] = by_model_period.get(printer_model, 0) + 1

            location_key = f"{branch}|{location}"
            location_row = by_location_raw.get(location_key)
            if location_row is None:
                location_row = {
                    "branch": branch,
                    "location": location,
                    "operations": 0,
                    "last_timestamp": "",
                    "by_type": {},
                    "by_item": {},
                }
                by_location_raw[location_key] = location_row

            location_row["operations"] += 1
            location_row["by_type"][component_type_label] = location_row["by_type"].get(component_type_label, 0) + 1
            location_row["by_item"][replacement_item] = location_row["by_item"].get(replacement_item, 0) + 1

            event_ts = timestamp.isoformat()
            if event_ts > str(location_row["last_timestamp"] or ""):
                location_row["last_timestamp"] = event_ts

            recent_replacements.append(
                {
                    "timestamp": event_ts,
                    "branch": branch,
                    "location": location,
                    "printer_model": printer_model,
                    "component_type": component_type_label,
                    "replacement_item": replacement_item,
                    "db_name": str(record.get("db_name") or "").strip(),
                    "employee": str(record.get("employee") or "").strip(),
                    "inv_no": str(record.get("inv_no") or "").strip(),
                    "serial_no": str(record.get("serial_no") or record.get("serial_number") or "").strip(),
                }
            )

        for record in cartridges:
            if not self._is_printer_mfu_operation_record(record):
                continue
            event_at = self._parse_timestamp(record.get("timestamp"))
            if event_at is None or event_at < start_dt:
                continue
            register_record(record, event_at)

        # Include only legacy printer component records from component_replacements.json.
        # Printer components from cartridge_replacements.json are already counted above.
        for record in component_file_records:
            if not self._is_printer_component_record(record):
                continue
            event_at = self._parse_timestamp(record.get("timestamp"))
            if event_at is None or event_at < start_dt:
                continue
            register_record(record, event_at)

        by_location_period = []
        for row in by_location_raw.values():
            by_location_period.append(
                {
                    "branch": row["branch"],
                    "location": row["location"],
                    "operations": row["operations"],
                    "last_timestamp": row["last_timestamp"],
                    "by_type": dict(sorted(row["by_type"].items(), key=lambda kv: (-kv[1], kv[0]))),
                    "top_items": [
                        {"name": name, "count": count}
                        for name, count in sorted(row["by_item"].items(), key=lambda kv: (-kv[1], kv[0]))[:5]
                    ],
                }
            )
        by_location_period.sort(key=lambda x: (-x["operations"], x["branch"], x["location"]))
        recent_replacements.sort(key=lambda x: x["timestamp"], reverse=True)
        recent_limit = max(0, int(max_recent)) if max_recent is not None else None

        return {
            "generated_at": now.isoformat(),
            "period_days": safe_period_days,
            "start_date": start_dt.date().isoformat(),
            "end_date": now.date().isoformat(),
            "totals": {
                "total_operations": total_operations,
                "unique_branches": len(by_branch_period),
                "unique_locations": len(by_location_period),
            },
            "by_type_period": dict(sorted(by_type_period.items(), key=lambda kv: (-kv[1], kv[0]))),
            "by_item_period": dict(sorted(by_item_period.items(), key=lambda kv: (-kv[1], kv[0]))),
            "by_branch_period": dict(sorted(by_branch_period.items(), key=lambda kv: (-kv[1], kv[0]))),
            "by_model_period": [
                {"model": model, "count": count}
                for model, count in sorted(by_model_period.items(), key=lambda kv: (-kv[1], kv[0]))[:15]
            ],
            "by_location_period": by_location_period,
            "recent_replacements": recent_replacements[:recent_limit] if recent_limit is not None else recent_replacements,
        }

    def get_pc_components_statistics(
        self,
        period_days: int = 90,
        db_name: Optional[str] = None,
        max_recent: Optional[int] = 300,
    ) -> Dict[str, Any]:
        """
        Build PC component replacement statistics from JSON records.

        Output is event-based:
        - what component was replaced
        - where replacements happened
        - how many components were used
        """
        safe_period_days = max(1, int(period_days or 90))
        now = datetime.now()
        start_dt = now - timedelta(days=safe_period_days)

        records = self.get_component_replacements(db_name=db_name)

        by_component_period: Dict[str, int] = {}
        by_item_period: Dict[str, int] = {}
        by_branch_period: Dict[str, int] = {}
        by_model_period: Dict[str, int] = {}
        by_location_raw: Dict[str, Dict[str, Any]] = {}
        recent_replacements: List[Dict[str, Any]] = []
        total_operations = 0

        for record in records:
            if not self._is_pc_component_record(record):
                continue

            event_at = self._parse_timestamp(record.get("timestamp"))
            if event_at is None or event_at < start_dt:
                continue

            branch = self._normalize_branch_name(record.get("branch"))
            location = self._normalize_location_name(record.get("location"))
            component_name = self._resolve_pc_component_name(record)
            replacement_item = self._resolve_pc_component_item(record, component_name)
            model_name = str(record.get("model_name") or "Не указано").strip() or "Не указано"
            manufacturer = str(record.get("manufacturer") or "Не указано").strip() or "Не указано"

            total_operations += 1
            by_component_period[component_name] = by_component_period.get(component_name, 0) + 1
            by_item_period[replacement_item] = by_item_period.get(replacement_item, 0) + 1
            by_branch_period[branch] = by_branch_period.get(branch, 0) + 1
            by_model_period[model_name] = by_model_period.get(model_name, 0) + 1

            location_key = f"{branch}|{location}"
            location_row = by_location_raw.get(location_key)
            if location_row is None:
                location_row = {
                    "branch": branch,
                    "location": location,
                    "operations": 0,
                    "last_timestamp": "",
                    "top_items": {},
                }
                by_location_raw[location_key] = location_row

            location_row["operations"] += 1
            location_row["top_items"][replacement_item] = location_row["top_items"].get(replacement_item, 0) + 1

            ts_text = event_at.isoformat()
            if ts_text > str(location_row["last_timestamp"] or ""):
                location_row["last_timestamp"] = ts_text

            recent_replacements.append(
                {
                    "timestamp": ts_text,
                    "branch": branch,
                    "location": location,
                    "model_name": model_name,
                    "manufacturer": manufacturer,
                    "component_name": component_name,
                    "replacement_item": replacement_item,
                    "db_name": str(record.get("db_name") or "").strip(),
                    "employee": str(record.get("employee") or "").strip(),
                    "inv_no": str(record.get("inv_no") or "").strip(),
                    "serial_no": str(record.get("serial_no") or record.get("serial_number") or "").strip(),
                }
            )

        by_location_period = []
        for row in by_location_raw.values():
            by_location_period.append(
                {
                    "branch": row["branch"],
                    "location": row["location"],
                    "operations": row["operations"],
                    "last_timestamp": row["last_timestamp"],
                    "top_items": [
                        {"name": name, "count": count}
                        for name, count in sorted(row["top_items"].items(), key=lambda kv: (-kv[1], kv[0]))[:5]
                    ],
                }
            )
        by_location_period.sort(key=lambda x: (-x["operations"], x["branch"], x["location"]))
        recent_replacements.sort(key=lambda x: x["timestamp"], reverse=True)
        recent_limit = max(0, int(max_recent)) if max_recent is not None else None

        return {
            "generated_at": now.isoformat(),
            "period_days": safe_period_days,
            "start_date": start_dt.date().isoformat(),
            "end_date": now.date().isoformat(),
            "totals": {
                "total_operations": total_operations,
                "unique_branches": len(by_branch_period),
                "unique_locations": len(by_location_period),
            },
            "by_component_period": dict(sorted(by_component_period.items(), key=lambda kv: (-kv[1], kv[0]))),
            "by_item_period": dict(sorted(by_item_period.items(), key=lambda kv: (-kv[1], kv[0]))),
            "by_branch_period": dict(sorted(by_branch_period.items(), key=lambda kv: (-kv[1], kv[0]))),
            "by_model_period": [
                {"model": model, "count": count}
                for model, count in sorted(by_model_period.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
            ],
            "by_location_period": by_location_period,
            "recent_replacements": recent_replacements[:recent_limit] if recent_limit is not None else recent_replacements,
        }

    def _get_pc_inventory(self, db_name: Optional[str]) -> List[Dict[str, Any]]:
        """Load current PC inventory from SQL database for branch coverage calculations."""
        rows = self._load_inventory_with_context(db_name=db_name)
        return [row for row in rows if self._is_pc_record(row)]

    def _get_mfu_inventory(self, db_name: Optional[str]) -> List[Dict[str, Any]]:
        """Load current printer/MFU inventory from SQL database."""
        rows = self._load_inventory_with_context(db_name=db_name)
        return [row for row in rows if self._is_printer_mfu_record(row)]

    def _load_inventory_with_context(self, db_name: Optional[str]) -> List[Dict[str, Any]]:
        """Load generic inventory rows used for statistics calculations."""
        try:
            from backend.database.connection import get_db

            db = get_db(db_name)
            query = """
                SELECT
                    b.BRANCH_NAME as branch_name,
                    l.DESCR as location,
                    i.INV_NO as inv_no,
                    i.SERIAL_NO as serial_no,
                    i.HW_SERIAL_NO as hw_serial_no,
                    t.TYPE_NAME as type_name,
                    m.MODEL_NAME as model_name,
                    v.VENDOR_NAME as vendor_name
                FROM ITEMS i
                LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
                LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
                LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
                LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
                LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
                WHERE i.CI_TYPE = 1
            """
            rows = db.execute_query(query, ())
            if not isinstance(rows, list):
                return []
            return rows
        except Exception as e:
            logger.error(f"Error loading inventory for statistics: {e}")
            return []

    def _is_pc_record(self, row: Dict[str, Any]) -> bool:
        """Check if SQL record belongs to PC-like equipment by keywords."""
        type_name = str(row.get("type_name") or "").lower()
        model_name = str(row.get("model_name") or "").lower()
        vendor_name = str(row.get("vendor_name") or "").lower()
        full_text = f"{type_name} {model_name} {vendor_name}".strip()
        if not full_text:
            return False

        for keyword in self.PC_KEYWORDS:
            if keyword in ("pc", "пк"):
                if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", full_text):
                    return True
            elif keyword in full_text:
                return True
        return False

    def _is_printer_mfu_record(self, row: Dict[str, Any]) -> bool:
        """Check if SQL record belongs to printer/MFU equipment by keywords."""
        type_name = str(row.get("type_name") or "").lower()
        model_name = str(row.get("model_name") or "").lower()
        vendor_name = str(row.get("vendor_name") or "").lower()
        full_text = f"{type_name} {model_name} {vendor_name}".strip()
        if not full_text:
            return False
        return any(keyword in full_text for keyword in self.PRINTER_MFU_KEYWORDS)

    def _is_printer_mfu_operation_record(self, record: Dict[str, Any]) -> bool:
        """
        Check if maintenance JSON record belongs to printer/MFU/plotter.

        This guard filters out invalid events (e.g. accidental PC cartridge writes).
        """
        model_name = str(record.get("printer_model") or record.get("model_name") or "").lower()
        manufacturer = str(record.get("manufacturer") or "").lower()
        component_name = str(record.get("component_name") or "").lower()
        component_type = str(record.get("component_type") or "").strip().lower()
        full_text = f"{model_name} {manufacturer} {component_name}".strip()

        if self._is_pc_record({"type_name": "", "model_name": model_name, "vendor_name": manufacturer}):
            return False
        if component_type in self.PRINTER_COMPONENT_TYPES:
            return True
        if component_type == "cartridge":
            return any(keyword in full_text for keyword in self.PRINTER_MFU_KEYWORDS)
        return any(keyword in full_text for keyword in self.PRINTER_MFU_KEYWORDS)

    def _is_printer_component_record(self, record: Dict[str, Any]) -> bool:
        """Determine whether component replacement record belongs to printer/MFU."""
        equipment_kind = str(record.get("equipment_kind") or "").strip().lower()
        if equipment_kind == "printer":
            return True

        component_type = str(record.get("component_type") or "").strip().lower()
        if component_type in self.PRINTER_COMPONENT_TYPES:
            return True

        model_name = str(record.get("model_name") or "").strip().lower()
        manufacturer = str(record.get("manufacturer") or "").strip().lower()
        component_name = str(record.get("component_name") or "").strip().lower()
        full_text = f"{model_name} {manufacturer} {component_name}".strip()
        if not full_text:
            return False
        return any(keyword in full_text for keyword in self.PRINTER_MFU_KEYWORDS)

    def _is_pc_component_record(self, record: Dict[str, Any]) -> bool:
        """Determine whether component replacement record belongs to PC hardware."""
        equipment_kind = str(record.get("equipment_kind") or "").strip().lower()
        if equipment_kind == "pc":
            return True
        if equipment_kind == "printer":
            return False

        component_type = str(record.get("component_type") or "").strip().lower()
        if component_type in self.PC_COMPONENT_TYPES:
            return True
        if component_type in self.PRINTER_COMPONENT_TYPES:
            return False

        # Fallback by model/manufacturer text when type is unknown.
        if self._is_printer_component_record(record):
            return False
        return True

    @staticmethod
    def _normalize_location_name(value: Any) -> str:
        """Normalize location display name."""
        text = str(value or "").strip()
        return text or "Не указано"

    @staticmethod
    def _map_component_type_label(component_type: str) -> str:
        """Map internal component type to user-friendly label."""
        normalized = str(component_type or "").strip().lower()
        labels = {
            "cartridge": "Картридж",
            "fuser": "Фьюзер (печка)",
            "photoconductor": "Фотобарабан",
            "drum": "Барабан",
            "waste_toner": "Бункер отработки",
            "transfer_belt": "Трансфер",
        }
        return labels.get(normalized, normalized or "Не указано")

    @staticmethod
    def _map_pc_component_type_label(component_type: str) -> str:
        """Map internal PC component type to user-friendly label."""
        normalized = str(component_type or "").strip().lower()
        labels = {
            "ram": "Оперативная память",
            "ssd": "SSD",
            "hdd": "HDD",
            "hdd_ssd": "Накопитель (HDD/SSD)",
            "gpu": "Видеокарта",
            "cpu": "Процессор",
            "motherboard": "Материнская плата",
            "psu": "Блок питания",
            "cooler": "Кулер",
            "fan": "Вентилятор",
        }
        return labels.get(normalized, normalized or "Не указано")

    def _resolve_mfu_replacement_item(self, record: Dict[str, Any], default_type_label: str) -> str:
        """Build replacement item name used in consumption counters."""
        model = str(record.get("cartridge_model") or record.get("component_model") or "").strip()
        component_name = str(record.get("component_name") or "").strip()

        if model:
            return model
        if component_name:
            return component_name
        return default_type_label

    def _resolve_pc_component_name(self, record: Dict[str, Any]) -> str:
        """Resolve display name for PC component type."""
        explicit = str(record.get("component_name") or "").strip()
        if explicit:
            return explicit
        component_type = str(record.get("component_type") or "").strip()
        return self._map_pc_component_type_label(component_type)

    def _resolve_pc_component_item(self, record: Dict[str, Any], default_component_name: str) -> str:
        """Resolve concrete item/model used for PC component replacement."""
        model = str(record.get("component_model") or "").strip()
        if model:
            return model
        return default_component_name

    @staticmethod
    def _resolve_battery_item_name(record: Dict[str, Any]) -> str:
        """Resolve battery item label from known metadata fields."""
        additional = record.get("additional_data")
        if isinstance(additional, dict):
            for key in ("battery_model", "battery_type", "battery_name", "replacement_item"):
                value = str(additional.get(key) or "").strip()
                if value:
                    return value
        return "Батарея ИБП"

    def _resolve_service_timestamp_for_item(
        self,
        item: Dict[str, Any],
        services_by_identifier: Dict[str, datetime],
        services_by_signature: Dict[str, datetime],
    ) -> Optional[datetime]:
        """Resolve latest service timestamp for an inventory item."""
        latest = None

        for identifier in self._extract_identifiers(item):
            candidate = services_by_identifier.get(identifier)
            if candidate is not None and (latest is None or candidate > latest):
                latest = candidate

        signature = self._build_signature_key(item)
        if signature:
            candidate = services_by_signature.get(signature)
            if candidate is not None and (latest is None or candidate > latest):
                latest = candidate

        return latest

    def _build_signature_key(self, record: Dict[str, Any]) -> str:
        """
        Build fallback signature key (branch + location + model).

        Used when serial/inventory identifiers are absent in historical records.
        """
        branch = self._normalize_branch_name(
            record.get("branch") if "branch" in record else record.get("branch_name")
        ).lower()
        location = str(record.get("location") or "").strip().lower()
        if not location:
            location = str(record.get("location_name") or "").strip().lower()
        model = str(
            record.get("printer_model")
            or record.get("model_name")
            or ""
        ).strip().lower()
        parts = [branch, location, model]
        if not any(parts):
            return ""
        return "|".join(parts)

    @staticmethod
    def _normalize_identifier(value: Any) -> str:
        """Normalize serial/inventory identifiers for robust matching."""
        if value is None:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        if re.fullmatch(r"\d+(\.0+)?", text):
            try:
                text = str(int(float(text)))
            except ValueError:
                pass
        return text.upper()

    def _extract_identifiers(self, record: Dict[str, Any]) -> List[str]:
        """Extract normalized identifiers from JSON or SQL record."""
        keys = (
            "serial_no",
            "SERIAL_NO",
            "serial_number",
            "SERIAL_NUMBER",
            "hw_serial_no",
            "HW_SERIAL_NO",
            "inv_no",
            "INV_NO",
        )
        values = []
        for key in keys:
            normalized = self._normalize_identifier(record.get(key))
            if normalized:
                values.append(normalized)
        # preserve order, remove duplicates
        return list(dict.fromkeys(values))

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        """Parse ISO-like timestamp into naive datetime."""
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return None

        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt

    @staticmethod
    def _normalize_branch_name(value: Any) -> str:
        """Normalize branch display name."""
        text = str(value or "").strip()
        return text or "Не указано"

    # ========== All Works ==========

    def get_all_works(
        self,
        work_type: Optional[WorkType] = None,
        db_name: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all works with optional filtering.

        Args:
            work_type: Filter by specific work type
            db_name: Filter by database name
            from_date: Filter works after this ISO date
            to_date: Filter works before this ISO date
            limit: Maximum records per type

        Returns:
            Dictionary with work types as keys and lists of records as values
        """
        result = {}

        if work_type is None or work_type == 'cartridge':
            result['cartridge'] = self.get_cartridge_replacements(
                db_name=db_name, from_date=from_date, to_date=to_date, limit=limit
            )

        if work_type is None or work_type == 'battery':
            result['battery'] = self.get_battery_replacements(
                db_name=db_name, from_date=from_date, to_date=to_date, limit=limit
            )

        if work_type is None or work_type == 'component':
            result['component'] = self.get_component_replacements(
                db_name=db_name, from_date=from_date, to_date=to_date, limit=limit
            )

        if work_type is None or work_type == 'cleaning':
            result['cleaning'] = self.get_pc_cleanings(
                db_name=db_name, from_date=from_date, to_date=to_date, limit=limit
            )

        return result

    def get_works_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about all works.

        Returns:
            Statistics dictionary
        """
        cartridge = self.get_cartridge_replacements()
        battery = self.get_battery_replacements()
        component = self.get_component_replacements()
        cleaning = self.get_pc_cleanings()

        return {
            'cartridge': {
                'total': len(cartridge),
                'by_branch': self._count_by_field(cartridge, 'branch'),
            },
            'battery': {
                'total': len(battery),
                'by_branch': self._count_by_field(battery, 'branch'),
            },
            'component': {
                'total': len(component),
                'by_type': self._count_by_field(component, 'component_type'),
                'by_branch': self._count_by_field(component, 'branch'),
            },
            'cleaning': {
                'total': len(cleaning),
                'by_branch': self._count_by_field(cleaning, 'branch'),
            },
            'total_all': len(cartridge) + len(battery) + len(component) + len(cleaning),
        }

    @staticmethod
    def _count_by_field(records: List[Dict[str, Any]], field: str) -> Dict[str, int]:
        """Count records by a specific field."""
        counts: Dict[str, int] = {}
        for record in records:
            value = record.get(field, 'Неизвестно')
            counts[value] = counts.get(value, 0) + 1
        return counts
