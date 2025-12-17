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
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

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
        [InlineKeyboardButton("🔧 Экспорт замен комплектующих", callback_data="export_type:cartridges")],
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

    # Разные клавиатуры для разных типов экспорта
    if export_type == 'cartridges':
        # Для картриджей - выбор периода без выбора базы
        keyboard = [
            [InlineKeyboardButton("📅 За последний месяц", callback_data="export_period:1month")],
            [InlineKeyboardButton("📊 За последние 3 месяца", callback_data="export_period:3months")],
            [InlineKeyboardButton("📕 За весь период", callback_data="export_period:all")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_export_menu")]
        ]
    else:
        # Для остальных типов - стандартный выбор
        keyboard = [
            [InlineKeyboardButton("📅 Все данные", callback_data="export_period:full")],
            [InlineKeyboardButton("🆕 Только новые", callback_data="export_period:new")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_export_menu")]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    type_names = {
        'unfound': 'ненайденного оборудования',
        'transfers': 'перемещений',
        'cartridges': 'замен комплектующих',
        'installations': 'установок оборудования'
    }
    type_name = type_names.get(export_type, 'данных')

    period_text = "Выберите период для экспорта:"
    if export_type == 'cartridges':
        period_text = "Выберите период для анализа картриджей:"

    await update.callback_query.edit_message_text(
        f"📊 <b>Экспорт {type_name}</b>\n\n"
        f"{period_text}",
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
    export_type = context.user_data.get('export_type', 'unfound')

    if callback_data.startswith("export_period:"):
        period = callback_data.split(":")[1]
        context.user_data['export_period'] = period

        # Для картриджей - прямой экспорт без выбора базы
        if export_type == 'cartridges':
            return await handle_cartridge_export_directly(update, context, period)
        else:
            # Для остальных типов - показываем выбор базы данных
            return await show_export_database(update, context)

    elif callback_data == "back_to_export_menu":
        # Возврат к выбору типа экспорта
        keyboard = [
            [InlineKeyboardButton("📦 Экспорт ненайденного оборудования", callback_data="export_type:unfound")],
            [InlineKeyboardButton("🔄 Экспорт перемещений", callback_data="export_type:transfers")],
            [InlineKeyboardButton("🔧 Экспорт замен комплектующих", callback_data="export_type:cartridges")],
            [InlineKeyboardButton("📦 Экспорт установок оборудования", callback_data="export_type:installations")],
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


@handle_errors
async def handle_cartridge_export_directly(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str) -> int:
    """
    Обрабатывает прямой экспорт картриджей без выбора базы данных

    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        period: Выбранный период

    Возвращает:
        int: Следующее состояние
    """
    query = update.callback_query
    await query.edit_message_text("⏳ Анализ данных о заменах комплектующих...")

    try:
        # Выполняем экспорт с LLM-структурированием
        excel_file = await export_components_to_excel_structured(period=period, db_filter=None)

        if excel_file and os.path.exists(excel_file):
            context.user_data['export_file'] = excel_file
            return await show_delivery_options(update, context, excel_file)
        else:
            await query.edit_message_text(
                "❌ Нет данных для экспорта или ошибка создания файла."
            )
            return ConversationHandler.END

    except Exception as e:
        logger.error(f"Ошибка при экспорте картриджей: {e}")
        await query.edit_message_text(
            f"❌ Ошибка при экспорте: {str(e)}"
        )
        return ConversationHandler.END


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
                # Экспорт замен комплектующих
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
    Экспортирует замены комплектующих МФУ в Excel

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
        
        # Создаем отображаемые имена компонентов
        def get_component_name(component_type):
            names = {
                'cartridge': 'Картридж',
                'fuser': 'Фьюзер (печка)',
                'drum': 'Фотобарабан',  # Обратная совместимость
                'photoconductor': 'Фотобарабан',
                'waste_toner': 'Контейнер отраб. тонера',
                'transfer_belt': 'Трансферный ремень'
            }
            return names.get(component_type, component_type)

        # Если есть component_type, используем новые поля
        if 'component_type' in df.columns:
            # Создаем колонку с отображаемыми именами компонентов
            df['Компонент'] = df['component_type'].apply(get_component_name)

            # Переименовываем колонки
            column_names = {
                'branch': 'Филиал',
                'location': 'Локация',
                'printer_model': 'Модель принтера',
                'component_type': 'Тип компонента',
                'component_color': 'Цвет',
                'db_name': 'База данных',
                'timestamp': 'Дата и время'
            }
            df = df.rename(columns=column_names)

            # Упорядочиваем колонки для нового формата
            desired_order = ['Дата и время', 'База данных', 'Филиал', 'Локация', 'Модель принтера', 'Тип компонента', 'Компонент', 'Цвет']
        else:
            # Старый формат для обратной совместимости
            column_names = {
                'branch': 'Филиал',
                'location': 'Локация',
                'printer_model': 'Модель принтера',
                'cartridge_color': 'Цвет картриджа',
                'db_name': 'База данных',
                'timestamp': 'Дата и время'
            }
            df = df.rename(columns=column_names)

            # Упорядочиваем колонки для старого формата
            desired_order = ['Дата и время', 'База данных', 'Филиал', 'Локация', 'Модель принтера', 'Цвет картриджа']

        existing_cols = [col for col in desired_order if col in df.columns]
        df = df[existing_cols]
        
        # Создаем имя файла
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"exports/component_replacements_{timestamp}.xlsx"
        
        # Создаем директорию если не существует
        Path("exports").mkdir(exist_ok=True)
        
        # Сохраняем в Excel
        df.to_excel(output_file, index=False, engine='openpyxl')
        
        logger.info(f"Экспорт замен комплектующих завершен: {output_file}")
        return output_file
        
    except Exception as e:
        logger.error(f"Ошибка экспорта замен комплектующих: {e}")
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


async def structure_component_data_with_llm(data: list, period: str) -> dict:
    """
    Отправляет данные о заменах комплектующих в LLM для структурирования

    Параметры:
        data: Список записей о заменах комплектующих
        period: Период анализа

    Возвращает:
        dict: Структурированные данные
    """
    import json
    from openai import AsyncOpenAI
    from bot.config import config

    try:
        # Фильтруем по периоду
        filtered_data = filter_data_by_period(data, period)

        if not filtered_data:
            return {"error": "Нет данных за указанный период"}

        # Подготавливаем данные для LLM
        data_summary = json.dumps(filtered_data, ensure_ascii=False, indent=2)

        # Получаем русское название периода
        period_ru = get_period_name_ru(period)

        # Создаем промпт для LLM
        prompt = f"""
Проанализируй данные о заменах комплектующих {period_ru} и верни структурированный JSON ответ.

Важно:
- Группируй данные по моделям принтеров внутри каждой локации
- Для каждой записи определи тип компонента: картридж, фьюзер, барабан и т.д.
- Определи тип принтера: МФУ или обычный принтер
- Определи модель совместимого компонента на основе модели принтера
- Для картриджей используй точные модели: HP 05A, HP 88A, Xerox 106R02773, Canon CRG-041 и т.д.
- Для фьюзеров используй модели: RM1-0045, RM1-6405, JC96, Xerox 115R00089 и т.д.
- Для фотобарабанов (OPC) используй модели: DR420CL, DR421CL, Xerox 115R00090 и т.д.
- Цвет компонента важен только для картриджей, для остальных компонентов укажи "Универсальный"
- Если модель компонента неизвестна, укажи "Не определено"

Данные:
{data_summary}

Структурируй данные в следующем формате:
{{
  "summary": {{
    "total_components": общее количество замен компонентов,
    "period": "{period_ru}",
    "branches_count": количество филиалов,
    "component_types": {{
      "Картриджи": количество,
      "Фьюзеры": количество,
      "Фотобарабаны": количество,
      "Прочее": количество
    }},
    "colors": {{
      "Черный": количество,
      "Синий": количество,
      "Желтый": количество,
      "Пурпурный": количество,
      "Универсальный": количество
    }}
  }},
  "branches": [
    {{
      "name": "Название филиала",
      "components_count": общее количество компонентов в филиале,
      "locations": [
        {{
          "name": "Локация",
          "components": {{
            "Картриджи": {{"Черный": количество, "Синий": количество, "Желтый": количество, "Пурпурный": количество}},
            "Фьюзеры": {{"Универсальный": количество}},
            "Фотобарабаны": {{"Универсальный": количество}}
          }},
          "printers": [
            {{
              "model": "Модель принтера",
              "replacements": [
                {{
                  "component_type": "Картридж/Фьюзер/Фотобарабан",
                  "component_color": "Цвет компонента",
                  "count": количество замен,
                  "compatible_models": ["Модель1", "Модель2"]
                }}
              ]
            }}
          ]
        }}
      ]
    }}
  ],
  "top_printers": [
    {{
      "model": "Модель принтера",
      "total_components": общее количество компонентов
    }}
  ]
}}

Верни только JSON без дополнительного текста.
"""

        # Инициализируем клиент OpenAI
        client = AsyncOpenAI(
            api_key=config.api.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1"
        )

        # Отправляем запрос в LLM
        response = await client.chat.completions.create(
            model=config.api.cartridge_analysis_model,  # Модель из конфигурации
            messages=[
                {"role": "system", "content": "Ты - аналитик данных. Структурируй данные о заменах компонентов (картриджи, фьюзеры, барабаны) в точном JSON формате."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )

        # Парсим ответ
        result_text = response.choices[0].message.content

        # Извлекаем JSON из ответа
        import re
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            structured_data = json.loads(json_match.group())
            return structured_data
        else:
            logger.error(f"LLM ответ не содержит JSON: {result_text}")
            return {"error": "Ошибка структурирования данных"}

    except Exception as e:
        logger.error(f"Ошибка при структурировании данных с LLM: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        logger.error(f"Детали: {str(e)}")
        return {"error": f"Ошибка структурирования: {str(e)}"}


def get_period_name_ru(period: str) -> str:
    """
    Возвращает русское название периода

    Параметры:
        period: Период (1month, 3months, all)

    Возвращает:
        str: Русское название периода
    """
    period_names = {
        '1month': 'За последний месяц',
        '3months': 'За последние 3 месяца',
        'all': 'За весь период',
        'full': 'За весь период',
        'new': 'Только новые'
    }
    return period_names.get(period, period)


def filter_data_by_period(data: list, period: str) -> list:
    """
    Фильтрует данные по указанному периоду

    Параметры:
        data: Список записей
        period: Период (1month, 3months, all)

    Возвращает:
        list: Отфильтрованные данные
    """
    from datetime import datetime, timedelta

    if period == "all":
        return data

    try:
        now = datetime.now()
        if period == "1month":
            start_date = now - timedelta(days=30)
        elif period == "3months":
            start_date = now - timedelta(days=90)
        else:
            return data

        filtered_data = []
        for item in data:
            if 'timestamp' in item:
                item_date = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
                if item_date >= start_date:
                    filtered_data.append(item)

        return filtered_data
    except Exception as e:
        logger.error(f"Ошибка фильтрации по периоду: {e}")
        return data


async def export_components_to_excel_structured(period: str = "all", db_filter: str = None) -> str:
    """
    Экспортирует замены комплектующих в Excel с LLM-структурированием

    Параметры:
        period: Период экспорта (1month, 3months, all)
        db_filter: Фильтр по базе данных (None = все базы)

    Возвращает:
        str: Путь к созданному файлу
    """
    import json
    import pandas as pd
    from pathlib import Path
    from datetime import datetime
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils.dataframe import dataframe_to_rows

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

        # Получаем структурированные данные от LLM
        structured_data = await structure_component_data_with_llm(data, period)

        if "error" in structured_data:
            # Если LLM не сработал, создаем базовый отчет
            return create_basic_component_report(data, period)

        # Создаем Excel с множественными страницами
        return create_structured_component_excel(structured_data, period)

    except Exception as e:
        logger.error(f"Ошибка экспорта структурированных замен комплектующих: {e}")
        # В случае ошибки создаем базовый отчет
        return create_basic_component_report(data, period)


def create_structured_component_excel(structured_data: dict, period: str) -> str:
    """
    Создает структурированный Excel файл

    Параметры:
        structured_data: Структурированные данные от LLM
        period: Период анализа

    Возвращает:
        str: Путь к созданному файлу
    """
    from pathlib import Path
    from datetime import datetime
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils.dataframe import dataframe_to_rows
    import pandas as pd
    from bot.services.printer_component_detector import component_detector

    try:
        # Создаем директорию если не существует
        Path("exports").mkdir(exist_ok=True)

        # Создаем имя файла
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"exports/component_analysis_{timestamp}.xlsx"

        # Создаем workbook
        wb = Workbook()

        # Удаляем лист по умолчанию
        wb.remove(wb.active)

        # Создаем сводный лист
        create_summary_sheet(wb, structured_data, period)

        # Создаем листы по филиалам
        for branch in structured_data.get('branches', []):
            create_branch_sheet(wb, branch)

        # Создаем лист топовых принтеров
        create_top_printers_sheet(wb, structured_data.get('top_printers', []))

        # Сохраняем файл
        wb.save(output_file)

        logger.info(f"Структурированный экспорт комплектующих завершен: {output_file}")
        return output_file

    except Exception as e:
        logger.error(f"Ошибка создания структурированного Excel: {e}")
        return None


def create_summary_sheet(wb: Workbook, structured_data: dict, period: str):
    """Создает сводную страницу"""

    ws = wb.create_sheet("Сводка")

    # Стили
    header_font = Font(bold=True, size=12)
    title_font = Font(bold=True, size=14, color='4472C4')
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')

    # Заголовок
    ws['B2'] = f'АНАЛИТИЧЕСКИЙ ОТЧЕТ ЗАМЕН КОМПЛЕКТУЮЩИХ'
    ws['B2'].font = title_font
    ws['B2'].alignment = Alignment(horizontal='center')

    # Получаем русское название периода
    period_ru = get_period_name_ru(period)

    ws['B3'] = f'Период: {period_ru}'
    ws['B3'].font = Font(bold=True)

    # Общая сводка
    row = 6
    summary = structured_data.get('summary', {})

    ws['B6'] = 'ОБЩАЯ СТАТИСТИКА'
    ws['B6'].font = header_font
    ws['B6'].fill = header_fill

    row += 1
    ws[f'B{row}'] = 'Общее количество компонентов:'
    ws[f'C{row}'] = summary.get('total_components', 0)

    row += 1
    ws[f'B{row}'] = 'Количество филиалов:'
    ws[f'C{row}'] = summary.get('branches_count', 0)

    # Статистика по цветам
    row += 2
    ws[f'B{row}'] = 'СТАТИСТИКА ПО ЦВЕТАМ'
    ws[f'B{row}'].font = header_font
    ws[f'B{row}'].fill = header_fill

    colors = summary.get('colors', {})
    row += 1
    for color, count in colors.items():
        ws[f'B{row}'] = color
        ws[f'C{row}'] = count
        row += 1

    # Автоширина колонок
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 15


def create_branch_sheet(wb: Workbook, branch: dict):
    """Создает страницу для филиала с табличным форматом"""

    branch_name = branch.get('name', 'Неизвестный филиал')
    ws = wb.create_sheet(branch_name[:31])  # Ограничение длины имени листа

    # Стили
    header_font = Font(bold=True, size=12)
    title_font = Font(bold=True, size=14, color='4472C4')
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    table_header_fill = PatternFill(start_color='D9E2F3', end_color='D9E2F3', fill_type='solid')
    border = Border(left=Side(style='thin'), right=Side(style='thin'),
                   top=Side(style='thin'), bottom=Side(style='thin'))

    # Заголовок
    ws['B2'] = f'ФИЛИАЛ: {branch_name}'
    ws['B2'].font = title_font

    ws['B3'] = f'Всего компонентов: {branch.get("components_count", 0)}'
    ws['B3'].font = Font(bold=True)

    # Начинаем таблицу с заголовками
    row = 6

    # Заголовки таблицы
    headers = ['Локация', 'Модель принтера', 'Компонент', 'Совместимые модели', 'Черный', 'Синий', 'Желтый', 'Пурпурный', 'Универсальный', 'Всего']
    col = 2  # Начинаем с колонки B

    for header in headers:
        cell = ws.cell(row=row, column=col, value=header)
        cell.font = header_font
        cell.fill = table_header_fill
        cell.border = border
        col += 1

    row += 1

    # Данные по локациям и компонентам
    for location in branch.get('locations', []):
        location_name = location.get('name', '')
        components = location.get('components', {})

        # Показываем общую статистику по компонентам в локации
        cell = ws.cell(row=row, column=2, value=location_name)
        cell.border = border
        cell.font = Font(bold=True)

        # Модель принтера (пусто для сводной строки)
        cell = ws.cell(row=row, column=3, value='')
        cell.border = border

        # Тип компонента (пусто для сводной строки)
        cell = ws.cell(row=row, column=4, value='')
        cell.border = border

        # Совместимые модели (пусто для сводной строки)
        cell = ws.cell(row=row, column=5, value='')
        cell.border = border

        # Количество по цветам для каждого типа компонента
        colors = ['Черный', 'Синий', 'Желтый', 'Пурпурный', 'Универсальный']
        total_count = 0

        for col_idx, color in enumerate(colors, start=6):
            count = 0
            # Суммируем по всем типам компонентов
            for component_type in components:
                component_colors = components.get(component_type, {})
                count += component_colors.get(color, 0)

            cell = ws.cell(row=row, column=col_idx, value=count if count > 0 else '')
            cell.border = border
            if count > 0:
                cell.fill = PatternFill(start_color='E8F5E8', end_color='E8F5E8', fill_type='solid')
            total_count += count

        # Всего компонентов для этой локации
        cell = ws.cell(row=row, column=11, value=total_count)
        cell.font = Font(bold=True)
        cell.border = border
        cell.fill = PatternFill(start_color='F0F8FF', end_color='F0F8FF', fill_type='solid')

        row += 1

        # Добавляем детализацию по каждому компоненту
        for component_type, component_colors in components.items():
            if component_type == 'Картриджи':
                # Для картриджей показываем детализацию по принтерам
                printers = location.get('printers', [])
                for printer in printers:
                    replacements = printer.get('replacements', [])
                    for replacement in replacements:
                        if replacement.get('component_type') == 'Картридж':
                            # Локация (пусто, уже указана выше)
                            cell = ws.cell(row=row, column=2, value='')
                            cell.border = border

                            # Модель принтера
                            printer_model = printer.get('model', '')
                            cell = ws.cell(row=row, column=3, value=printer_model)
                            cell.border = border

                            # Тип компонента
                            cell = ws.cell(row=row, column=4, value=replacement.get('component_type', ''))
                            cell.border = border
                            cell.fill = PatternFill(start_color='FFF9CC', end_color='FFF9CC', fill_type='solid')

                            # Совместимые модели
                            compatible_models = replacement.get('compatible_models', [])
                            if compatible_models and compatible_models != ['Не определено']:
                                models_text = ', '.join(compatible_models[:2])  # Показываем до 2 моделей
                                if len(compatible_models) > 2:
                                    models_text += '...'
                                cell = ws.cell(row=row, column=5, value=models_text)
                            else:
                                # Получаем модели из компонент-детектора
                                try:
                                    models = component_detector.get_compatible_models(printer_model, 'cartridge')
                                    models_text = ', '.join(models[:2])
                                    if len(models) > 2:
                                        models_text += '...'
                                    cell = ws.cell(row=row, column=5, value=models_text)
                                except:
                                    cell = ws.cell(row=row, column=5, value='Не определено')
                            cell.border = border
                            cell.fill = PatternFill(start_color='E6F3FF', end_color='E6F3FF', fill_type='solid')

                            # Цвет
                            color = replacement.get('component_color', '')
                            col_idx = {'Черный': 6, 'Синий': 7, 'Желтый': 8, 'Пурпурный': 9, 'Универсальный': 10}.get(color, 6)
                            cell = ws.cell(row=row, column=col_idx, value=replacement.get('count', 0))
                            cell.border = border
                            cell.fill = PatternFill(start_color='E8F5E8', end_color='E8F5E8', fill_type='solid')

                            # Всего
                            cell = ws.cell(row=row, column=11, value=replacement.get('count', 0))
                            cell.font = Font(bold=True)
                            cell.border = border

                            row += 1
            else:
                # Для фьюзеров и фотобарабанов - общая строка
                universal_count = component_colors.get('Универсальный', 0)
                if universal_count > 0:
                    # Локация (пусто)
                    cell = ws.cell(row=row, column=2, value='')
                    cell.border = border

                    # Модель принтера (пусто)
                    cell = ws.cell(row=row, column=3, value='')
                    cell.border = border

                    # Тип компонента
                    cell = ws.cell(row=row, column=4, value=component_type)
                    cell.border = border
                    cell.fill = PatternFill(start_color='FFF9CC', end_color='FFF9CC', fill_type='solid')

                    # Совместимые модели
                    component_type_eng = component_type.lower().replace('ы', '').replace('Фьюзер', 'fuser').replace('Фотобарабан', 'photoconductor').replace('Барабан', 'photoconductor')
                    try:
                        models = component_detector.get_compatible_models('', component_type_eng)
                        models_text = ', '.join(models[:2])
                        if len(models) > 2:
                            models_text += '...'
                        cell = ws.cell(row=row, column=5, value=models_text)
                    except:
                        cell = ws.cell(row=row, column=5, value='Не определено')
                    cell.border = border
                    cell.fill = PatternFill(start_color='E6F3FF', end_color='E6F3FF', fill_type='solid')

                    # Универсальный (в соответствующей колонке)
                    cell = ws.cell(row=row, column=10, value=universal_count)
                    cell.border = border
                    cell.fill = PatternFill(start_color='E8F5E8', end_color='E8F5E8', fill_type='solid')

                    # Всего
                    cell = ws.cell(row=row, column=11, value=universal_count)
                    cell.font = Font(bold=True)
                    cell.border = border

                    row += 1

            
    # Автоширина колонок
    column_widths = {
        'B': 20,  # Локация
        'C': 30,  # Модель принтера
        'D': 20,  # Компонент
        'E': 30,  # Совместимые модели
        'F': 10,  # Черный
        'G': 10,  # Синий
        'H': 10,  # Желтый
        'I': 12,  # Пурпурный
        'J': 12,  # Универсальный
        'K': 8    # Всего
    }

    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width

    # Добавляем пустую строку после таблицы
    row += 1


def create_top_printers_sheet(wb: Workbook, top_printers: list):
    """Создает страницу топовых принтеров"""
    import pandas as pd
    from openpyxl.utils.dataframe import dataframe_to_rows

    if not top_printers:
        return

    ws = wb.create_sheet("Топ принтеры")

    # Создаем DataFrame
    df = pd.DataFrame(top_printers)

    # Записываем данные
    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
        for c_idx, value in enumerate(row, 1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    # Форматируем заголовки
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')

    # Автоширина колонок
    ws.column_dimensions['A'].width = 40
    ws.column_dimensions['B'].width = 20


def create_basic_component_report(data: list, period: str) -> str:
    """
    Создает базовый отчет если LLM недоступен

    Параметры:
        data: Данные о компонентах
        period: Период

    Возвращает:
        str: Путь к файлу
    """
    import pandas as pd
    from pathlib import Path
    from datetime import datetime

    try:
        # Фильтруем по периоду
        filtered_data = filter_data_by_period(data, period)

        if not filtered_data:
            return None

        # Создаем DataFrame
        df = pd.DataFrame(filtered_data)

        # Добавляем db_name если отсутствует
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
        output_file = f"exports/component_replacements_{timestamp}.xlsx"

        # Создаем директорию если не существует
        Path("exports").mkdir(exist_ok=True)

        # Сохраняем в Excel
        df.to_excel(output_file, index=False, engine='openpyxl')

        logger.info(f"Базовый экспорт замен комплектующих завершен: {output_file}")
        return output_file

    except Exception as e:
        logger.error(f"Ошибка базового экспорта замен комплектующих: {e}")
        return None
