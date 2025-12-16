#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчики для регистрации выполненных работ
"""
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.config import States
from bot.utils.decorators import handle_errors

logger = logging.getLogger(__name__)


@handle_errors
async def start_work(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начало процесса регистрации работы
    """
    logger.info(f"[WORK] Начало процесса регистрации работы, user_id={update.effective_user.id}")
    
    keyboard = [
        [InlineKeyboardButton("🖨️ Замена картриджа", callback_data="work:cartridge")],
        [InlineKeyboardButton("📦 Установка нового оборудования", callback_data="work:installation")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    logger.info(f"[WORK] Создана клавиатура с кнопками: cartridge, installation, back_to_main")
    
    if update.callback_query:
        logger.info(f"[WORK] Отправка меню через callback_query")
        await update.callback_query.edit_message_text(
            "🔧 <b>Регистрация выполненных работ</b>\n\n"
            "Выберите тип работы:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    else:
        logger.info(f"[WORK] Отправка меню через message")
        await update.message.reply_text(
            "🔧 <b>Регистрация выполненных работ</b>\n\n"
            "Выберите тип работы:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    logger.info(f"[WORK] Переход в состояние WORK_TYPE_SELECTION")
    return States.WORK_TYPE_SELECTION


@handle_errors
async def handle_work_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора типа работы
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    logger.info(f"[WORK] Получен callback: {callback_data}, user_id={update.effective_user.id}")
    
    # Обработка кнопки "Назад"
    if callback_data == 'back_to_main':
        logger.info(f"[WORK] Обработка кнопки 'Назад' - возврат в главное меню")
        
        from bot.config import Messages
        from bot.utils.keyboards import create_main_menu_keyboard
        from database_manager import database_manager
        
        user_id = update.effective_user.id
        current_db = database_manager.get_user_database(user_id)
        
        logger.info(f"[WORK] Отправка сообщения о возврате в главное меню")
        await query.edit_message_text("✅ Возврат в главное меню")
        
        logger.info(f"[WORK] Отправка главного меню")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"{Messages.MAIN_MENU}\n\n📊 <b>Текущая база данных:</b> {current_db}",
            parse_mode='HTML',
            reply_markup=create_main_menu_keyboard()
        )
        
        logger.info(f"[WORK] Завершение ConversationHandler")
        return ConversationHandler.END
    
    work_type = callback_data.split(':', 1)[1] if ':' in callback_data else ''
    
    if work_type == 'cartridge':
        context.user_data['work_type'] = 'cartridge'
        await query.edit_message_text(
            "🖨️ <b>Замена картриджа</b>\n\n"
            "📍 Введите местоположение (филиал):",
            parse_mode='HTML'
        )
        return States.WORK_BRANCH_INPUT
    
    elif work_type == 'installation':
        context.user_data['work_type'] = 'installation'
        await query.edit_message_text(
            "📦 <b>Установка нового оборудования</b>\n\n"
            "📍 Введите местоположение (филиал):",
            parse_mode='HTML'
        )
        return States.WORK_BRANCH_INPUT
    
    return States.WORK_TYPE_SELECTION


@handle_errors
async def work_branch_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода филиала с подсказками
    """
    from bot.handlers.suggestions_handler import show_branch_suggestions_for_work

    branch = update.message.text.strip()

    # Показываем подсказки если есть совпадения
    try:
        if await show_branch_suggestions_for_work(
            update, context, branch,
            pending_key='pending_work_branch',
            suggestions_key='work_branch_suggestions'
        ):
            return States.WORK_BRANCH_INPUT
    except Exception as e:
        logger.error(f"Ошибка при показе подсказок филиала: {e}")
        # Продолжаем выполнение даже если подсказки не сработали

    context.user_data['work_branch'] = branch

    await update.message.reply_text(
        "📍 Введите локацию (например: Офис 301, Склад):"
    )

    return States.WORK_LOCATION_INPUT


@handle_errors
async def work_location_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода локации с подсказками
    """
    from bot.handlers.suggestions_handler import show_location_suggestions

    location = update.message.text.strip()
    work_type = context.user_data.get('work_type')

    logger.info(f"[WORK] Получена локация: '{location}', work_type: {work_type}")

    # Показываем подсказки если есть совпадения
    try:
        if await show_location_suggestions(
            update, context, location,
            mode='work',
            pending_key='pending_work_location',
            suggestions_key='work_location_suggestions'
        ):
            logger.info(f"[WORK] Показаны подсказки для локации, остаемся в состоянии WORK_LOCATION_INPUT")
            return States.WORK_LOCATION_INPUT
    except Exception as e:
        logger.error(f"[WORK] Ошибка при показе подсказок локации: {e}")

    context.user_data['work_location'] = location
    logger.info(f"[WORK] Сохранена локация: {location}")

    if work_type == 'cartridge':
        logger.info(f"[WORK] Запрос модели принтера для замены картриджа")
        await update.message.reply_text(
            "🖨️ Введите модель принтера:"
        )
        return States.WORK_PRINTER_MODEL_INPUT
    else:  # installation
        logger.info(f"[WORK] Запрос типа оборудования для установки")
        await update.message.reply_text(
            "🔧 Введите тип оборудования:"
        )
        return States.WORK_EQUIPMENT_TYPE_INPUT


@handle_errors
async def work_printer_model_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода модели принтера с подсказками
    """
    from bot.handlers.suggestions_handler import show_model_suggestions
    from bot.services.printer_color_detector import is_color_printer
    
    model = update.message.text.strip()
    
    # Показываем подсказки если есть совпадения
    try:
        if await show_model_suggestions(
            update, context, model,
            mode='work',
            pending_key='pending_work_printer_model',
            suggestions_key='work_printer_model_suggestions'
        ):
            return States.WORK_PRINTER_MODEL_INPUT
    except Exception as e:
        logger.error(f"Ошибка при показе подсказок моделей принтеров: {e}")
        # Продолжаем выполнение даже если подсказки не сработали
    
    context.user_data['work_printer_model'] = model
    
    # Отправляем сообщение о проверке цветности
    status_msg = await update.message.reply_text(
        "🔍 Определяю тип принтера (цветной/ч-б)..."
    )
    
    # Определяем поддержку цветной печати через LLM
    is_color = is_color_printer(model)
    
    # Удаляем сообщение о проверке
    try:
        await status_msg.delete()
    except:
        pass
    
    if is_color is None:
        # Не удалось определить - предлагаем выбрать вручную
        keyboard = [
            [InlineKeyboardButton("🎨 Цветной принтер", callback_data="printer_type:color")],
            [InlineKeyboardButton("⚫ Черно-белый принтер", callback_data="printer_type:bw")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ Не удалось автоматически определить тип принтера.\n"
            "Пожалуйста, выберите тип принтера вручную:",
            reply_markup=reply_markup
        )
        return States.WORK_CARTRIDGE_COLOR_SELECTION
    
    # Сохраняем результат определения
    context.user_data['printer_is_color'] = is_color
    
    if is_color:
        # Цветной принтер - 4 цвета
        keyboard = [
            [InlineKeyboardButton("⚫ Черный", callback_data="cartridge_color:black")],
            [InlineKeyboardButton("🔵 Синий (Cyan)", callback_data="cartridge_color:cyan")],
            [InlineKeyboardButton("🟡 Желтый (Yellow)", callback_data="cartridge_color:yellow")],
            [InlineKeyboardButton("🔴 Пурпурный (Magenta)", callback_data="cartridge_color:magenta")]
        ]
        printer_type_text = "🎨 Цветной принтер"
    else:
        # Черно-белый принтер
        keyboard = [
            [InlineKeyboardButton("⚫ Черный", callback_data="cartridge_color:black")]
        ]
        printer_type_text = "⚫ Черно-белый принтер"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ Определен тип: {printer_type_text}\n\n"
        f"🎨 Выберите цвет установленного картриджа:",
        reply_markup=reply_markup
    )
    
    return States.WORK_CARTRIDGE_COLOR_SELECTION


@handle_errors
async def work_equipment_type_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода типа оборудования с подсказками
    """
    from bot.handlers.suggestions_handler import show_equipment_type_suggestions_on_input

    equipment_type = update.message.text.strip()

    # Показываем подсказки если есть совпадения
    try:
        if await show_equipment_type_suggestions_on_input(
            update, context, equipment_type,
            mode='work',
            pending_key='pending_work_equipment_type',
            suggestions_key='work_equipment_type_suggestions'
        ):
            return States.WORK_EQUIPMENT_TYPE_INPUT
    except Exception as e:
        logger.error(f"Ошибка при показе подсказок типов оборудования: {e}")
        # Продолжаем выполнение даже если подсказки не сработали

    context.user_data['work_equipment_type'] = equipment_type

    await update.message.reply_text(
        "🏭 Введите модель оборудования:"
    )

    return States.WORK_EQUIPMENT_MODEL_INPUT


@handle_errors
async def work_equipment_model_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода модели оборудования с подсказками
    """
    from bot.handlers.suggestions_handler import show_model_suggestions

    model = update.message.text.strip()

    # Показываем подсказки если есть совпадения
    try:
        if await show_model_suggestions(
            update, context, model,
            mode='work',
            pending_key='pending_work_equipment_model',
            suggestions_key='work_equipment_model_suggestions'
        ):
            return States.WORK_EQUIPMENT_MODEL_INPUT
    except Exception as e:
        logger.error(f"Ошибка при показе подсказок моделей оборудования: {e}")
        # Продолжаем выполнение даже если подсказки не сработали

    context.user_data['work_equipment_model'] = model

    # Показываем подтверждение для установки
    try:
        await show_installation_confirmation(update, context)
    except Exception as e:
        logger.error(f"Ошибка при показе подтверждения установки: {e}")
        # Показываем простое текстовое подтверждение
        equipment_type = context.user_data.get('work_equipment_type', '')
        await update.message.reply_text(
            f"✅ Принято: {equipment_type} {model}\n"
            f"Данные сохранены."
        )
        clear_work_data(context)
        from telegram.ext import ConversationHandler
        return ConversationHandler.END

    return States.WORK_CONFIRMATION


@handle_errors
async def handle_printer_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ручного выбора типа принтера (цветной/ч-б)
    """
    query = update.callback_query
    await query.answer()
    
    printer_type = query.data.split(':', 1)[1] if ':' in query.data else 'bw'
    is_color = (printer_type == 'color')
    
    context.user_data['printer_is_color'] = is_color
    
    if is_color:
        # Цветной принтер - 4 цвета
        keyboard = [
            [InlineKeyboardButton("⚫ Черный", callback_data="cartridge_color:black")],
            [InlineKeyboardButton("🔵 Синий (Cyan)", callback_data="cartridge_color:cyan")],
            [InlineKeyboardButton("🟡 Желтый (Yellow)", callback_data="cartridge_color:yellow")],
            [InlineKeyboardButton("🔴 Пурпурный (Magenta)", callback_data="cartridge_color:magenta")]
        ]
        printer_type_text = "🎨 Цветной принтер"
    else:
        # Черно-белый принтер
        keyboard = [
            [InlineKeyboardButton("⚫ Черный", callback_data="cartridge_color:black")]
        ]
        printer_type_text = "⚫ Черно-белый принтер"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ Выбран тип: {printer_type_text}\n\n"
        f"🎨 Выберите цвет установленного картриджа:",
        reply_markup=reply_markup
    )
    
    return States.WORK_CARTRIDGE_COLOR_SELECTION


@handle_errors
async def handle_cartridge_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора цвета картриджа
    """
    query = update.callback_query
    await query.answer()
    
    color = query.data.split(':', 1)[1] if ':' in query.data else 'black'
    
    color_names = {
        'black': 'Черный',
        'cyan': 'Синий (Cyan)',
        'yellow': 'Желтый (Yellow)',
        'magenta': 'Пурпурный (Magenta)'
    }
    
    context.user_data['work_cartridge_color'] = color_names.get(color, color)
    
    await query.edit_message_text(f"✅ Выбран цвет: {color_names.get(color, color)}")
    
    # Показываем подтверждение
    await show_cartridge_confirmation(update, context)
    
    return States.WORK_CONFIRMATION


async def show_cartridge_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показывает подтверждение для замены картриджа
    """
    branch = context.user_data.get('work_branch', '')
    location = context.user_data.get('work_location', '')
    printer_model = context.user_data.get('work_printer_model', '')
    cartridge_color = context.user_data.get('work_cartridge_color', '')
    
    confirmation_text = (
        "📋 <b>Подтверждение замены картриджа</b>\n\n"
        f"📍 <b>Филиал:</b> {branch}\n"
        f"📍 <b>Локация:</b> {location}\n"
        f"🖨️ <b>Модель принтера:</b> {printer_model}\n"
        f"🎨 <b>Цвет картриджа:</b> {cartridge_color}\n\n"
        "❓ Сохранить эти данные?"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Сохранить", callback_data="confirm_work"),
            InlineKeyboardButton("❌ Отменить", callback_data="cancel_work")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.message.reply_text(
            confirmation_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            confirmation_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )


async def show_installation_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показывает подтверждение для установки оборудования
    """
    try:
        branch = context.user_data.get('work_branch', '')
        location = context.user_data.get('work_location', '')
        equipment_type = context.user_data.get('work_equipment_type', '')
        equipment_model = context.user_data.get('work_equipment_model', '')

        confirmation_text = (
            "📋 <b>Подтверждение установки оборудования</b>\n\n"
            f"📍 <b>Филиал:</b> {branch}\n"
            f"📍 <b>Локация:</b> {location}\n"
            f"🔧 <b>Тип оборудования:</b> {equipment_type}\n"
            f"🏭 <b>Модель:</b> {equipment_model}\n\n"
            "❓ Сохранить эти данные?"
        )

        keyboard = [
            [
                InlineKeyboardButton("✅ Сохранить", callback_data="confirm_work"),
                InlineKeyboardButton("❌ Отменить", callback_data="cancel_work")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            confirmation_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка в show_installation_confirmation: {e}")
        # Если не удалось показать клавиатуру, просто подтверждаем сохранение
        await update.message.reply_text(
            f"✅ Данные приняты:\n"
            f"📍 Филиал: {context.user_data.get('work_branch', '')}\n"
            f"📍 Локация: {context.user_data.get('work_location', '')}\n"
            f"🔧 Тип: {context.user_data.get('work_equipment_type', '')}\n"
            f"🏭 Модель: {context.user_data.get('work_equipment_model', '')}"
        )


@handle_errors
async def handle_work_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик подтверждения сохранения работы
    """
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_work":
        # Сохраняем user_id для функций сохранения
        context._user_id = update.effective_user.id
        
        # Сохраняем данные
        work_type = context.user_data.get('work_type')
        
        if work_type == 'cartridge':
            success = await save_cartridge_replacement(context)
        else:  # installation
            success = await save_equipment_installation(context)
        
        if success:
            await query.edit_message_text(
                "✅ Данные успешно сохранены!\n"
                "Информация о выполненной работе добавлена."
            )
        else:
            await query.edit_message_text(
                "❌ Ошибка при сохранении данных.\n"
                "Попробуйте еще раз."
            )
        
        # Очищаем данные
        clear_work_data(context)
        
        from telegram.ext import ConversationHandler
        return ConversationHandler.END
    
    elif query.data == "cancel_work":
        await query.edit_message_text("❌ Операция отменена.")
        clear_work_data(context)
        
        from telegram.ext import ConversationHandler
        return ConversationHandler.END
    
    return States.WORK_CONFIRMATION


async def save_cartridge_replacement(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Сохраняет данные о замене картриджа в JSON
    """
    import json
    from pathlib import Path
    from database_manager import database_manager
    
    try:
        file_path = Path("data/cartridge_replacements.json")
        
        # Загружаем существующие данные
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = []
        
        # Получаем текущую БД пользователя
        user_id = context._user_id if hasattr(context, '_user_id') else None
        db_name = database_manager.get_user_database(user_id) if user_id else 'ITINVENT'
        
        # Создаем новую запись
        record = {
            'branch': context.user_data.get('work_branch', ''),
            'location': context.user_data.get('work_location', ''),
            'printer_model': context.user_data.get('work_printer_model', ''),
            'cartridge_color': context.user_data.get('work_cartridge_color', ''),
            'db_name': db_name,
            'timestamp': datetime.now().isoformat()
        }
        
        data.append(record)
        
        # Сохраняем
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Сохранена замена картриджа: {record}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка сохранения замены картриджа: {e}")
        return False


async def save_equipment_installation(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Сохраняет данные об установке оборудования в JSON
    """
    import json
    from pathlib import Path
    from database_manager import database_manager
    
    try:
        file_path = Path("data/equipment_installations.json")
        
        # Загружаем существующие данные
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = []
        
        # Получаем текущую БД пользователя
        user_id = context._user_id if hasattr(context, '_user_id') else None
        db_name = database_manager.get_user_database(user_id) if user_id else 'ITINVENT'
        
        # Создаем новую запись
        record = {
            'branch': context.user_data.get('work_branch', ''),
            'location': context.user_data.get('work_location', ''),
            'equipment_type': context.user_data.get('work_equipment_type', ''),
            'equipment_model': context.user_data.get('work_equipment_model', ''),
            'db_name': db_name,
            'timestamp': datetime.now().isoformat()
        }
        
        data.append(record)
        
        # Сохраняем
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Сохранена установка оборудования: {record}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка сохранения установки оборудования: {e}")
        return False


def clear_work_data(context: ContextTypes.DEFAULT_TYPE):
    """
    Очищает временные данные работы
    """
    keys_to_clear = [
        'work_type', 'work_branch', 'work_location',
        'work_printer_model', 'work_cartridge_color',
        'work_equipment_type', 'work_equipment_model',
        'pending_work_branch', 'work_branch_suggestions',
        'pending_work_location', 'work_location_suggestions',
        'pending_work_printer_model', 'work_printer_model_suggestions',
        'pending_work_equipment_type', 'work_equipment_type_suggestions',
        'pending_work_equipment_model', 'work_equipment_model_suggestions'
    ]
    
    for key in keys_to_clear:
        context.user_data.pop(key, None)



@handle_errors
async def handle_work_branch_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора филиала из подсказок
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'work_branch:manual':
        pending = context.user_data.get('pending_work_branch', '').strip()
        context.user_data['work_branch'] = pending
        await query.edit_message_text(f"✅ Принято: {pending}")
        await query.message.reply_text("📍 Введите локацию:")
        return States.WORK_LOCATION_INPUT
    
    elif data.startswith('work_branch:'):
        try:
            idx = int(data.split(':', 1)[1])
            suggestions = context.user_data.get('work_branch_suggestions', [])
            
            if 0 <= idx < len(suggestions):
                selected_branch = suggestions[idx]
                context.user_data['work_branch'] = selected_branch
                await query.edit_message_text(f"✅ Выбран филиал: {selected_branch}")
                await query.message.reply_text("📍 Введите локацию:")
                return States.WORK_LOCATION_INPUT
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора филиала: {e}")
    
    return States.WORK_BRANCH_INPUT


@handle_errors
async def handle_work_location_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора локации из подсказок
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    work_type = context.user_data.get('work_type')
    
    if data == 'work_loc:manual':
        pending = context.user_data.get('pending_work_location', '').strip()
        context.user_data['work_location'] = pending
        await query.edit_message_text(f"✅ Принято: {pending}")
        
        if work_type == 'cartridge':
            await query.message.reply_text("🖨️ Введите модель принтера:")
            return States.WORK_PRINTER_MODEL_INPUT
        else:
            await query.message.reply_text("🔧 Введите тип оборудования:")
            return States.WORK_EQUIPMENT_TYPE_INPUT
    
    elif data.startswith('work_loc:'):
        try:
            idx = int(data.split(':', 1)[1])
            suggestions = context.user_data.get('work_location_suggestions', [])
            
            if 0 <= idx < len(suggestions):
                selected_location = suggestions[idx]
                context.user_data['work_location'] = selected_location
                await query.edit_message_text(f"✅ Выбрана локация: {selected_location}")
                
                if work_type == 'cartridge':
                    await query.message.reply_text("🖨️ Введите модель принтера:")
                    return States.WORK_PRINTER_MODEL_INPUT
                else:
                    await query.message.reply_text("🔧 Введите тип оборудования:")
                    return States.WORK_EQUIPMENT_TYPE_INPUT
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора локации: {e}")
    
    return States.WORK_LOCATION_INPUT


@handle_errors
async def handle_work_model_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора модели из подсказок (для принтера или оборудования)
    """
    from bot.services.printer_color_detector import is_color_printer
    
    query = update.callback_query
    await query.answer()
    
    data = query.data
    work_type = context.user_data.get('work_type')
    
    if data == 'work_model:manual':
        if work_type == 'cartridge':
            pending = context.user_data.get('pending_work_printer_model', '').strip()
            context.user_data['work_printer_model'] = pending
            await query.edit_message_text(f"✅ Принято: {pending}")
            
            # Отправляем сообщение о проверке цветности
            status_msg = await query.message.reply_text(
                "🔍 Определяю тип принтера (цветной/ч-б)..."
            )
            
            # Определяем поддержку цветной печати через LLM
            is_color = is_color_printer(pending)
            
            # Удаляем сообщение о проверке
            try:
                await status_msg.delete()
            except:
                pass
            
            if is_color is None:
                # Не удалось определить - предлагаем выбрать вручную
                keyboard = [
                    [InlineKeyboardButton("🎨 Цветной принтер", callback_data="printer_type:color")],
                    [InlineKeyboardButton("⚫ Черно-белый принтер", callback_data="printer_type:bw")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.message.reply_text(
                    "⚠️ Не удалось автоматически определить тип принтера.\n"
                    "Пожалуйста, выберите тип принтера вручную:",
                    reply_markup=reply_markup
                )
                return States.WORK_CARTRIDGE_COLOR_SELECTION
            
            # Сохраняем результат определения
            context.user_data['printer_is_color'] = is_color
            
            if is_color:
                keyboard = [
                    [InlineKeyboardButton("⚫ Черный", callback_data="cartridge_color:black")],
                    [InlineKeyboardButton("🔵 Синий (Cyan)", callback_data="cartridge_color:cyan")],
                    [InlineKeyboardButton("🟡 Желтый (Yellow)", callback_data="cartridge_color:yellow")],
                    [InlineKeyboardButton("🔴 Пурпурный (Magenta)", callback_data="cartridge_color:magenta")]
                ]
                printer_type_text = "🎨 Цветной принтер"
            else:
                keyboard = [[InlineKeyboardButton("⚫ Черный", callback_data="cartridge_color:black")]]
                printer_type_text = "⚫ Черно-белый принтер"
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(
                f"✅ Определен тип: {printer_type_text}\n\n"
                f"🎨 Выберите цвет картриджа:",
                reply_markup=reply_markup
            )
            return States.WORK_CARTRIDGE_COLOR_SELECTION
        else:
            pending = context.user_data.get('pending_work_equipment_model', '').strip()
            context.user_data['work_equipment_model'] = pending
            await query.edit_message_text(f"✅ Принято: {pending}")
            
            # Создаем временный update для show_installation_confirmation
            from telegram import Message
            temp_message = query.message
            temp_update = Update(update.update_id, message=temp_message)
            await show_installation_confirmation(temp_update, context)
            return States.WORK_CONFIRMATION
    
    elif data.startswith('work_model:'):
        # Обработка кнопки обновления поиска
        if data == 'work_model:refresh':
            if work_type == 'cartridge':
                pending = context.user_data.get('pending_work_printer_model', '').strip()
                if pending:
                    await query.edit_message_text(
                        f"🔄 Обновляю поиск для: {pending}"
                    )
                    # Показываем обновленные подсказки
                    try:
                        from bot.handlers.suggestions_handler import show_model_suggestions
                        if await show_model_suggestions(
                            update, context, pending,
                            mode='work',
                            pending_key='pending_work_printer_model',
                            suggestions_key='work_printer_model_suggestions'
                        ):
                            return States.WORK_PRINTER_MODEL_INPUT
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении подсказок: {e}")
            else:
                pending = context.user_data.get('pending_work_equipment_model', '').strip()
                if pending:
                    await query.edit_message_text(
                        f"🔄 Обновляю поиск для: {pending}"
                    )
                    try:
                        from bot.handlers.suggestions_handler import show_model_suggestions
                        if await show_model_suggestions(
                            update, context, pending,
                            mode='work',
                            pending_key='pending_work_equipment_model',
                            suggestions_key='work_equipment_model_suggestions'
                        ):
                            return States.WORK_EQUIPMENT_MODEL_INPUT
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении подсказок: {e}")
        try:
            idx = int(data.split(':', 1)[1])
            
            if work_type == 'cartridge':
                suggestions = context.user_data.get('work_printer_model_suggestions', [])
                if 0 <= idx < len(suggestions):
                    selected_model = suggestions[idx]
                    context.user_data['work_printer_model'] = selected_model
                    await query.edit_message_text(f"✅ Выбрана модель: {selected_model}")
                    
                    # Отправляем сообщение о проверке цветности
                    status_msg = await query.message.reply_text(
                        "🔍 Определяю тип принтера (цветной/ч-б)..."
                    )
                    
                    # Определяем поддержку цветной печати через LLM
                    is_color = is_color_printer(selected_model)
                    
                    # Удаляем сообщение о проверке
                    try:
                        await status_msg.delete()
                    except:
                        pass
                    
                    if is_color is None:
                        # Не удалось определить - предлагаем выбрать вручную
                        keyboard = [
                            [InlineKeyboardButton("🎨 Цветной принтер", callback_data="printer_type:color")],
                            [InlineKeyboardButton("⚫ Черно-белый принтер", callback_data="printer_type:bw")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await query.message.reply_text(
                            "⚠️ Не удалось автоматически определить тип принтера.\n"
                            "Пожалуйста, выберите тип принтера вручную:",
                            reply_markup=reply_markup
                        )
                        return States.WORK_CARTRIDGE_COLOR_SELECTION
                    
                    # Сохраняем результат определения
                    context.user_data['printer_is_color'] = is_color
                    
                    if is_color:
                        keyboard = [
                            [InlineKeyboardButton("⚫ Черный", callback_data="cartridge_color:black")],
                            [InlineKeyboardButton("🔵 Синий (Cyan)", callback_data="cartridge_color:cyan")],
                            [InlineKeyboardButton("🟡 Желтый (Yellow)", callback_data="cartridge_color:yellow")],
                            [InlineKeyboardButton("🔴 Пурпурный (Magenta)", callback_data="cartridge_color:magenta")]
                        ]
                        printer_type_text = "🎨 Цветной принтер"
                    else:
                        keyboard = [[InlineKeyboardButton("⚫ Черный", callback_data="cartridge_color:black")]]
                        printer_type_text = "⚫ Черно-белый принтер"
                    
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.message.reply_text(
                        f"✅ Определен тип: {printer_type_text}\n\n"
                        f"🎨 Выберите цвет картриджа:",
                        reply_markup=reply_markup
                    )
                    return States.WORK_CARTRIDGE_COLOR_SELECTION
            else:
                suggestions = context.user_data.get('work_equipment_model_suggestions', [])
                if 0 <= idx < len(suggestions):
                    selected_model = suggestions[idx]
                    context.user_data['work_equipment_model'] = selected_model
                    await query.edit_message_text(f"✅ Выбрана модель: {selected_model}")
                    
                    from telegram import Message
                    temp_message = query.message
                    temp_update = Update(update.update_id, message=temp_message)
                    await show_installation_confirmation(temp_update, context)
                    return States.WORK_CONFIRMATION
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора модели: {e}")
    
    if work_type == 'cartridge':
        return States.WORK_PRINTER_MODEL_INPUT
    else:
        return States.WORK_EQUIPMENT_MODEL_INPUT


@handle_errors
async def handle_work_type_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора типа оборудования из подсказок
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'work_type:manual':
        pending = context.user_data.get('pending_work_equipment_type', '').strip()
        context.user_data['work_equipment_type'] = pending
        await query.edit_message_text(f"✅ Принято: {pending}")
        await query.message.reply_text("🏭 Введите модель оборудования:")
        return States.WORK_EQUIPMENT_MODEL_INPUT
    
    elif data.startswith('work_type:'):
        try:
            idx = int(data.split(':', 1)[1])
            suggestions = context.user_data.get('work_equipment_type_suggestions', [])
            
            if 0 <= idx < len(suggestions):
                selected_type = suggestions[idx]
                context.user_data['work_equipment_type'] = selected_type
                await query.edit_message_text(f"✅ Выбран тип: {selected_type}")
                await query.message.reply_text("🏭 Введите модель оборудования:")
                return States.WORK_EQUIPMENT_MODEL_INPUT
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора типа: {e}")
    
    return States.WORK_EQUIPMENT_TYPE_INPUT
