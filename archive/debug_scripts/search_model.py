#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для поиска модели по названию
"""
import sys
import os
import pyodbc
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def search_model(search_term: str, ci_type: int = 2):
    """Ищет модель по подстроке"""
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

        print(f"Поиск модели: '{search_term}'")
        print("=" * 60)

        # Поиск с LIKE
        cursor.execute("""
            SELECT MODEL_NO, CI_TYPE, MODEL_NAME
            FROM CI_MODELS
            WHERE CI_TYPE = ? AND MODEL_NAME LIKE ?
            ORDER BY MODEL_NAME
        """, (ci_type, f"%{search_term}%"))

        rows = cursor.fetchall()

        if rows:
            print(f"{'MODEL_NO':<10} {'CI_TYPE':<10} {'MODEL_NAME'}")
            print("-" * 60)
            for row in rows:
                model_no = row[0] if row[0] is not None else "NULL"
                ci_type_val = row[1] if row[1] is not None else "NULL"
                model_name = row[2] if row[2] is not None else "NULL"
                print(f"{model_no:<10} {ci_type_val:<10} {model_name}")
        else:
            print("Модели не найдены.")

        print()
        print("=" * 60)

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Поиск Xerox
    if len(sys.argv) > 1:
        search_model(sys.argv[1])
    else:
        # Ищем Xerox по умолчанию
        search_model("Xerox")
        print()
        search_model("Versalink")
        print()
        search_model("B405")
