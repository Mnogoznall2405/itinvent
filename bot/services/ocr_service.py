#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR сервис для распознавания текста с изображений

Использует OpenRouter API для анализа изображений и извлечения серийных номеров.
"""

import base64
import logging
import re
from typing import Optional
from openai import OpenAI

from bot.config import config

logger = logging.getLogger(__name__)

# Инициализация клиента OpenRouter
try:
    client = OpenAI(
        base_url=config.api.openrouter_base_url,
        api_key=config.api.openrouter_api_key
    )
except Exception as e:
    logger.error(f"Ошибка инициализации OpenAI клиента: {e}")
    client = None


async def analyze_image(file_path: str) -> str:
    """
    Анализирует изображение для извлечения серийного номера
    
    Параметры:
        file_path: Путь к файлу изображения
        
    Возвращает:
        str: Текстовый ответ от AI модели
    """
    if client is None:
        return "OpenAI клиент не инициализирован. Проверьте настройки API."
    
    try:
        # Читаем и кодируем изображение в base64
        with open(file_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Оптимизированный промпт (короткий и эффективный)
        prompt = """Find the SERIAL NUMBER on this device image.

Look for labels: "Serial Number", "S/N", "SN", "Service Tag", or "Серийный номер"

Serial numbers are typically:
- 8-15 characters long
- Mix of letters and numbers
- Examples: ABCD1234, CN-04YMDT-FCC00-97Q-ATLB-A05, 9B2032AC0520

NOT serial numbers:
- Model names (short, like BV650I-GR, M404dn)
- MAC addresses (XX:XX:XX:XX:XX:XX)
- Part numbers (P/N)

IMPORTANT:
- If serial number is on multiple lines, combine them without spaces
- Keep exact case and all symbols (dashes, spaces)
- Choose the longer number if multiple options

Answer format:
Серийный номер: [EXACT_SERIAL_NUMBER]

