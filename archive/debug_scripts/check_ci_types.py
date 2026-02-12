#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка таблицы CI_TYPES
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

    print("=== CI_TYPES таблица ===")
    cursor.execute("SELECT * FROM CI_TYPES")
    rows = cursor.fetchall()

    # Получаем имена колонок
    columns = [column[0] for column in cursor.description]
    print(f"{'CI_TYPE':<10} {'TYPE_NO':<10} {'TYPE_NAME'}")
    print("-" * 60)

    for row in rows:
        print(f"{str(row[0]):<10} {str(row[1]):<10} {row[2]}")

    print("\n=== Связь с ITEMS ===")
    cursor.execute("""
        SELECT i.CI_TYPE, t.TYPE_NAME, COUNT(*) as cnt
        FROM ITEMS i
        LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
        GROUP BY i.CI_TYPE, t.TYPE_NAME
        ORDER BY i.CI_TYPE
    """)
    rows = cursor.fetchall()
    for row in rows:
        print(f"CI_TYPE {row[0]}: {row[1]} - {row[2]} записей")

    conn.close()

except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()
