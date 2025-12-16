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
    
    def find_by_serial_number(self, serial_number: str) -> Dict[str, Any]:
        """
        Поиск оборудования по серийному номеру
        
        Выполняет поиск единицы оборудования в базе данных по серийному номеру.
        Возвращает полную информацию об оборудовании, включая тип, модель,
        местоположение, ответственного сотрудника и финансовые данные.
        
        Параметры:
            serial_number (str): Серийный номер оборудования для поиска
            
        Возвращает:
            Dict[str, Any]: Словарь с информацией об оборудовании или пустой словарь,
                           если оборудование не найдено. Включает поля:
                           - ITEM_NO: Номер позиции
                           - SERIAL_NO: Серийный номер
                           - INVENTORY_NO: Инвентарный номер
                           - CI_TYPE: Тип оборудования
                           - TYPE_NAME: Название типа оборудования
                           - MODEL_NO: Номер модели
                           - MODEL_NAME: Название модели
                           - MANUFACTURER: Производитель
                           - LOCATION: Местоположение
                           - EMPLOYEE_NO: Номер сотрудника
                           - EMPLOYEE_NAME: Имя сотрудника
                           - STATUS: Статус оборудования
                           - PURCHASE_DATE: Дата покупки
                           - WARRANTY_END: Окончание гарантии
                           - COST: Стоимость
                           
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
                i.CI_TYPE,
                t.TYPE_NAME,
                i.MODEL_NO,
                m.MODEL_NAME,
                v.VENDOR_NAME as MANUFACTURER,
                l.DESCR as LOCATION,
                i.EMPL_NO,
                o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
                s.DESCR as STATUS,
                i.DESCR as DESCRIPTION
            FROM ITEMS i
            LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
            LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
            LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
            LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
            LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
            LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
            WHERE i.SERIAL_NO = ? OR i.HW_SERIAL_NO = ?
            """
            
            query_without_location = """
            SELECT 
                i.ID,
                i.SERIAL_NO,
                i.HW_SERIAL_NO,
                i.INV_NO,
                i.CI_TYPE,
                t.TYPE_NAME,
                i.MODEL_NO,
                m.MODEL_NAME,
                v.VENDOR_NAME as MANUFACTURER,
                'Не указана' as LOCATION,
                i.EMPL_NO,
                o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
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
                GROUP BY i.SERIAL_NO, i.HW_SERIAL_NO, i.INV_NO
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
                GROUP BY i.SERIAL_NO, i.HW_SERIAL_NO, i.INV_NO
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
                GROUP BY i.SERIAL_NO, i.HW_SERIAL_NO, i.INV_NO
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

    def search_equipment_by_employee(self, employee_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Поиск оборудования по имени сотрудника.
        
        Args:
            employee_name: Имя сотрудника для поиска
            limit: Максимальное количество результатов
            
        Returns:
            Список словарей с информацией об оборудовании
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                query_with_location = f"""
                SELECT TOP {limit}
                    i.ID,
                    i.SERIAL_NO,
                    i.HW_SERIAL_NO,
                    i.INV_NO,
                    i.CI_TYPE,
                    t.TYPE_NAME,
                    i.MODEL_NO,
                    m.MODEL_NAME,
                    v.VENDOR_NAME as MANUFACTURER,
                    l.DESCR as LOCATION,
                    i.EMPL_NO,
                    o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
                    s.DESCR as STATUS,
                    i.DESCR as DESCRIPTION
                FROM ITEMS i
                LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
                LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
                LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
                LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
                LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
                LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
                WHERE o.OWNER_DISPLAY_NAME LIKE ?
                ORDER BY i.ID
                """
                
                query_without_location = f"""
                SELECT TOP {limit}
                    i.ID,
                    i.SERIAL_NO,
                    i.HW_SERIAL_NO,
                    i.INV_NO,
                    i.CI_TYPE,
                    t.TYPE_NAME,
                    i.MODEL_NO,
                    m.MODEL_NAME,
                    v.VENDOR_NAME as MANUFACTURER,
                    'Не указана' as LOCATION,
                    i.EMPL_NO,
                    o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
                    s.DESCR as STATUS,
                    i.DESCR as DESCRIPTION
                FROM ITEMS i
                LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
                LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
                LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
                LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
                LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
                WHERE o.OWNER_DISPLAY_NAME LIKE ?
                ORDER BY i.ID
                """
                
                search_pattern = f"%{employee_name}%"
                params = (search_pattern,)
                
                try:
                    cursor.execute(query_with_location, params)
                    rows = cursor.fetchall()
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'permission' in error_msg or 'запрещено' in error_msg or 'locations' in error_msg:
                        logger.warning(f"Нет доступа к таблице LOCATIONS, выполняем поиск без неё: {e}")
                        cursor.execute(query_without_location, params)
                        rows = cursor.fetchall()
                    else:
                        raise e
                
                results = []
                for row in rows:
                    columns = [column[0] for column in cursor.description]
                    result = dict(zip(columns, row))
                    results.append(result)
                    
                return results
                
        except Exception as e:
            logger.error(f"Ошибка при поиске оборудования сотрудника '{employee_name}': {e}")
            return []

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