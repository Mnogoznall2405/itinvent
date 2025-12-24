#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Улучшенный детектор компонентов принтеров
Использует базу данных картриджей + LLM как запасной вариант
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from openai import OpenAI

from bot.config import config
from bot.services.cartridge_database import cartridge_database, CartridgeInfo, PrinterCompatibility
from bot.services.printer_component_detector import component_detector

logger = logging.getLogger(__name__)

class EnhancedPrinterDetector:
    """Улучшенный детектор компонентов принтера с базой данных"""

    def __init__(self):
        self.client = OpenAI(
            api_key=config.api.openrouter_api_key,
            base_url=config.api.openrouter_base_url
        )
        self.fallback_detector = component_detector  # Используем старый как запасной

    def detect_printer_components(self, printer_model: str) -> Dict[str, Any]:
        """
        Определяет компоненты принтера с использованием базы данных

        Args:
            printer_model: Модель принтера

        Returns:
            Dict с информацией о компонентах и картриджах
        """
        logger.info(f"Detecting components for {printer_model} using enhanced detector")

        # Сначала пробуем базу данных
        compatibility = cartridge_database.find_printer_compatibility(printer_model)

        if compatibility:
            logger.info(f"Found printer {printer_model} in cartridge database")

            # Формируем компоненты на основе базы данных
            components = {}
            component_list = []

            for component in compatibility.components:
                components[component] = True
                component_list.append(component)

            # Получаем картриджи
            cartridges = compatibility.compatible_models

            return {
                "color": compatibility.is_color,
                "components": components,
                "component_list": component_list,
                "cartridges": [
                    {
                        "model": cart.model,
                        "description": cart.description,
                        "color": cart.color,
                        "page_yield": cart.page_yield,
                        "is_oem": cart.model == compatibility.oem_cartridge
                    }
                    for cart in cartridges
                ],
                "confidence": 0.95,  # Высокая уверенность для базы данных
                "determined_at": datetime.now().isoformat(),
                "from_cache": False,
                "source": "database",
                "oem_cartridge": compatibility.oem_cartridge
            }

        # Если нет в базе данных, используем LLM
        logger.info(f"Printer {printer_model} not found in database, using LLM fallback")
        return self._detect_with_llm_fallback(printer_model)

    def _detect_with_llm_fallback(self, printer_model: str) -> Dict[str, Any]:
        """Использует LLM как запасной вариант"""
        try:
            # Используем старый детектор
            result = self.fallback_detector.detect_printer_components(printer_model)

            # Добавляем информацию об источнике
            result["source"] = "llm_fallback"
            result["cartridges"] = []  # Пустой список, так как LLM не дает точных моделей

            return result

        except Exception as e:
            logger.error(f"Both database and LLM detection failed for {printer_model}: {e}")

            # Возвращаем базовые значения
            return {
                "color": False,
                "components": {
                    "cartridge": True,
                    "fuser": True,
                    "photoconductor": True,
                    "waste_toner": False,
                    "transfer_belt": False
                },
                "component_list": ["cartridge", "fuser", "photoconductor"],
                "cartridges": [],
                "confidence": 0.3,  # Низкая уверенность
                "determined_at": datetime.now().isoformat(),
                "from_cache": False,
                "source": "fallback",
                "error": str(e)
            }

    def get_cartridges_for_printer(self, printer_model: str) -> List[CartridgeInfo]:
        """
        Возвращает список картриджей для принтера

        Args:
            printer_model: Модель принтера

        Returns:
            List[CartridgeInfo]: Список совместимых картриджей
        """
        return cartridge_database.get_cartridges_for_printer(printer_model)

    def get_cartridges_by_color(self, printer_model: str, color: str) -> List[CartridgeInfo]:
        """
        Возвращает картриджи указанного цвета для принтера

        Args:
            printer_model: Модель принтера
            color: Цвет картриджа

        Returns:
            List[CartridgeInfo]: Список картриджей указанного цвета
        """
        cartridges = self.get_cartridges_for_printer(printer_model)
        return [cart for cart in cartridges if cart.color.lower() == color.lower()]

    def add_printer_from_user_input(self, printer_model: str, cartridges_info: List[Dict[str, Any]]):
        """
        Добавляет информацию о принтере от пользователя в базу данных

        Args:
            printer_model: Модель принтера
            cartridges_info: Информация о картриджах от пользователя
        """
        try:
            # Определяем цветной принтер или нет
            is_color = any(cart.get('color', '').lower() in ['синий', 'желтый', 'пурпурный', 'cyan', 'yellow', 'magenta', 'blue', 'red']
                          for cart in cartridges_info)

            # Создаем объекты CartridgeInfo
            compatible_models = []
            oem_cartridge = ""

            for cart_info in cartridges_info:
                cartridge = CartridgeInfo(
                    model=cart_info.get('model', ''),
                    description=cart_info.get('description', ''),
                    color=cart_info.get('color', 'Черный'),
                    page_yield=cart_info.get('page_yield'),
                    oem_part=cart_info.get('oem_part')
                )
                compatible_models.append(cartridge)

                # OEM картридж - первый или помеченный как OEM
                if cart_info.get('is_oem', False) or not oem_cartridge:
                    oem_cartridge = cartridge.model

            # Определяем компоненты
            components = ["cartridge", "fuser", "photoconductor"]
            if is_color:
                components.extend(["waste_toner", "transfer_belt"])

            # Создаем объект совместимости
            compatibility = PrinterCompatibility(
                oem_cartridge=oem_cartridge,
                compatible_models=compatible_models,
                is_color=is_color,
                components=components
            )

            # Добавляем в базу данных
            cartridge_database.add_printer(printer_model, compatibility)

            logger.info(f"Added printer from user input: {printer_model}")

            return True

        except Exception as e:
            logger.error(f"Error adding printer from user input: {e}")
            return False

    def get_cartridge_display_info(self, printer_model: str, color: str = None) -> str:
        """
        Возвращает отформатированную информацию о картриджах для принтера

        Args:
            printer_model: Модель принтера
            color: Опциональный фильтр по цвету

        Returns:
            str: Отформатированная строка с информацией о картриджах
        """
        cartridges = self.get_cartridges_for_printer(printer_model)

        if color:
            cartridges = [cart for cart in cartridges if cart.color.lower() == color.lower()]

        if not cartridges:
            return "Картриджи не найдены"

        lines = [f"🖨️ Картриджи для {printer_model}:"]
        lines.append("")

        for cart in cartridges:
            oem_mark = " (OEM)" if cart.model == cartridge_database.find_printer_compatibility(printer_model).oem_cartridge else ""
            yield_info = f" - {cart.page_yield} стр." if cart.page_yield else ""

            lines.append(f"• {cart.model}{oem_mark}")
            lines.append(f"  {cart.description} - {cart.color}{yield_info}")
            lines.append("")

        return "\n".join(lines)

    def suggest_cartridge_correction(self, printer_model: str, wrong_cartridges: List[str]) -> List[str]:
        """
        Предлагает коррекцию для неверных картриджей

        Args:
            printer_model: Модель принтера
            wrong_cartridges: Список неверных картриджей

        Returns:
            List[str]: Предложения по коррекции
        """
        correct_cartridges = self.get_cartridges_for_printer(printer_model)
        suggestions = []

        # Ищем похожие номера
        for wrong_cart in wrong_cartridges:
            for correct_cart in correct_cartridges:
                # Простая эвристика для поиска похожих номеров
                if self._is_similar_cartridge(wrong_cart, correct_cart.model):
                    suggestions.append(f"❌ {wrong_cart} → ✅ {correct_cart.model}")

        return suggestions

    def _is_similar_cartridge(self, wrong: str, correct: str) -> bool:
        """Проверяет похожесть номеров картриджей"""
        # Нормализуем
        wrong_clean = wrong.upper().replace('-', '').replace(' ', '')
        correct_clean = correct.upper().replace('-', '').replace(' ', '')

        # Проверяем вхождение одного в другой
        if wrong_clean in correct_clean or correct_clean in wrong_clean:
            return True

        # Проверяем похожесть по цифрам
        wrong_digits = ''.join(filter(str.isdigit, wrong))
        correct_digits = ''.join(filter(str.isdigit, correct))

        if wrong_digits and correct_digits and len(wrong_digits) >= 3:
            return wrong_digits in correct_digits or correct_digits in wrong_digits

        return False

# Глобальный экземпляр
enhanced_detector = EnhancedPrinterDetector()