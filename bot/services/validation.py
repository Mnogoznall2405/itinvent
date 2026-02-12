#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Валидация пользовательских данных

Функции для проверки корректности вводимых данных.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def validate_serial_number(serial: str) -> bool:
    """
    Валидация серийного номера
    
    Параметры:
        serial: Серийный номер для проверки
        
    Возвращает:
        bool: True если серийный номер валиден
    """
    if not serial or not isinstance(serial, str):
        return False
    
    serial = serial.strip()
    
    # Проверка длины
    if len(serial) < 1 or len(serial) > 50:
        logger.warning(f"Серийный номер имеет некорректную длину: {len(serial)}")
        return False
    
    # Проверка допустимых символов (буквы, цифры, дефис, подчеркивание, точка, пробел, двоеточие)
    if not re.match(r'^[a-zA-Z0-9_\-\. :]+$', serial):
        logger.warning(f"Серийный номер содержит недопустимые символы: {serial}")
        return False
    
    return True


def validate_employee_name(name: str) -> bool:
    """
    Валидация ФИО сотрудника
    
    Параметры:
        name: ФИО сотрудника
        
    Возвращает:
        bool: True если ФИО валидно
    """
    if not name or not isinstance(name, str):
        return False
    
    name = name.strip()
    
    # Проверка длины
    if len(name) < 2 or len(name) > 100:
        logger.warning(f"ФИО имеет некорректную длину: {len(name)}")
        return False
    
    # Проверка на опасные символы
    dangerous_chars = ['<', '>', '"', "'", '&', ';', '|', '`', '\n', '\r']
    if any(char in name for char in dangerous_chars):
        logger.warning(f"ФИО содержит опасные символы: {name}")
        return False
    
    # Проверка на SQL ключевые слова
    sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'UNION', 'EXEC']
    name_upper = name.upper()
    if any(keyword in name_upper for keyword in sql_keywords):
        logger.warning(f"ФИО содержит SQL ключевые слова: {name}")
        return False
    
    return True


def validate_ip_address(ip: str) -> bool:
    """
    Валидация IP адреса
    
    Параметры:
        ip: IP адрес
        
    Возвращает:
        bool: True если IP адрес валиден
    """
    if not ip or not isinstance(ip, str):
        return False
    
    ip = ip.strip()
    
    # Проверка формата IPv4
    ipv4_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    if re.match(ipv4_pattern, ip):
        return True
    
    # Проверка формата IPv6 (упрощенная)
    ipv6_pattern = r'^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$'
    if re.match(ipv6_pattern, ip):
        return True
    
    logger.warning(f"IP адрес имеет некорректный формат: {ip}")
    return False


def validate_inventory_number(inv_num: str) -> bool:
    """
    Валидация инвентарного номера

    Параметры:
        inv_num: Инвентарный номер

    Возвращает:
        bool: True если инвентарный номер валиден
    """
    if not inv_num or not isinstance(inv_num, str):
        return False

    inv_num = inv_num.strip()

    # Проверка длины
    if len(inv_num) < 1 or len(inv_num) > 30:
        logger.warning(f"Инвентарный номер имеет некорректную длину: {len(inv_num)}")
        return False

    # Убрана проверка на символы - разрешаем кириллицу и любые символы
    # Проверяем только на опасные символы
    dangerous_chars = ['<', '>', '"', "'", '&', ';', '|', '`', '\n', '\r']
    if any(char in inv_num for char in dangerous_chars):
        logger.warning(f"Инвентарный номер содержит опасные символы: {inv_num}")
        return False

    return True


def sanitize_input(text: str, max_length: Optional[int] = None) -> str:
    """
    Очищает пользовательский ввод от опасных символов
    
    Параметры:
        text: Исходный текст
        max_length: Максимальная длина (опционально)
        
    Возвращает:
        str: Очищенный текст
    """
    if not text:
        return ""
    
    # Удаляем опасные символы
    text = text.strip()
    text = re.sub(r'[<>"\';|`]', '', text)
    
    # Ограничиваем длину
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    return text
