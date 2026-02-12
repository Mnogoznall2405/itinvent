#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для поиска модели по названию во всех CI_TYPE
"""
import sys
import os
import pyodbc
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def search_model_all(search_term: str):
    """Ищет модель по подстроке во всех CI_TYPE"""
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

        print(f"Поиск модели: '{search_term}' (во всех CI_TYPE)")
        print("=" * 70)

        # Поиск с LIKE без фильтра по CI_TYPE
        cursor.execute("""
            SELECT MODEL_NO, CI_TYPE, MODEL_NAME
            FROM CI_MODELS
            WHERE MODEL_NAME LIKE ?
            ORDER BY CI_TYPE, MODEL_NAME
        """, (f"%{search_term}%",))

        rows = cursor.fetchall()

        if rows:
            print(f"{'MODEL_NO':<10} {'CI_TYPE':<10} {'MODEL_NAME'}")
            print("-" * 70)
            for row in rows:
                model_no = row[0] if row[0] is not None else "NULL"
                ci_type_val = row[1] if row[1] is not None else "NULL"
                model_name = row[2] if row[2] is not None else "NULL"
                print(f"{model_no:<10} {ci_type_val:<10} {model_name}")
            print(f"\nНайдено записей: {len(rows)}")
        else:
            print("Модели не найдены.")

        print()
        print("=" * 70)

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Поиск Xerox
    if len(sys.argv) > 1:
        search_model_all(sys.argv[1])
    else:
        # Ищем по умолчанию
        search_model_all("Xerox")
        print()
        search_model_all("Versalink")
        print()
        search_model_all("B405")