If not found:
Серийный номер: НЕ НАЙДЕН"""
        
        # Отправляем запрос к AI модели с увеличенным max_tokens
        completion = client.chat.completions.create(
            model=config.api.ocr_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=150,  # Увеличено для более детального анализа
            temperature=0.1  # Низкая температура для точности
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка при вызове OCR API: {e}")
        return "Не удалось обработать изображение из-за ошибки API."


def validate_serial_format(serial: str) -> bool:
    """
    Проверяет, похож ли номер на серийный номер
    
    Параметры:
        serial: Строка для проверки
        
    Возвращает:
        bool: True если похож на серийный номер
    """
    if not serial or len(serial) < 5:
        return False
    
    # Проверка максимальной длины (Dell Service Tag может быть до 35 символов)
    if len(serial) > 40:
        logger.info(f"Отклонено: слишком длинный (>{40}): {serial}")
        return False
    
    # Проверка на MAC-адрес (XX:XX:XX:XX:XX:XX или XX-XX-XX-XX-XX-XX)
    if re.match(r'^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$', serial):
        logger.info(f"Отклонено как MAC-адрес: {serial}")
        return False
    
    # Проверка на IMEI (15 цифр подряд)
    if re.match(r'^\d{15}$', serial):
        logger.info(f"Отклонено как IMEI: {serial}")
        return False
    
    # Проверка на штрих-код (только цифры, очень длинный)
    if re.match(r'^\d{13,}$', serial):
        logger.info(f"Отклонено как штрих-код: {serial}")
        return False
    
    # Серийный номер должен содержать хотя бы одну букву И одну цифру
    has_letter = bool(re.search(r'[A-Za-z]', serial))
    has_digit = bool(re.search(r'\d', serial))
    
    if not (has_letter and has_digit):
        # Исключение: некоторые серийные номера могут быть только буквами или только цифрами
        # но тогда они должны быть достаточно длинными (8+ символов для букв, 10+ для цифр)
        if not has_letter and len(serial) < 10:
            # Только цифры - должно быть минимум 10 символов
            logger.info(f"Отклонено: только цифры и слишком короткий: {serial}")
            return False
        if not has_digit and len(serial) < 8:
            # Только буквы - должно быть минимум 8 символов
            logger.info(f"Отклонено: только буквы и слишком короткий: {serial}")
            return False
    
    # Серийные номера обычно длиннее 6 символов
    # Очень короткие номера (менее 6 символов) часто являются моделями или кодами
    if len(serial) < 6:
        logger.info(f"Отклонено: слишком короткий для серийного номера (возможно модель): {serial}")
        return False
    
    # Проверка на подозрительные паттерны
    suspicious_patterns = [
        r'^INV[-\s]?\d+',  # Инвентарный номер
        r'^PN[-\s]?',      # Part Number
        r'^P/N[-\s]?',     # Part Number
        r'^MODEL[-\s]?',   # Model
        r'^[A-Z]{2}\d{3,4}[A-Z]{0,2}[-]?[A-Z]{1,3}$',  # Типичные модели: BV650I-GR, M404dn, G3411
    ]
    
    for pattern in suspicious_patterns:
        if re.match(pattern, serial, re.IGNORECASE):
            logger.info(f"Отклонено по подозрительному паттерну (возможно модель): {serial}")
            return False
    
    return True


def generate_serial_variants(serial: str) -> list[str]:
    """
    Генерирует варианты серийного номера с заменой O↔0
    
    LLM иногда путает букву O с цифрой 0 и наоборот.
    Эта функция создает все возможные варианты замены.
    
    Параметры:
        serial: Исходный серийный номер
        
    Возвращает:
        list[str]: Список вариантов серийного номера (включая оригинал)
        
    Примеры:
        "PC0U" -> ["PC0U", "PCOU", "PC0U", "PCOU"]
        "O123" -> ["O123", "0123"]
    """
    if not serial:
        return []
    
    variants = set()
    variants.add(serial)  # Добавляем оригинал
    
    # Вариант 1: Все O → 0
    variant_o_to_0 = serial.replace('O', '0').replace('o', '0')
    if variant_o_to_0 != serial:
        variants.add(variant_o_to_0)
        logger.debug(f"Вариант O→0: {variant_o_to_0}")
    
    # Вариант 2: Все 0 → O
    variant_0_to_o = serial.replace('0', 'O')
    if variant_0_to_o != serial:
        variants.add(variant_0_to_o)
        logger.debug(f"Вариант 0→O: {variant_0_to_o}")
    
    # Вариант 3: Смешанный (если есть и O и 0)
    if 'O' in serial.upper() and '0' in serial:
        # Заменяем O на 0, но оставляем существующие 0 как O
        mixed = serial.replace('O', '0').replace('o', '0')
        # Теперь заменяем первоначальные 0 на O (это сложно, пропускаем)
        # Этот вариант уже покрыт предыдущими заменами
        pass
    
    result = list(variants)
    logger.info(f"Сгенерировано {len(result)} вариантов для '{serial}': {result}")
    return result


def extract_serial_number(text: str) -> Optional[str]:
    """
    Извлекает серийный номер из текстового ответа AI модели
    
    Параметры:
        text: Текстовый ответ от AI модели
        
    Возвращает:
        Optional[str]: Найденный серийный номер или None
    """
    if not text:
        return None
    
    logger.info(f"Анализируем текст для извлечения серийного номера: {text}")
    
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if 'Серийный номер:' in line or 'Serial Number:' in line or 'S/N:' in line:
            if ':' in line:
                serial_part = line.split(':', 1)[1].strip()
                
                # Удаляем возможные кавычки или скобки
                serial_part = serial_part.strip('"\'[](){}')
                
                # Отбрасываем служебные ответы
                lower_val = serial_part.lower()
                not_found_markers = {
                    'не найден', 'не найдено', 'не указано', 'unknown',
                    'not found', 'n/a', 'нет', 'отсутствует', 'none'
                }
                if lower_val in not_found_markers:
                    logger.info("Модель сообщила, что серийный номер не найден")
                    return None
                
                # Проверка минимальной длины
                if not serial_part or len(serial_part) < 5:
                    logger.warning(f"Серийный номер слишком короткий: {serial_part}")
                    continue
                
                # Проверка максимальной длины (серийные номера обычно не длиннее 40 символов)
                # Dell Service Tag может быть до 35 символов
                if len(serial_part) > 40:
                    logger.warning(f"Серийный номер слишком длинный: {serial_part}")
                    continue
                
                # Валидация формата
                if not validate_serial_format(serial_part):
                    logger.warning(f"Серийный номер не прошел валидацию формата: {serial_part}")
                    continue
                
                logger.info(f"✅ Найден и валидирован серийный номер: {serial_part}")
                return serial_part
    
    logger.warning("Серийный номер не найден в тексте")
    return None


async def analyze_image_detailed(file_path: str) -> str:
    """
    Детальный анализ изображения с запросом всех видимых номеров
    Используется как fallback при неудаче основного метода
    
    Параметры:
        file_path: Путь к файлу изображения
        
    Возвращает:
        str: Текстовый ответ от AI модели
    """
    if client is None:
        return "OpenAI клиент не инициализирован. Проверьте настройки API."
    
    try:
        with open(file_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Альтернативный промпт для детального анализа
        prompt = """Проанализируй изображение и найди ВСЕ номера, которые видны на устройстве.

