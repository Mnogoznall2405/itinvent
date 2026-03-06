#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Менеджер баз данных для поддержки множественных подключений

Этот модуль предоставляет функциональность для управления множественными
базами данных, включая их конфигурацию, статистику и переключение между ними.

Основные возможности:
- Загрузка конфигураций множественных баз данных из .env
- Получение статистики по каждой базе данных
- Управление активной базой данных для пользователя
- Создание подключений к различным базам данных

Автор: AI Assistant
Версия: 1.0
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from bot.universal_database import UniversalInventoryDB, DatabaseConfig
from bot.local_json_store import load_json_data, save_json_data

logger = logging.getLogger(__name__)

@dataclass
class DatabaseInfo:
    """
    Информация о базе данных
    
    Атрибуты:
        name (str): Название базы данных
        config (DatabaseConfig): Конфигурация подключения
        display_name (str): Отображаемое название
        description (str): Описание базы данных
    """
    name: str
    config: DatabaseConfig
    display_name: str
    description: str = ""

class DatabaseManager:
    """
    Менеджер для управления множественными базами данных
    
    Предоставляет методы для загрузки конфигураций, получения статистики
    и управления активными подключениями к различным базам данных.
    """
    
    def __init__(self):
        """
        Инициализация менеджера баз данных

        Загружает конфигурации всех доступных баз данных из переменных окружения.
        """
        self.databases: Dict[str, DatabaseInfo] = {}
        self.user_selected_db: Dict[int, str] = {}  # user_id -> database_name
        self.user_assigned_db: Dict[int, str] = {}  # user_id -> назначенная база (только чтение)
        # Файл для хранения выборов пользователей - используем абсолютный путь
        base_dir = Path(__file__).parent.parent
        self.user_selection_file = str(base_dir / "data" / "user_db_selection.json")
        self.user_selection_name = Path(self.user_selection_file).name
        # Загружаем администраторов с доступом ко всем базам
        self.admin_user_ids = self._load_admin_users()
        self._load_database_configs()
        # Загружаем назначенные базы пользователей
        self._load_user_assignations()
    
    def _load_database_configs(self):
        """
        Загружает конфигурации баз данных из переменных окружения
        
        Ищет основную базу данных (SQL_SERVER_*) и дополнительные базы (DB_*_*)
        """
        # Загружаем основную базу данных ITINVENT
        main_config = DatabaseConfig(
            server=os.getenv('SQL_SERVER_HOST', ''),
            database=os.getenv('SQL_SERVER_DATABASE', ''),
            username=os.getenv('SQL_SERVER_USERNAME', ''),
            password=os.getenv('SQL_SERVER_PASSWORD', '')
        )
        
        if main_config.server and main_config.database:
            self.databases['ITINVENT'] = DatabaseInfo(
                name='ITINVENT',
                config=main_config,
                display_name='🏢 ITINVENT (Основная)',
                description='Основная база данных инвентаризации'
            )
            logger.info(f"Загружена основная база данных: ITINVENT")
        
        # Загружаем дополнительные базы данных
        available_dbs = os.getenv('AVAILABLE_DATABASES', 'ITINVENT').split(',')
        
        for db_name in available_dbs:
            db_name = db_name.strip()
            if db_name == 'ITINVENT':
                continue  # Уже загружена выше
            
            # Ищем конфигурацию для дополнительной базы
            # Имена переменных окружения используют дефисы как есть
            host = os.getenv(f'DB_{db_name}_HOST')
            database = os.getenv(f'DB_{db_name}_DATABASE')
            username = os.getenv(f'DB_{db_name}_USERNAME')
            password = os.getenv(f'DB_{db_name}_PASSWORD')
            
            logger.info(f"Поиск конфигурации для {db_name}: DB_{db_name}_HOST={host}, DB_{db_name}_DATABASE={database}")
            
            if host and database and username and password:
                config = DatabaseConfig(
                    server=host,
                    database=database,
                    username=username,
                    password=password
                )
                
                self.databases[db_name] = DatabaseInfo(
                    name=db_name,
                    config=config,
                    display_name=f'🗄️ {db_name}',
                    description=f'База данных {db_name}'
                )
                logger.info(f"Загружена дополнительная база данных: {db_name}")
            else:
                logger.warning(f"Не удалось загрузить базу данных {db_name}: отсутствуют параметры подключения (host={host}, database={database}, username={username}, password={'***' if password else None})")
        
        logger.info(f"Загружено {len(self.databases)} баз данных: {list(self.databases.keys())}")

    def _load_admin_users(self) -> set:
        """
        Загружает ID администраторов из переменной окружения

        Возвращает:
            set: Множество ID администраторов
        """
        try:
            import os
            admin_ids_str = os.getenv('ADMIN_USER_IDS', '')
            if admin_ids_str:
                admin_ids = set()
                for id_str in admin_ids_str.split(','):
                    try:
                        admin_ids.add(int(id_str.strip()))
                    except ValueError:
                        continue
                logger.info(f"Загружены администраторы: {admin_ids}")
                return admin_ids
        except Exception as e:
            logger.warning(f"Ошибка при загрузке администраторов: {e}")
        return set()

    def is_admin_user(self, user_id: int) -> bool:
        """
        Проверяет, является ли пользователь администратором

        Параметры:
            user_id (int): ID пользователя Telegram

        Возвращает:
            bool: True если пользователь администратор
        """
        return user_id in self.admin_user_ids
    
    def get_available_databases(self) -> List[str]:
        """
        Возвращает список названий всех доступных баз данных
        
        Возвращает:
            List[str]: Список названий баз данных
        """
        return list(self.databases.keys())
    
    def get_available_database_info(self) -> List[DatabaseInfo]:
        """
        Возвращает список всех доступных баз данных с полной информацией
        
        Возвращает:
            List[DatabaseInfo]: Список информации о базах данных
        """
        return list(self.databases.values())
    
    def get_database_config(self, db_name: str) -> Optional[DatabaseConfig]:
        """
        Получает конфигурацию для указанной базы данных
        
        Параметры:
            db_name (str): Название базы данных
            
        Возвращает:
            Optional[DatabaseConfig]: Конфигурация базы данных или None
        """
        db_info = self.databases.get(db_name)
        return db_info.config if db_info else None
    
    def get_user_assigned_database(self, user_id: int) -> Optional[str]:
        """
        Получает назначенную базу данных для пользователя (только чтение)

        Параметры:
            user_id (int): ID пользователя Telegram

        Возвращает:
            Optional[str]: Название назначенной базы данных или None
        """
        return self.user_assigned_db.get(user_id)

    def set_user_database(self, user_id: int, db_name: str) -> bool:
        """
        Устанавливает активную базу данных для пользователя

        Параметры:
            user_id (int): ID пользователя Telegram
            db_name (str): Название базы данных

        Возвращает:
            bool: True если база данных установлена успешно
        """
        # Админы могут переключаться между всеми базами
        if not self.is_admin_user(user_id):
            # Проверяем: обычный пользователь может работать только в своей назначенной базе
            assigned_db = self.user_assigned_db.get(user_id)
            if assigned_db and db_name != assigned_db:
                logger.warning(f"Пользователь {user_id} пытается переключиться на {db_name}, но назначен на {assigned_db}")
                return False

        if db_name in self.databases:
            self.user_selected_db[user_id] = db_name
            # Сохраняем выбор пользователя на диск
            self._save_user_selections()
            return True
        return False
    
    def get_user_database(self, user_id: int) -> str:
        """
        Получает активную базу данных для пользователя
        
        Параметры:
            user_id (int): ID пользователя Telegram
            
        Возвращает:
            str: Название активной базы данных (по умолчанию ITINVENT)
        """
        return self.user_selected_db.get(user_id, 'ITINVENT')
    
    def get_user_database_config(self, user_id: int) -> Optional[DatabaseConfig]:
        """
        Получает конфигурацию активной базы данных для пользователя
        
        Параметры:
            user_id (int): ID пользователя Telegram
            
        Возвращает:
            Optional[DatabaseConfig]: Конфигурация активной базы данных
        """
        db_name = self.get_user_database(user_id)
        return self.get_database_config(db_name)
    
    def create_database_connection(self, user_id: int) -> Optional[UniversalInventoryDB]:
        """
        Создает подключение к активной базе данных пользователя
        
        Параметры:
            user_id (int): ID пользователя Telegram
            
        Возвращает:
            Optional[UniversalInventoryDB]: Объект для работы с базой данных
        """
        config = self.get_user_database_config(user_id)
        if config:
            try:
                return UniversalInventoryDB(config)
            except Exception as e:
                logger.error(f"Ошибка создания подключения к БД для пользователя {user_id}: {e}")
        return None
    
    def get_database_statistics(self, db_name: str) -> Dict[str, Any]:
        """
        Получает статистику по указанной базе данных
        
        Параметры:
            db_name (str): Название базы данных
            
        Возвращает:
            Dict[str, Any]: Статистика базы данных
        """
        config = self.get_database_config(db_name)
        if not config:
            return {'error': 'База данных не найдена'}
        
        db = None
        try:
            db = UniversalInventoryDB(config)
            
            # Получаем базовую статистику
            stats = {
                'name': db_name,
                'display_name': self.databases[db_name].display_name,
                'status': '🟢 Подключена',
                'total_items': 0,
                'total_employees': 0,
                'connection_test': False
            }
            
            # Тестируем подключение и получаем статистику
            test_results = db.test_database_connection()
            stats['connection_test'] = test_results.get('connection', False)
            
            if stats['connection_test']:
                # Получаем полную статистику оборудования
                equipment_stats = db.get_equipment_statistics()
                if equipment_stats:
                    stats['total_items'] = equipment_stats.get('total_items', 'Н/Д')
                    stats['total_employees'] = equipment_stats.get('total_employees', 'Н/Д')
                    stats['equipment_types'] = equipment_stats.get('equipment_types', [])
                else:
                    # Fallback к старому методу если get_equipment_statistics не работает
                    conn = db._get_connection()
                    cursor = conn.cursor()
                    
                    try:
                        cursor.execute("SELECT COUNT(*) FROM ITEMS")
                        stats['total_items'] = cursor.fetchone()[0]
                    except Exception as e:
                        logger.warning(f"Не удалось получить количество ITEMS для {db_name}: {e}")
                        stats['total_items'] = 'Н/Д'
                    
                    try:
                        cursor.execute("SELECT COUNT(*) FROM OWNERS")
                        stats['total_employees'] = cursor.fetchone()[0]
                    except Exception as e:
                        logger.warning(f"Не удалось получить количество OWNERS для {db_name}: {e}")
                        stats['total_employees'] = 'Н/Д'
                    
                    stats['equipment_types'] = []
                    cursor.close()
            else:
                stats['status'] = '🔴 Ошибка подключения'
            
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики для БД {db_name}: {e}")
            return {
                'name': db_name,
                'display_name': self.databases[db_name].display_name,
                'status': '🔴 Ошибка подключения',
                'error': str(e)
            }
        finally:
            # Закрываем соединение
            if db:
                db.close_connection()
    
    def get_all_statistics(self) -> List[Dict[str, Any]]:
        """
        Получает статистику по всем доступным базам данных
        
        Возвращает:
            List[Dict[str, Any]]: Список статистики всех баз данных
        """
        stats = []
        for db_name in self.databases.keys():
            stats.append(self.get_database_statistics(db_name))
        return stats

    def _load_user_assignations(self):
        """Загружает назначенные базы пользователей из файла user_db_selection.json."""
        try:
            data = load_json_data(self.user_selection_name, default_content={})
            if isinstance(data, dict):
                for k, v in data.items():
                    try:
                        uid = int(k)
                    except Exception:
                        continue
                    # Сохраняем назначенную базу (только чтение)
                    self.user_assigned_db[uid] = v
                    # Также устанавливаем как текущую по умолчанию
                    self.user_selected_db[uid] = v
            logger.info(f"Загружены назначения баз для {len(self.user_assigned_db)} пользователей")
        except FileNotFoundError:
            # Файл отсутствует — это нормально при первом запуске
            logger.warning(f"Файл {self.user_selection_file} не найден")
        except Exception as e:
            logger.warning(f"Не удалось загрузить назначения баз пользователей: {e}")

    def _load_user_selections(self):
        """Загружает сохранённые выборы БД пользователей из файла."""
        try:
            data = load_json_data(self.user_selection_name, default_content={})
            if isinstance(data, dict):
                for k, v in data.items():
                    try:
                        uid = int(k)
                    except Exception:
                        continue
                    # При восстановлении просто записываем; актуальность БД проверяется при создании соединения
                    self.user_selected_db[uid] = v
        except FileNotFoundError:
            # Файл отсутствует — это нормально при первом запуске
            pass
        except Exception as e:
            logger.warning(f"Не удалось загрузить выбор баз пользователей: {e}")
    
    def _save_user_selections(self):
        """Сохраняет текущие выборы БД пользователей в файл."""
        try:
            to_save = {str(k): v for k, v in self.user_selected_db.items()}
            save_json_data(self.user_selection_name, to_save)
        except Exception as e:
            logger.warning(f"Не удалось сохранить выбор баз пользователей: {e}")

# Глобальный экземпляр менеджера баз данных
database_manager = DatabaseManager()
