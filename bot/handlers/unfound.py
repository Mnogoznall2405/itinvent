#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчики добавления ненайденного оборудования
Многошаговый процесс ввода данных об оборудовании, не найденном в БД.
"""
import logging
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import States, Messages, StorageKeys
from bot.utils.decorators import require_user_access, handle_errors
from bot.services.validation import (
    validate_employee_name,
    validate_serial_number,
    validate_ip_address,
    validate_inventory_number
)
from equipment_data_manager import EquipmentDataManager

logger = logging.getLogger(__name__)

# Глобальный менеджер данных
equipment_manager = EquipmentDataManager()


@require_user_access
async def start_unfound_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начало процесса добавления ненайденного оборудования
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Состояние UNFOUND_EMPLOYEE_INPUT
    """
    # Получаем серийный номер из контекста (если пришли из поиска)
    serial_number = context.user_data.get('last_search_serial', '')
    
    if serial_number:
        context.user_data['unfound_serial'] = serial_number
        await update.message.reply_text(
            f"📝 Добавление информации об оборудовании\n"
            f"Серийный номер: <b>{serial_number}</b>\n\n"
            f"👤 Введите ФИО сотрудника:",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text(
            "📝 Добавление ненайденного оборудования\n\n"
            "👤 Введите ФИО сотрудника:",
            reply_markup=ReplyKeyboardRemove()
        )
    
    return States.UNFOUND_EMPLOYEE_INPUT


@handle_errors
async def unfound_employee_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода ФИО сотрудника с подсказками
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние или текущее при ошибке
    """
    from bot.handlers.suggestions_handler import show_employee_suggestions
    
    employee_name = update.message.text.strip()
    
    # Показываем подсказки если есть совпадения
    if await show_employee_suggestions(
        update, context, employee_name,
        mode='unfound',
        pending_key='pending_unfound_employee_input',
        suggestions_key='unfound_employee_suggestions'
    ):
        return States.UNFOUND_EMPLOYEE_INPUT
    
    # Валидация ФИО
    if not validate_employee_name(employee_name):
        await update.message.reply_text(
            "⚠️ Недопустимое ФИО сотрудника.\n"
            "Введите корректное ФИО (только буквы и пробелы, от 2 до 100 символов)."
        )
        return States.UNFOUND_EMPLOYEE_INPUT
    
    context.user_data['unfound_employee'] = employee_name
    
    await update.message.reply_text(
        "🔧 Укажите тип оборудования\n"
        "(например: Системный блок, МФУ, Монитор, ИБП):"
    )
    
    return States.UNFOUND_TYPE_INPUT


@handle_errors
async def unfound_type_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода типа оборудования с подсказками при вводе
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    from bot.handlers.suggestions_handler import show_equipment_type_suggestions_on_input
    
    equipment_type = update.message.text.strip()
    
    # Показываем подсказки если есть совпадения (минимум 2 символа)
    if await show_equipment_type_suggestions_on_input(
        update, context, equipment_type,
        mode='unfound',
        pending_key='pending_unfound_type_input',
        suggestions_key='unfound_type_suggestions'
    ):
        return States.UNFOUND_TYPE_INPUT
    
    if not equipment_type or len(equipment_type) < 2:
        await update.message.reply_text(
            "⚠️ Введите корректный тип оборудования (минимум 2 символа)."
        )
        return States.UNFOUND_TYPE_INPUT
    
    context.user_data['unfound_type'] = equipment_type
    
    await update.message.reply_text(
        "🏭 Введите модель оборудования\n"
        "(например: Dell Latitude 5420, HP LaserJet Pro M404dn):"
    )
    
    return States.UNFOUND_MODEL_INPUT


@handle_errors
async def unfound_model_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода модели оборудования с подсказками
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    from bot.handlers.suggestions_handler import show_model_suggestions
    
    model_name = update.message.text.strip()
    
    # Показываем подсказки если есть совпадения
    if await show_model_suggestions(
        update, context, model_name,
        mode='unfound',
        pending_key='pending_unfound_model_input',
        suggestions_key='unfound_model_suggestions'
    ):
        return States.UNFOUND_MODEL_INPUT
    
    if not model_name or len(model_name) < 2:
        await update.message.reply_text(
            "⚠️ Введите корректную модель оборудования (минимум 2 символа)."
        )
        return States.UNFOUND_MODEL_INPUT
    
    context.user_data['unfound_model'] = model_name
    
    # Создаем клавиатуру с кнопкой "Пропустить"
    keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_description")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📄 Введите описание оборудования (необязательно):",
        reply_markup=reply_markup
    )
    
    return States.UNFOUND_DESCRIPTION_INPUT


@handle_errors
async def unfound_description_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода описания оборудования
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    description = update.message.text.strip()
    context.user_data['unfound_description'] = description
    
    # Создаем клавиатуру с кнопкой "Пропустить"
    keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_inventory")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔢 Введите инвентарный номер (необязательно):",
        reply_markup=reply_markup
    )
    
    return States.UNFOUND_INVENTORY_INPUT


@handle_errors
async def unfound_inventory_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода инвентарного номера
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    inventory_number = update.message.text.strip()
    
    # Валидация инвентарного номера
    if inventory_number and not validate_inventory_number(inventory_number):
        await update.message.reply_text(
            "⚠️ Недопустимый формат инвентарного номера.\n"
            "Используйте только буквы, цифры и символы: - _ ."
        )
        return States.UNFOUND_INVENTORY_INPUT
    
    context.user_data['unfound_inventory'] = inventory_number
    
    # Создаем клавиатуру с кнопкой "Пропустить"
    keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_ip")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🌐 Введите IP-адрес (необязательно):",
        reply_markup=reply_markup
    )
    
    return States.UNFOUND_IP_INPUT


@handle_errors
async def unfound_ip_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода IP-адреса
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    ip_address = update.message.text.strip()
    
    # Валидация IP-адреса
    if ip_address and not validate_ip_address(ip_address):
        await update.message.reply_text(
            "⚠️ Недопустимый формат IP-адреса.\n"
            "Введите корректный IPv4 адрес (например: 192.168.1.100)."
        )
        return States.UNFOUND_IP_INPUT
    
    context.user_data['unfound_ip'] = ip_address
    
    # Сохраняем user_id для show_branch_buttons
    context._user_id = update.effective_user.id
    
    logger.info(f"Переход к выбору филиала, user_id: {context._user_id}")
    
    # Показываем филиалы
    await show_branch_buttons(update.message, context, mode='unfound')
    
    return States.UNFOUND_BRANCH_INPUT


@handle_errors
async def unfound_location_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода локации с подсказками
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    from bot.handlers.suggestions_handler import show_location_suggestions
    
    location = update.message.text.strip()
    
    if location.lower() == '/skip':
        context.user_data['unfound_location'] = ''
        await show_status_buttons(update.message, context, mode='unfound')
        return States.UNFOUND_STATUS_INPUT
    
    # Показываем подсказки если есть совпадения
    if await show_location_suggestions(
        update, context, location,
        mode='unfound',
        pending_key='pending_unfound_location_input',
        suggestions_key='unfound_location_suggestions'
    ):
        return States.UNFOUND_LOCATION_INPUT
    
    context.user_data['unfound_location'] = location
    
    await show_status_buttons(update.message, context, mode='unfound')
    
    return States.UNFOUND_STATUS_INPUT


@handle_errors
async def unfound_status_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода статуса (теперь только через кнопки)
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    # Если пользователь ввел текст, показываем кнопки
    from bot.handlers.suggestions_handler import show_status_suggestions
    await update.message.reply_text(
        "📊 Пожалуйста, выберите статус из предложенных вариантов:"
    )
    await show_status_suggestions(update, context, mode='unfound')
    
    return States.UNFOUND_STATUS_INPUT


@handle_errors
async def unfound_branch_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода филиала с подсказками
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние UNFOUND_CONFIRMATION
    """
    # Если это первый вход, показываем подсказки
    if not context.user_data.get('unfound_branch_shown'):
        from bot.handlers.suggestions_handler import show_branch_suggestions
        context.user_data['unfound_branch_shown'] = True
        await show_branch_suggestions(update, context, mode='unfound', suggestions_key='unfound_branch_suggestions')
        return States.UNFOUND_BRANCH_INPUT
    
    branch = update.message.text.strip()
    
    if branch.lower() == '/skip':
        context.user_data['unfound_branch'] = ''
    else:
        context.user_data['unfound_branch'] = branch
    
    # Создаем клавиатуру с кнопкой "Пропустить"
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_location")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📍 Введите локацию (необязательно):",
        reply_markup=reply_markup
    )
    
    return States.UNFOUND_LOCATION_INPUT


