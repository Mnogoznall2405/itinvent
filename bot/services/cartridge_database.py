#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
База данных картриджей для принтеров
Точные соответствия моделей принтеров и совместимых картриджей
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

@dataclass
class CartridgeInfo:
    """Информация о картридже"""
    model: str
    description: str
    color: str
    page_yield: Optional[int] = None
    oem_part: Optional[str] = None

@dataclass
class PrinterCompatibility:
    """Информация о совместимости принтера"""
    oem_cartridge: str
    compatible_models: List[CartridgeInfo]
    is_color: bool = False
    components: List[str] = None
    fuser_models: List[str] = None
    photoconductor_models: List[str] = None
    waste_toner_models: List[str] = None
    transfer_belt_models: List[str] = None

class CartridgeDatabase:
    """База данных соответствия картриджей"""

    def __init__(self):
        self.data_file = Path("data/cartridge_database.json")
        self.cartridge_db = self._load_database()

    def _load_database(self) -> Dict[str, PrinterCompatibility]:
        """Загружает базу данных картриджей"""
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Конвертируем в объекты
                result = {}
                for printer_name, printer_data in data.items():
                    compatible_models = []
                    for cart_data in printer_data.get('compatible_models', []):
                        compatible_models.append(CartridgeInfo(
                            model=cart_data['model'],
                            description=cart_data.get('description', ''),
                            color=cart_data.get('color', 'Черный'),
                            page_yield=cart_data.get('page_yield'),
                            oem_part=cart_data.get('oem_part')
                        ))

                    result[printer_name] = PrinterCompatibility(
                        oem_cartridge=printer_data.get('oem_cartridge', ''),
                        compatible_models=compatible_models,
                        is_color=printer_data.get('is_color', False),
                        components=printer_data.get('components', ['cartridge', 'fuser', 'photoconductor']),
                        fuser_models=printer_data.get('fuser_models', []),
                        photoconductor_models=printer_data.get('photoconductor_models', []),
                        waste_toner_models=printer_data.get('waste_toner_models', []),
                        transfer_belt_models=printer_data.get('transfer_belt_models', [])
                    )

                logger.info(f"Загружена база данных картриджей: {len(result)} принтеров")
                return result
            else:
                logger.warning("Файл базы данных картриджей не найден, используем встроенные данные")
                return self._get_builtin_database()
        except Exception as e:
            logger.error(f"Ошибка загрузки базы данных картриджей: {e}")
            return self._get_builtin_database()

    def _get_builtin_database(self) -> Dict[str, PrinterCompatibility]:
        """Встроенная база данных (базовые модели)"""
        return {
            # HP монохромные принтеры
            "hp laserjet pro m404n": PrinterCompatibility(
                oem_cartridge="HP 05A",
                compatible_models=[
                    CartridgeInfo("HP 05A", "Стандартный картридж", "Черный", 2300),
                    CartridgeInfo("HP 05X", "Увеличенной емкости", "Черный", 6500),
                    CartridgeInfo("HP 05H", "Высокой емкости", "Черный", 9000),
                ],
                is_color=False,
                components=["cartridge", "fuser", "photoconductor"]
            ),

            "hp laserjet pro m404dn": PrinterCompatibility(
                oem_cartridge="HP 05A",
                compatible_models=[
                    CartridgeInfo("HP 05A", "Стандартный картридж", "Черный", 2300),
                    CartridgeInfo("HP 05X", "Увеличенной емкости", "Черный", 6500),
                    CartridgeInfo("HP 05H", "Высокой емкости", "Черный", 9000),
                ],
                is_color=False,
                components=["cartridge", "fuser", "photoconductor"]
            ),

            "hp laserjet pro m402dn": PrinterCompatibility(
                oem_cartridge="HP 05A",
                compatible_models=[
                    CartridgeInfo("HP 05A", "Стандартный картридж", "Черный", 2300),
                    CartridgeInfo("HP 05X", "Увеличенной емкости", "Черный", 6500),
                ],
                is_color=False,
                components=["cartridge", "fuser", "photoconductor"]
            ),

            # HP цветные принтеры
            "hp color laserjet pro m454dn": PrinterCompatibility(
                oem_cartridge="HP 410A",
                compatible_models=[
                    CartridgeInfo("HP 410A", "Стандартный картридж", "Черный", 2500),
                    CartridgeInfo("HP 410A", "Стандартный картридж", "Синий", 2400),
                    CartridgeInfo("HP 410A", "Стандартный картридж", "Желтый", 2400),
                    CartridgeInfo("HP 410A", "Стандартный картридж", "Пурпурный", 2400),
                    CartridgeInfo("HP 410X", "Увеличенной емкости", "Черный", 7500),
                    CartridgeInfo("HP 410X", "Увеличенной емкости", "Синий", 7500),
                    CartridgeInfo("HP 410X", "Увеличенной емкости", "Желтый", 7500),
                    CartridgeInfo("HP 410X", "Увеличенной емкости", "Пурпурный", 7500),
                ],
                is_color=True,
                components=["cartridge", "fuser", "photoconductor", "waste_toner", "transfer_belt"]
            ),

            # Canon принтеры
            " Canon i-SENSYS MF244dw": PrinterCompatibility(
                oem_cartridge="Canon CRG-041",
                compatible_models=[
                    CartridgeInfo("Canon CRG-041", "Стандартный картридж", "Черный", 2100),
                    CartridgeInfo("Canon CRG-041H", "Увеличенной емкости", "Черный", 6400),
                ],
                is_color=False,
                components=["cartridge", "fuser", "photoconductor"]
            ),

            "Canon MF3010": PrinterCompatibility(
                oem_cartridge="Canon CRG-325",
                compatible_models=[
                    CartridgeInfo("Canon CRG-325", "Стандартный картридж", "Черный", 1600),
                ],
                is_color=False,
                components=["cartridge", "fuser", "photoconductor"]
            ),

            # Xerox принтеры
            "xerox versalink c7020": PrinterCompatibility(
                oem_cartridge="Xerox 106R02773",
                compatible_models=[
                    CartridgeInfo("Xerox 106R02773", "Черный картридж", "Черный", 3000),
                    CartridgeInfo("Xerox 106R02774", "Синий картридж", "Синий", 3000),
                    CartridgeInfo("Xerox 106R02775", "Желтый картридж", "Желтый", 3000),
                    CartridgeInfo("Xerox 106R02776", "Пурпурный картридж", "Пурпурный", 3000),
                ],
                is_color=True,
                components=["cartridge", "fuser", "photoconductor", "waste_toner", "transfer_belt"]
            ),

            # Brother принтеры
            "brother hl-l2350dw": PrinterCompatibility(
                oem_cartridge="Brother TN-2480",
                compatible_models=[
                    CartridgeInfo("Brother TN-2480", "Стандартный картридж", "Черный", 1200),
                    CartridgeInfo("Brother TN-2485", "Увеличенной емкости", "Черный", 3000),
                ],
                is_color=False,
                components=["cartridge", "fuser", "photoconductor"]
            ),
        }

    def find_printer_compatibility(self, printer_model: str) -> Optional[PrinterCompatibility]:
        """
        Ищет совместимость для принтера с учетом вариантов написания

        Args:
            printer_model: Модель принтера

        Returns:
            Optional[PrinterCompatibility]: Информация о совместимости или None
        """
        # Нормализуем имя принтера для поиска
        normalized_model = self._normalize_printer_name(printer_model)

        # Прямой поиск
        if normalized_model in self.cartridge_db:
            return self.cartridge_db[normalized_model]

        # Нечеткий поиск
        best_match = None
        best_ratio = 0.0

        for db_printer in self.cartridge_db.keys():
            ratio = SequenceMatcher(None, normalized_model, db_printer).ratio()
            if ratio > best_ratio and ratio > 0.8:  # 80% совпадение
                best_ratio = ratio
                best_match = db_printer

        if best_match:
            logger.info(f"Found fuzzy match for {printer_model}: {best_match} (ratio: {best_ratio:.2f})")
            return self.cartridge_db[best_match]

        return None

    def _normalize_printer_name(self, printer_model: str) -> str:
        """Нормализует имя принтера для поиска"""
        normalized = printer_model.lower().strip()

        # Удаляем артикли и лишние слова
        words_to_remove = ['the ', 'a ', 'an ']
        for word in words_to_remove:
            normalized = normalized.replace(word, '')

        # Заменяем множественные пробелы на один
        normalized = ' '.join(normalized.split())

        return normalized

    def get_cartridges_for_printer(self, printer_model: str) -> List[CartridgeInfo]:
        """
        Возвращает список картриджей для принтера

        Args:
            printer_model: Модель принтера

        Returns:
            List[CartridgeInfo]: Список совместимых картриджей
        """
        compatibility = self.find_printer_compatibility(printer_model)

        if compatibility:
            return compatibility.compatible_models

        return []

    def get_cartridge_colors(self, printer_model: str) -> List[str]:
        """
        Возвращает доступные цвета картриджей для принтера

        Args:
            printer_model: Модель принтера

        Returns:
            List[str]: Список доступных цветов
        """
        cartridges = self.get_cartridges_for_printer(printer_model)

        colors = set()
        for cartridge in cartridges:
            colors.add(cartridge.color)

        return sorted(list(colors))

    def get_printer_components(self, printer_model: str) -> List[str]:
        """
        Возвращает список компонентов для принтера

        Args:
            printer_model: Модель принтера

        Returns:
            List[str]: Список доступных компонентов
        """
        compatibility = self.find_printer_compatibility(printer_model)

        if compatibility:
            return compatibility.components

        # По умолчанию базовые компоненты
        return ["cartridge", "fuser", "photoconductor"]

    def is_color_printer(self, printer_model: str) -> bool:
        """
        Определяет является ли принтер цветным

        Args:
            printer_model: Модель принтера

        Returns:
            bool: True если цветной принтер
        """
        compatibility = self.find_printer_compatibility(printer_model)

        if compatibility:
            return compatibility.is_color

        return False

    def update_database(self, new_data: Dict[str, PrinterCompatibility]):
        """Обновляет базу данных новыми данными"""
        self.cartridge_db.update(new_data)
        self._save_database()

    def _save_database(self):
        """Сохраняет базу данных в файл"""
        try:
            # Создаем директорию если нужно
            self.data_file.parent.mkdir(exist_ok=True)

            # Конвертируем объекты в словари
            data = {}
            for printer_name, compatibility in self.cartridge_db.items():
                compatible_models = []
                for cartridge in compatibility.compatible_models:
                    compatible_models.append({
                        'model': cartridge.model,
                        'description': cartridge.description,
                        'color': cartridge.color,
                        'page_yield': cartridge.page_yield,
                        'oem_part': cartridge.oem_part
                    })

                data[printer_name] = {
                    'oem_cartridge': compatibility.oem_cartridge,
                    'compatible_models': compatible_models,
                    'is_color': compatibility.is_color,
                    'components': compatibility.components
                }

            # Сохраняем
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"База данных картриджей сохранена: {len(data)} принтеров")

        except Exception as e:
            logger.error(f"Ошибка сохранения базы данных картриджей: {e}")

    def add_printer(self, printer_model: str, compatibility: PrinterCompatibility):
        """
        Добавляет новый принтер в базу данных

        Args:
            printer_model: Модель принтера
            compatibility: Информация о совместимости
        """
        normalized_name = self._normalize_printer_name(printer_model)
        self.cartridge_db[normalized_name] = compatibility
        self._save_database()
        logger.info(f"Добавлен принтер в базу: {printer_model}")

# Глобальный экземпляр
cartridge_database = CartridgeDatabase()