#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для отображения всех типов оборудования из базы данных
"""
import sys
import os
import pyodbc
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def show_all_types():
    """Показывает все типы оборудования из CI_TYPES"""
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

        print("=" * 60)
        print("ТИПЫ ОБОРУДОВАНИЯ (CI_TYPES)")
        print("=" * 60)
        print()

        # Получаем все типы
        cursor.execute("""
            SELECT TYPE_NO, CI_TYPE, TYPE_NAME
            FROM CI_TYPES
            ORDER BY CI_TYPE, TYPE_NO
        """)

        rows = cursor.fetchall()

        if rows:
            print(f"{'TYPE_NO':<10} {'CI_TYPE':<10} {'TYPE_NAME'}")
            print("-" * 60)
            for row in rows:
                type_no = row[0] if row[0] is not None else "NULL"
                ci_type = row[1] if row[1] is not None else "NULL"
                type_name = row[2] if row[2] is not None else "NULL"
                print(f"{type_no:<10} {ci_type:<10} {type_name}")
        else:
            print("Типы оборудования не найдены.")

        print()
        print("=" * 60)

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()


def show_all_models():
    """Показывает все модели оборудования из CI_MODELS"""
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

        print()
        print("=" * 80)
        print("МОДЕЛИ ОБОРУДОВАНИЯ (CI_MODELS) - первые 50")
        print("=" * 80)
        print()

        # Получаем модели
        cursor.execute("""
            SELECT TOP 50 MODEL_NO, CI_TYPE, MODEL_NAME
            FROM CI_MODELS
            ORDER BY MODEL_NAME
        """)

        rows = cursor.fetchall()

        if rows:
            print(f"{'MODEL_NO':<10} {'CI_TYPE':<10} {'MODEL_NAME'}")
            print("-" * 80)
            for row in rows:
                model_no = row[0] if row[0] is not None else "NULL"
                ci_type = row[1] if row[1] is not None else "NULL"
                model_name = row[2] if row[2] is not None else "NULL"
                print(f"{model_no:<10} {ci_type:<10} {model_name}")
        else:
            print("Модели оборудования не найдены.")

        print()
        print("=" * 80)

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()


def show_all_statuses():
    """Показывает все статусы из STATUS"""
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

        print()
        print("=" * 60)
        print("СТАТУСЫ (STATUS)")
        print("=" * 60)
        print()

        # Получаем статусы
        cursor.execute("""
            SELECT STATUS_NO, DESCR
            FROM STATUS
            ORDER BY STATUS_NO
        """)

        rows = cursor.fetchall()

        if rows:
            print(f"{'STATUS_NO':<15} {'DESCR'}")
            print("-" * 60)
            for row in rows:
                status_no = row[0] if row[0] is not None else "NULL"
                descr = row[1] if row[1] is not None else "NULL"
                print(f"{status_no:<15} {descr}")
        else:
            print("Статусы не найдены.")

        print()
        print("=" * 60)

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    show_all_types()
    show_all_models()
    show_all_statuses()
