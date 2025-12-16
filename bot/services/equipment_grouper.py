#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис группировки оборудования по сотрудникам для создания множественных актов
"""
import logging
import re
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def group_equipment_by_employee(serials_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Группирует оборудование по текущим владельцам (старым сотрудникам)
    
    Параметры:
        serials_data: Список данных об оборудовании с полями:
            - serial: серийный номер
            - current_employee: текущий владелец
            - equipment: данные из БД
    
    Возвращает:
        Dict[str, List[Dict]]: Словарь {employee_name: [equipment_list]}
        
    Пример:
        {
            "Иванов Иван Иванович": [
                {"serial": "ABC123", "current_employee": "Иванов Иван Иванович", ...},
                {"serial": "DEF456", "current_employee": "Иванов Иван Иванович", ...}
            ],
            "Петров Петр Петрович": [
                {"serial": "GHI789", "current_employee": "Петров Петр Петрович", ...}
            ]
        }
    """
    logger.info(f"Начало группировки оборудования: {len(serials_data)} единиц")
    
    grouped = {}
    
    for item in serials_data:
        # Получаем текущего владельца
        current_employee = item.get('current_employee', '').strip()
        
        # Нормализация: если пустое или "Не указан", группируем как "Без владельца"
        if not current_employee or current_employee.lower() in ['не указан', 'не указано', '']:
            employee_key = 'Без владельца'
        else:
            employee_key = current_employee
        
        # Добавляем в группу
        if employee_key not in grouped:
            grouped[employee_key] = []
        
        grouped[employee_key].append(item)
    
    # Логируем результаты группировки
    logger.info(f"Группировка завершена: {len(grouped)} групп")
    for employee, items in grouped.items():
        logger.info(f"  - {employee}: {len(items)} единиц")
    
    return grouped


def sanitize_filename(name: str) -> str:
    """
    Очищает имя для использования в имени файла
    
    Выполняет транслитерацию кириллицы в латиницу, удаляет опасные символы,
    заменяет пробелы и дефисы на подчеркивания, ограничивает длину.
    
    Параметры:
        name: Исходное имя (может содержать кириллицу, пробелы)
    
    Возвращает:
        str: Безопасное имя файла (транслитерация, без пробелов)
        
    Примеры:
        >>> sanitize_filename("Иванов Иван Иванович")
        'Ivanov_Ivan_Ivanovich'
        >>> sanitize_filename("Без владельца")
        'Bez_vladelca'
        >>> sanitize_filename("Test User")
        'Test_User'
    """
    if not name:
        return "Unknown"
    
    try:
        # Импортируем библиотеку транслитерации
        from transliterate import translit
        
        # Транслитерация кириллицы в латиницу
        try:
            transliterated = translit(name, 'ru', reversed=True)
        except Exception as e:
            logger.warning(f"Ошибка транслитерации '{name}': {e}. Используем исходное имя.")
            transliterated = name
    except ImportError:
        logger.warning("Библиотека transliterate не установлена. Транслитерация недоступна.")
        # Если библиотека не установлена, используем простую замену
        transliterated = name
        # Простая замена кириллических символов
        cyrillic_to_latin = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
            'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
            'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
            'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
            'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
            'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
        }
        for cyr, lat in cyrillic_to_latin.items():
            transliterated = transliterated.replace(cyr, lat)
    
    # Удаляем опасные символы (защита от path traversal)
    # Оставляем только буквы, цифры, пробелы, дефисы и подчеркивания
    safe_name = re.sub(r'[^\w\s-]', '', transliterated)
    
    # Заменяем пробелы и дефисы на подчеркивания
    safe_name = re.sub(r'[-\s]+', '_', safe_name)
    
    # Удаляем множественные подчеркивания
    safe_name = re.sub(r'_+', '_', safe_name)
    
    # Удаляем подчеркивания в начале и конце
    safe_name = safe_name.strip('_')
    
    # Ограничиваем длину имени файла (50 символов)
    max_length = 50
    if len(safe_name) > max_length:
        safe_name = safe_name[:max_length].rstrip('_')
    
    # Если после всех операций имя пустое, возвращаем дефолтное
    if not safe_name:
        safe_name = "Unknown"
    
    logger.debug(f"Sanitized filename: '{name}' -> '{safe_name}'")
    
    return safe_name
