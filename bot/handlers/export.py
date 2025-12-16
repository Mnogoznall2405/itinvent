#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчики экспорта данных
Экспорт ненайденного оборудования и перемещений, отправка на email.
"""
import logging
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import States, Messages
from bot.utils.decorators import require_user_access, handle_errors
from bot.utils.keyboards import create_main_menu_keyboard
from database_manager import database_manager
from equipment_data_manager import EquipmentDataManager
from email_sender import send_export_email

logger = logging.getLogger(__name__)

# Глобальный менеджер данных
equipment_manager = EquipmentDataManager()


@require_user_access
async def show_export_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню экспорта данных
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Состояние для ConversationHandler
    """
    keyboard = [
        [InlineKeyboardButton("📦 Экспорт ненайденного оборудования", callback_data="export_type:unfound")],
        [InlineKeyboardButton("🔄 Экспорт перемещений", callback_data="export_type:transfers")],
        [InlineKeyboardButton("🖨️ Экспорт замен картриджей", callback_data="export_type:cartridges")],
        [InlineKeyboardButton("📦 Экспорт установок оборудования", callback_data="export_type:installations")],
        [InlineKeyboardButton("🔙 Назад в главное меню", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📊 <b>Экспорт данных</b>\n\n"
        "Выберите тип данных для экспорта:",
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    return States.DB_SELECTION_MENU  # Используем существующее состояние


@handle_errors
async def handle_export_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор типа экспорта
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data.startswith("export_type:"):
        export_type = callback_data.split(":")[1]
        context.user_data['export_type'] = export_type
        
        # Показываем выбор периода
        return await show_export_period(update, context)
    
    elif callback_data == "back_to_main":
        await query.edit_message_text("✅ Возврат в главное меню")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=Messages.MAIN_MENU,
            reply_markup=create_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    return States.DB_SELECTION_MENU


async def show_export_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показывает выбор периода экспорта
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    export_type = context.user_data.get('export_type', 'unfound')
    
    keyboard = [
        [InlineKeyboardButton("📅 Все данные", callback_data="export_period:full")],
        [InlineKeyboardButton("🆕 Только новые", callback_data="export_period:new")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_export_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    type_names = {
        'unfound': 'ненайденного оборудования',
        'transfers': 'перемещений',
        'cartridges': 'замен картриджей',
        'installations': 'установок оборудования'
    }
    type_name = type_names.get(export_type, 'данных')
    
    await update.callback_query.edit_message_text(
        f"📊 <b>Экспорт {type_name}</b>\n\n"
        f"Выберите период:",
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    return States.DB_SELECTION_MENU


@handle_errors
async def handle_export_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор периода экспорта
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data.startswith("export_period:"):
        period = callback_data.split(":")[1]
        context.user_data['export_period'] = period
        
        # Показываем выбор базы данных
        return await show_export_database(update, context)
    
    elif callback_data == "back_to_export_menu":
        # Возврат к выбору типа экспорта
        keyboard = [
            [InlineKeyboardButton("📦 Экспорт ненайденного оборудования", callback_data="export_type:unfound")],
            [InlineKeyboardButton("🔄 Экспорт перемещений", callback_data="export_type:transfers")],
            [InlineKeyboardButton("🔙 Назад в главное меню", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📊 <b>Экспорт данных</b>\n\n"
            "Выберите тип данных для экспорта:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    return States.DB_SELECTION_MENU


async def show_export_database(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показывает выбор базы данных для экспорта
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    # Получаем список доступных БД
    available_databases = database_manager.get_available_databases()
    
    keyboard = [[InlineKeyboardButton("📦 Все базы", callback_data="export_db:all")]]
    
    for db_name in available_databases:
        keyboard.append([InlineKeyboardButton(f"🏛 {db_name}", callback_data=f"export_db:{db_name}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_period")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "📂 <b>Выбор базы данных</b>\n\n"
        "Выберите базу данных для экспорта:",
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    return States.DB_SELECTION_MENU


@handle_errors
async def handle_export_database(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор БД и выполняет экспорт
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data.startswith("export_db:"):
        db_name = callback_data.split(":")[1]
        
        export_type = context.user_data.get('export_type', 'unfound')
        period = context.user_data.get('export_period', 'full')
        
        # Выполняем экспорт
        await query.edit_message_text("⏳ Подготовка данных для экспорта...")
        
        try:
            only_new = (period == 'new')
            db_filter = None if db_name == 'all' else db_name
            
            if export_type == 'unfound':
                # Экспорт ненайденного оборудования
                exported_files = equipment_manager.export_to_csv(
                    date_filter=None,
                    db_filter=db_filter,
                    only_new=only_new
                )
                
                unfound_csv = exported_files.get('unfound')
                
                if unfound_csv and os.path.exists(unfound_csv):
                    # Сохраняем путь к файлу
                    context.user_data['export_file'] = unfound_csv
                    
                    # Показываем опции доставки
                    return await show_delivery_options(update, context, unfound_csv)
                else:
                    await query.edit_message_text(
                        "❌ Нет данных для экспорта или ошибка создания файла."
                    )
                    return ConversationHandler.END
            
            elif export_type == 'transfers':
                # Экспорт перемещений
                text_file = equipment_manager.export_transfers_to_text(
                    date_filter=None,
                    db_filter=db_filter,
                    only_new=only_new
                )
                
                if text_file and os.path.exists(text_file):
                    context.user_data['export_file'] = text_file
                    return await show_delivery_options(update, context, text_file)
                else:
                    await query.edit_message_text(
                        "❌ Нет данных для экспорта или ошибка создания файла."
                    )
                    return ConversationHandler.END
            
            elif export_type == 'cartridges':
                # Экспорт замен картриджей
                excel_file = export_cartridges_to_excel(only_new=only_new, db_filter=db_filter)
                
                if excel_file and os.path.exists(excel_file):
                    context.user_data['export_file'] = excel_file
                    return await show_delivery_options(update, context, excel_file)
                else:
                    await query.edit_message_text(
                        "❌ Нет данных для экспорта или ошибка создания файла."
                    )
                    return ConversationHandler.END
            
            elif export_type == 'installations':
                # Экспорт установок оборудования
                excel_file = export_installations_to_excel(only_new=only_new, db_filter=db_filter)
                
                if excel_file and os.path.exists(excel_file):
                    context.user_data['export_file'] = excel_file
                    return await show_delivery_options(update, context, excel_file)
                else:
                    await query.edit_message_text(
                        "❌ Нет данных для экспорта или ошибка создания файла."
                    )
                    return ConversationHandler.END
        
        except Exception as e:
            logger.error(f"Ошибка при экспорте: {e}")
            await query.edit_message_text(
                f"❌ Ошибка при экспорте: {str(e)}"
            )
            return ConversationHandler.END
    
    elif callback_data == "back_to_period":
        return await show_export_period(update, context)
    
    return States.DB_SELECTION_MENU


async def show_delivery_options(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str) -> int:
    """
    Показывает опции доставки файла
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        file_path: Путь к экспортированному файлу
        
    Возвращает:
        int: Следующее состояние
    """
    # Получаем размер файла
    file_size = os.path.getsize(file_path)
    size_kb = round(file_size / 1024, 1)
    filename = os.path.basename(file_path)
    
    keyboard = [
        [InlineKeyboardButton("💬 Отправить в чат", callback_data="delivery:chat")],
        [InlineKeyboardButton("📧 Отправить на email", callback_data="delivery:email")],
        [InlineKeyboardButton("🔙 Назад в главное меню", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        f"✅ <b>Файл создан</b>\n\n"
        f"📄 Имя: {filename}\n"
        f"📊 Размер: {size_kb} КБ\n\n"
        f"Выберите способ доставки:",
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    return States.DB_SELECTION_MENU


@handle_errors
async def handle_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор способа доставки
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: ConversationHandler.END
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data == "delivery:chat":
        # Отправка в чат
        file_path = context.user_data.get('export_file')
        
        if file_path and os.path.exists(file_path):
            await query.edit_message_text("📤 Отправка файла...")
            
            try:
                with open(file_path, 'rb') as file:
                    await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=file,
                        filename=os.path.basename(file_path),
                        caption="✅ Экспортированные данные"
                    )
                
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="✅ Файл успешно отправлен!"
                )
            
            except Exception as e:
                logger.error(f"Ошибка отправки файла: {e}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"❌ Ошибка отправки файла: {str(e)}"
                )
        else:
            await query.edit_message_text("❌ Файл не найден.")
        
        return ConversationHandler.END
    
    elif callback_data == "delivery:email":
        # Запрос email адреса
        await query.edit_message_text(
            "📧 <b>Отправка на email</b>\n\n"
            "Введите email адрес для отправки файла:",
            parse_mode='HTML'
        )
        
        return States.UNFOUND_EMPLOYEE_INPUT  # Используем существующее состояние для ввода текста
    
    elif callback_data == "back_to_main":
        await query.edit_message_text("✅ Возврат в главное меню")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=Messages.MAIN_MENU,
            reply_markup=create_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    return ConversationHandler.END


@handle_errors
async def handle_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает ввод email адреса и отправляет файл
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: ConversationHandler.END
    """
    email = update.message.text.strip()
    
    # Простая валидация email
    import re
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        await update.message.reply_text(
            "❌ Некорректный email адрес. Попробуйте еще раз."
        )
        return States.UNFOUND_EMPLOYEE_INPUT
    
    file_path = context.user_data.get('export_file')
    export_type = context.user_data.get('export_type', 'export')
    
    if not file_path or not os.path.exists(file_path):
        await update.message.reply_text("❌ Файл не найден.")
        return ConversationHandler.END
    
    await update.message.reply_text("📤 Отправка на email...")
    
    try:
        # Отправляем email
        success = send_export_email(
            recipient=email,
            csv_files={export_type: file_path},
            subject="Экспорт данных IT-invent",
            body="Во вложении экспортированные данные из системы IT-invent."
        )
        
        if success:
            await update.message.reply_text(
                f"✅ Файл успешно отправлен на {email}!"
            )
        else:
            await update.message.reply_text(
                "❌ Ошибка отправки email. Проверьте настройки SMTP."
            )
    
    except Exception as e:
        logger.error(f"Ошибка отправки email: {e}")
        await update.message.reply_text(
            f"❌ Ошибка отправки email: {str(e)}"
        )
    
    return ConversationHandler.END



def export_cartridges_to_excel(only_new: bool = False, db_filter: str = None) -> str:
    """
    Экспортирует замены картриджей в Excel
    
    Параметры:
        only_new: Экспортировать только новые записи
        db_filter: Фильтр по базе данных (None = все базы)
        
    Возвращает:
        str: Путь к созданному файлу
    """
    import json
    import pandas as pd
    from pathlib import Path
    from datetime import datetime
    
    try:
        file_path = Path("data/cartridge_replacements.json")
        
        if not file_path.exists():
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not data:
            return None
        
        # Фильтруем по БД если указан фильтр
        if db_filter:
            data = [item for item in data if item.get('db_name') == db_filter]
        
        if not data:
            return None
        
        # Создаем DataFrame
        df = pd.DataFrame(data)
        
        # Добавляем db_name если отсутствует (для старых записей)
        if 'db_name' not in df.columns:
            df['db_name'] = 'ITINVENT'
        
        # Форматируем timestamp
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Переименовываем колонки
        column_names = {
            'branch': 'Филиал',
            'location': 'Локация',
            'printer_model': 'Модель принтера',
            'cartridge_color': 'Цвет картриджа',
            'db_name': 'База данных',
            'timestamp': 'Дата и время'
        }
        df = df.rename(columns=column_names)
        
        # Упорядочиваем колонки
        desired_order = ['Дата и время', 'База данных', 'Филиал', 'Локация', 'Модель принтера', 'Цвет картриджа']
        existing_cols = [col for col in desired_order if col in df.columns]
        df = df[existing_cols]
        
        # Создаем имя файла
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"exports/cartridge_replacements_{timestamp}.xlsx"
        
        # Создаем директорию если не существует
        Path("exports").mkdir(exist_ok=True)
        
        # Сохраняем в Excel
        df.to_excel(output_file, index=False, engine='openpyxl')
        
        logger.info(f"Экспорт замен картриджей завершен: {output_file}")
        return output_file
        
    except Exception as e:
        logger.error(f"Ошибка экспорта замен картриджей: {e}")
        return None


def export_installations_to_excel(only_new: bool = False, db_filter: str = None) -> str:
    """
    Экспортирует установки оборудования в Excel
    
    Параметры:
        only_new: Экспортировать только новые записи
        db_filter: Фильтр по базе данных (None = все базы)
        
    Возвращает:
        str: Путь к созданному файлу
    """
    import json
    import pandas as pd
    from pathlib import Path
    from datetime import datetime
    
    try:
        file_path = Path("data/equipment_installations.json")
        
        if not file_path.exists():
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not data:
            return None
        
        # Фильтруем по БД если указан фильтр
        if db_filter:
            data = [item for item in data if item.get('db_name') == db_filter]
        
        if not data:
            return None
        
        # Создаем DataFrame
        df = pd.DataFrame(data)
        
        # Добавляем db_name если отсутствует (для старых записей)
        if 'db_name' not in df.columns:
            df['db_name'] = 'ITINVENT'
        
        # Форматируем timestamp
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Переименовываем колонки
        column_names = {
            'branch': 'Филиал',
            'location': 'Локация',
            'equipment_type': 'Тип оборудования',
            'equipment_model': 'Модель',
            'db_name': 'База данных',
            'timestamp': 'Дата и время'
        }
        df = df.rename(columns=column_names)
        
        # Упорядочиваем колонки
        desired_order = ['Дата и время', 'База данных', 'Филиал', 'Локация', 'Тип оборудования', 'Модель']
        existing_cols = [col for col in desired_order if col in df.columns]
        df = df[existing_cols]
        
        # Создаем имя файла
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"exports/equipment_installations_{timestamp}.xlsx"
        
        # Создаем директорию если не существует
        Path("exports").mkdir(exist_ok=True)
        
        # Сохраняем в Excel
        df.to_excel(output_file, index=False, engine='openpyxl')
        
        logger.info(f"Экспорт установок оборудования завершен: {output_file}")
        return output_file
        
    except Exception as e:
        logger.error(f"Ошибка экспорта установок оборудования: {e}")
        return None