async def show_unfound_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отображает данные для подтверждения перед сохранением
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
    """
    # Собираем все данные
    data = {
        'serial_number': context.user_data.get('unfound_serial', 'Не указан'),
        'employee_name': context.user_data.get('unfound_employee', ''),
        'equipment_type': context.user_data.get('unfound_type', ''),
        'model_name': context.user_data.get('unfound_model', ''),
        'description': context.user_data.get('unfound_description', '-'),
        'inventory_number': context.user_data.get('unfound_inventory', '-'),
        'ip_address': context.user_data.get('unfound_ip', '-'),
        'location': context.user_data.get('unfound_location', '-'),
        'status': context.user_data.get('unfound_status', '-'),
        'branch': context.user_data.get('unfound_branch', '-'),
    }
    
    # Формируем сообщение
    message_lines = [
        "📋 <b>Проверьте введенные данные:</b>\n",
        f"🔢 <b>Серийный номер:</b> {data['serial_number']}",
        f"👤 <b>Сотрудник:</b> {data['employee_name']}",
        f"🔧 <b>Тип:</b> {data['equipment_type']}",
        f"🏷️ <b>Модель:</b> {data['model_name']}",
        f"📄 <b>Описание:</b> {data['description']}",
        f"🔢 <b>Инв. номер:</b> {data['inventory_number']}",
        f"🌐 <b>IP-адрес:</b> {data['ip_address']}",
        f"📍 <b>Локация:</b> {data['location']}",
        f"📊 <b>Статус:</b> {data['status']}",
        f"🏢 <b>Филиал:</b> {data['branch']}",
    ]
    
    message_text = "\n".join(message_lines)
    
    # Создаем клавиатуру подтверждения
    keyboard = [
        [
            InlineKeyboardButton("✅ Сохранить", callback_data="confirm_unfound"),
            InlineKeyboardButton("✏️ Изменить", callback_data="edit_unfound")
        ],
        [
            InlineKeyboardButton("❌ Отменить", callback_data="cancel_unfound")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            message_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )


@handle_errors
async def handle_unfound_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик подтверждения/отмены сохранения данных
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: ConversationHandler.END
    """
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_unfound":
        # Сохраняем данные
        try:
            from database_manager import database_manager
            
            user_id = update.effective_user.id
            db_name = database_manager.get_user_database(user_id)
            
            success = equipment_manager.add_unfound_equipment(
                serial_number=context.user_data.get('unfound_serial', ''),
                model_name=context.user_data.get('unfound_model', ''),
                employee_name=context.user_data.get('unfound_employee', ''),
                location=context.user_data.get('unfound_location', ''),
                equipment_type=context.user_data.get('unfound_type', ''),
                description=context.user_data.get('unfound_description', ''),
                inventory_number=context.user_data.get('unfound_inventory', ''),
                ip_address=context.user_data.get('unfound_ip', ''),
                status=context.user_data.get('unfound_status', ''),
                branch=context.user_data.get('unfound_branch', ''),
                additional_data={'db_name': db_name}
            )
            
            if success:
                await query.edit_message_text(
                    "✅ Данные успешно сохранены!\n"
                    "Информация об оборудовании добавлена в базу ненайденного оборудования."
                )
            else:
                await query.edit_message_text(
                    "❌ Ошибка при сохранении данных.\n"
                    "Возможно, оборудование с таким серийным номером уже существует."
                )
            
            # Очищаем временные данные
            clear_unfound_data(context)
            
        except Exception as e:
            logger.error(f"Ошибка сохранения ненайденного оборудования: {e}")
            await query.edit_message_text(
                "❌ Произошла ошибка при сохранении данных. Попробуйте позже."
            )
    
    elif query.data == "cancel_unfound":
        await query.edit_message_text("❌ Добавление оборудования отменено.")
        clear_unfound_data(context)
    
    return ConversationHandler.END


