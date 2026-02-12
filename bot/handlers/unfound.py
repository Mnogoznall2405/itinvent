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
from bot.utils.pagination import PaginationHandler
from bot.services.validation import (
    validate_employee_name,
    validate_serial_number,
    validate_ip_address,
    validate_inventory_number
)
from bot.equipment_data_manager import EquipmentDataManager

logger = logging.getLogger(__name__)

# Глобальный менеджер данных
equipment_manager = EquipmentDataManager()


# ============================ ИМПОРТ УНИВЕРСАЛЬНЫХ ОБРАБОТЧИКОВ ЛОКАЦИЙ ============================
from bot.handlers.location import (
    _unfound_location_pagination_handler,
    handle_location_navigation_universal,
    show_location_buttons,
)


# Обработчик для пагинации статусов в unfound
_unfound_status_pagination_handler = PaginationHandler(
    page_key='unfound_status_page',
    items_key='unfound_status_suggestions',
    items_per_page=8,
    callback_prefix='unfound_status'
)


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
    from bot.database_manager import database_manager

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

    # Проверяем, существует ли сотрудник в базе
    user_id = update.effective_user.id
    db = database_manager.create_database_connection(user_id)

    employee_exists = False
    if db:
        try:
            owner_no = db.get_owner_no_by_name(employee_name, strict=True)
            if not owner_no:
                owner_no = db.get_owner_no_by_name(employee_name, strict=False)
            employee_exists = owner_no is not None
        finally:
            db.close_connection()

    if employee_exists:
        # Сотрудник найден - сохраняем и продолжаем
        context.user_data['unfound_employee'] = employee_name
        await update.message.reply_text(
            "🔧 Укажите тип оборудования\n"
            "(например: Системный блок, МФУ, Монитор, ИБП):"
        )
        return States.UNFOUND_TYPE_INPUT
    else:
        # Сотрудник не найден - предлагаем создать нового
        context.user_data['pending_unfound_employee'] = employee_name

        keyboard = [
            [InlineKeyboardButton("✅ Создать нового сотрудника", callback_data="create_new_employee")],
            [InlineKeyboardButton("✏️ Ввести ФИО заново", callback_data="retry_employee_input")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"⚠️ Сотрудник <b>{employee_name}</b> не найден в базе данных.\n\n"
            "Вы можете:\n"
            "• Создать нового сотрудника с этим ФИО\n"
            "• Ввести другое ФИО",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return States.UNFOUND_EMPLOYEE_CONFIRMATION


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
        suggestions_key='unfound_model_suggestions',
        equipment_type='all'  # Ищем все типы оборудования, не только принтеры/МФУ
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

    # Пропускаем инвентарный номер (генерируется автоматически)
    # Создаем клавиатуру с кнопкой "Пропустить"
    keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_ip")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🌐 Введите IP-адрес (необязательно):",
        reply_markup=reply_markup
    )

    return States.UNFOUND_IP_INPUT


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
            from bot.database_manager import database_manager

            user_id = update.effective_user.id
            db_name = database_manager.get_user_database(user_id)

            # Сначала сохраняем в JSON (как было раньше)
            json_success = equipment_manager.add_unfound_equipment(
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

            # Теперь добавляем в таблицу ITEMS в базе данных
            db_success = False
            db_message = ""

            if json_success:
                db = database_manager.create_database_connection(user_id)
                if db:
                    try:
                        result = db.add_equipment_to_items(
                            serial_number=context.user_data.get('unfound_serial', ''),
                            model_name=context.user_data.get('unfound_model', ''),
                            employee_name=context.user_data.get('unfound_employee', ''),
                            location_descr=context.user_data.get('unfound_location', ''),
                            branch_name=context.user_data.get('unfound_branch', ''),
                            equipment_type=context.user_data.get('unfound_type', ''),
                            inv_no=context.user_data.get('unfound_inventory', ''),
                            description=context.user_data.get('unfound_description', ''),
                            ip_address=context.user_data.get('unfound_ip', ''),
                            status=context.user_data.get('unfound_status', 'В эксплуатации'),
                            status_no=context.user_data.get('unfound_status_no'),  # Передаём ID напрямую
                            type_no=context.user_data.get('unfound_type_no'),  # Передаём ID напрямую
                            model_no=context.user_data.get('unfound_model_no')  # Передаём ID напрямую
                        )
                        db_success = result.get('success', False)
                        db_message = result.get('message', '')

                    finally:
                        db.close_connection()

            # Формируем ответ пользователю
            if json_success and db_success:
                await query.edit_message_text(
                    f"✅ Данные успешно сохранены!\n\n"
                    f"Оборудование добавлено в базу данных (ITEMS).\n"
                    f"{db_message}"
                )
            elif json_success:
                await query.edit_message_text(
                    f"⚠️ Данные сохранены в JSON, но возникли проблемы с базой данных:\n\n"
                    f"{db_message}\n\n"
                    f"Информация об оборудовании добавлена в базу ненайденного оборудования."
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
        context.user_data['unfound_inventory'] = None  # Инвентарный номер будет сгенерирован автоматически

        keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_ip")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🌐 Введите IP-адрес (необязательно):",
            reply_markup=reply_markup
        )
        return States.UNFOUND_IP_INPUT

    elif callback_data == "skip_inventory":
        context.user_data['unfound_inventory'] = None  # Инвентарный номер будет сгенерирован автоматически

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

        await query.edit_message_text("⏭️ Локация пропущена")

        # Показываем статусы кнопками
        await show_status_buttons(query.message, context, mode='unfound')
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
        'unfound_type_no', 'unfound_model_no',  # Добавляем ID
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

                # Сразу ищем и сохраним TYPE_NO
                from bot.database_manager import database_manager
                user_id = query.from_user.id
                db = database_manager.create_database_connection(user_id)
                if db:
                    try:
                        type_no = db.get_type_no_by_name(selected_type, strict=True)
                        if not type_no:
                            type_no = db.get_type_no_by_name(selected_type, strict=False)
                        if type_no:
                            context.user_data['unfound_type_no'] = type_no
                            logger.info(f"Сохранён TYPE_NO={type_no} для типа '{selected_type}'")
                    finally:
                        db.close_connection()

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

                # Сразу ищем и сохраним MODEL_NO
                from bot.database_manager import database_manager
                user_id = query.from_user.id
                db = database_manager.create_database_connection(user_id)
                if db:
                    try:
                        model_no = db.get_model_no_by_name(selected_model, strict=True)
                        if not model_no:
                            model_no = db.get_model_no_by_name(selected_model, strict=False)
                        if model_no:
                            context.user_data['unfound_model_no'] = model_no
                            logger.info(f"Сохранён MODEL_NO={model_no} для модели '{selected_model}'")
                    finally:
                        db.close_connection()

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


@handle_errors
async def handle_unfound_location_button_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора локации из кнопок (после выбора филиала) с поддержкой пагинации
    """
    query = update.callback_query
    await query.answer()

    data = query.data

    # Обработка пагинации через универсальный обработчик
    if data in ('unfound_location_prev', 'unfound_location_next'):
        return await handle_location_navigation_universal(update, context, mode='unfound') or States.UNFOUND_LOCATION_INPUT

    elif data == 'skip_location':
        context.user_data['unfound_location'] = ''
        await query.edit_message_text("⏭️ Локация пропущена")

        # Показываем статусы
        await show_status_buttons(query.message, context, mode='unfound')
        return States.UNFOUND_STATUS_INPUT

    elif data.startswith('unfound_location:'):
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
            logger.error(f"Ошибка обработки выбора локации из кнопок: {e}")

    return States.UNFOUND_LOCATION_INPUT


async def show_status_buttons(message, context, mode='unfound', query=None):
    """
    Показывает кнопки выбора статуса (подгружает из базы данных) с пагинацией

    Параметры:
        message: Объект Message или CallbackQuery.message
        context: Контекст выполнения
        mode: Режим работы ('unfound', 'transfer', и т.д.)
        query: Объект CallbackQuery (опционально, для редактирования сообщения)
    """
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from bot.database_manager import database_manager

    try:
        # Получаем user_id из context
        user_id = getattr(context, '_user_id', None)

        if not user_id:
            logger.warning("user_id не найден в context для show_status_buttons")
            if query:
                await query.edit_message_text("📊 Введите статус оборудования:")
            else:
                await message.reply_text("📊 Введите статус оборудования:")
            return

        # Получаем статусы из БД с ID
        db = database_manager.create_database_connection(user_id)
        if not db:
            logger.warning("Не удалось подключиться к БД для show_status_buttons")
            if query:
                await query.edit_message_text("📊 Введите статус оборудования:")
            else:
                await message.reply_text("📊 Введите статус оборудования:")
            return

        try:
            statuses_with_ids = db.get_status_list_with_ids()
        finally:
            db.close_connection()

        if not statuses_with_ids:
            logger.warning("Список статусов пуст")
            if query:
                await query.edit_message_text("📊 Введите статус оборудования:")
            else:
                await message.reply_text("📊 Введите статус оборудования:")
            return

        # Сохраняем список кортежей (STATUS_NO, DESCR)
        if mode == 'unfound':
            _unfound_status_pagination_handler.set_items(context, statuses_with_ids)
        else:
            # Для других modes используем старый метод
            context.user_data[f'{mode}_status_suggestions'] = statuses_with_ids

        # Пагинация - получаем данные через PaginationHandler
        if mode == 'unfound':
            page_statuses, current_page, total_pages, has_prev, has_next = _unfound_status_pagination_handler.get_page_data(context)
            start_idx = current_page * _unfound_status_pagination_handler.items_per_page
        else:
            # Старый метод для других modes
            current_page = context.user_data.get(f'{mode}_status_page', 0)
            items_per_page = 8
            total_pages = (len(statuses_with_ids) + items_per_page - 1) // items_per_page
            start_idx = current_page * items_per_page
            end_idx = start_idx + items_per_page
            page_statuses = statuses_with_ids[start_idx:end_idx]

        keyboard = []
        for idx, (status_no, status_name) in enumerate(page_statuses):
            global_idx = start_idx + idx  # Глобальный индекс в полном списке
            keyboard.append([InlineKeyboardButton(
                f"📊 {status_name}",
                callback_data=f"{mode}_status:{global_idx}"
            )])

        # Навигация
        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"{mode}_status_prev"))

        if total_pages > 1:
            nav_buttons.append(InlineKeyboardButton(
                f"📄 {current_page + 1}/{total_pages}",
                callback_data=f"{mode}_status_page_info"
            ))

        if current_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"{mode}_status_next"))

        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton(
            "⏭️ Пропустить",
            callback_data="skip_status"
        )])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Используем query.edit_message_text если передан query, иначе проверяем тип message
        if query:
            await query.edit_message_text(
                "📊 Выберите статус оборудования:",
                reply_markup=reply_markup
            )
        elif hasattr(message, 'reply_text'):
            await message.reply_text(
                "📊 Выберите статус оборудования:",
                reply_markup=reply_markup
            )
        else:
            await message.edit_text(
                "📊 Выберите статус оборудования:",
                reply_markup=reply_markup
            )

    except Exception as e:
        logger.error(f"Ошибка в show_status_buttons: {e}")
        if query:
            await query.edit_message_text("📊 Введите статус оборудования:")
        else:
            await message.reply_text("📊 Введите статус оборудования:")


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
    Обработчик выбора статуса из подсказок с поддержкой пагинации
    """
    query = update.callback_query
    await query.answer()

    data = query.data

    # Обработка пагинации
    if data == 'unfound_status_prev':
        _unfound_status_pagination_handler.handle_navigation(update, context, 'prev')
        await show_status_buttons(query.message, context, mode='unfound', query=query)
        return States.UNFOUND_STATUS_INPUT

    elif data == 'unfound_status_next':
        _unfound_status_pagination_handler.handle_navigation(update, context, 'next')
        await show_status_buttons(query.message, context, mode='unfound', query=query)
        return States.UNFOUND_STATUS_INPUT

    elif data == 'skip_status':
        context.user_data['unfound_status'] = ''
        context.user_data['unfound_status_no'] = None
        await query.edit_message_text("⏭️ Статус пропущен")
        await show_unfound_confirmation_after_callback(query, context)
        return States.UNFOUND_CONFIRMATION

    elif data.startswith('unfound_status:'):
        try:
            idx = int(data.split(':', 1)[1])
            suggestions = context.user_data.get('unfound_status_suggestions', [])

            if 0 <= idx < len(suggestions):
                # suggestions теперь содержит кортежи (STATUS_NO, DESCR)
                selected = suggestions[idx]
                if isinstance(selected, tuple) and len(selected) == 2:
                    status_no, status_name = selected
                    context.user_data['unfound_status'] = status_name
                    context.user_data['unfound_status_no'] = status_no
                    logger.info(f"Выбран статус: {status_name} (STATUS_NO={status_no})")
                else:
                    # Fallback для старого формата (просто строка)
                    status_name = selected
                    context.user_data['unfound_status'] = status_name
                    logger.info(f"Выбран статус (без ID): {status_name}")

                await query.edit_message_text(f"✅ Выбран статус: {status_name}")
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

        # Показываем локации с кнопкой "Пропустить"
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

                # Показываем локации кнопками для выбранного филиала
                context._user_id = update.effective_user.id
                await show_location_buttons(query.message, context, mode='unfound', branch=selected_branch)

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


@handle_errors
async def handle_create_new_employee(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик кнопки "Создать нового сотрудника"

    Создает нового сотрудника в таблице OWNERS и переходит к вводу типа оборудования.
    """
    from bot.database_manager import database_manager

    query = update.callback_query
    await query.answer()

    employee_name = context.user_data.get('pending_unfound_employee', '').strip()

    if not employee_name:
        await query.edit_message_text("❌ Ошибка: ФИО сотрудника не найдено. Попробуйте заново.")
        return States.UNFOUND_EMPLOYEE_INPUT

    user_id = update.effective_user.id
    db = database_manager.create_database_connection(user_id)

    if db:
        try:
            # Проверяем еще раз, вдруг сотрудник уже создали
            owner_no = db.get_owner_no_by_name(employee_name, strict=True)
            if not owner_no:
                owner_no = db.get_owner_no_by_name(employee_name, strict=False)

            if owner_no:
                # Сотрудник уже существует
                context.user_data['unfound_employee'] = employee_name
                await query.edit_message_text(f"✅ Сотрудник {employee_name} уже существует в базе")
                await query.message.reply_text(
                    "🔧 Укажите тип оборудования\n"
                    "(например: Системный блок, МФУ, Монитор, ИБП):"
                )
                return States.UNFOUND_TYPE_INPUT

            # Создаем нового сотрудника
            logger.info(f"Создаем нового сотрудника: {employee_name}")
            new_owner_no = db.create_owner(employee_name=employee_name, department=None)

            if new_owner_no:
                context.user_data['unfound_employee'] = employee_name
                logger.info(f"✅ Создан новый сотрудник: {employee_name} (OWNER_NO={new_owner_no})")
                await query.edit_message_text(f"✅ Создан новый сотрудник: {employee_name}")
                await query.message.reply_text(
                    "🔧 Укажите тип оборудования\n"
                    "(например: Системный блок, МФУ, Монитор, ИБП):"
                )
                return States.UNFOUND_TYPE_INPUT
            else:
                await query.edit_message_text("❌ Не удалось создать сотрудника. Попробуйте позже.")
                return States.UNFOUND_EMPLOYEE_INPUT

        finally:
            db.close_connection()
    else:
        await query.edit_message_text("❌ Ошибка подключения к базе данных")
        return States.UNFOUND_EMPLOYEE_INPUT


@handle_errors
async def handle_retry_employee_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик кнопки "Ввести ФИО заново"

    Возвращает пользователя к вводу ФИО сотрудника.
    """
    query = update.callback_query
    await query.answer()

    await query.edit_message_text("👤 Введите ФИО сотрудника:")

    return States.UNFOUND_EMPLOYEE_INPUT
