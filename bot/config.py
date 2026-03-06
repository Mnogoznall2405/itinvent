#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ Рё РєРѕРЅСЃС‚Р°РЅС‚С‹ РґР»СЏ IT-invent Bot

Р­С‚РѕС‚ РјРѕРґСѓР»СЊ СЃРѕРґРµСЂР¶РёС‚ РІСЃРµ РЅР°СЃС‚СЂРѕР№РєРё, РєРѕРЅСЃС‚Р°РЅС‚С‹ Рё РєРѕРЅС„РёРіСѓСЂР°С†РёСЋ РїСЂРёР»РѕР¶РµРЅРёСЏ.
Р—Р°РіСЂСѓР¶Р°РµС‚ РїРµСЂРµРјРµРЅРЅС‹Рµ РѕРєСЂСѓР¶РµРЅРёСЏ Рё РїСЂРµРґРѕСЃС‚Р°РІР»СЏРµС‚ С†РµРЅС‚СЂР°Р»РёР·РѕРІР°РЅРЅС‹Р№ РґРѕСЃС‚СѓРї Рє РЅР°СЃС‚СЂРѕР№РєР°Рј.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Р—Р°РіСЂСѓР·РєР° РїРµСЂРµРјРµРЅРЅС‹С… РѕРєСЂСѓР¶РµРЅРёСЏ
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_ENV_PATH = PROJECT_ROOT / '.env'
load_dotenv(str(ROOT_ENV_PATH))


@dataclass
class TelegramConfig:
    """РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ Telegram Р±РѕС‚Р°"""
    bot_token: str
    allowed_group_id: str
    allowed_users: List[str]


@dataclass
class APIConfig:
    """РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ РІРЅРµС€РЅРёС… API"""
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ocr_model: str = "qwen/qwen3-vl-8b-instruct"
    cartridge_analysis_model: str = "google/gemini-3-flash-preview"


@dataclass
class DatabaseConfig:
    """РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ Р±Р°Р· РґР°РЅРЅС‹С…"""
    available_databases: List[str]


@dataclass
class TransferConfig:
    """РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ РїРµСЂРµРјРµС‰РµРЅРёСЏ РѕР±РѕСЂСѓРґРѕРІР°РЅРёСЏ"""
    template_path: str
    acts_dir: str
    max_photos: int


@dataclass
class PaginationConfig:
    """РќР°СЃС‚СЂРѕР№РєРё РїР°РіРёРЅР°С†РёРё"""
    items_per_page: int = 5
    employee_items_per_page: int = 3


@dataclass
class AppConfig:
    """Р“Р»Р°РІРЅР°СЏ РєРѕРЅС„РёРіСѓСЂР°С†РёСЏ РїСЂРёР»РѕР¶РµРЅРёСЏ"""
    telegram: TelegramConfig
    api: APIConfig
    database: DatabaseConfig
    transfer: TransferConfig
    pagination: PaginationConfig


# РљРѕРЅСЃС‚Р°РЅС‚С‹ СЃРѕСЃС‚РѕСЏРЅРёР№ ConversationHandler
class States:
    """РЎРѕСЃС‚РѕСЏРЅРёСЏ РґР»СЏ ConversationHandler"""
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
    UNFOUND_EMPLOYEE_CONFIRMATION = 39
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
    WORK_PC_CLEANING_SERIAL_INPUT = 34
    WORK_PC_CLEANING_CONFIRMATION = 35
    WORK_COMPONENT_SERIAL_INPUT = 37
    WORK_COMPONENT_CONFIRMATION = 38
    WORK_SUCCESS = 36


# РўРµРєСЃС‚РѕРІС‹Рµ РєРѕРЅСЃС‚Р°РЅС‚С‹
class Messages:
    """РўРµРєСЃС‚РѕРІС‹Рµ СЃРѕРѕР±С‰РµРЅРёСЏ Р±РѕС‚Р°"""
    MAIN_MENU = 'Р’С‹Р±РµСЂРёС‚Рµ СЂРµР¶РёРј РїРѕРёСЃРєР°: РїРѕ СЃРµСЂРёР№РЅРѕРјСѓ РЅРѕРјРµСЂСѓ/С„РѕС‚Рѕ РёР»Рё РїРѕ СЃРѕС‚СЂСѓРґРЅРёРєСѓ.'
    ACCESS_DENIED = (
        "вќЊ Р”РѕСЃС‚СѓРї Р·Р°РїСЂРµС‰РµРЅ!\n\n"
        "Р­С‚РѕС‚ Р±РѕС‚ РґРѕСЃС‚СѓРїРµРЅ С‚РѕР»СЊРєРѕ СѓС‡Р°СЃС‚РЅРёРєР°Рј РѕРїСЂРµРґРµР»РµРЅРЅРѕР№ РіСЂСѓРїРїС‹.\n"
        "РћР±СЂР°С‚РёС‚РµСЃСЊ Рє Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ РґР»СЏ РїРѕР»СѓС‡РµРЅРёСЏ РґРѕСЃС‚СѓРїР°."
    )
    PROCESSING_PHOTO = "рџ› пёЏ Р¤РѕС‚Рѕ РѕР±СЂР°Р±Р°С‚С‹РІР°РµС‚СЃСЏ, РїРѕР¶Р°Р»СѓР№СЃС‚Р°, РїРѕРґРѕР¶РґРёС‚Рµ..."
    CREATING_ACT = "рџ› пёЏ РђРєС‚ РїСЂРёРµРјР°-РїРµСЂРµРґР°С‡Рё СЃРѕР·РґР°РµС‚СЃСЏ..."


