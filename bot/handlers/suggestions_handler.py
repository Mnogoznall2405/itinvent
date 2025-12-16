#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Универсальный обработчик подсказок для переиспользования

Содержит общие функции для работы с подсказками сотрудников, моделей и т.д.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot.services.suggestions import get_employee_suggestions
from bot.services.validation import validate_employee_name
from bot.utils.keyboards import create_employee_suggestions_keyboard

logger = logging.getLogger(__name__)


async def handle_employee_suggestion_generic(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mode: str,
    storage_key: str,
    pending_key: str,
    suggestions_key: str,
    next_state: int,
    next_message: str = None
) -> int:
    """
    Универсальный обработчик выбора сотрудника из подсказок
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        mode: Режим работы ('unfound', 'transfer', и т.д.)
        storage_key: Ключ для сохранения выбранного значения
        pending_key: Ключ для временного хранения ввода
        suggestions_key: Ключ для хранения списка подсказок
        next_state: Следующее состояние после выбора
        next_message: Сообщение для следующего шага (опционально)
        
    Возвращает:
        int: Следующее состояние
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    suggestions = context.user_data.get(suggestions_key, [])
    
    # Обработка выбора конкретного сотрудника
    if data.startswith(f'{mode}_emp:') and not data.endswith((':manual', ':refresh')):
        try:
            idx = int(data.split(':', 1)[1])
            if 0 <= idx < len(suggestions):
                selected_name = suggestions[idx]
                context.user_data[storage_key] = selected_name
                
                await query.edit_message_text(f"✅ Выбран сотрудник: {selected_name}")
                
                if next_message:
                    await query.message.reply_text(next_message)
                
                return next_state
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора сотрудника ({mode}): {e}")
    
    # Обработка "Ввести как есть"
    elif data == f'{mode}_emp:manual':
        pending = context.user_data.get(pending_key, '').strip()
        
        if not pending:
            await query.edit_message_text(
                "❌ Не найден введённый текст. Пожалуйста, введите ФИО заново."
            )
            return next_state - 1  # Возврат к предыдущему состоянию
        
        # Валидация
        if not validate_employee_name(pending):
            await query.edit_message_text(
                "❌ ФИО должно содержать только буквы и пробелы.\n"
                "Пожалуйста, введите корректное ФИО."
            )
            return next_state - 1
        
        context.user_data[storage_key] = pending
        await query.edit_message_text(f"✅ Принято: {pending}")
        
        if next_message:
            await query.message.reply_text(next_message)
        
        return next_state
    
    # Обработка "Обновить список"
    elif data == f'{mode}_emp:refresh':
        pending = context.user_data.get(pending_key, '').strip()
        
        if pending and len(pending) >= 2:
            try:
                user_id = update.effective_user.id
                fresh_suggestions = get_employee_suggestions(pending, user_id)
                
                if fresh_suggestions:
                    context.user_data[suggestions_key] = fresh_suggestions
                    reply_markup = create_employee_suggestions_keyboard(fresh_suggestions, mode=mode)
                    await query.edit_message_text(
                        "🔎 Обновлённый список совпадений. Выберите из списка или нажмите 'Ввести как есть'.",
                        reply_markup=reply_markup
                    )
                else:
                    await query.edit_message_text(
                        "❌ Совпадений не найдено. Введите ФИО заново."
                    )
            except Exception as e:
                logger.error(f"Ошибка обновления подсказок ({mode}): {e}")
                await query.edit_message_text(
                    "❌ Ошибка обновления списка. Попробуйте ввести ФИО заново."
                )
        else:
            await query.edit_message_text(
                "❌ Введите хотя бы 2 символа для поиска."
            )
        
        return next_state - 1
    
    return next_state - 1


async def show_employee_suggestions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    employee_name: str,
    mode: str,
    pending_key: str,
    suggestions_key: str
) -> bool:
    """
    Показывает подсказки для ФИО сотрудника
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        employee_name: Введённое ФИО
        mode: Режим работы ('unfound', 'transfer', и т.д.)
        pending_key: Ключ для временного хранения
        suggestions_key: Ключ для хранения подсказок
        
    Возвращает:
        bool: True если подсказки показаны, False если нет
    """
    logger.info(f"[SHOW_SUGGESTIONS] Вызов для '{employee_name}', mode={mode}, user_id={update.effective_user.id}")
    
    # Сохраняем для подсказок
    context.user_data[pending_key] = employee_name
    
    # Если введено 2+ символа, показываем подсказки
    if len(employee_name) >= 2:
        try:
            user_id = update.effective_user.id
            suggestions = get_employee_suggestions(employee_name, user_id)
            
            logger.info(f"[SHOW_SUGGESTIONS] Получено подсказок: {len(suggestions) if suggestions else 0}")
            
            if suggestions:
                context.user_data[suggestions_key] = suggestions
                reply_markup = create_employee_suggestions_keyboard(suggestions, mode=mode)
                await update.message.reply_text(
                    "🔎 Найдены совпадения по сотрудникам. Выберите из списка или нажмите 'Ввести как есть'.",
                    reply_markup=reply_markup
                )
                logger.info(f"[SHOW_SUGGESTIONS] Подсказки отправлены пользователю")
                return True
            else:
                logger.info(f"[SHOW_SUGGESTIONS] Подсказок не найдено для '{employee_name}'")
        except Exception as e:
            logger.error(f"[SHOW_SUGGESTIONS] Ошибка при получении подсказок ФИО ({mode}): {e}", exc_info=True)
    else:
        logger.info(f"[SHOW_SUGGESTIONS] Недостаточно символов ({len(employee_name)}) для подсказок")
    
    return False



async def show_model_suggestions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    model_name: str,
    mode: str,
    pending_key: str,
    suggestions_key: str,
    equipment_type: str = "printers_mfu"
) -> bool:
    """
    Показывает подсказки для модели оборудования с улучшенным поиском по частям слов

    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        model_name: Введённая модель
        mode: Режим работы
        pending_key: Ключ для временного хранения
        suggestions_key: Ключ для хранения подсказок
        equipment_type: Тип оборудования ('printers', 'printers_mfu', или 'all')

    Возвращает:
        bool: True если подсказки показаны
    """
    from bot.services.suggestions import get_model_suggestions
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton

    context.user_data[pending_key] = model_name

    if len(model_name.strip()) >= 2:
        try:
            user_id = update.effective_user.id
            suggestions = get_model_suggestions(model_name, user_id, equipment_type=equipment_type)

            if suggestions:
                context.user_data[suggestions_key] = suggestions

                # Улучшенное форматирование клавиатуры
                keyboard = []
                for idx, model in enumerate(suggestions):
                    # Обрезаем слишком длинные названия для кнопок
                    display_model = model[:40] + "..." if len(model) > 40 else model

                    # Определяем иконку в зависимости от типа устройства
                    icon = "🖨️" if any(keyword in model.lower() for keyword in ['printer', 'принтер', 'hp', 'canon', 'xerox', 'brother']) else "🖥️"
                    if any(keyword in model.lower() for keyword in ['laptop', 'ноутбук', 'notebook']):
                        icon = "💻"
                    elif any(keyword in model.lower() for keyword in ['monitor', 'монитор']):
                        icon = "🖥️"
                    elif any(keyword in model.lower() for keyword in ['scanner', 'сканер']):
                        icon = "📷"
                    elif any(keyword in model.lower() for keyword in ['mfp', 'mfc', 'муфта']):
                        icon = "📠"

                    keyboard.append([InlineKeyboardButton(
                        f"{icon} {display_model}",
                        callback_data=f"{mode}_model:{idx}"
                    )])

                # Добавляем опции ручного ввода
                keyboard.extend([
                    [InlineKeyboardButton(
                        "⌨️ Ввести как есть",
                        callback_data=f"{mode}_model:manual"
                    )],
                    [InlineKeyboardButton(
                        "🔄 Другие варианты",
                        callback_data=f"{mode}_model:refresh"
                    )]
                ])

                reply_markup = InlineKeyboardMarkup(keyboard)

                # Улучшенное сообщение с информацией о поиске
                search_info = []
                if len(model_name.split()) > 1:
                    search_info.append(f"по словам: {' + '.join(model_name.split())}")
                search_info.append(f"всего найдено: {len(suggestions)}")

                await update.message.reply_text(
                    f"🔎 <b>Найдены модели</b> по запросу <code>{model_name}</code>\n"
                    f"📊 {' | '.join(search_info)}\n\n"
                    f"Выберите из списка или введите вручную:",
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
                return True
            else:
                # Если ничего не найдено, предлагаем альтернативы
                keyboard = [
                    [InlineKeyboardButton(
                        "⌨️ Ввести как есть",
                        callback_data=f"{mode}_model:manual"
                    )],
                    [InlineKeyboardButton(
                        "🔄 Попробовать другой поиск",
                        callback_data=f"{mode}_model:refresh"
                    )]
                ]

                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"❌ По запросу <code>{model_name}</code> ничего не найдено\n\n"
                    f"💡 Попробуйте:\n"
                    f"• Ввести только часть названия (например: 'laser' или 'hp')\n"
                    f"• Использовать другие ключевые слова\n"
                    f"• Ввести название вручную",
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
                return True

        except Exception as e:
            logger.error(f"Ошибка при получении подсказок моделей ({mode}): {e}")

    return False


async def show_location_suggestions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    location: str,
    mode: str,
    pending_key: str,
    suggestions_key: str
) -> bool:
    """
    Показывает подсказки для локации
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        location: Введённая локация
        mode: Режим работы
        pending_key: Ключ для временного хранения
        suggestions_key: Ключ для хранения подсказок
        
    Возвращает:
        bool: True если подсказки показаны
    """
    from bot.services.suggestions import get_location_suggestions
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    
    context.user_data[pending_key] = location
    
    if len(location) >= 2:
        try:
            user_id = update.effective_user.id
            suggestions = get_location_suggestions(location, user_id)
            
            if suggestions:
                context.user_data[suggestions_key] = suggestions
                
                # Создаем клавиатуру
                keyboard = []
                for idx, loc in enumerate(suggestions):
                    keyboard.append([InlineKeyboardButton(
                        f"📍 {loc}",
                        callback_data=f"{mode}_loc:{idx}"
                    )])
                
                keyboard.append([InlineKeyboardButton(
                    "⌨️ Ввести как есть",
                    callback_data=f"{mode}_loc:manual"
                )])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "🔎 Найдены совпадения по локациям. Выберите из списка или нажмите 'Ввести как есть'.",
                    reply_markup=reply_markup
                )
                return True
        except Exception as e:
            logger.error(f"Ошибка при получении подсказок локаций ({mode}): {e}")
    
    return False


async def show_branch_suggestions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mode: str,
    suggestions_key: str
) -> bool:
    """
    Показывает список всех филиалов для выбора
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        mode: Режим работы
        suggestions_key: Ключ для хранения подсказок
        
    Возвращает:
        bool: True если подсказки показаны
    """
    from bot.services.suggestions import get_branch_suggestions
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    
    try:
        user_id = update.effective_user.id
        suggestions = get_branch_suggestions(user_id)
        
        if suggestions:
            context.user_data[suggestions_key] = suggestions
            
            # Создаем клавиатуру
            keyboard = []
            for idx, branch in enumerate(suggestions):
                keyboard.append([InlineKeyboardButton(
                    f"🏢 {branch}",
                    callback_data=f"{mode}_branch:{idx}"
                )])
            
            keyboard.append([InlineKeyboardButton(
                "⏭️ Пропустить",
                callback_data="skip_branch"
            )])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "🏢 Выберите филиал из списка:",
                reply_markup=reply_markup
            )
            return True
    except Exception as e:
        logger.error(f"Ошибка при получении подсказок филиалов ({mode}): {e}")
    
    return False


async def show_equipment_type_suggestions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mode: str
) -> bool:
    """
    Показывает список типов оборудования для выбора из БД
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        mode: Режим работы
        
    Возвращает:
        bool: True если подсказки показаны
    """
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from bot.services.suggestions import get_equipment_type_suggestions
    
    try:
        user_id = update.effective_user.id
        equipment_types = get_equipment_type_suggestions(user_id)
        
        # Если типы не получены из БД, используем предустановленные
        if not equipment_types:
            equipment_types = [
                "Системный блок",
                "Монитор",
                "МФУ",
                "ИБП",
                "Ноутбук",
                "Принтер",
                "Сканер",
                "Клавиатура",
                "Мышь",
                "Телефон"
            ]
        
        context.user_data[f'{mode}_type_suggestions'] = equipment_types
        
        # Создаем клавиатуру
        keyboard = []
        for idx, eq_type in enumerate(equipment_types):
            keyboard.append([InlineKeyboardButton(
                f"🔧 {eq_type}",
                callback_data=f"{mode}_type:{idx}"
            )])
        
        keyboard.append([InlineKeyboardButton(
            "⌨️ Ввести вручную",
            callback_data=f"{mode}_type:manual"
        )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔧 Выберите тип оборудования из списка или введите вручную:",
            reply_markup=reply_markup
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при показе подсказок типов оборудования: {e}")
        return False


async def show_status_suggestions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mode: str
) -> bool:
    """
    Показывает список статусов для выбора
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        mode: Режим работы
        
    Возвращает:
        bool: True если подсказки показаны
    """
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    
    # Стандартные статусы
    statuses = [
        "В работе",
        "На складе",
        "В ремонте",
        "Списано",
        "Резерв",
        "Новое"
    ]
    
    context.user_data[f'{mode}_status_suggestions'] = statuses
    
    # Создаем клавиатуру
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
    await update.message.reply_text(
        "📊 Выберите статус оборудования:",
        reply_markup=reply_markup
    )
    return True



async def show_equipment_type_suggestions_on_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    equipment_type: str,
    mode: str,
    pending_key: str,
    suggestions_key: str
) -> bool:
    """
    Показывает подсказки для типа оборудования при вводе (как для модели)
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        equipment_type: Введённый тип
        mode: Режим работы
        pending_key: Ключ для временного хранения
        suggestions_key: Ключ для хранения подсказок
        
    Возвращает:
        bool: True если подсказки показаны
    """
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from bot.services.suggestions import get_equipment_type_suggestions_by_query
    
    context.user_data[pending_key] = equipment_type
    
    if len(equipment_type) >= 2:
        try:
            user_id = update.effective_user.id
            suggestions = get_equipment_type_suggestions_by_query(equipment_type, user_id)
            
            if suggestions:
                context.user_data[suggestions_key] = suggestions
                
                # Создаем клавиатуру
                keyboard = []
                for idx, eq_type in enumerate(suggestions):
                    keyboard.append([InlineKeyboardButton(
                        f"🔧 {eq_type}",
                        callback_data=f"{mode}_type:{idx}"
                    )])
                
                keyboard.append([InlineKeyboardButton(
                    "⌨️ Ввести как есть",
                    callback_data=f"{mode}_type:manual"
                )])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "🔎 Найдены совпадения по типам оборудования. Выберите из списка или нажмите 'Ввести как есть'.",
                    reply_markup=reply_markup
                )
                return True
        except Exception as e:
            logger.error(f"Ошибка при получении подсказок типов оборудования ({mode}): {e}")
    
    return False



async def show_branch_suggestions_for_work(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    branch: str,
    pending_key: str,
    suggestions_key: str
) -> bool:
    """
    Показывает подсказки для филиала в работах
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        branch: Введённый филиал
        pending_key: Ключ для временного хранения
        suggestions_key: Ключ для хранения подсказок
        
    Возвращает:
        bool: True если подсказки показаны
    """
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from bot.services.suggestions import get_branch_suggestions
    
    context.user_data[pending_key] = branch
    
    if len(branch) >= 2:
        try:
            user_id = update.effective_user.id
            # Получаем все филиалы и фильтруем
            all_branches = get_branch_suggestions(user_id)
            
            if all_branches:
                # Фильтруем по введенному тексту
                branch_lower = branch.lower()
                suggestions = [b for b in all_branches if branch_lower in b.lower()]
                
                if suggestions:
                    context.user_data[suggestions_key] = suggestions
                    
                    # Создаем клавиатуру
                    keyboard = []
                    for idx, b in enumerate(suggestions[:8]):  # Максимум 8
                        keyboard.append([InlineKeyboardButton(
                            f"🏢 {b}",
                            callback_data=f"work_branch:{idx}"
                        )])
                    
                    keyboard.append([InlineKeyboardButton(
                        "⌨️ Ввести как есть",
                        callback_data="work_branch:manual"
                    )])
                    
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(
                        "🔎 Найдены совпадения по филиалам. Выберите из списка или нажмите 'Ввести как есть'.",
                        reply_markup=reply_markup
                    )
                    return True
        except Exception as e:
            logger.error(f"Ошибка при получении подсказок филиалов для работ: {e}")
    
    return False
