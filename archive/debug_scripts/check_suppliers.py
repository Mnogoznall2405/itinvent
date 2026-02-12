#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка таблицы поставщиков
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

    print("=== ПОСТАВЩИКИ ===")
    cursor.execute("SELECT TOP 20 SUPPL_NO, SUPPL_NAME FROM SUPPLIERS ORDER BY SUPPL_NO")
    rows = cursor.fetchall()

    if rows:
        for row in rows:
            print(f"SUPPL_NO: {row[0]} - {row[1]}")

        # Ищем Запсибгазпром
        cursor.execute("SELECT SUPPL_NO, SUPPL_NAME FROM SUPPLIERS WHERE SUPPL_NAME LIKE '%Запсиб%'")
        row = cursor.fetchone()
        if row:
            print(f"\nНайден Запсибгазпром: SUPPL_NO={row[0]}, NAME={row[1]}")
        else:
            print("\nЗапсибгазпром не найден")
    else:
        print("Таблица SUPPLIERS пуста")

    # Проверяем существующую запись с ITEMS
    cursor.execute("SELECT TOP 5 ID, SERIAL_NO, SUPPL_NO FROM ITEMS WHERE SUPPL_NO IS NOT NULL")
    rows = cursor.fetchall()
    print(f"\n=== ОБОРУДОВАНИЕ С SUPPL_NO ({len(rows)} записей) ===")
    for row in rows:
        print(f"ID: {row[0]}, SERIAL: {row[1]}, SUPPL_NO: {row[2]}")

    conn.close()

except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()