Для каждого номера укажи:
1. Сам номер (точная копия)
2. Метку рядом с ним (если есть)
3. Длину номера
4. Тип (модель, серийный номер, или другое)

Формат ответа:
Номер 1: [номер] - Метка: [метка] - Длина: [X] - Тип: [тип]
Номер 2: [номер] - Метка: [метка] - Длина: [X] - Тип: [тип]
...

ВАЖНО: Различай модель и серийный номер!
- Модель: короткая (5-10 символов), описывает тип устройства
- Серийный номер: длинный (8-15+ символов), уникальный для каждого устройства
- Серийный номер может быть разбит на несколько строк - объедини их!

Затем укажи ТОЛЬКО серийный номер (не модель!), объединив все части если он многострочный:
Серийный номер: [выбранный номер]

Если серийных номеров нет:
Серийный номер: НЕ НАЙДЕН"""
        
        completion = client.chat.completions.create(
            model=config.api.ocr_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=300,
            temperature=0.2
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка при детальном анализе: {e}")
        return "Ошибка анализа"


async def extract_serial_from_image(file_path: str, retry_on_failure: bool = True) -> Optional[str]:
    """
    Унифицированная функция: анализ изображения -> извлечение серийного номера
    
    Параметры:
        file_path: Путь к файлу изображения
        retry_on_failure: Повторить с детальным анализом при неудаче
        
    Возвращает:
        Optional[str]: Серийный номер или None
    """
    try:
        # Первая попытка: стандартный анализ
        logger.info("Попытка 1: Стандартный анализ изображения")
        text = await analyze_image(file_path)
        serial = extract_serial_number(text)
        
        if serial:
            logger.info(f"✅ Серийный номер найден с первой попытки: {serial}")
            return serial
        
        # Вторая попытка: детальный анализ
        if retry_on_failure:
            logger.info("Попытка 2: Детальный анализ изображения")
            text_detailed = await analyze_image_detailed(file_path)
            serial = extract_serial_number(text_detailed)
            
            if serial:
                logger.info(f"✅ Серийный номер найден со второй попытки: {serial}")
                return serial
            else:
                logger.warning("❌ Серийный номер не найден после двух попыток")
        
        return None
        
    except Exception as e:
        logger.error(f"Ошибка извлечения серийного номера из изображения: {e}")
        return None


def extract_model(text: str) -> Optional[str]:
    """
    Извлекает модель устройства из текстового ответа AI модели
    
    Параметры:
        text: Текстовый ответ от AI модели
        
    Возвращает:
        Optional[str]: Найденная модель или None
    """
    if not text:
        return None
    
    logger.info(f"Анализируем текст для извлечения модели: {text}")
    
    # Паттерны для поиска модели
    patterns = [
        r"Модель\s*[:\-]?\s*([A-Za-z0-9\s\-_/\.\(\)]+)",
        r"Model\s*[:\-]?\s*([A-Za-z0-9\s\-_/\.\(\)]+)",
    ]
    
    for i, pattern in enumerate(patterns):
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            for match in matches:
                model = match.strip()
                # Фильтруем служебные слова
                if model and model.lower() not in ['не найдено', 'не указано', 'unknown', 'not found', 'н/д', 'нет']:
                    logger.info(f"Найдена модель по паттерну {i+1}: {model}")
                    return model
    
    logger.warning("Модель не найдена в тексте")
    return None


def clean_serial_number(serial: str) -> str:
    """
    Очищает серийный номер от типовых префиксов
    
    Параметры:
        serial: Сырой серийный номер
        
    Возвращает:
        str: Очищенный серийный номер
    """
    if not serial:
        return ""
    
    # Удаляем типовые префиксы
    prefix_pattern = re.compile(
        r'^\s*(?:serial\s*number|serial\s*no\.?|serial\s*#|s/?n|sn|service\s*tag|серийный\s*номер|серийный)\s*[:#\-]?\s*',
        re.IGNORECASE
    )
    
    cleaned = prefix_pattern.sub('', serial)
    return cleaned.strip()



def get_serial_confidence_score(serial: str) -> float:
    """
    Оценивает уверенность в том, что это серийный номер (0.0 - 1.0)
    
    Параметры:
        serial: Серийный номер для оценки
        
    Возвращает:
        float: Оценка уверенности от 0.0 до 1.0
    """
    if not serial:
        return 0.0
    
    score = 0.5  # Базовая оценка
    
    # Длина в оптимальном диапазоне (7-15 символов)
    if 7 <= len(serial) <= 15:
        score += 0.2
    elif 5 <= len(serial) <= 20:
        score += 0.1
    
    # Содержит буквы и цифры
    has_letter = bool(re.search(r'[A-Za-z]', serial))
    has_digit = bool(re.search(r'\d', serial))
    if has_letter and has_digit:
        score += 0.2
    
    # Содержит заглавные буквы (типично для серийных номеров)
    if re.search(r'[A-Z]', serial):
        score += 0.1
    
    # Не содержит пробелов (большинство серийных номеров без пробелов)
    if ' ' not in serial:
        score += 0.1
    
    # Содержит дефисы (типично для некоторых производителей)
    if '-' in serial:
        score += 0.05
    
    # Штрафы
    # Слишком много специальных символов
    special_chars = len(re.findall(r'[^A-Za-z0-9\-]', serial))
    if special_chars > 2:
        score -= 0.1
    
    # Слишком длинный
    if len(serial) > 20:
        score -= 0.2
    
    # Слишком короткий
    if len(serial) < 5:
        score -= 0.3
    
    return max(0.0, min(1.0, score))


async def analyze_image_with_confidence(file_path: str) -> tuple[Optional[str], float]:
    """
    Анализирует изображение и возвращает серийный номер с оценкой уверенности
    
    Параметры:
        file_path: Путь к файлу изображения
        
    Возвращает:
        tuple: (серийный_номер, оценка_уверенности)
    """
    serial = await extract_serial_from_image(file_path)
    
    if serial:
        confidence = get_serial_confidence_score(serial)
        logger.info(f"Серийный номер: {serial}, уверенность: {confidence:.2f}")
        return serial, confidence
    
    return None, 0.0
