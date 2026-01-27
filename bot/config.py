#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конфигурация и константы для IT-invent Bot

Этот модуль содержит все настройки, константы и конфигурацию приложения.
Загружает переменные окружения и предоставляет централизованный доступ к настройкам.
"""

import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()


@dataclass
class TelegramConfig:
    """Конфигурация Telegram бота"""
    bot_token: str
    allowed_group_id: str
    allowed_users: List[str]


@dataclass
class APIConfig:
    """Конфигурация внешних API"""
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ocr_model: str = "qwen/qwen3-vl-8b-instruct"
    cartridge_analysis_model: str = "anthropic/claude-3.5-sonnet"


@dataclass
class DatabaseConfig:
    """Конфигурация баз данных"""
    available_databases: List[str]


@dataclass
class TransferConfig:
    """Конфигурация перемещения оборудования"""
    template_path: str
    acts_dir: str
    max_photos: int


@dataclass
class PaginationConfig:
    """Настройки пагинации"""
    items_per_page: int = 5
    employee_items_per_page: int = 3


@dataclass
class AppConfig:
    """Главная конфигурация приложения"""
    telegram: TelegramConfig
    api: APIConfig
    database: DatabaseConfig
    transfer: TransferConfig
    pagination: PaginationConfig


# Константы состояний ConversationHandler
class States:
    """Состояния для ConversationHandler"""
    FIND_WAIT_INPUT = 0
    FIND_BY_EMPLOYEE_WAIT_INPUT = 1
    EMPLOYEE_PAGINATION = 2
    UNFOUND_EMPLOYEE_INPUT = 3
    UNFOUND_LOCATION_INPUT = 4
    CHANGE_EMPLOYEE_INPUT = 5
    DB_SELECTION_MENU = 6
    DB_VIEW_PAGINATION = 7
    UNFOUND_TYPE_INPUT = 8
    UNFOUND_DESCRIPTION_INPUT = 9
    UNFOUND_BATCH_INPUT = 10
    UNFOUND_INVENTORY_INPUT = 11
    UNFOUND_IP_INPUT = 12
    UNFOUND_STATUS_INPUT = 13
    UNFOUND_BRANCH_INPUT = 14
    UNFOUND_MODEL_INPUT = 15
    TRANSFER_WAIT_PHOTOS = 16
    TRANSFER_NEW_EMPLOYEE = 17
    TRANSFER_NEW_BRANCH = 30
    TRANSFER_NEW_LOCATION = 31
    TRANSFER_CONFIRMATION = 18
    UNFOUND_CONFIRMATION = 19
    WORK_TYPE_SELECTION = 20
    WORK_BRANCH_INPUT = 21
    WORK_LOCATION_INPUT = 22
    WORK_PRINTER_MODEL_INPUT = 23
    WORK_CARTRIDGE_COLOR_SELECTION = 24
    WORK_COMPONENT_SELECTION = 29
    WORK_CONFIRMATION = 27
    EMPLOYEE_EMAIL_INPUT = 28
    WORK_BATTERY_SERIAL_INPUT = 32
    WORK_BATTERY_CONFIRMATION = 33


# Текстовые константы
class Messages:
    """Текстовые сообщения бота"""
    MAIN_MENU = 'Выберите режим поиска: по серийному номеру/фото или по сотруднику.'
    ACCESS_DENIED = (
        "❌ Доступ запрещен!\n\n"
        "Этот бот доступен только участникам определенной группы.\n"
        "Обратитесь к администратору для получения доступа."
    )
    PROCESSING_PHOTO = "🛠️ Фото обрабатывается, пожалуйста, подождите..."
    CREATING_ACT = "🛠️ Акт приема-передачи создается..."


# Ключи для хранения данных
class StorageKeys:
    """Ключи для context.user_data и context.bot_data"""
    DB_CONNECTION = 'db'
    SELECTED_DATABASE = 'selected_database'
    DB_VIEW_RESULTS = 'db_view_results'
    DB_VIEW_PAGE = 'db_view_page'
    EQUIPMENT_TYPES_LIST = 'equipment_types_list'
    EQUIPMENT_TYPES_PAGE = 'equipment_types_page'
    BRANCHES_LIST = 'branches_list'
    TEMP_PHOTOS = 'temp_photos'
    TEMP_SERIALS = 'temp_serials'
    UNFOUND_DATA = 'unfound_data'
    TRANSFER_DATA = 'transfer_data'
    CALLBACK_PAYLOADS = 'cb_payloads'
    DB_STATUS_MESSAGES = 'db_status_messages'


def load_config() -> AppConfig:
    """
    Загружает конфигурацию из переменных окружения
    
    Возвращает:
        AppConfig: Объект с полной конфигурацией приложения
        
    Исключения:
        ValueError: Если отсутствуют обязательные переменные окружения
    """
    # Telegram конфигурация
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен в .env")
    
    allowed_group_id = os.getenv("ALLOWED_GROUP_ID", "")
    allowed_users_str = os.getenv("ALLOWED_USERS", "")
    allowed_users = allowed_users_str.split(",") if allowed_users_str else []
    
    telegram_config = TelegramConfig(
        bot_token=bot_token,
        allowed_group_id=allowed_group_id,
        allowed_users=allowed_users
    )
    
    # API конфигурация
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        raise ValueError("OPENROUTER_API_KEY не установлен в .env")

    api_config = APIConfig(
        openrouter_api_key=openrouter_key,
        ocr_model=os.getenv("OCR_MODEL", "qwen/qwen3-vl-8b-instruct"),
        cartridge_analysis_model=os.getenv("CARTRIDGE_ANALYSIS_MODEL", "google/gemini-3-flash-preview")
    )
    
    # Database конфигурация
    available_dbs_str = os.getenv("AVAILABLE_DATABASES", "ITINVENT")
    available_dbs = [db.strip() for db in available_dbs_str.split(",")]
    
    database_config = DatabaseConfig(
        available_databases=available_dbs
    )
    
    # Transfer конфигурация
    transfer_config = TransferConfig(
        template_path=os.getenv("TRANSFER_TEMPLATE_PATH", "templates/transfer_act_template.docx"),
        acts_dir=os.getenv("TRANSFER_ACTS_DIR", "transfer_acts"),
        max_photos=int(os.getenv("MAX_TRANSFER_PHOTOS", "10"))
    )
    
    # Pagination конфигурация
    pagination_config = PaginationConfig()
    
    return AppConfig(
        telegram=telegram_config,
        api=api_config,
        database=database_config,
        transfer=transfer_config,
        pagination=pagination_config
    )


# Глобальный экземпляр конфигурации
try:
    config = load_config()
except ValueError as e:
    import logging
    logging.error(f"Ошибка загрузки конфигурации: {e}")
    raise