@handle_errors
async def handle_skip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик кнопок "Пропустить" для необязательных полей
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data == "skip_description":
        context.user_data['unfound_description'] = ''
        
        keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_inventory")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔢 Введите инвентарный номер (необязательно):",
            reply_markup=reply_markup
        )
        return States.UNFOUND_INVENTORY_INPUT
    
    elif callback_data == "skip_inventory":
        context.user_data['unfound_inventory'] = ''
        
        keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_ip")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🌐 Введите IP-адрес (необязательно):",
            reply_markup=reply_markup
        )
        return States.UNFOUND_IP_INPUT
    
    elif callback_data == "skip_ip":
        context.user_data['unfound_ip'] = ''
        
        await query.edit_message_text("⏭️ IP-адрес пропущен")
        
        # Сохраняем user_id для show_branch_buttons
        context._user_id = update.effective_user.id
        
        # Показываем филиалы
        await show_branch_buttons(query.message, context, mode='unfound')
        
        return States.UNFOUND_BRANCH_INPUT
    
    elif callback_data == "skip_location":
        context.user_data['unfound_location'] = ''
        
        keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_status")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📊 Введите статус оборудования (необязательно):",
            reply_markup=reply_markup
        )
        return States.UNFOUND_STATUS_INPUT
    
    elif callback_data == "skip_status":
        context.user_data['unfound_status'] = ''
        
        keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_branch")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🏢 Введите филиал (необязательно):",
            reply_markup=reply_markup
        )
        return States.UNFOUND_BRANCH_INPUT
    
    elif callback_data == "skip_branch":
        context.user_data['unfound_branch'] = ''
        await show_unfound_confirmation(update, context)
        return States.UNFOUND_CONFIRMATION
    
    return States.UNFOUND_CONFIRMATION