# РљР»СЋС‡Рё РґР»СЏ С…СЂР°РЅРµРЅРёСЏ РґР°РЅРЅС‹С…
class StorageKeys:
    """РљР»СЋС‡Рё РґР»СЏ context.user_data Рё context.bot_data"""
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
    Р—Р°РіСЂСѓР¶Р°РµС‚ РєРѕРЅС„РёРіСѓСЂР°С†РёСЋ РёР· РїРµСЂРµРјРµРЅРЅС‹С… РѕРєСЂСѓР¶РµРЅРёСЏ
    
    Р’РѕР·РІСЂР°С‰Р°РµС‚:
        AppConfig: РћР±СЉРµРєС‚ СЃ РїРѕР»РЅРѕР№ РєРѕРЅС„РёРіСѓСЂР°С†РёРµР№ РїСЂРёР»РѕР¶РµРЅРёСЏ
        
    РСЃРєР»СЋС‡РµРЅРёСЏ:
        ValueError: Р•СЃР»Рё РѕС‚СЃСѓС‚СЃС‚РІСѓСЋС‚ РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Рµ РїРµСЂРµРјРµРЅРЅС‹Рµ РѕРєСЂСѓР¶РµРЅРёСЏ
    """
    # Telegram РєРѕРЅС„РёРіСѓСЂР°С†РёСЏ
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ РІ .env")
    
    allowed_group_id = os.getenv("ALLOWED_GROUP_ID", "")
    allowed_users_str = os.getenv("ALLOWED_USERS", "")
    allowed_users = allowed_users_str.split(",") if allowed_users_str else []
    
    telegram_config = TelegramConfig(
        bot_token=bot_token,
        allowed_group_id=allowed_group_id,
        allowed_users=allowed_users
    )
    
    # API РєРѕРЅС„РёРіСѓСЂР°С†РёСЏ
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        raise ValueError("OPENROUTER_API_KEY РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ РІ .env")

    api_config = APIConfig(
        openrouter_api_key=openrouter_key,
        ocr_model=os.getenv("OCR_MODEL", "qwen/qwen3-vl-8b-instruct"),
        cartridge_analysis_model=os.getenv("CARTRIDGE_ANALYSIS_MODEL", "google/gemini-3-flash-preview")
    )
    
    # Database РєРѕРЅС„РёРіСѓСЂР°С†РёСЏ
    available_dbs_str = os.getenv("AVAILABLE_DATABASES", "ITINVENT")
    available_dbs = [db.strip() for db in available_dbs_str.split(",")]
    
    database_config = DatabaseConfig(
        available_databases=available_dbs
    )
    
    # Transfer РєРѕРЅС„РёРіСѓСЂР°С†РёСЏ
    transfer_config = TransferConfig(
        template_path=os.getenv("TRANSFER_TEMPLATE_PATH", "templates/transfer_act_template.docx"),
        acts_dir=os.getenv("TRANSFER_ACTS_DIR", "transfer_acts"),
        max_photos=int(os.getenv("MAX_TRANSFER_PHOTOS", "10"))
    )
    
    # Pagination РєРѕРЅС„РёРіСѓСЂР°С†РёСЏ
    pagination_config = PaginationConfig()
    
    return AppConfig(
        telegram=telegram_config,
        api=api_config,
        database=database_config,
        transfer=transfer_config,
        pagination=pagination_config
    )


# Р“Р»РѕР±Р°Р»СЊРЅС‹Р№ СЌРєР·РµРјРїР»СЏСЂ РєРѕРЅС„РёРіСѓСЂР°С†РёРё
try:
    config = load_config()
except ValueError as e:
    import logging
    logging.error(f"РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё РєРѕРЅС„РёРіСѓСЂР°С†РёРё: {e}")
    raise

