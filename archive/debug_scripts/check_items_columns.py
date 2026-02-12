#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка структуры таблицы ITEMS - какие колонки NOT NULL
"""
import sys
import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

def check_items_structure():
    """Проверяет структуру таблицы ITEMS"""
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

        print("СТРУКТУРА ТАБЛИЦЫ ITEMS")
        print("=" * 80)

        # Получаем информацию о колонках
        cursor.execute("""
            SELECT
                COLUMN_NAME,
                IS_NULLABLE,
                DATA_TYPE,
                CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'ITEMS'
            ORDER BY ORDINAL_POSITION
        """)

        rows = cursor.fetchall()

        print(f"{'Column Name':<25} {'Nullable':<10} {'Type':<20}")
        print("-" * 80)

        not_null_columns = []
        for row in rows:
            col_name = row[0]
            is_nullable = row[1]
            data_type = row[2]
            max_len = row[3]

            type_str = data_type
            if max_len:
                type_str += f"({max_len})"

            nullable_str = "NULL" if is_nullable == "YES" else "NOT NULL"

            print(f"{col_name:<25} {nullable_str:<10} {type_str:<20}")

            if is_nullable == "NO":
                not_null_columns.append(col_name)

        print()
        print("=" * 80)
        print(f"NOT NULL колонки ({len(not_null_columns)}):")
        for col in not_null_columns:
            print(f"  - {col}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_items_structure()