def clear_unfound_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Очищает временные данные ненайденного оборудования из контекста
    
    Параметры:
        context: Контекст выполнения
    """
    keys_to_clear = [
        'unfound_serial', 'unfound_employee', 'unfound_type', 'unfound_model',
        'unfound_description', 'unfound_inventory', 'unfound_ip',
        'unfound_location', 'unfound_status', 'unfound_branch'
    ]
    
    for key in keys_to_clear:
        context.user_data.pop(key, None)



@handle_errors
async def handle_unfound_employee_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора сотрудника из подсказок для ненайденного оборудования
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    from bot.handlers.suggestions_handler import handle_employee_suggestion_generic
    
    return await handle_employee_suggestion_generic(
        update=update,
        context=context,
        mode='unfound',
        storage_key='unfound_employee',
        pending_key='pending_unfound_employee_input',
        suggestions_key='unfound_employee_suggestions',
        next_state=States.UNFOUND_TYPE_INPUT,
        next_message="🔧 Укажите тип оборудования\n(например: Системный блок, МФУ, Монитор, ИБП):"
    )



@handle_errors
async def handle_unfound_type_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора типа оборудования из подсказок
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'unfound_type:manual':
        pending = context.user_data.get('pending_unfound_type_input', '').strip()
        
        if not pending or len(pending) < 2:
            await query.edit_message_text(
                "❌ Введите корректный тип оборудования (минимум 2 символа)."
            )
            return States.UNFOUND_TYPE_INPUT
        
        context.user_data['unfound_type'] = pending
        await query.edit_message_text(f"✅ Принято: {pending}")
        await query.message.reply_text(
            "🏭 Введите модель оборудования\n"
            "(например: Dell Latitude 5420, HP LaserJet Pro M404dn):"
        )
        
        return States.UNFOUND_MODEL_INPUT
    
    elif data.startswith('unfound_type:'):
        try:
            idx = int(data.split(':', 1)[1])
            suggestions = context.user_data.get('unfound_type_suggestions', [])
            
            if 0 <= idx < len(suggestions):
                selected_type = suggestions[idx]
                context.user_data['unfound_type'] = selected_type
                
                await query.edit_message_text(f"✅ Выбран тип: {selected_type}")
                await query.message.reply_text(
                    "🏭 Введите модель оборудования\n"
                    "(например: Dell Latitude 5420, HP LaserJet Pro M404dn):"
                )
                
                return States.UNFOUND_MODEL_INPUT
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора типа: {e}")
    
    return States.UNFOUND_TYPE_INPUT


@handle_errors
async def handle_unfound_model_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора модели из подсказок
    """
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'unfound_model:manual':
        pending = context.user_data.get('pending_unfound_model_input', '').strip()
        
        if not pending or len(pending) < 2:
            await query.edit_message_text(
                "❌ Введите корректную модель (минимум 2 символа)."
            )
            return States.UNFOUND_MODEL_INPUT
        
        context.user_data['unfound_model'] = pending
        await query.edit_message_text(f"✅ Принято: {pending}")
        
        # Создаем клавиатуру с кнопкой "Пропустить"
        keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_description")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            "📄 Введите описание оборудования (необязательно):",
            reply_markup=reply_markup
        )
        
        return States.UNFOUND_DESCRIPTION_INPUT
    
    elif data.startswith('unfound_model:'):
        try:
            idx = int(data.split(':', 1)[1])
            suggestions = context.user_data.get('unfound_model_suggestions', [])
            
            if 0 <= idx < len(suggestions):
                selected_model = suggestions[idx]
                context.user_data['unfound_model'] = selected_model
                
                await query.edit_message_text(f"✅ Выбрана модель: {selected_model}")
                
                # Создаем клавиатуру с кнопкой "Пропустить"
                keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_description")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.message.reply_text(
                    "📄 Введите описание оборудования (необязательно):",
                    reply_markup=reply_markup
                )
                
                return States.UNFOUND_DESCRIPTION_INPUT
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора модели: {e}")
    
    return States.UNFOUND_MODEL_INPUT


