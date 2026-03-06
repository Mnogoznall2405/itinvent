#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Printer Component Detection Service

Определяет доступные компоненты для замены в принтерах и МФУ:
- Картриджи (черные/цветные)
- Фьюзеры (печки)
- Барабаны
- Прочие компоненты

Использует LLM для детекции и кэширует результаты в JSON.
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import re
from openai import OpenAI

from bot.config import config
from bot.local_json_store import load_json_data, save_json_data

logger = logging.getLogger(__name__)


class PrinterComponentDetector:
    """Сервис для определения компонентов принтера"""

    def __init__(self):
        # Инициализация клиента OpenRouter
        self.client = OpenAI(
            api_key=config.api.openrouter_api_key,
            base_url=config.api.openrouter_base_url
        )
        self.cache_file = "data/printer_component_cache.json"
        self.cartridge_db_file = "data/cartridge_database.json"
        self.cache = self._load_cache()
        self.cartridge_db = self._load_cartridge_db()
        self._migrate_old_cache()

    def _load_cartridge_db(self) -> Dict[str, Any]:
        """Загружает базу данных картриджей"""
        try:
            data = load_json_data(self.cartridge_db_file, default_content={})
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.error(f"Error loading cartridge database: {e}")

        return {}

    def _find_in_cartridge_db(self, printer_model: str) -> Optional[Dict[str, Any]]:
        """
        Ищет принтер в базе данных картриджей

        Args:
            printer_model: Модель принтера

        Returns:
            Dict с данными из cartridge_database.json или None
        """
        normalized_model = printer_model.lower().strip()

        # Пробуем точное совпадение
        if normalized_model in self.cartridge_db:
            logger.info(f"Found exact match in cartridge DB for {printer_model}")
            return self.cartridge_db[normalized_model]

        # Пробуем найти частичное совпадение
        for db_model, data in self.cartridge_db.items():
            if normalized_model in db_model or db_model in normalized_model:
                logger.info(f"Found partial match in cartridge DB: {printer_model} -> {db_model}")
                return data

        return None

    def _convert_from_cartridge_db(self, cartridge_data: Dict[str, Any], printer_model: str) -> Dict[str, Any]:
        """
        Конвертирует данные из cartridge_database.json в формат детектора

        Args:
            cartridge_data: Данные из cartridge_database.json
            printer_model: Модель принтера

        Returns:
            Dict в формате, который ожидает детектор
        """
        is_color = cartridge_data.get("is_color", False)
        components_list = cartridge_data.get("components", ["cartridge"])

        # Определяем какие компоненты доступны
        components = {}
        for comp in components_list:
            if comp == "cartridge":
                components["cartridge"] = True
            elif comp in ["fuser", "fuser_models"]:
                components["fuser"] = True
            elif comp in ["photoconductor", "photoconductor_models", "drum"]:
                components["photoconductor"] = True
            elif comp in ["waste_toner", "waste_toner_models"]:
                components["waste_toner"] = True
            elif comp in ["transfer_belt", "transfer_belt_models"]:
                components["transfer_belt"] = True

        # Формируем список доступных компонентов
        component_list = [comp for comp, available in components.items() if available]

        # Формируем данные о совместимых моделях для LLM-формата
        llm_components = {}
        if cartridge_data.get("compatible_models"):
            cartridge_models = [m["model"] for m in cartridge_data["compatible_models"]]
            llm_components["cartridge"] = {
                "available": True,
                "compatible_models": cartridge_models
            }
        if cartridge_data.get("fuser_models"):
            llm_components["fuser"] = {
                "available": True,
                "compatible_models": cartridge_data["fuser_models"]
            }
        if cartridge_data.get("photoconductor_models"):
            llm_components["photoconductor"] = {
                "available": True,
                "compatible_models": cartridge_data["photoconductor_models"]
            }
        if cartridge_data.get("waste_toner_models"):
            llm_components["waste_toner"] = {
                "available": True,
                "compatible_models": cartridge_data["waste_toner_models"]
            }
        if cartridge_data.get("transfer_belt_models"):
            llm_components["transfer_belt"] = {
                "available": True,
                "compatible_models": cartridge_data["transfer_belt_models"]
            }

        result = {
            "color": is_color,
            "components": components,
            "component_list": component_list,
            "confidence": 1.0,  # Максимальная уверенность для базы данных
            "determined_at": datetime.now().isoformat(),
            "from_db": True,
            "raw_llm_response": json.dumps({"components": llm_components})
        }

        logger.info(f"Converted from cartridge DB: {printer_model} -> color={is_color}, components={component_list}")
        return result

    def _load_cache(self) -> Dict[str, Any]:
        """Загружает кэш из файла"""
        try:
            data = load_json_data(self.cache_file, default_content={})
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.error(f"Error loading component cache: {e}")

        return {}

    def _save_cache(self):
        """Сохраняет кэш в файл"""
        try:
            save_json_data(self.cache_file, self.cache)
        except Exception as e:
            logger.error(f"Error saving component cache: {e}")

    def _migrate_old_cache(self):
        """Мигрирует старый кэш цветов в новый формат"""
        old_cache_file = "data/printer_color_cache.json"

        try:
            old_cache = load_json_data(old_cache_file, default_content={})
            if not isinstance(old_cache, dict) or not old_cache:
                return

            migrated = False
            for printer_name, old_data in old_cache.items():
                if printer_name not in self.cache:
                    # old_data может быть bool или dict
                    if isinstance(old_data, bool):
                        # Старый формат: просто True/False
                        is_color = old_data
                        model = "unknown"
                        determined_at = datetime.now().isoformat()
                    else:
                        # Новый формат dict
                        is_color = old_data.get("is_color_printer", False)
                        model = old_data.get("model", "unknown")
                        determined_at = old_data.get("determined_at", datetime.now().isoformat())

                    # Мигрируем старую запись в новый формат
                    self.cache[printer_name] = {
                        "color": is_color,
                        "components": {
                            "cartridge": True,  # По умолчанию есть картридж
                            "fuser": True,      # Будем определять через LLM
                            "photoconductor": True,  # Будем определять через LLM (было drum)
                            "waste_toner": False,
                            "transfer_belt": False
                        },
                        "determined_at": determined_at,
                        "confidence": 0.8,  # Средняя уверенность для мигрированных данных
                        "model": model
                    }
                    migrated = True

            if migrated:
                self._save_cache()
                logger.info(f"Migrated {len(old_cache)} entries from old color cache")

                # Резервное копирование старого файла

        except Exception as e:
            logger.error(f"Error migrating old cache: {e}")

    def _normalize_printer_name(self, printer_model: str) -> str:
        """Нормализует имя принтера для кэша"""
        # Приводим к нижнему регистру и убираем лишние пробелы
        normalized = printer_model.lower().strip()

        # Убираем артикли и предлоги
        words_to_remove = ['the ', 'a ', 'an ', 'hp ', 'canon ', 'xerox ', 'brother ']
        for word in words_to_remove:
            normalized = normalized.replace(word, '')

        # Заменяем множественные пробелы на один
        normalized = re.sub(r'\s+', ' ', normalized)

        return normalized.strip()

    def get_compatible_models(self, printer_model: str, component_type: str) -> List[str]:
        """
        Возвращает список совместимых моделей компонента для принтера

        Args:
            printer_model: Модель принтера
            component_type: Тип компонента (cartridge, fuser, drum)

        Returns:
            List[str]: Список совместимых моделей
        """
        # СНАЧАЛА проверяем базу данных картриджей
        cartridge_data = self._find_in_cartridge_db(printer_model)
        if cartridge_data:
            if component_type == "cartridge" or component_type == "cartridges":
                if cartridge_data.get("compatible_models"):
                    return [m["model"] for m in cartridge_data["compatible_models"]]
            elif component_type == "fuser" or component_type == "fuser_models":
                if cartridge_data.get("fuser_models"):
                    return cartridge_data["fuser_models"]
            elif component_type in ["drum", "photoconductor", "photoconductor_models"]:
                if cartridge_data.get("photoconductor_models"):
                    return cartridge_data["photoconductor_models"]

        normalized_name = self._normalize_printer_name(printer_model)

        # ПОТОМ проверяем кэш
        if normalized_name in self.cache:
            cached_data = self.cache[normalized_name]
            # Ищем совместимые модели в сырых данных LLM
            if "raw_llm_response" in cached_data:
                try:
                    llm_data = json.loads(cached_data["raw_llm_response"])
                    components = llm_data.get("components", {})
                    comp_data = components.get(component_type, {})
                    if isinstance(comp_data, dict) and "compatible_models" in comp_data:
                        return comp_data["compatible_models"]
                except (json.JSONDecodeError, KeyError):
                    pass

        # В КОНЦЕ если в кэше нет информации, делаем новый запрос
        try:
            components_data = self._detect_via_llm(printer_model)
            components = components_data.get("components", {})
            comp_data = components.get(component_type, {})

            if isinstance(comp_data, dict) and "compatible_models" in comp_data:
                return comp_data["compatible_models"]

        except Exception as e:
            logger.error(f"Error getting compatible models for {printer_model} {component_type}: {e}")

        # Возвращаем общие рекомендации если не удалось определить
        fallback_models = {
            'cartridge': ['Не определено'],
            'fuser': ['Не определено'],
            'drum': ['Не определено'],  # Для обратной совместимости
            'photoconductor': ['Не определено'],
            'waste_toner': ['Не определено'],
            'transfer_belt': ['Не определено']
        }
        return fallback_models.get(component_type, ['Не определено'])

    def detect_printer_components(self, printer_model: str) -> Dict[str, Any]:
        """
        Определяет доступные компоненты для принтера

        Args:
            printer_model: Модель принтера

        Returns:
            Dict с информацией о компонентах:
            {
                "color": bool,
                "components": {
                    "cartridge": bool,
                    "fuser": bool,
                    "drum": bool,
                    "waste_toner": bool,
                    "transfer_belt": bool
                },
                "component_list": ["cartridge", "fuser", ...],
                "confidence": float,
                "determined_at": str
            }
        """
        normalized_name = self._normalize_printer_name(printer_model)

        # СНАЧАЛА проверяем базу данных картриджей
        cartridge_data = self._find_in_cartridge_db(printer_model)
        if cartridge_data:
            logger.info(f"Using cartridge database for {printer_model}")
            return self._convert_from_cartridge_db(cartridge_data, printer_model)

        # ПОТОМ проверяем кэш
        if normalized_name in self.cache:
            cached_data = self.cache[normalized_name]
            logger.info(f"Found cached components for {printer_model}")
            return {
                "color": cached_data.get("color", False),
                "components": cached_data.get("components", {}),
                "component_list": [comp for comp, available in cached_data.get("components", {}).items() if available],
                "confidence": cached_data.get("confidence", 0.8),
                "determined_at": cached_data.get("determined_at"),
                "from_cache": True
            }

        # В КОНЦЕ используем LLM для детекции
        logger.info(f"Detecting components for {printer_model} via LLM")

        try:
            components_data = self._detect_via_llm(printer_model)

            # Сохраняем в кэш (включая сырой ответ LLM для будущих запросов)
            self.cache[normalized_name] = {
                "color": components_data["color"],
                "components": components_data["components"],
                "determined_at": datetime.now().isoformat(),
                "confidence": components_data.get("confidence", 0.9),
                "model": printer_model,
                "raw_llm_response": json.dumps(components_data)  # Сохраняем полный ответ
            }
            self._save_cache()

            return {
                "color": components_data["color"],
                "components": components_data["components"],
                "component_list": components_data["component_list"],
                "confidence": components_data.get("confidence", 0.9),
                "determined_at": datetime.now().isoformat(),
                "from_cache": False
            }

        except Exception as e:
            logger.error(f"Error detecting components for {printer_model}: {e}")

            # Возвращаем значения по умолчанию при ошибке
            default_components = {
                "cartridge": True,
                "fuser": True,
                "photoconductor": True,
                "waste_toner": False,
                "transfer_belt": False
            }

            return {
                "color": False,  # По умолчанию считаем черно-белым
                "components": default_components,
                "component_list": ["cartridge", "fuser", "photoconductor"],
                "confidence": 0.5,
                "determined_at": datetime.now().isoformat(),
                "from_cache": False,
                "error": str(e)
            }

    def _detect_via_llm(self, printer_model: str) -> Dict[str, Any]:
        """Использует LLM для определения компонентов принтера"""

        prompt = f"""Проанализируй принтер или МФУ "{printer_model}" и определи какие компоненты доступны для замены.

Отметь галочкой [✓] доступные компоненты:
- Картридж (черный/цветной) - всегда есть у лазерных принтеров
- Фьюзер (печка) - узел прогрева, есть у лазерных принтеров и МФУ
- Фотобарабан (фотоэлектрический барабан, OPC) - есть у лазерных принтеров и МФУ
- Устройство сбора отработанного тонера - есть у цветных лазерных принтеров
- Трансферный ремень - есть у цветных лазерных принтеров

Также определи является ли принтер цветным или черно-белым.

И УКАЖИ МОДЕЛИ СОВМЕСТИМЫХ КОМПЛЕКТУЮЩИХ:
- Для картриджей: используй форматы производителей (HP 05A, HP 88A, Xerox 106R02773, Canon CRG-041)
- Для фьюзеров: RM1-0045, RM1-6405, JC96, etc.
- Для фотобарабанов: DR421CL, DR420CL, etc.

Ответь в формате JSON:
{{
  "color": true/false,
  "components": {{
    "cartridge": {{
      "available": true/false,
      "compatible_models": ["модель1", "модель2"]
    }},
    "fuser": {{
      "available": true/false,
      "compatible_models": ["модель1", "модель2"]
    }},
    "photoconductor": {{
      "available": true/false,
      "compatible_models": ["модель1", "модель2"]
    }},
    "waste_toner": {{
      "available": true/false,
      "compatible_models": ["модель1", "модель2"]
    }},
    "transfer_belt": {{
      "available": true/false,
      "compatible_models": ["модель1", "модель2"]
    }}
  }},
  "component_list": ["cartridge", "fuser", "photoconductor"],
  "confidence": 0.0-1.0,
  "explanation": "краткое объяснение"
}}

Примеры:
HP LaserJet Pro M404n -> {{
  "color": false,
  "components": {{
    "cartridge": {{"available": true, "compatible_models": ["HP 05A", "HP 05X", "HP 05H"]}},
    "fuser": {{"available": true, "compatible_models": ["RM1-0045", "RM1-0046"]}},
    "photoconductor": {{"available": true, "compatible_models": ["DR420CL"]}}
  }},
  "component_list": ["cartridge", "fuser", "photoconductor"]
}}
Xerox Versalink C7020 -> {{
  "color": true,
  "components": {{
    "cartridge": {{"available": true, "compatible_models": ["Xerox 106R02773", "Xerox 106R02774", "Xerox 106R02775", "Xerox 106R02776"]}},
    "fuser": {{"available": true, "compatible_models": ["Xerox 115R00089"]}},
    "photoconductor": {{"available": true, "compatible_models": ["Xerox 115R00090"]}},
    "waste_toner": {{"available": true, "compatible_models": ["Xerox 115R00091"]}}
  }},
  "component_list": ["cartridge", "fuser", "photoconductor", "waste_toner"]
}}"""

        try:
            response = self.client.chat.completions.create(
                model=config.api.cartridge_analysis_model,  # Используем ту же модель
                messages=[
                    {"role": "system", "content": "Ты - эксперт по принтерам и оргтехнике. Отвечай только в формате JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )

            response = response.choices[0].message.content

            # Извлекаем JSON из ответа
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in LLM response")

            result = json.loads(json_match.group())

            # Валидация результата
            if not all(key in result for key in ["color", "components"]):
                raise ValueError("Invalid LLM response structure")

            # Преобразуем новую структуру в старую для обратной совместимости
            processed_components = {}
            component_list = []

            for comp_name, comp_data in result["components"].items():
                if comp_name in ["cartridge", "fuser", "drum", "photoconductor", "waste_toner", "transfer_belt"]:
                    # Обработка новой структуры с available/compatible_models
                    if isinstance(comp_data, dict) and "available" in comp_data:
                        processed_components[comp_name] = comp_data["available"]
                        if comp_data["available"]:
                            component_list.append(comp_name)
                    else:
                        # Обработка старой структуры (обратная совместимость)
                        processed_components[comp_name] = bool(comp_data)
                        if comp_data:
                            component_list.append(comp_name)

            # Обратная совместимость: если LLM вернул "drum", конвертируем в "photoconductor"
            if "drum" in processed_components:
                processed_components["photoconductor"] = processed_components["drum"]
                del processed_components["drum"]
                if "drum" in component_list:
                    component_list.remove("drum")
                    component_list.append("photoconductor")

            # Убедимся что картридж всегда доступен
            if not processed_components.get("cartridge", False):
                processed_components["cartridge"] = True
                if "cartridge" not in component_list:
                    component_list.insert(0, "cartridge")

            # Обновляем результат в формате, понятном остальному коду
            result["components"] = processed_components
            result["component_list"] = component_list

            return result

        except Exception as e:
            logger.error(f"LLM detection failed for {printer_model}: {e}")
            raise

    def is_color_printer(self, printer_model: str) -> bool:
        """
        Определяет является ли принтер цветным (обратная совместимость)

        Args:
            printer_model: Модель принтера

        Returns:
            bool: True если цветной
        """
        normalized_name = self._normalize_printer_name(printer_model)

        if normalized_name in self.cache:
            return self.cache[normalized_name].get("color", False)

        # Если нет в кэше, используем старую логику
        color_keywords = [
            'color', 'colour', 'mfp', 'mfc', '激光打印', '彩',
            ' Canon MF', 'Canon i-SENSYS MF', 'HP Color', 'Xerox WorkCentre'
        ]

        printer_lower = printer_model.lower()
        return any(keyword.lower() in printer_lower for keyword in color_keywords)

    def get_component_display_name(self, component_type: str) -> str:
        """Возвращает отображаемое имя компонента"""
        display_names = {
            "cartridge": "🖨️ Картридж",
            "fuser": "🔥 Фьюзер (печка)",
            "drum": "🥁 Барабан",  # Обратная совместимость
            "photoconductor": "🥁 Фотобарабан (OPC)",
            "waste_toner": "🗑️ Контейнер отработанного тонера",
            "transfer_belt": "📼 Трансферный ремень"
        }
        return display_names.get(component_type, f"🔧 {component_type}")

    def get_component_color_options(self, component_type: str) -> List[str]:
        """Возвращает доступные цвета для компонента"""
        if component_type == "cartridge":
            return ["Черный", "Синий", "Желтый", "Пурпурный"]
        else:
            # Для фьюзера, барабана и других компонентов цвет не важен
            return ["Универсальный"]

    def clear_cache(self):
        """Очищает кэш"""
        self.cache = {}
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)
        logger.info("Component cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Возвращает статистику кэша"""
        total_entries = len(self.cache)
        color_printers = sum(1 for entry in self.cache.values() if entry.get("color", False))

        component_stats = {}
        for entry in self.cache.values():
            components = entry.get("components", {})
            for comp, available in components.items():
                if comp not in component_stats:
                    component_stats[comp] = 0
                if available:
                    component_stats[comp] += 1

        return {
            "total_printers": total_entries,
            "color_printers": color_printers,
            "monochrome_printers": total_entries - color_printers,
            "component_availability": component_stats,
            "cache_file": self.cache_file,
            "file_exists": os.path.exists(self.cache_file)
        }


# Глобальный экземпляр для использования в обработчиках
component_detector = PrinterComponentDetector()
