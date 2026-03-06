#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис для определения цветности принтера через LLM с кэшированием результатов
"""

import logging
from typing import Optional, Dict, Any
from openai import OpenAI

from bot.config import config
from bot.local_json_store import load_json_data, save_json_data

logger = logging.getLogger(__name__)

# Файл для кэширования результатов
PRINTER_CACHE_FILE = "data/printer_color_cache.json"


class PrinterColorDetector:
    """
    Класс для определения цветности принтера через LLM с кэшированием
    """
    
    def __init__(self):
        """Инициализация детектора"""
        self.cache = self._load_cache()
        
        # Инициализация клиента OpenRouter
        try:
            self.client = OpenAI(
                base_url=config.api.openrouter_base_url,
                api_key=config.api.openrouter_api_key
            )
        except Exception as e:
            logger.error(f"Ошибка инициализации OpenAI клиента: {e}")
            self.client = None
    
    def _load_cache(self) -> Dict[str, bool]:
        """Load printer color cache from local store."""
        try:
            cache_data = load_json_data(PRINTER_CACHE_FILE, default_content={})
            if isinstance(cache_data, dict):
                logger.info(f"Loaded printer cache entries: {len(cache_data)}")
                return cache_data
        except Exception as e:
            logger.error(f"Failed to load printer cache: {e}")

        return {}

    def _save_cache(self) -> None:
        """Persist printer color cache to local store."""
        try:
            save_json_data(PRINTER_CACHE_FILE, self.cache)
            logger.info(f"Saved printer cache entries: {len(self.cache)}")
        except Exception as e:
            logger.error(f"Failed to save printer cache: {e}")

    def _normalize_printer_model(self, model: str) -> str:
        """
        Нормализует название модели принтера для кэширования
        
        Параметры:
            model: Название модели принтера
            
        Возвращает:
            str: Нормализованное название
        """
        if not model:
            return ""
        
        # Приводим к нижнему регистру и убираем лишние пробелы
        normalized = ' '.join(model.strip().lower().split())
        
        # Убираем общие префиксы/суффиксы
        prefixes_to_remove = ['принтер', 'printer', 'мфу', 'mfp', 'мфп']
        for prefix in prefixes_to_remove:
            if normalized.startswith(prefix + ' '):
                normalized = normalized[len(prefix) + 1:]
            elif normalized.endswith(' ' + prefix):
                normalized = normalized[:-len(prefix) - 1]
        
        return normalized.strip()
    
    def _query_llm_for_color_support(self, printer_model: str) -> Optional[bool]:
        """
        Запрашивает у LLM информацию о цветности принтера
        
        Параметры:
            printer_model: Модель принтера
            
        Возвращает:
            bool: True если цветной, False если черно-белый, None при ошибке
        """
        if self.client is None:
            logger.error("OpenAI клиент не инициализирован")
            return None
        
        try:
            prompt = f"""Определи, является ли принтер "{printer_model}" цветным или черно-белым.

Отвечай ТОЛЬКО одним словом:
- "ДА" - если принтер цветной (поддерживает цветную печать)
- "НЕТ" - если принтер черно-белый (только монохромная печать)

Модель принтера: {printer_model}

Ответ:"""
            
            logger.info(f"Запрос к LLM для определения цветности принтера: {printer_model}")
            
            completion = self.client.chat.completions.create(
                model=config.api.ocr_model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=10,
                temperature=0.1
            )
            
            content = completion.choices[0].message.content.strip().upper()
            logger.info(f"LLM ответ для {printer_model}: '{content}'")
            
            # Парсим ответ
            if 'ДА' in content or 'YES' in content or 'ЦВЕТН' in content or 'COLOR' in content:
                return True
            elif 'НЕТ' in content or 'NO' in content or 'ЧЕРНО-БЕЛ' in content or 'МОНОХРОМ' in content or 'BLACK' in content:
                return False
            else:
                logger.warning(f"Неожиданный ответ LLM: {content}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при запросе к LLM: {e}")
            return None
    
    def is_color_printer(self, printer_model: str) -> Optional[bool]:
        """
        Определяет, является ли принтер цветным
        
        Параметры:
            printer_model: Модель принтера
            
        Возвращает:
            bool: True если цветной, False если черно-белый, None при ошибке
        """
        if not printer_model:
            logger.warning("Пустая модель принтера")
            return None
        
        # Нормализуем название модели
        normalized_model = self._normalize_printer_model(printer_model)
        if not normalized_model:
            logger.warning(f"Не удалось нормализовать модель: {printer_model}")
            return None
        
        # Проверяем кэш
        if normalized_model in self.cache:
            is_color = self.cache[normalized_model]
            logger.info(f"Найдено в кэше: {printer_model} -> {'цветной' if is_color else 'ч/б'}")
            return is_color
        
        # Запрашиваем у LLM
        logger.info(f"Запрос к LLM для нового принтера: {printer_model}")
        is_color = self._query_llm_for_color_support(printer_model)
        
        if is_color is not None:
            # Сохраняем в кэш
            self.cache[normalized_model] = is_color
            self._save_cache()
            logger.info(f"Определено и сохранено в кэш: {printer_model} -> {'цветной' if is_color else 'ч/б'}")
        else:
            logger.error(f"Не удалось определить цветность принтера: {printer_model}")
        
        return is_color
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику кэша
        
        Возвращает:
            Dict: Статистика кэша
        """
        color_count = sum(1 for is_color in self.cache.values() if is_color)
        bw_count = len(self.cache) - color_count
        
        return {
            'total_models': len(self.cache),
            'color_printers': color_count,
            'bw_printers': bw_count,
            'cache_file': PRINTER_CACHE_FILE
        }
    
    def clear_cache(self) -> None:
        """Очищает кэш"""
        self.cache.clear()
        self._save_cache()
        logger.info("Кэш принтеров очищен")


# Глобальный экземпляр детектора
printer_detector = PrinterColorDetector()


def is_color_printer(printer_model: str) -> Optional[bool]:
    """
    Удобная функция для определения цветности принтера
    
    Параметры:
        printer_model: Модель принтера
        
    Возвращает:
        bool: True если цветной, False если черно-белый, None при ошибке
    """
    return printer_detector.is_color_printer(printer_model)


def get_printer_cache_stats() -> Dict[str, Any]:
    """
    Возвращает статистику кэша принтеров
    
    Возвращает:
        Dict: Статистика кэша
    """
    return printer_detector.get_cache_stats()