@handle_errors
async def handle_unfound_location_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора локации из подсказок
    """
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'unfound_loc:manual':
        pending = context.user_data.get('pending_unfound_location_input', '').strip()
        
        context.user_data['unfound_location'] = pending
        await query.edit_message_text(f"✅ Принято: {pending}")
        
        # Показываем статусы напрямую
        await show_status_buttons(query.message, context, mode='unfound')
        
        return States.UNFOUND_STATUS_INPUT
    
    elif data.startswith('unfound_loc:'):
        try:
            idx = int(data.split(':', 1)[1])
            suggestions = context.user_data.get('unfound_location_suggestions', [])
            
            if 0 <= idx < len(suggestions):
                selected_location = suggestions[idx]
                context.user_data['unfound_location'] = selected_location
                
                await query.edit_message_text(f"✅ Выбрана локация: {selected_location}")
                
                # Показываем статусы напрямую
                await show_status_buttons(query.message, context, mode='unfound')
                
                return States.UNFOUND_STATUS_INPUT
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора локации: {e}")
    
    return States.UNFOUND_LOCATION_INPUT


async def show_status_buttons(message, context, mode='unfound'):
    """
    Показывает кнопки выбора статуса
    """
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    
    statuses = [
        "В работе",
        "На складе",
        "В ремонте",
        "Списано",
        "Резерв",
        "Новое"
    ]
    
    context.user_data[f'{mode}_status_suggestions'] = statuses
    
    keyboard = []
    for idx, status in enumerate(statuses):
        keyboard.append([InlineKeyboardButton(
            f"📊 {status}",
            callback_data=f"{mode}_status:{idx}"
        )])
    
    keyboard.append([InlineKeyboardButton(
        "⏭️ Пропустить",
        callback_data="skip_status"
    )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        "📊 Выберите статус оборудования:",
        reply_markup=reply_markup
    )


async def show_branch_buttons(message, context, mode='unfound'):
    """
    Показывает кнопки выбора филиала
    """
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from bot.services.suggestions import get_branch_suggestions
    
    try:
        # Получаем user_id из context
        user_id = getattr(context, '_user_id', None)
        
        logger.info(f"show_branch_buttons вызвана, user_id: {user_id}")
        
        if not user_id:
            logger.warning("user_id не найден в context для show_branch_buttons")
            await message.reply_text(
                "🏢 Введите филиал (или отправьте /skip чтобы пропустить):"
            )
            return
        
        # Получаем филиалы из БД
        branches = get_branch_suggestions(user_id)
        logger.info(f"Получено филиалов: {len(branches) if branches else 0}")
        
        if branches:
            context.user_data[f'{mode}_branch_suggestions'] = branches
            
            keyboard = []
            for idx, branch in enumerate(branches):
                keyboard.append([InlineKeyboardButton(
                    f"🏢 {branch}",
                    callback_data=f"{mode}_branch:{idx}"
                )])
            
            keyboard.append([InlineKeyboardButton(
                "⏭️ Пропустить",
                callback_data="skip_branch"
            )])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text(
                "🏢 Выберите филиал из списка:",
                reply_markup=reply_markup
            )
        else:
            # Если филиалы не получены, просим ввести вручную
            await message.reply_text(
                "🏢 Введите филиал (или отправьте /skip чтобы пропустить):"
            )
    except Exception as e:
        logger.error(f"Ошибка при показе кнопок филиалов: {e}")
        await message.reply_text(
            "🏢 Введите филиал (или отправьте /skip чтобы пропустить):"
        )


@handle_errors
async def handle_unfound_status_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора статуса из подсказок
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'skip_status':
        context.user_data['unfound_status'] = ''
        await query.edit_message_text("⏭️ Статус пропущен")
        await show_unfound_confirmation_after_callback(query, context)
        return States.UNFOUND_CONFIRMATION
    
    elif data.startswith('unfound_status:'):
        try:
            idx = int(data.split(':', 1)[1])
            suggestions = context.user_data.get('unfound_status_suggestions', [])
            
            if 0 <= idx < len(suggestions):
                selected_status = suggestions[idx]
                context.user_data['unfound_status'] = selected_status
                
                await query.edit_message_text(f"✅ Выбран статус: {selected_status}")
                await show_unfound_confirmation_after_callback(query, context)
                
                return States.UNFOUND_CONFIRMATION
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора статуса: {e}")
    
    return States.UNFOUND_STATUS_INPUT


@handle_errors
async def handle_unfound_branch_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора филиала из подсказок
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'skip_branch':
        context.user_data['unfound_branch'] = ''
        await query.edit_message_text("⏭️ Филиал пропущен")
        
        # Создаем клавиатуру с кнопкой "Пропустить"
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_location")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            "📍 Введите локацию (необязательно):",
            reply_markup=reply_markup
        )
        return States.UNFOUND_LOCATION_INPUT
    
    elif data.startswith('unfound_branch:'):
        try:
            idx = int(data.split(':', 1)[1])
            suggestions = context.user_data.get('unfound_branch_suggestions', [])
            
            if 0 <= idx < len(suggestions):
                selected_branch = suggestions[idx]
                context.user_data['unfound_branch'] = selected_branch
                
                await query.edit_message_text(f"✅ Выбран филиал: {selected_branch}")
                
                # Создаем клавиатуру с кнопкой "Пропустить"
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_location")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.message.reply_text(
                    "📍 Введите локацию (необязательно):",
                    reply_markup=reply_markup
                )
                
                return States.UNFOUND_LOCATION_INPUT
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора филиала: {e}")
    
    return States.UNFOUND_BRANCH_INPUT


async def show_unfound_confirmation_after_callback(query, context):
    """
    Показывает подтверждение после callback query
    """
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    
    # Формируем сообщение подтверждения
    employee = context.user_data.get('unfound_employee', 'Не указан')
    equipment_type = context.user_data.get('unfound_type', 'Не указан')
    model = context.user_data.get('unfound_model', 'Не указана')
    description = context.user_data.get('unfound_description', '')
    inventory = context.user_data.get('unfound_inventory', '')
    ip_address = context.user_data.get('unfound_ip', '')
    location = context.user_data.get('unfound_location', '')
    status = context.user_data.get('unfound_status', '')
    branch = context.user_data.get('unfound_branch', '')
    serial = context.user_data.get('unfound_serial', '')
    
    confirmation_text = f"📋 <b>Подтверждение данных</b>\n\n"
    confirmation_text += f"👤 <b>Сотрудник:</b> {employee}\n"
    confirmation_text += f"🔧 <b>Тип:</b> {equipment_type}\n"
    confirmation_text += f"🏭 <b>Модель:</b> {model}\n"
    
    if serial:
        confirmation_text += f"🔢 <b>Серийный номер:</b> {serial}\n"
    if description:
        confirmation_text += f"📝 <b>Описание:</b> {description}\n"
    if inventory:
        confirmation_text += f"📦 <b>Инвентарный номер:</b> {inventory}\n"
    if ip_address:
        confirmation_text += f"🌐 <b>IP-адрес:</b> {ip_address}\n"
    if location:
        confirmation_text += f"📍 <b>Локация:</b> {location}\n"
    if status:
        confirmation_text += f"📊 <b>Статус:</b> {status}\n"
    if branch:
        confirmation_text += f"🏢 <b>Филиал:</b> {branch}\n"
    
    confirmation_text += "\n❓ Сохранить эти данные?"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Сохранить", callback_data="confirm_unfound"),
            InlineKeyboardButton("✏️ Изменить", callback_data="edit_unfound")
        ],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_unfound")]
    ])
    
    await query.message.reply_text(
        confirmation_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )



@handle_errors
async def handle_edit_unfound(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик кнопки "Изменить" - показывает меню выбора поля для редактирования
    """
    query = update.callback_query
    await query.answer()
    
    # Создаем клавиатуру с полями для редактирования
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    
    keyboard = [
        [InlineKeyboardButton("👤 ФИО сотрудника", callback_data="edit_field:employee")],
        [InlineKeyboardButton("🔧 Тип оборудования", callback_data="edit_field:type")],
        [InlineKeyboardButton("🏭 Модель", callback_data="edit_field:model")],
        [InlineKeyboardButton("📝 Описание", callback_data="edit_field:description")],
        [InlineKeyboardButton("📦 Инвентарный номер", callback_data="edit_field:inventory")],
        [InlineKeyboardButton("🌐 IP-адрес", callback_data="edit_field:ip")],
        [InlineKeyboardButton("🏢 Филиал", callback_data="edit_field:branch")],
        [InlineKeyboardButton("📍 Локация", callback_data="edit_field:location")],
        [InlineKeyboardButton("📊 Статус", callback_data="edit_field:status")],
        [InlineKeyboardButton("◀️ Назад к подтверждению", callback_data="back_to_confirmation")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "✏️ <b>Выберите поле для изменения:</b>",
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    return States.UNFOUND_CONFIRMATION


@handle_errors
async def handle_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора поля для редактирования
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    field = data.split(':', 1)[1] if ':' in data else ''
    
    if field == 'employee':
        await query.edit_message_text("👤 Введите новое ФИО сотрудника:")
        return States.UNFOUND_EMPLOYEE_INPUT
    
    elif field == 'type':
        await query.edit_message_text("🔧 Введите новый тип оборудования (минимум 2 символа):")
        context.user_data.pop('unfound_type_shown', None)  # Сбрасываем флаг
        return States.UNFOUND_TYPE_INPUT
    
    elif field == 'model':
        await query.edit_message_text("🏭 Введите новую модель оборудования:")
        return States.UNFOUND_MODEL_INPUT
    
    elif field == 'description':
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_description")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📝 Введите новое описание:",
            reply_markup=reply_markup
        )
        return States.UNFOUND_DESCRIPTION_INPUT
    
    elif field == 'inventory':
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_inventory")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📦 Введите новый инвентарный номер:",
            reply_markup=reply_markup
        )
        return States.UNFOUND_INVENTORY_INPUT
    
    elif field == 'ip':
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_ip")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🌐 Введите новый IP-адрес:",
            reply_markup=reply_markup
        )
        return States.UNFOUND_IP_INPUT
    
    elif field == 'branch':
        await query.edit_message_text("🏢 Выберите новый филиал:")
        context.user_data.pop('unfound_branch_shown', None)  # Сбрасываем флаг
        context._user_id = update.effective_user.id
        await show_branch_buttons(query.message, context, mode='unfound')
        return States.UNFOUND_BRANCH_INPUT
    
    elif field == 'location':
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_location")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📍 Введите новую локацию:",
            reply_markup=reply_markup
        )
        return States.UNFOUND_LOCATION_INPUT
    
    elif field == 'status':
        await query.edit_message_text("📊 Выберите новый статус:")
        context._user_id = update.effective_user.id
        await show_status_buttons(query.message, context, mode='unfound')
        return States.UNFOUND_STATUS_INPUT
    
    return States.UNFOUND_CONFIRMATION


@handle_errors
async def handle_back_to_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик кнопки "Назад к подтверждению"
    """
    query = update.callback_query
    await query.answer()
    
    await show_unfound_confirmation_after_callback(query, context)
    
    return States.UNFOUND_CONFIRMATION
