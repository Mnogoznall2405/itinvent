#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Поиск таблицы с компаниями
"""
import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

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

    # Ищем таблицы с названиями похожими на компания
    print("=== Поиск таблиц с компаниями ===")
    cursor.execute("""
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
        AND (TABLE_NAME LIKE '%COMP%'
             OR TABLE_NAME LIKE '%FIRM%'
             OR TABLE_NAME LIKE '%ORG%'
             OR TABLE_NAME LIKE '%COMPANY%')
        ORDER BY TABLE_NAME
    """)
    rows = cursor.fetchall()

    for row in rows:
        print(f"  {row[0]}")

    # Проверяем каждую найденную таблицу
    for row in rows:
        table_name = row[0]
        print(f"\n=== {table_name} ===")

        # Получаем колонки
        cursor.execute(f"""
            SELECT TOP 5 COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{table_name}'
        """)
        cols = cursor.fetchall()
        for col in cols:
            print(f"  {col[0]} - {col[1]}")

        # Получаем данные
        try:
            cursor.execute(f"SELECT TOP 5 * FROM {table_name}")
            data_rows = cursor.fetchall()
            if data_rows:
                print(f"  Данные ({len(data_rows)} записей):")
                for dr in data_rows[:3]:
                    print(f"    {dr}")
        except Exception as e:
            print(f"  Ошибка чтения данных: {e}")

    # Также проверим в ITEMS - может есть внешний ключ на компанию
    print("\n\n=== Колонки в ITEMS связанные с компанией ===")
    cursor.execute("""
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'ITEMS'
        AND (COLUMN_NAME LIKE '%COMP%'
             OR COLUMN_NAME LIKE '%FIRM%'
             OR COLUMN_NAME LIKE '%ORG%')
    """)
    rows = cursor.fetchall()
    for row in rows:
        print(f"  {row[0]} - {row[1]}")

    conn.close()

except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()
