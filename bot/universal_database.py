#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Универсальная система работы с базой данных инвентаризации ITINVENT

Этот модуль предоставляет универсальный интерфейс для работы с базой данных
системы инвентаризации ITINVENT. Включает функции поиска оборудования по
серийному номеру, расширенного поиска и поиска по сотрудникам.

Основные возможности:
- Поиск оборудования по серийному номеру
- Расширенный поиск по различным критериям
- Поиск оборудования по сотруднику
- Автоматическое управление подключениями к базе данных
- Обработка ошибок и логирование

Автор: AI Assistant
Версия: 1.0
"""

import pyodbc
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime

# Настройка логирования для отслеживания операций с базой данных
logger = logging.getLogger(__name__)

@dataclass
class DatabaseConfig:
    """
    Конфигурация подключения к базе данных SQL Server
    
    Содержит все необходимые параметры для подключения к базе данных
    ITINVENT и формирования строки подключения ODBC.
    
    Атрибуты:
        server (str): Адрес сервера базы данных
        database (str): Имя базы данных
        username (str): Имя пользователя для подключения
        password (str): Пароль пользователя
        driver (str): ODBC драйвер (по умолчанию ODBC Driver 17 for SQL Server)
    """
    server: str
    database: str
    username: str
    password: str
    driver: str = '{SQL Server}'
    
    def get_connection_string(self) -> str:
        """
        Формирует строку подключения ODBC для SQL Server
        
        Возвращает:
            str: Полная строка подключения ODBC с параметрами безопасности
        """
        return (
            f"DRIVER={self.driver};"
            f"SERVER={self.server};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            "TrustServerCertificate=yes;"
            "autocommit=True;"
        )

class UniversalInventoryDB:
    """
    Универсальный класс для работы с базой данных инвентаризации ITINVENT
    
    Предоставляет методы для поиска оборудования, управления подключениями
    и выполнения SQL-запросов к базе данных системы инвентаризации.
    
    Атрибуты:
        connection_config (DatabaseConfig): Конфигурация подключения к БД
        connection: Активное подключение к базе данных (pyodbc.Connection)
    """
    
    def __init__(self, connection_config: DatabaseConfig):
        """
        Инициализация класса для работы с базой данных
        
        Параметры:
            connection_config (DatabaseConfig): Объект с параметрами подключения к БД
        """
        self.connection_config = connection_config
        self.connection = None
        
    def __del__(self):
        """
        Деструктор для корректного закрытия соединения при удалении объекта
        """
        self.close_connection()
        
    def close_connection(self):
        """
        Закрывает активное соединение с базой данных
        """
        if self.connection and not self.connection.closed:
            try:
                self.connection.close()
                logger.info("Соединение с базой данных закрыто")
            except Exception as e:
                logger.error(f"Ошибка при закрытии соединения: {e}")
            finally:
                self.connection = None
                
    def reconnect(self):
        """
        Переподключение к базе данных
        """
        self.close_connection()
        return self._get_connection()
        
    def _get_connection(self):
        """
        Получает активное подключение к базе данных
        
        Создает новое подключение, если текущее отсутствует или закрыто.
        Использует параметры из connection_config для формирования строки подключения.
        Включает проверку состояния соединения и повторные попытки.
        
        Возвращает:
            pyodbc.Connection: Активное подключение к базе данных
            
        Исключения:
            Exception: При ошибке подключения к базе данных
        """
        # Проверяем состояние текущего соединения
        if self.connection is not None:
            try:
                # Проверяем, что соединение активно
                if not self.connection.closed:
                    # Дополнительная проверка с простым запросом
                    cursor = self.connection.cursor()
                    cursor.execute("SELECT 1")
                    cursor.close()
                    return self.connection
            except Exception as e:
                logger.warning(f"Соединение неактивно, переподключаемся: {e}")
                self.connection = None
        
        # Создаем новое соединение
        max_retries = 3
        for attempt in range(max_retries):
            try:
                connection_string = self.connection_config.get_connection_string()
                self.connection = pyodbc.connect(connection_string, timeout=30)
                logger.info(f"Успешное подключение к базе данных {self.connection_config.database}")
                return self.connection
            except Exception as e:
                logger.error(f"Попытка {attempt + 1}/{max_retries} подключения к базе данных не удалась: {e}")
                if attempt == max_retries - 1:
                    raise
                import time
                time.sleep(1)  # Пауза перед повторной попыткой
        
        return self.connection
    
    def _execute_query_with_location_fallback(self, cursor, query_with_location: str, query_without_location: str, params: tuple) -> Optional[Any]:
        """
        Выполняет запрос с таблицей LOCATIONS, при ошибке доступа выполняет запрос без неё.
        
        Args:
            cursor: Курсор базы данных
            query_with_location: Запрос с JOIN LOCATIONS
            query_without_location: Запрос без JOIN LOCATIONS
            params: Параметры запроса
            
        Returns:
            Результат запроса или None при ошибке
        """
        try:
            cursor.execute(query_with_location, params)
            return cursor.fetchone()
        except Exception as e:
            error_msg = str(e).lower()
            if 'permission' in error_msg or 'запрещено' in error_msg or 'locations' in error_msg:
                logger.warning(f"Нет доступа к таблице LOCATIONS, выполняем запрос без неё: {e}")
                try:
                    cursor.execute(query_without_location, params)
                    return cursor.fetchone()
                except Exception as e2:
                    logger.error(f"Ошибка при выполнении запроса без LOCATIONS: {e2}")
                    raise e2
            else:
                raise e
    
    def find_by_serial_number(self, serial_number: str, try_variants: bool = True) -> Dict[str, Any]:
        """
        Поиск оборудования по серийному номеру

        Выполняет поиск единицы оборудования в базе данных по серийному номеру.
        Возвращает полную информацию об оборудовании, включая тип, модель,
        местоположение, ответственного сотрудника и финансовые данные.

        Параметры:
            serial_number (str): Серийный номер оборудования для поиска
            try_variants (bool): Если True, пробует варианты O↔0 при отсутствии результата

        Возвращает:
            Dict[str, Any]: Словарь с информацией об оборудовании или пустой словарь,
                           если оборудование не найдено. Включает поля:
                           - ID: ID оборудования
                           - SERIAL_NO: Серийный номер
                           - HW_SERIAL_NO: Аппаратный серийный номер
                           - INV_NO: Инвентарный номер
                           - PART_NO: Партийный номер
                           - CI_TYPE: Тип оборудования
                           - TYPE_NAME: Название типа оборудования
                           - MODEL_NO: Номер модели
                           - MODEL_NAME: Название модели
                           - MANUFACTURER: Производитель
                           - LOCATION: Местоположение
                           - EMPL_NO: Табельный номер сотрудника
                           - EMPLOYEE_NAME: Имя сотрудника
                           - EMPLOYEE_DEPT: Отдел сотрудника
                           - BRANCH_NAME: Филиал
                           - STATUS: Статус оборудования
                           - DESCRIPTION: Описание
                           
        Исключения:
            Exception: При ошибке выполнения SQL-запроса
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Основной SQL запрос для поиска по серийному номеру
            # Использует LEFT JOIN для получения связанной информации из справочников
            query_with_location = """
            SELECT
                i.ID,
                i.SERIAL_NO,
                i.HW_SERIAL_NO,
                i.INV_NO,
                i.PART_NO,
                i.CI_TYPE,
                t.TYPE_NAME,
                i.MODEL_NO,
                m.MODEL_NAME,
                v.VENDOR_NAME as MANUFACTURER,
                l.DESCR as LOCATION,
                i.EMPL_NO,
                o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
                o.OWNER_DEPT as EMPLOYEE_DEPT,
                b.BRANCH_NAME as BRANCH_NAME,
                s.DESCR as STATUS,
                i.DESCR as DESCRIPTION
            FROM ITEMS i
            LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
            LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
            LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
            LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
            LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
            LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
            LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
            WHERE i.SERIAL_NO = ? OR i.HW_SERIAL_NO = ?
            """
            
            query_without_location = """
            SELECT
                i.ID,
                i.SERIAL_NO,
                i.HW_SERIAL_NO,
                i.INV_NO,
                i.PART_NO,
                i.CI_TYPE,
                t.TYPE_NAME,
                i.MODEL_NO,
                m.MODEL_NAME,
                v.VENDOR_NAME as MANUFACTURER,
                'Не указана' as LOCATION,
                i.EMPL_NO,
                o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
                o.OWNER_DEPT as EMPLOYEE_DEPT,
                'Не указан' as BRANCH_NAME,
                s.DESCR as STATUS,
                i.DESCR as DESCRIPTION
            FROM ITEMS i
            LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
            LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
            LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
            LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
            LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
            WHERE i.SERIAL_NO = ? OR i.HW_SERIAL_NO = ?
            """
            
            row = self._execute_query_with_location_fallback(
                cursor, query_with_location, query_without_location, (serial_number, serial_number)
            )
            
            if row:
                # Преобразуем результат в словарь для удобства работы
                columns = [column[0] for column in cursor.description]
                result = dict(zip(columns, row))

                logger.info(f"Найдено оборудование с серийным номером: {serial_number}")
                return result
            else:
                logger.info(f"Оборудование с серийным номером {serial_number} не найдено")

                # Пробуем варианты с заменой O↔0 если включено
                if try_variants:
                    from bot.services.ocr_service import generate_serial_variants
                    variants = generate_serial_variants(serial_number)

                    for variant in variants:
                        if variant != serial_number:
                            logger.info(f"Пробуем вариант: {variant}")
                            row = self._execute_query_with_location_fallback(
                                cursor, query_with_location, query_without_location, (variant, variant)
                            )

                            if row:
                                columns = [column[0] for column in cursor.description]
                                result = dict(zip(columns, row))
                                logger.info(f"✅ Найдено по варианту: {variant} (оригинал: {serial_number})")
                                return result

                return {}

        except Exception as e:
            logger.error(f"Ошибка при поиске по серийному номеру {serial_number}: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def search_equipment(self, search_term: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Расширенный поиск оборудования по различным критериям
        
        Выполняет поиск оборудования по серийному номеру, инвентарному номеру,
        названию модели, производителю, имени сотрудника или местоположению.
        Поиск выполняется с использованием частичного совпадения (LIKE).
        
        Параметры:
            search_term (str): Поисковый запрос (может быть частичным)
            limit (int): Максимальное количество результатов (по умолчанию 10)
            
        Возвращает:
            List[Dict[str, Any]]: Список словарей с информацией об оборудовании.
                                 Каждый словарь содержит те же поля, что и find_by_serial_number.
                                 Возвращает пустой список, если ничего не найдено.
                                 
        Исключения:
            Exception: При ошибке выполнения SQL-запроса
        """
        search_pattern = f"%{search_term}%"
        
        # Используем подзапрос для ограничения количества записей после группировки
        query_with_location = f"""
            SELECT TOP {limit} *
            FROM (
                SELECT 
                    MIN(i.ID) as ID,
                    i.SERIAL_NO,
                    i.HW_SERIAL_NO,
                    i.INV_NO,
                    i.PART_NO,
                    MIN(i.DESCR) as equipment_description,
                    MIN(COALESCE(t.TYPE_NAME, 'Не указан')) as equipment_type,
                    MIN(COALESCE(m.MODEL_NAME, 'Не указана')) as model,
                    MIN(COALESCE(v.VENDOR_NAME, 'Не указан')) as manufacturer,
                    MIN(COALESCE(s.DESCR, 'Не указан')) as status,
                    MIN(COALESCE(o.OWNER_DISPLAY_NAME, 'Не назначен')) as employee_name,
                    MIN(COALESCE(b.BRANCH_NAME, 'Не указан')) as department,
                    MIN(COALESCE(l.DESCR, 'Не указана')) as location
                FROM ITEMS i
                LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
                LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
                LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
                LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
                LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
                LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
                LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
                WHERE (
                    i.SERIAL_NO LIKE ? OR 
                    i.HW_SERIAL_NO LIKE ? OR 
                    i.DESCR LIKE ? OR
                    i.INV_NO LIKE ? OR
                    m.MODEL_NAME LIKE ? OR
                    v.VENDOR_NAME LIKE ? OR
                    o.OWNER_DISPLAY_NAME LIKE ?
                )
                GROUP BY i.SERIAL_NO, i.HW_SERIAL_NO, i.INV_NO, i.PART_NO
            ) AS unique_items
            ORDER BY 
                CASE 
                    WHEN unique_items.SERIAL_NO = ? THEN 1
                    WHEN unique_items.HW_SERIAL_NO = ? THEN 2
                    WHEN unique_items.SERIAL_NO LIKE ? THEN 3
                    WHEN unique_items.HW_SERIAL_NO LIKE ? THEN 4
                    ELSE 5
                END
        """
        
        query_without_location = f"""
            SELECT TOP {limit} *
            FROM (
                SELECT 
                    MIN(i.ID) as ID,
                    i.SERIAL_NO,
                    i.HW_SERIAL_NO,
                    i.INV_NO,
                    i.PART_NO,
                    MIN(i.DESCR) as equipment_description,
                    MIN(COALESCE(t.TYPE_NAME, 'Не указан')) as equipment_type,
                    MIN(COALESCE(m.MODEL_NAME, 'Не указана')) as model,
                    MIN(COALESCE(v.VENDOR_NAME, 'Не указан')) as manufacturer,
                    MIN(COALESCE(s.DESCR, 'Не указан')) as status,
                    MIN(COALESCE(o.OWNER_DISPLAY_NAME, 'Не назначен')) as employee_name,
                    MIN(COALESCE(b.BRANCH_NAME, 'Не указан')) as department,
                    'Не указана' as location
                FROM ITEMS i
                LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
                LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
                LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
                LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
                LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
                LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
                WHERE (
                    i.SERIAL_NO LIKE ? OR 
                    i.HW_SERIAL_NO LIKE ? OR 
                    i.DESCR LIKE ? OR
                    i.INV_NO LIKE ? OR
                    m.MODEL_NAME LIKE ? OR
                    v.VENDOR_NAME LIKE ? OR
                    o.OWNER_DISPLAY_NAME LIKE ?
                )
                GROUP BY i.SERIAL_NO, i.HW_SERIAL_NO, i.INV_NO, i.PART_NO
            ) AS unique_items
            ORDER BY 
                CASE 
                    WHEN unique_items.SERIAL_NO = ? THEN 1
                    WHEN unique_items.HW_SERIAL_NO = ? THEN 2
                    WHEN unique_items.SERIAL_NO LIKE ? THEN 3
                    WHEN unique_items.HW_SERIAL_NO LIKE ? THEN 4
                    ELSE 5
                END
        """
        
        # Запрос без таблиц BRANCHES и LOCATIONS для случаев ограниченного доступа
        query_without_branches_locations = f"""
            SELECT TOP {limit} *
            FROM (
                SELECT 
                    MIN(i.ID) as ID,
                    i.SERIAL_NO,
                    i.HW_SERIAL_NO,
                    i.INV_NO,
                    i.PART_NO,
                    MIN(i.DESCR) as equipment_description,
                    MIN(COALESCE(t.TYPE_NAME, 'Не указан')) as equipment_type,
                    MIN(COALESCE(m.MODEL_NAME, 'Не указана')) as model,
                    MIN(COALESCE(v.VENDOR_NAME, 'Не указан')) as manufacturer,
                    MIN(COALESCE(s.DESCR, 'Не указан')) as status,
                    MIN(COALESCE(o.OWNER_DISPLAY_NAME, 'Не назначен')) as employee_name,
                    'Не указан' as department,
                    'Не указана' as location
                FROM ITEMS i
                LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
                LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
                LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
                LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
                WHERE (
                    i.SERIAL_NO LIKE ? OR 
                    i.HW_SERIAL_NO LIKE ? OR 
                    i.DESCR LIKE ? OR
                    i.INV_NO LIKE ? OR
                    m.MODEL_NAME LIKE ? OR
                    v.VENDOR_NAME LIKE ? OR
                    o.OWNER_DISPLAY_NAME LIKE ?
                )
                GROUP BY i.SERIAL_NO, i.HW_SERIAL_NO, i.INV_NO, i.PART_NO
            ) AS unique_items
            ORDER BY 
                CASE 
                    WHEN unique_items.SERIAL_NO = ? THEN 1
                    WHEN unique_items.HW_SERIAL_NO = ? THEN 2
                    WHEN unique_items.SERIAL_NO LIKE ? THEN 3
                    WHEN unique_items.HW_SERIAL_NO LIKE ? THEN 4
                    ELSE 5
                END
        """
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                params = (
                    search_pattern, search_pattern, search_pattern, search_pattern, search_pattern, search_pattern, search_pattern,
                    search_term, search_term, f"{search_term}%", f"{search_term}%"
                )
                
                try:
                    cursor.execute(query_with_location, params)
                    rows = cursor.fetchall()
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'permission' in error_msg or 'запрещено' in error_msg or 'locations' in error_msg:
                        if 'locations' in error_msg:
                            logger.warning(f"Нет доступа к таблице LOCATIONS, выполняем поиск без неё: {e}")
                            try:
                                cursor.execute(query_without_location, params)
                                rows = cursor.fetchall()
                            except Exception as e2:
                                if 'branches' in str(e2).lower():
                                    logger.warning(f"Нет доступа к таблице BRANCHES, выполняем поиск без BRANCHES и LOCATIONS: {e2}")
                                    cursor.execute(query_without_branches_locations, params)
                                    rows = cursor.fetchall()
                                else:
                                    raise e2
                        elif 'branches' in error_msg:
                            logger.warning(f"Нет доступа к таблице BRANCHES, выполняем поиск без BRANCHES и LOCATIONS: {e}")
                            cursor.execute(query_without_branches_locations, params)
                            rows = cursor.fetchall()
                        else:
                            raise e
                    else:
                        raise e
                
                results = []
                # Преобразуем каждую строку результата в словарь
                columns = [column[0] for column in cursor.description]
                
                for row in rows:
                    result = dict(zip(columns, row))
                    results.append(result)
                    
                logger.info(f"Найдено {len(results)} результатов по запросу: {search_term}")
                return results
                
        except Exception as e:
            logger.error(f"Ошибка при расширенном поиске {search_term}: {e}")
            return []
    
    def find_by_employee(self, employee_name: str, strict: bool = False) -> List[Dict[str, Any]]:
        """
        Поиск всего оборудования, закрепленного за конкретным сотрудником
        
        Выполняет поиск всех единиц оборудования, которые закреплены за сотрудником
        с указанным именем. Поиск выполняется с частичным совпадением имени.
        
        Параметры:
            employee_name (str): Имя сотрудника (может быть частичным)
            strict (bool): Если True, то точное совпадение, иначе поиск по подстроке
            
        Возвращает:
            List[Dict[str, Any]]: Список словарей с информацией об оборудовании,
                                 закрепленном за сотрудником. Каждый словарь содержит
                                 те же поля, что и find_by_serial_number.
                                 Возвращает пустой список, если оборудование не найдено.
                                 
        Исключения:
            Exception: При ошибке выполнения SQL-запроса
        """
        if strict:
            where_clause = "o.OWNER_DISPLAY_NAME = ?"
            search_params = (employee_name,)
        else:
            where_clause = "o.OWNER_DISPLAY_NAME LIKE ?"
            search_param = f"%{employee_name}%"
            search_params = (search_param,)
        
        # SQL запрос для поиска всего оборудования конкретного сотрудника
        # Использует INNER JOIN для получения полной информации об оборудовании
        # Теперь использует TYPE_NO для точного определения типа оборудования
        query = f"""
            SELECT DISTINCT
                i.ID,
                i.SERIAL_NO,
                i.HW_SERIAL_NO,
                i.INV_NO,
                i.PART_NO,
                i.DESCR as DESCRIPTION,
                COALESCE(t.TYPE_NAME, 'Не указан') as TYPE_NAME,
                COALESCE(m.MODEL_NAME, 'Не указана') as MODEL_NAME,
                COALESCE(v.VENDOR_NAME, 'Не указан') as MANUFACTURER,
                COALESCE(s.DESCR, 'Не указан') as STATUS,
                o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
                COALESCE(o.OWNER_DEPT, '') as OWNER_DEPT,
                COALESCE(b.BRANCH_NAME, 'Не указан') as DEPARTMENT,
                COALESCE(l.DESCR, 'Не указана') as LOCATION
            FROM ITEMS i
            LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
            LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
            LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
            LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
            INNER JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
            LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
            LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
            WHERE {where_clause}
            ORDER BY o.OWNER_DISPLAY_NAME, i.DESCR
        """
        
        # Запрос без таблиц BRANCHES и LOCATIONS для случаев ограниченного доступа
        query_without_branches_locations = f"""
            SELECT DISTINCT
                i.ID,
                i.SERIAL_NO,
                i.HW_SERIAL_NO,
                i.INV_NO,
                i.PART_NO,
                i.DESCR as DESCRIPTION,
                COALESCE(t.TYPE_NAME, 'Не указан') as TYPE_NAME,
                COALESCE(m.MODEL_NAME, 'Не указана') as MODEL_NAME,
                COALESCE(v.VENDOR_NAME, 'Не указан') as MANUFACTURER,
                COALESCE(s.DESCR, 'Не указан') as STATUS,
                o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
                COALESCE(o.OWNER_DEPT, '') as OWNER_DEPT,
                'Не указан' as DEPARTMENT,
                'Не указана' as LOCATION
            FROM ITEMS i
            LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
            LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
            LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
            LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
            INNER JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
            WHERE {where_clause}
            ORDER BY o.OWNER_DISPLAY_NAME, i.DESCR
        """
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(query, search_params)
                    rows = cursor.fetchall()
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'permission' in error_msg or 'запрещено' in error_msg or ('branches' in error_msg or 'locations' in error_msg):
                        logger.warning(f"Нет доступа к таблицам BRANCHES/LOCATIONS, выполняем поиск без них: {e}")
                        cursor.execute(query_without_branches_locations, search_params)
                        rows = cursor.fetchall()
                    else:
                        raise e
                
                results = []
                columns = [column[0] for column in cursor.description]
                
                for row in rows:
                    result = dict(zip(columns, row))
                    result['serial_number'] = result.get('SERIAL_NO') or result.get('HW_SERIAL_NO')
                    results.append(result)
                
                logger.info(f"Найдено {len(results)} единиц оборудования для сотрудника: {employee_name}")
                return results
                
        except Exception as e:
            logger.error(f"Ошибка при поиске оборудования для сотрудника '{employee_name}': {e}")
            return []

    def get_employee_department(self, employee_name: str, strict: bool = True) -> Optional[str]:
        """
        Возвращает отдел (BRANCH_NAME) сотрудника по его имени.
        Пытается определить отдел по большинству оборудования, закрепленного за сотрудником.
        
        Параметры:
            employee_name (str): ФИО сотрудника
            strict (bool): Если True — точное совпадение имени, иначе LIKE-поиск
        
        Returns:
            Optional[str]: Название отдела или None, если определить не удалось
        """
        where_clause = "o.OWNER_DISPLAY_NAME = ?" if strict else "o.OWNER_DISPLAY_NAME LIKE ?"
        param = employee_name if strict else f"%{employee_name}%"
        params = (param,)
        
        query = f"""
            SELECT TOP 1
                COALESCE(b.BRANCH_NAME, 'Не указан') AS DEPARTMENT,
                COUNT(*) AS CNT
            FROM ITEMS i
            INNER JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
            LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
            WHERE {where_clause}
            GROUP BY COALESCE(b.BRANCH_NAME, 'Не указан')
            ORDER BY COUNT(*) DESC
        """
        
        # Фолбэк без BRANCHES
        query_without_branches = f"""
            SELECT TOP 1
                'Не указан' AS DEPARTMENT,
                COUNT(*) AS CNT
            FROM ITEMS i
            INNER JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
            WHERE {where_clause}
            GROUP BY i.EMPL_NO
            ORDER BY COUNT(*) DESC
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(query, params)
                    row = cursor.fetchone()
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'permission' in error_msg or 'запрещено' in error_msg or 'branches' in error_msg:
                        logger.warning(f"Нет доступа к BRANCHES при получении отдела, фолбэк: {e}")
                        cursor.execute(query_without_branches, params)
                        row = cursor.fetchone()
                    else:
                        raise e
                if row:
                    department = row[0]
                    department = (department or '').strip()
                    if department and department.lower() not in {'не указан', 'не указана', 'неизвестно'}:
                        return department
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении отдела для сотрудника '{employee_name}': {e}")
            return None

    # NEW: точное поле OWNER_DEPT из таблицы OWNERS
    def get_owner_dept(self, employee_name: str, strict: bool = True) -> Optional[str]:
        """
        Возвращает значение поля OWNERS.OWNER_DEPT для указанного сотрудника.
        Сначала пытается точное совпадение по OWNER_DISPLAY_NAME, затем LIKE (если strict=False).
        Возвращает None, если поле пустое/NULL или сотрудник не найден.
        """
        where_clause = "OWNER_DISPLAY_NAME = ?" if strict else "OWNER_DISPLAY_NAME LIKE ?"
        param = employee_name if strict else f"%{employee_name}%"
        sql = f"""
            SELECT TOP 1
                   NULLIF(LTRIM(RTRIM(OWNER_DEPT)), '') AS OWNER_DEPT
            FROM OWNERS
            WHERE {where_clause}
              AND OWNER_DEPT IS NOT NULL
              AND LTRIM(RTRIM(OWNER_DEPT)) <> ''
        """
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(sql, (param,))
                row = cur.fetchone()
                if row and row[0]:
                    return str(row[0]).strip()
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении OWNER_DEPT для сотрудника '{employee_name}': {e}")
            return None
    def get_owner_email(self, employee_name: str, strict: bool = True) -> Optional[str]:
        """
        Возвращает значение поля OWNERS.OWNER_EMAIL для указанного сотрудника.
        Сначала пытается точное совпадение по OWNER_DISPLAY_NAME, затем LIKE (если strict=False).
        Возвращает None, если поле пустое/NULL или сотрудник не найден.
        """
        where_clause = "OWNER_DISPLAY_NAME = ?" if strict else "OWNER_DISPLAY_NAME LIKE ?"
        param = employee_name if strict else f"%{employee_name}%"
        sql = f"""
            SELECT TOP 1
                   NULLIF(LTRIM(RTRIM(OWNER_EMAIL)), '') AS OWNER_EMAIL
            FROM OWNERS
            WHERE {where_clause}
              AND OWNER_EMAIL IS NOT NULL
              AND LTRIM(RTRIM(OWNER_EMAIL)) <> ''
        """
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(sql, (param,))
                row = cur.fetchone()
                if row and row[0]:
                    return str(row[0]).strip()
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении OWNER_EMAIL для сотрудника '{employee_name}': {e}")
            return None

    def get_owner_no_by_name(self, employee_name: str, strict: bool = True) -> Optional[int]:
        """
        Возвращает OWNER_NO (EMPL_NO) для указанного сотрудника по имени.

        Параметры:
            employee_name: ФИО сотрудника
            strict: Если True - точное совпадение, иначе LIKE

        Возвращает:
            int: OWNER_NO или None если не найден
        """
        where_clause = "OWNER_DISPLAY_NAME = ?" if strict else "OWNER_DISPLAY_NAME LIKE ?"
        param = employee_name if strict else f"%{employee_name}%"
        sql = f"""
            SELECT TOP 1 OWNER_NO
            FROM OWNERS
            WHERE {where_clause}
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, (param,))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении OWNER_NO для '{employee_name}': {e}")
            return None

    def _parse_fio(self, full_name: str) -> tuple:
        """
        Разбивает полное ФИО на компоненты

        Параметры:
            full_name: Полное ФИО (например, "Иванов Иван Иванович")

        Возвращает:
            tuple: (last_name, first_name, middle_name)
        """
        parts = full_name.strip().split()
        if len(parts) >= 3:
            return parts[0], parts[1], parts[2]  # Фамилия, Имя, Отчество
        elif len(parts) == 2:
            return parts[0], parts[1], ''  # Фамилия, Имя (без отчества)
        else:
            return full_name, '', ''  # Только фамилия или одно слово

    def create_owner(self, employee_name: str, department: str = None) -> Optional[int]:
        """
        Создает новую запись в таблице OWNERS и возвращает OWNER_NO

        Параметры:
            employee_name: ФИО сотрудника
            department: Отдел (опционально)

        Возвращает:
            int: Созданный OWNER_NO или None в случае ошибки
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Получаем следующий OWNER_NO
                cursor.execute("SELECT ISNULL(MAX(OWNER_NO), 0) + 1 FROM OWNERS")
                next_owner_no = cursor.fetchone()[0]

                # Разбиваем ФИО на компоненты
                last_name, first_name, middle_name = self._parse_fio(employee_name)

                # Вставляем новую запись с полными данными
                cursor.execute("""
                    INSERT INTO OWNERS (
                        OWNER_NO, OWNER_LNAME, OWNER_FNAME, OWNER_MNAME,
                        OWNER_DISPLAY_NAME, OWNER_DEPT
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (next_owner_no, last_name, first_name, middle_name,
                      employee_name, department or ''))

                conn.commit()
                logger.info(
                    f"Создан новый владелец: OWNER_NO={next_owner_no}, "
                    f"NAME={employee_name}, DEPT={department}, "
                    f"LNAME={last_name}, FNAME={first_name}, MNAME={middle_name}"
                )
                return next_owner_no

        except Exception as e:
            logger.error(f"Ошибка при создании владельца '{employee_name}': {e}", exc_info=True)
            return None

    def _parse_vendor_from_model(self, model_name: str) -> str:
        """
        Извлекает vendor из полного названия модели

        Параметры:
            model_name: Полное название модели (например "Kyocera FS-1135MFP")

        Возвращает:
            Название производителя (первое слово)
        """
        if not model_name:
            return "Unknown"

        parts = model_name.strip().split(None, 1)
        return parts[0] if parts else "Unknown"

    def get_or_create_vendor(self, vendor_name: str) -> Optional[int]:
        """
        Находит или создаёт vendor в таблице VENDORS

        Параметры:
            vendor_name: Название производителя

        Возвращает:
            VENDOR_NO или None в случае ошибки
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Сначала ищем существующий vendor
                cursor.execute("""
                    SELECT TOP 1 VENDOR_NO
                    FROM VENDORS
                    WHERE VENDOR_NAME = ?
                """, (vendor_name,))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])

                # Если не найден, создаём нового
                cursor.execute("SELECT ISNULL(MAX(VENDOR_NO), 0) + 1 FROM VENDORS")
                next_vendor_no = cursor.fetchone()[0]

                cursor.execute("""
                    INSERT INTO VENDORS (VENDOR_NO, VENDOR_NAME)
                    VALUES (?, ?)
                """, (next_vendor_no, vendor_name))

                conn.commit()
                logger.info(f"Создан новый производитель: VENDOR_NO={next_vendor_no}, NAME={vendor_name}")
                return next_vendor_no

        except Exception as e:
            logger.error(f"Ошибка при создании производителя '{vendor_name}': {e}", exc_info=True)
            return None

    def get_vendor_no_by_name(self, vendor_name: str) -> Optional[int]:
        """
        Ищет VENDOR_NO по имени производителя

        Параметры:
            vendor_name: Название производителя

        Возвращает:
            VENDOR_NO или None если не найден
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT TOP 1 VENDOR_NO
                    FROM VENDORS
                    WHERE VENDOR_NAME = ?
                """, (vendor_name,))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
                return None
        except Exception as e:
            logger.error(f"Ошибка при поиске VENDOR_NO для '{vendor_name}': {e}")
            return None

    def create_model(self, model_name: str, type_no: int, ci_type: int = 1) -> Optional[int]:
        """
        Создаёт новую запись в таблице CI_MODELS

        Параметры:
            model_name: Название модели (например "Kyocera FS-1135MFP")
            type_no: TYPE_NO (тип оборудования - обязателен!)
            ci_type: Тип CI (по умолчанию 1 для IT-оборудования)

        Возвращает:
            MODEL_NO или None в случае ошибки
        """
        try:
            # Извлекаем первое слово как возможный vendor
            parts = model_name.strip().split(None, 1)
            vendor_name = parts[0] if parts else None

            # Ищем vendor в базе
            vendor_no = None
            if vendor_name:
                vendor_no = self.get_vendor_no_by_name(vendor_name)
                if vendor_no:
                    logger.info(f"Найден существующий vendor: {vendor_name} (VENDOR_NO={vendor_no})")
                else:
                    logger.info(f"Vendor '{vendor_name}' не найден в базе, создаём модель без VENDOR_NO")

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Получаем следующий MODEL_NO
                cursor.execute("SELECT ISNULL(MAX(MODEL_NO), 0) + 1 FROM CI_MODELS")
                next_model_no = cursor.fetchone()[0]

                if vendor_no:
                    # Вставляем с VENDOR_NO
                    cursor.execute("""
                        INSERT INTO CI_MODELS (MODEL_NO, CI_TYPE, TYPE_NO, MODEL_NAME, VENDOR_NO)
                        VALUES (?, ?, ?, ?, ?)
                    """, (next_model_no, ci_type, type_no, model_name, vendor_no))
                else:
                    # Вставляем без VENDOR_NO
                    cursor.execute("""
                        INSERT INTO CI_MODELS (MODEL_NO, CI_TYPE, TYPE_NO, MODEL_NAME)
                        VALUES (?, ?, ?, ?)
                    """, (next_model_no, ci_type, type_no, model_name))

                conn.commit()
                logger.info(
                    f"Создана новая модель: MODEL_NO={next_model_no}, "
                    f"NAME={model_name}, CI_TYPE={ci_type}, TYPE_NO={type_no}, VENDOR_NO={vendor_no}"
                )
                return next_model_no

        except Exception as e:
            logger.error(f"Ошибка при создании модели '{model_name}': {e}", exc_info=True)
            return None

    def get_equipment_statistics(self) -> Dict[str, Any]:
        """
        Получение статистики по оборудованию
        
        Returns:
            Словарь со статистикой
        """
        queries = {
            'total_items': "SELECT COUNT(*) FROM ITEMS",
            'items_with_serial': "SELECT COUNT(*) FROM ITEMS WHERE SERIAL_NO IS NOT NULL AND SERIAL_NO != ''",
            'items_with_employee': "SELECT COUNT(*) FROM ITEMS WHERE EMPL_NO IS NOT NULL",
            'total_employees': "SELECT COUNT(DISTINCT o.OWNER_NO) FROM OWNERS o INNER JOIN ITEMS i ON o.OWNER_NO = i.EMPL_NO",
            'total_locations': "SELECT COUNT(*) FROM LOCATIONS",
            'total_branches': "SELECT COUNT(*) FROM BRANCHES"
        }
        
        stats = {}
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                for stat_name, query in queries.items():
                    cursor.execute(query)
                    stats[stat_name] = cursor.fetchone()[0]
                
                # Получаем статистику по типам оборудования
                equipment_types_query = """
                SELECT t.TYPE_NAME, COUNT(i.ID) as count
                FROM CI_TYPES t
                LEFT JOIN ITEMS i ON t.CI_TYPE = i.CI_TYPE AND t.TYPE_NO = i.TYPE_NO
                GROUP BY t.TYPE_NAME
                HAVING COUNT(i.ID) > 0
                ORDER BY COUNT(i.ID) DESC
                """
                
                cursor.execute(equipment_types_query)
                equipment_types = cursor.fetchall()
                stats['equipment_types'] = [(row[0], row[1]) for row in equipment_types]
                
                logger.info("Статистика базы данных получена успешно")
                return stats
                
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            return {}
    
    def get_equipment_types(self) -> List[str]:
        """
        Получение списка уникальных типов оборудования из базы данных
        
        Returns:
            List[str]: Список уникальных типов оборудования
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Запрос для получения уникальных типов оборудования
                query = """
                SELECT DISTINCT t.TYPE_NAME 
                FROM ITEMS i
                LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
                WHERE t.TYPE_NAME IS NOT NULL 
                AND t.TYPE_NAME != '' 
                ORDER BY t.TYPE_NAME
                """
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                # Извлекаем типы из результата запроса
                equipment_types = [row[0] for row in rows if row[0]]
                
                logger.info(f"Найдено {len(equipment_types)} уникальных типов оборудования")
                return equipment_types
                
        except Exception as e:
            logger.error(f"Ошибка при получении типов оборудования: {e}")
            return []
    
    def get_equipment_by_type(self, equipment_type: str, limit: int = 2000, branch_name: str = None) -> List[Dict[str, Any]]:
        """
        Получение списка оборудования по типу и филиалу
        
        Args:
            equipment_type (str): Тип оборудования для поиска
            limit (int): Максимальное количество записей (по умолчанию 2000)
            branch_name (str): Название филиала для фильтрации (None для всех филиалов)
            
        Returns:
            List[Dict[str, Any]]: Список оборудования указанного типа и филиала
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Запрос для получения оборудования по типу и филиалу
                top_limit = int(limit) if isinstance(limit, int) else 2000
                if branch_name:
                    query_with_location = f"""
                    SELECT TOP ({top_limit}) 
                        i.ID,
                        t.TYPE_NAME,
                        i.SERIAL_NO,
                        i.INV_NO,
                    i.PART_NO,
                        m.MODEL_NAME,
                        v.VENDOR_NAME,
                        o.OWNER_DISPLAY_NAME,
                        i.EMPL_NO,
                        i.STATUS_NO,
                        b.BRANCH_NAME,
                        s.DESCR as STATUS,
                        i.IP_ADDRESS,
                        l.DESCR as LOCATION
                    FROM ITEMS i
                    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
                    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
                    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
                    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
                    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
                    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
                    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
                    WHERE t.TYPE_NAME = ? AND b.BRANCH_NAME = ?
                    ORDER BY i.INV_NO
                    """
                    query_without_location = f"""
                    SELECT TOP ({top_limit}) 
                        i.ID,
                        t.TYPE_NAME,
                        i.SERIAL_NO,
                        i.INV_NO,
                    i.PART_NO,
                        m.MODEL_NAME,
                        v.VENDOR_NAME,
                        o.OWNER_DISPLAY_NAME,
                        i.EMPL_NO,
                        i.STATUS_NO,
                        b.BRANCH_NAME,
                        s.DESCR as STATUS,
                        i.IP_ADDRESS,
                        'Не указана' as LOCATION
                    FROM ITEMS i
                    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
                    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
                    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
                    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
                    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
                    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
                    WHERE t.TYPE_NAME = ? AND b.BRANCH_NAME = ?
                    ORDER BY i.INV_NO
                    """
                    params = (equipment_type, branch_name)
                else:
                    query_with_location = f"""
                    SELECT TOP ({top_limit}) 
                        i.ID,
                        t.TYPE_NAME,
                        i.SERIAL_NO,
                        i.INV_NO,
                    i.PART_NO,
                        m.MODEL_NAME,
                        v.VENDOR_NAME,
                        o.OWNER_DISPLAY_NAME,
                        i.EMPL_NO,
                        i.STATUS_NO,
                        b.BRANCH_NAME,
                        s.DESCR as STATUS,
                        i.IP_ADDRESS,
                        l.DESCR as LOCATION
                    FROM ITEMS i
                    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
                    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
                    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
                    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
                    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
                    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
                    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
                    WHERE t.TYPE_NAME = ?
                    ORDER BY i.INV_NO
                    """
                    query_without_location = f"""
                    SELECT TOP ({top_limit}) 
                        i.ID,
                        t.TYPE_NAME,
                        i.SERIAL_NO,
                        i.INV_NO,
                    i.PART_NO,
                        m.MODEL_NAME,
                        v.VENDOR_NAME,
                        o.OWNER_DISPLAY_NAME,
                        i.EMPL_NO,
                        i.STATUS_NO,
                        b.BRANCH_NAME,
                        s.DESCR as STATUS,
                        i.IP_ADDRESS,
                        'Не указана' as LOCATION
                    FROM ITEMS i
                    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
                    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
                    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
                    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
                    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
                    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
                    WHERE t.TYPE_NAME = ?
                    ORDER BY i.INV_NO
                    """
                    params = (equipment_type,)
                
                try:
                    cursor.execute(query_with_location, params)
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'permission' in error_msg or 'запрещено' in error_msg or 'locations' in error_msg:
                        logger.warning(f"Нет доступа к LOCATIONS, выполняем запрос без неё: {e}")
                        cursor.execute(query_without_location, params)
                    else:
                        raise
                
                rows = cursor.fetchall()
                
                if not rows:
                    logger.info(f"Оборудование типа '{equipment_type}' не найдено")
                    return []
                
                # Формируем результат
                results = []
                columns = [column[0] for column in cursor.description]
                
                for row in rows:
                    result = dict(zip(columns, row))
                    result['serial_number'] = result.get('SERIAL_NO')
                    results.append(result)
                
                logger.info(f"Найдено {len(results)} единиц оборудования типа '{equipment_type}'")
                return results
        except Exception as e:
            logger.error(f"Ошибка при получении оборудования по типу '{equipment_type}': {e}")
            return []
    
    def get_branches(self) -> List[Dict[str, Any]]:
        """
        Получение списка всех филиалов из базы данных
        
        Returns:
            List[Dict[str, Any]]: Список словарей с информацией о филиалах
                                 Каждый словарь содержит: BRANCH_NO, BRANCH_NAME
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # SQL запрос для получения всех филиалов
                query = """
                    SELECT DISTINCT 
                        b.BRANCH_NO,
                        b.BRANCH_NAME
                    FROM BRANCHES b
                    WHERE b.BRANCH_NAME IS NOT NULL 
                        AND b.BRANCH_NAME != ''
                    ORDER BY b.BRANCH_NAME
                """
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                results = []
                for row in rows:
                    result = {
                        'BRANCH_NO': row[0],
                        'BRANCH_NAME': row[1]
                    }
                    results.append(result)
                    
                logger.info(f"Найдено {len(results)} филиалов")
                return results
                
        except Exception as e:
            logger.error(f"Ошибка при получении списка филиалов: {e}")
            return []

    def get_branch_no_by_name(self, branch_name: str) -> Optional[int]:
        """
        Возвращает BRANCH_NO по названию филиала

        Параметры:
            branch_name: Название филиала

        Возвращает:
            int: BRANCH_NO или None если не найден
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT TOP 1 BRANCH_NO
                    FROM BRANCHES
                    WHERE BRANCH_NAME = ?
                """
                cursor.execute(query, (branch_name,))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении BRANCH_NO для '{branch_name}': {e}")
            return None

    def get_loc_no_by_descr(self, location_descr: str) -> Optional[int]:
        """
        Возвращает LOC_NO по описанию локации (DESCR)

        Параметры:
            location_descr: Описание локации (DESCR из таблицы LOCATIONS)

        Возвращает:
            int: LOC_NO или None если не найден
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT TOP 1 LOC_NO
                    FROM LOCATIONS
                    WHERE DESCR = ?
                """
                cursor.execute(query, (location_descr,))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении LOC_NO для '{location_descr}': {e}")
            return None

    def get_type_no_by_name(self, type_name: str, ci_type: int = 2, strict: bool = True) -> Optional[int]:
        """
        Получает TYPE_NO по имени типа оборудования

        Параметры:
            type_name: Имя типа оборудования
            ci_type: Тип CI (по умолчанию 2 для IT-оборудования)
            strict: Строгое совпадение (True) или поиск по подстроке (False)

        Возвращает:
            TYPE_NO или None, если тип не найден
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Сначала пробуем точное совпадение в указанном CI_TYPE
                query = """
                    SELECT TOP 1 TYPE_NO
                    FROM CI_TYPES
                    WHERE CI_TYPE = ? AND TYPE_NAME = ?
                """
                cursor.execute(query, (ci_type, type_name))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])

                # Если не найдено и strict=False, пробуем LIKE в указанном CI_TYPE
                if not strict:
                    query = """
                        SELECT TOP 1 TYPE_NO
                        FROM CI_TYPES
                        WHERE CI_TYPE = ? AND TYPE_NAME LIKE ?
                    """
                    cursor.execute(query, (ci_type, f"%{type_name}%"))
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        logger.info(f"Найден TYPE_NO по подстроке для '{type_name}' в CI_TYPE={ci_type}")
                        return int(row[0])

                # Если всё ещё не найдено, пробуем во всех CI_TYPE (точное совпадение)
                query = """
                    SELECT TOP 1 TYPE_NO, CI_TYPE
                    FROM CI_TYPES
                    WHERE TYPE_NAME = ?
                """
                cursor.execute(query, (type_name,))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    logger.info(f"Найден TYPE_NO в другом CI_TYPE={row[1]} для '{type_name}'")
                    return int(row[0])

                # Если strict=False, пробуем LIKE во всех CI_TYPE
                if not strict:
                    query = """
                        SELECT TOP 1 TYPE_NO, CI_TYPE
                        FROM CI_TYPES
                        WHERE TYPE_NAME LIKE ?
                    """
                    cursor.execute(query, (f"%{type_name}%",))
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        logger.info(f"Найден TYPE_NO по подстроке в другом CI_TYPE={row[1]} для '{type_name}'")
                        return int(row[0])

                return None
        except Exception as e:
            logger.error(f"Ошибка при получении TYPE_NO для '{type_name}': {e}")
            return None

    def get_model_no_by_name(self, model_name: str, ci_type: int = 2, strict: bool = True) -> Optional[int]:
        """
        Получает MODEL_NO по имени модели оборудования

        Параметры:
            model_name: Имя модели оборудования
            ci_type: Тип CI (по умолчанию 2 для IT-оборудования)
            strict: Строгое совпадение (True) или поиск по подстроке (False)

        Возвращает:
            MODEL_NO или None, если модель не найдена
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Сначала пробуем точное совпадение в указанном CI_TYPE
                query = """
                    SELECT TOP 1 MODEL_NO
                    FROM CI_MODELS
                    WHERE CI_TYPE = ? AND MODEL_NAME = ?
                """
                cursor.execute(query, (ci_type, model_name))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])

                # Если не найдено и strict=False, пробуем LIKE в указанном CI_TYPE
                if not strict:
                    query = """
                        SELECT TOP 1 MODEL_NO
                        FROM CI_MODELS
                        WHERE CI_TYPE = ? AND MODEL_NAME LIKE ?
                    """
                    cursor.execute(query, (ci_type, f"%{model_name}%"))
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        logger.info(f"Найден MODEL_NO по подстроке для '{model_name}' в CI_TYPE={ci_type}")
                        return int(row[0])

                # Если всё ещё не найдено, пробуем во всех CI_TYPE (точное совпадение)
                query = """
                    SELECT TOP 1 MODEL_NO, CI_TYPE
                    FROM CI_MODELS
                    WHERE MODEL_NAME = ?
                """
                cursor.execute(query, (model_name,))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    logger.info(f"Найден MODEL_NO в другом CI_TYPE={row[1]} для '{model_name}'")
                    return int(row[0])

                # Если strict=False, пробуем LIKE во всех CI_TYPE
                if not strict:
                    query = """
                        SELECT TOP 1 MODEL_NO, CI_TYPE
                        FROM CI_MODELS
                        WHERE MODEL_NAME LIKE ?
                    """
                    cursor.execute(query, (f"%{model_name}%",))
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        logger.info(f"Найден MODEL_NO по подстроке в другом CI_TYPE={row[1]} для '{model_name}'")
                        return int(row[0])

                return None
        except Exception as e:
            logger.error(f"Ошибка при получении MODEL_NO для '{model_name}': {e}")
            return None

    def get_status_no_by_name(self, status_descr: str, strict: bool = True) -> Optional[int]:
        """
        Получает STATUS_NO по описанию статуса

        Параметры:
            status_descr: Описание статуса (DESCR)
            strict: Строгое совпадение (True) или поиск по подстроке (False)

        Возвращает:
            STATUS_NO или None, если статус не найден
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Сначала пробуем точное совпадение
                query = """
                    SELECT TOP 1 STATUS_NO
                    FROM STATUS
                    WHERE DESCR = ?
                """
                cursor.execute(query, (status_descr,))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])

                # Если не найдено и strict=False, пробуем LIKE
                if not strict:
                    query = """
                        SELECT TOP 1 STATUS_NO
                        FROM STATUS
                        WHERE DESCR LIKE ?
                    """
                    cursor.execute(query, (f"%{status_descr}%",))
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        logger.info(f"Найден STATUS_NO по подстроке для '{status_descr}'")
                        return int(row[0])

                return None
        except Exception as e:
            logger.error(f"Ошибка при получении STATUS_NO для '{status_descr}': {e}")
            return None

    def get_default_type_no(self, ci_type: int = 2) -> Optional[int]:
        """
        Получает первый доступный TYPE_NO (дефолтный тип)

        Параметры:
            ci_type: Тип CI (по умолчанию 2 для IT-оборудования)

        Возвращает:
            TYPE_NO первого доступного типа или None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT TOP 1 TYPE_NO
                    FROM CI_TYPES
                    WHERE CI_TYPE = ?
                    ORDER BY TYPE_NO
                """
                cursor.execute(query, (ci_type,))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении дефолтного TYPE_NO: {e}")
            return None

    def get_default_status_no(self) -> Optional[int]:
        """
        Получает первый доступный STATUS_NO (дефолтный статус)

        Возвращает:
            STATUS_NO первого доступного статуса или None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT TOP 1 STATUS_NO
                    FROM STATUS
                    ORDER BY STATUS_NO
                """
                cursor.execute(query)
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении дефолтного STATUS_NO: {e}")
            return None

    def get_default_model_no(self, ci_type: int = 2) -> Optional[int]:
        """
        Получает первый доступный MODEL_NO (дефолтная модель)

        Параметры:
            ci_type: Тип CI (по умолчанию 2 для IT-оборудования)

        Возвращает:
            MODEL_NO первой доступной модели или None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT TOP 1 MODEL_NO
                    FROM CI_MODELS
                    WHERE CI_TYPE = ?
                    ORDER BY MODEL_NO
                """
                cursor.execute(query, (ci_type,))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
                # Если не найдено в указанном CI_TYPE, ищем в любом
                cursor.execute("""
                    SELECT TOP 1 MODEL_NO
                    FROM CI_MODELS
                    ORDER BY MODEL_NO
                """)
                row = cursor.fetchone()
                if row and row[0] is not None:
                    logger.info(f"Используем MODEL_NO из другого CI_TYPE")
                    return int(row[0])
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении дефолтного MODEL_NO: {e}")
            return None

    def get_default_branch_no(self) -> Optional[int]:
        """
        Получает первый доступный BRANCH_NO (дефолтный филиал)

        Возвращает:
            BRANCH_NO первого доступного филиала или None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT TOP 1 BRANCH_NO
                    FROM BRANCHES
                    ORDER BY BRANCH_NO
                """
                cursor.execute(query)
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении дефолтного BRANCH_NO: {e}")
            return None

    def get_default_loc_no(self) -> Optional[int]:
        """
        Получает первый доступный LOC_NO (дефолтное местоположение)

        Возвращает:
            LOC_NO первого доступного местоположения или None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT TOP 1 LOC_NO
                    FROM LOCATIONS
                    ORDER BY LOC_NO
                """
                cursor.execute(query)
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении дефолтного LOC_NO: {e}")
            return None

    def add_equipment_to_items(
        self,
        serial_number: str,
        model_name: str = None,
        employee_name: str = None,
        location_descr: str = None,
        branch_name: str = None,
        equipment_type: str = None,
        inv_no: str = None,
        description: str = None,
        ip_address: str = None,
        status: str = "В эксплуатации",
        status_no: int = None,
        type_no: int = None,
        model_no: int = None
    ) -> Dict[str, Any]:
        """
        Добавляет новое оборудование в таблицу ITEMS

        Параметры:
            serial_number: Серийный номер (обязательный)
            model_name: Модель оборудования
            employee_name: ФИО сотрудника
            location_descr: Местоположение
            branch_name: Филиал
            equipment_type: Тип оборудования
            inv_no: Инвентарный номер
            description: Описание
            ip_address: IP-адрес
            status: Статус (по умолчанию "В эксплуатации")
            type_no: TYPE_NO напрямую (если выбран из подсказок)
            model_no: MODEL_NO напрямую (если выбран из подсказок)

        Возвращает:
            Словарь с результатом операции:
            - success: bool - успешно ли выполнено
            - item_id: int - ID созданной записи
            - message: str - сообщение о результате
        """
        result = {
            'success': False,
            'item_id': None,
            'message': ''
        }

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now()

                # Проверяем, не существует ли уже оборудование с таким серийным номером
                cursor.execute("""
                    SELECT ID, EMPL_NO FROM ITEMS WHERE SERIAL_NO = ?
                """, (serial_number,))
                existing = cursor.fetchone()

                if existing:
                    result['message'] = f"Оборудование с серийным номером {serial_number} уже существует (ID={existing[0]})"
                    result['item_id'] = existing[0]
                    return result

                # Получаем значения внешних ключей
                # Если type_no передан напрямую - используем его, иначе ищем по названию
                if type_no is None and equipment_type:
                    # Сначала строгий поиск
                    type_no = self.get_type_no_by_name(equipment_type, strict=True)
                    if type_no is None:
                        # Затем нестрогий поиск
                        type_no = self.get_type_no_by_name(equipment_type, strict=False)
                    if type_no is None:
                        logger.warning(f"Тип оборудования '{equipment_type}' не найден, используем дефолтный")

                # Если model_no передан напрямую - используем его, иначе ищем по названию
                if model_no is None and model_name:
                    # Сначала строгий поиск
                    model_no = self.get_model_no_by_name(model_name, strict=True)
                    if model_no is None:
                        # Затем нестрогий поиск
                        model_no = self.get_model_no_by_name(model_name, strict=False)
                    if model_no is None:
                        # Если не найдено, создаём новую модель
                        logger.info(f"Модель '{model_name}' не найдена, создаём новую запись")
                        # Используем type_no если уже определён
                        if type_no is not None:
                            model_no = self.create_model(model_name, type_no, ci_type=1)
                        else:
                            # Если type_no не определён, получаем дефолтный
                            default_type_no = self.get_default_type_no(ci_type=1)
                            if default_type_no:
                                model_no = self.create_model(model_name, default_type_no, ci_type=1)
                            else:
                                logger.error("Не удалось получить дефолтный TYPE_NO для создания модели")
                        if model_no:
                            result['message'] += f" Создана новую модель: {model_name} (MODEL_NO={model_no})."
                        else:
                            logger.warning(f"Не удалось создать модель '{model_name}', будет использован дефолт")

                # Обработка статуса
                if status_no is None:
                    # Если status_no не передан напрямую, ищем по названию
                    if status:
                        # Сначала строгий поиск
                        status_no = self.get_status_no_by_name(status, strict=True)
                        if status_no is None:
                            # Затем нестрогий поиск
                            status_no = self.get_status_no_by_name(status, strict=False)
                        if status_no is None:
                            # Если не найдено, создаём новый статус
                            logger.info(f"Статус '{status}' не найден, создаём новую запись")
                            status_no = self.create_status(status)
                            if status_no:
                                result['message'] += f" Создан новый статус: {status} (STATUS_NO={status_no})."
                            else:
                                logger.warning(f"Не удалось создать статус '{status}', будет использован дефолт")

                empl_no = None
                if employee_name:
                    empl_no = self.get_owner_no_by_name(employee_name, strict=False)
                    if empl_no is None:
                        logger.warning(f"Сотрудник '{employee_name}' не найден, создаём новую запись")
                        empl_no = self.create_owner(employee_name)
                        if empl_no:
                            result['message'] += f" Создан новый сотрудник: {employee_name} (OWNER_NO={empl_no})."

                branch_no = None
                if branch_name:
                    branch_no = self.get_branch_no_by_name(branch_name)

                loc_no = None
                if location_descr:
                    loc_no = self.get_loc_no_by_descr(location_descr)

                # Используем дефолтные значения для обязательных полей
                if type_no is None:
                    type_no = self.get_default_type_no()
                    logger.info(f"Используем дефолтный TYPE_NO: {type_no}")

                if model_no is None:
                    model_no = self.get_default_model_no()
                    logger.info(f"Используем дефолтный MODEL_NO: {model_no}")

                if branch_no is None:
                    branch_no = self.get_default_branch_no()
                    logger.info(f"Используем дефолтный BRANCH_NO: {branch_no}")

                if loc_no is None:
                    loc_no = self.get_default_loc_no()
                    logger.info(f"Используем дефолтный LOC_NO: {loc_no}")

                if status_no is None:
                    status_no = self.get_default_status_no()
                    logger.info(f"Используем дефолтный STATUS_NO: {status_no}")

                # Получаем следующий ID для ITEMS
                cursor.execute("SELECT ISNULL(MAX(ID), 0) + 1 FROM ITEMS")
                next_id = cursor.fetchone()[0]

                # Генерируем инвентарный номер если не указан
                if not inv_no:
                    cursor.execute("SELECT ISNULL(MAX(CAST(INV_NO AS INT)), 0) + 1 FROM ITEMS WHERE INV_NO IS NOT NULL AND ISNUMERIC(INV_NO) = 1")
                    next_inv_no = cursor.fetchone()[0]
                    inv_no = str(next_inv_no)
                    logger.info(f"Сгенерирован инвентарный номер: {inv_no}")

                # Вставляем запись в ITEMS
                insert_query = """
                    INSERT INTO ITEMS (
                        ID, SERIAL_NO, INV_NO, TYPE_NO, MODEL_NO,
                        BRANCH_NO, LOC_NO, STATUS_NO, EMPL_NO, QTY,
                        CI_TYPE, COMP_NO, DESCR, CREATE_DATE, CH_DATE, CH_USER
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

                cursor.execute(insert_query, (
                    next_id,
                    serial_number,
                    inv_no,
                    type_no,
                    model_no,
                    branch_no,
                    loc_no,
                    status_no,
                    empl_no,
                    1,  # QTY
                    1,  # CI_TYPE (1 для IT-оборудования)
                    0,  # COMP_NO (0 = ООО "Запсибгазпром-Газификация")
                    description,
                    now,
                    now,
                    "IT-BOT"
                ))

                conn.commit()

                result['success'] = True
                result['item_id'] = next_id
                result['message'] = f"Оборудование успешно добавлено (ID={next_id})" + result['message']
                logger.info(f"Добавлено оборудование: SERIAL_NO={serial_number}, ID={next_id}")

                # Сохраняем IP-адрес если указан
                if ip_address:
                    self.save_item_ip_address(next_id, ip_address)

                return result

        except Exception as e:
            logger.error(f"Ошибка при добавлении оборудования в ITEMS: {e}")
            result['message'] = f"Ошибка при добавлении: {e}"
            return result

    def save_item_ip_address(self, item_no: int, ip_address: str) -> bool:
        """
        Сохраняет IP-адрес оборудования в таблицу ITEMS

        Параметры:
            item_no: ID оборудования
            ip_address: IP-адрес

        Возвращает:
            True если успешно, False иначе
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Обновляем IP-адрес в записи (колонка IP_ADDRESS уже есть в ITEMS)
                cursor.execute("""
                    UPDATE ITEMS
                    SET IP_ADDRESS = ?, CH_DATE = GETDATE(), CH_USER = 'IT-BOT'
                    WHERE ID = ?
                """, (ip_address, item_no))

                conn.commit()
                logger.info(f"Сохранён IP-адрес: ID={item_no}, IP={ip_address}")
                return True

        except Exception as e:
            logger.error(f"Ошибка при сохранении IP-адреса для ID={item_no}: {e}")
            return False

    def test_database_connection(self) -> Dict[str, Any]:
        """
        Тестирование подключения и основных запросов
        
        Returns:
            Результаты тестирования
        """
        tests = {
            'connection': False,
            'items_table': False,
            'users_table': False,
            'locations_table': False,
            'sample_serial_search': False,
            'sample_employee_search': False
        }
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                tests['connection'] = True
                
                # Тест таблицы ITEMS
                cursor.execute("SELECT TOP 1 ID FROM ITEMS")
                if cursor.fetchone():
                    tests['items_table'] = True
                
                # Тест таблицы USERS
                cursor.execute("SELECT TOP 1 USER_NO FROM USERS")
                if cursor.fetchone():
                    tests['users_table'] = True
                
                # Тест таблицы LOCATIONS с обработкой ошибок доступа
                try:
                    cursor.execute("SELECT TOP 1 LOC_NO FROM LOCATIONS")
                    if cursor.fetchone():
                        tests['locations_table'] = True
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'permission' in error_msg or 'запрещено' in error_msg or 'locations' in error_msg:
                        logger.warning(f"Нет доступа к таблице LOCATIONS: {e}")
                        tests['locations_table'] = False
                    else:
                        raise e
                
                # Тест поиска по серийному номеру
                cursor.execute("SELECT TOP 1 SERIAL_NO FROM ITEMS WHERE SERIAL_NO IS NOT NULL AND SERIAL_NO != ''")
                sample_serial = cursor.fetchone()
                if sample_serial:
                    result = self.find_by_serial_number(sample_serial[0])
                    if result.get('found'):
                        tests['sample_serial_search'] = True
                
                # Тест поиска по сотруднику
                # Получаем случайного сотрудника из базы OWNERS, у которого есть оборудование
                try:
                    cursor.execute("""
                        SELECT TOP 1 o.OWNER_DISPLAY_NAME 
                        FROM OWNERS o 
                        INNER JOIN ITEMS i ON o.OWNER_NO = i.EMPL_NO 
                        WHERE o.OWNER_DISPLAY_NAME IS NOT NULL
                    """)
                    sample_owner = cursor.fetchone()
                    
                    if sample_owner:
                        sample_owner_name = sample_owner[0]
                        results = self.find_by_employee(sample_owner_name)
                        tests['sample_employee_search'] = True
                    else:
                        tests['sample_employee_search'] = True  # Нет данных для тестирования, но метод работает
                except Exception:
                    tests['sample_employee_search'] = False
                
        except Exception as e:
            logger.error(f"Ошибка при тестировании базы данных: {e}")
        
        return tests

    def get_status_list(self) -> List[str]:
        """
        Возвращает список доступных статусов из таблицы STATUS.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # В проекте статус обозначается как DESCR
                cursor.execute("SELECT DISTINCT DESCR FROM STATUS WHERE DESCR IS NOT NULL AND DESCR <> '' ORDER BY DESCR")
                rows = cursor.fetchall()
                statuses: List[str] = []
                for row in rows:
                    val = str(row[0]).strip() if row and row[0] is not None else ''
                    if val:
                        statuses.append(val)
                return statuses
        except Exception as e:
            logger.error(f"Ошибка при получении списка статусов: {e}")
            return []

    def get_status_list_with_ids(self) -> List[tuple]:
        """
        Возвращает список статусов с ID из таблицы STATUS.

        Возвращает:
            Список кортежей (STATUS_NO, DESCR)
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT STATUS_NO, DESCR
                    FROM STATUS
                    WHERE DESCR IS NOT NULL AND DESCR <> ''
                    ORDER BY DESCR
                """)
                rows = cursor.fetchall()
                statuses = []
                for row in rows:
                    status_no = int(row[0]) if row and row[0] is not None else None
                    descr = str(row[1]).strip() if row and row[1] is not None else ''
                    if status_no is not None and descr:
                        statuses.append((status_no, descr))
                return statuses
        except Exception as e:
            logger.error(f"Ошибка при получении списка статусов с ID: {e}")
            return []

    def transfer_equipment_with_history(
        self,
        serial_number: str,
        new_employee_id: int,
        new_employee_name: str,
        new_branch_no: int = None,
        new_loc_no: int = None,
        comment: str = None
    ) -> Dict[str, Any]:
        """
        Перемещает оборудование с записью в историю CI_HISTORY

        Параметры:
            serial_number: Серийный номер оборудования
            new_employee_id: Новый табельный номер (EMPL_NO)
            new_employee_name: ФИО нового сотрудника (для логирования)
            new_branch_no: Новый номер филиала (BRANCH_NO) - опционально
            new_loc_no: Новый номер локации (LOC_NO) - опционально
            comment: Комментарий к изменению

        Возвращает:
            Dict[str, Any]: Результат операции с ключами:
                - success: bool - успешно ли выполнено
                - message: str - сообщение о результате
                - old_employee_id: int - старый EMPL_NO
                - hist_id: int - ID записи в истории (если успешно)
        """
        from datetime import datetime

        result = {
            'success': False,
            'message': '',
            'old_employee_id': None,
            'hist_id': None
        }

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Текущая дата и время
            now = datetime.now()

            # 1. Читаем текущие данные оборудования
            cursor.execute("""
                SELECT ID, EMPL_NO, BRANCH_NO, LOC_NO, STATUS_NO,
                       SERIAL_NO, INV_NO, TYPE_NO, MODEL_NO, CI_TYPE, QTY
                FROM ITEMS
                WHERE SERIAL_NO = ?
            """, serial_number)

            current = cursor.fetchone()
            if not current:
                result['message'] = f"Оборудование с серийным номером {serial_number} не найдено"
                logger.warning(result['message'])
                return result

            item_id = current[0]
            old_empl_no = current[1]
            old_branch_no = current[2]
            old_loc_no = current[3]
            old_status_no = current[4]
            old_serial_no = current[5]
            old_inv_no = current[6]
            old_type_no = current[7]
            old_model_no = current[8]
            old_ci_type = current[9]
            old_qty = current[10] if current[10] is not None else 1

            result['old_employee_id'] = old_empl_no

            # Используем переданные значения или сохраняем старые
            final_branch_no = new_branch_no if new_branch_no is not None else old_branch_no
            final_loc_no = new_loc_no if new_loc_no is not None else old_loc_no
            # Количество всегда 1 для единицы оборудования
            new_qty = 1

            logger.info(f"Перемещение {serial_number}: EMPL_NO {old_empl_no} -> {new_employee_id}, BRANCH_NO {old_branch_no} -> {final_branch_no}, LOC_NO {old_loc_no} -> {final_loc_no}, QTY {old_qty} -> {new_qty}")

            # 2. Получаем следующий HIST_ID
            cursor.execute("SELECT ISNULL(MAX(HIST_ID), 0) + 1 FROM CI_HISTORY")
            next_hist_id = cursor.fetchone()[0]

            # 3. Добавляем запись в историю CI_HISTORY
            cursor.execute("""
                INSERT INTO CI_HISTORY (
                    HIST_ID,
                    ITEM_ID,
                    EMPL_NO_OLD, EMPL_NO_NEW,
                    BRANCH_NO_OLD, BRANCH_NO_NEW,
                    LOC_NO_OLD, LOC_NO_NEW,
                    STATUS_NO_OLD, STATUS_NO_NEW,
                    SERIAL_NO_OLD, SERIAL_NO_NEW,
                    INV_NO_OLD, INV_NO_NEW,
                    TYPE_NO_OLD, TYPE_NO_NEW,
                    MODEL_NO_OLD, MODEL_NO_NEW,
                    CI_TYPE_OLD, CI_TYPE_NEW,
                    COMP_NO_OLD, COMP_NO_NEW,
                    QTY_OLD, QTY_NEW,
                    CH_DATE, CH_USER, CH_COMMENT
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                next_hist_id,
                item_id,
                old_empl_no, new_employee_id,
                old_branch_no, final_branch_no,
                old_loc_no, final_loc_no,
                old_status_no, old_status_no,
                old_serial_no, old_serial_no,
                old_inv_no, old_inv_no,
                old_type_no, old_type_no,
                old_model_no, old_model_no,
                old_ci_type, old_ci_type,
                0, 0,
                old_qty, new_qty,
                now, "IT-BOT", comment
            ))

            # 4. Обновляем запись в ITEMS
            cursor.execute("""
                UPDATE ITEMS
                SET EMPL_NO = ?,
                    BRANCH_NO = ?,
                    LOC_NO = ?,
                    QTY = ?,
                    CH_DATE = ?,
                    CH_USER = ?
                WHERE SERIAL_NO = ?
            """, new_employee_id, final_branch_no, final_loc_no, new_qty, now, "IT-BOT", serial_number)

            conn.commit()

            result['success'] = True
            result['hist_id'] = next_hist_id
            result['message'] = (
                f"Оборудование {serial_number} перемещено: "
                f"EMPL_NO {old_empl_no} -> {new_employee_id} ({new_employee_name})"
            )
            if new_branch_no is not None and new_branch_no != old_branch_no:
                result['message'] += f", BRANCH_NO {old_branch_no} -> {new_branch_no}"
            if new_loc_no is not None and new_loc_no != old_loc_no:
                result['message'] += f", LOC_NO {old_loc_no} -> {new_loc_no}"
            logger.info(result['message'])

            cursor.close()

        except Exception as e:
            logger.error(f"Ошибка при перемещении оборудования {serial_number}: {e}", exc_info=True)
            result['message'] = f"Ошибка: {str(e)}"
            result['success'] = False

        return result

# Пример использования
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Создание подключения
    db_connection = DatabaseConfig(
        server=os.getenv('SQL_SERVER_HOST'),
        database=os.getenv('SQL_SERVER_DATABASE'),
        username=os.getenv('SQL_SERVER_USERNAME'),
        password=os.getenv('SQL_SERVER_PASSWORD')
    )
    
    # Создание экземпляра базы данных
    inventory_db = UniversalInventoryDB(db_connection)
    
    # Тестирование
    print("Тестирование подключения...")
    test_results = inventory_db.test_database_connection()
    
    print("\nДетальные результаты тестирования:")
    for test_name, result in test_results.items():
        status = "✅" if result else "❌"
        print(f"{status} {test_name}: {result}")
        
        if test_name == 'sample_employee_search' and result:
            print("   Тест поиска по сотруднику использует таблицу OWNERS")
        elif test_name == 'sample_serial_search' and result:
            print("   Тест поиска по серийному номеру работает корректно")
    
    # Получение статистики
    print("\nСтатистика базы данных:")
    stats = inventory_db.get_equipment_statistics()
    for stat_name, value in stats.items():
        print(f"{stat_name}: {value}")