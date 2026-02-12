#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка оборудования по серийному номеру
"""
import sys
import os
import pyodbc
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def check_by_serial(serial: str):
    """Ищет оборудование по серийному номеру"""
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

        print("=" * 80)
        print(f"ПОИСК ОБОРУДОВАНИЯ ПО СЕРИЙНОМУ НОМЕРУ: {serial}")
        print("=" * 80)
        print()

        # Поиск по серийному номеру
        cursor.execute("""
            SELECT
                i.ID, i.SERIAL_NO, i.INV_NO, i.TYPE_NO, i.MODEL_NO,
                i.EMPL_NO, i.BRANCH_NO, i.LOC_NO, i.STATUS_NO,
                t.TYPE_NAME, m.MODEL_NAME, o.OWNER_DISPLAY_NAME,
                b.BRANCH_NAME, l.DESCR as LOCATION, s.DESCR as STATUS,
                i.CREATE_DATE, i.CH_DATE, i.CH_USER
            FROM ITEMS i
            LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
            LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
            LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
            LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
            LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
            LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
            WHERE i.SERIAL_NO = ?
        """, (serial,))

        row = cursor.fetchone()

        if row:
            print(f"✅ ОБОРУДОВАНИЕ НАЙДЕНО:")
            print(f"  ID: {row[0]}")
            print(f"  SERIAL_NO: {row[1]}")
            print(f"  INV_NO: {row[2]}")
            print(f"  TYPE_NO: {row[3]} -> {row[9]}")
            print(f"  MODEL_NO: {row[4]} -> {row[10]}")
            print(f"  EMPL_NO: {row[5]} -> {row[11]}")
            print(f"  BRANCH_NO: {row[6]} -> {row[12]}")
            print(f"  LOC_NO: {row[7]} -> {row[13]}")
            print(f"  STATUS_NO: {row[8]} -> {row[14]}")
            print(f"  CREATE_DATE: {row[15]}")
            print(f"  CH_DATE: {row[16]}")
            print(f"  CH_USER: {row[17]}")
        else:
            print(f"❌ Оборудование с серийным номером '{serial}' НЕ НАЙДЕНО")

        print()
        print("=" * 80)

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Проверяем ID 1593 из логов
    if len(sys.argv) > 1:
        check_by_serial(sys.argv[1])
    else:
        # Проверяем тестовый серийный номер
        check_by_serial("Gjsi57")
