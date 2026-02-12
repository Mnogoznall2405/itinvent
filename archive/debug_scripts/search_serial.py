#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import json
import pyodbc
from datetime import datetime, date, time
from decimal import Decimal
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

# Устанавливаем кодировку вывода
if sys.platform == 'win32':
    os.system('chcp 65001 > nul')

def json_serialize(obj):
    """Сериализация для JSON"""
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, bytes):
        return f"<bytes {len(obj)}>"
    return str(obj)

# Прямое подключение к базе данных
conn_str = (
    f"DRIVER={{SQL Server}};"
    f"SERVER={os.getenv('SQL_SERVER_HOST')};"
    f"DATABASE={os.getenv('SQL_SERVER_DATABASE')};"
    f"UID={os.getenv('SQL_SERVER_USERNAME')};"
    f"PWD={os.getenv('SQL_SERVER_PASSWORD')}"
)

try:
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    # Полный запрос с JOIN ко всем справочным таблицам
    query = """
    SELECT
        -- Все поля из ITEMS
        i.*,
        -- Поля из справочников
        t.TYPE_NAME,
        m.MODEL_NAME,
        v.VENDOR_NAME as MANUFACTURER,
        l.DESCR as LOCATION_DESCR,
        o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
        o.OWNER_DEPT as EMPLOYEE_DEPT,
        b.BRANCH_NAME,
        s.DESCR as STATUS_DESCR
    FROM ITEMS i
    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
    WHERE i.SERIAL_NO = ?
    """

    cursor.execute(query, '5B1324T01711')

    # Получаем имена колонок из cursor.description
    columns = [desc[0] for desc in cursor.description]

    row = cursor.fetchone()
    if row:
        print('=== Все поля с JOIN к справочным таблицам ===\n')
        result = {}
        for i, col in enumerate(columns):
            value = row[i]
            # Преобразуем типы для JSON
            if value is None:
                result[col] = None
            else:
                result[col] = value

        # Сериализуем вручную для datetime и других типов
        print(json.dumps(result, ensure_ascii=False, indent=2, default=json_serialize))
        print(f"\nВсего полей: {len(result)}")
    else:
        print('Оборудование не найдено')

    cursor.close()
    conn.close()

except Exception as e:
    print(f"Ошибка: {e}")
