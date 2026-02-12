#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчики управления базами данных
Выбор БД, просмотр по типам оборудования, статистика.
"""
import asyncio
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import TimedOut

from bot.config import States, Messages
from bot.utils.decorators import require_user_access, handle_errors
from bot.utils.keyboards import create_main_menu_keyboard
from bot.utils.pagination import paginate_results, PaginationHandler
from bot.utils.formatters import format_equipment_info
from bot.database_manager import database_manager
from bot.universal_database import UniversalInventoryDB

logger = logging.getLogger(__name__)


# ============================ ОБРАБОТЧИКИ ПАГИНАЦИИ ============================

# Обработчик для пагинации типов оборудования
_types_pagination_handler = PaginationHandler(
    page_key='equipment_types_page',
    items_key='equipment_types_list',
    items_per_page=8,
    callback_prefix='types'
)

# Обработчик для пагинации списка оборудования
_equipment_pagination_handler = PaginationHandler(
    page_key='equipment_view_page',
    items_key='equipment_view_list',
    items_per_page=5,
    callback_prefix='eq'
)


# ============================ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============================

async def send_document_with_retry(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    document_path: str,
    filename: str,
    caption: str,
    parse_mode: str = None,
    max_retries: int = 5
) -> bool:
    """
    Отправляет документ с автоматическим повтором при timed out ошибке

    Параметры:
        context: Контекст выполнения бота
        chat_id: ID чата для отправки
        document_path: Путь к файлу
        filename: Имя файла
        caption: Подпись к документу
        parse_mode: Режим форматирования (HTML, Markdown)
        max_retries: Максимальное количество попыток (по умолчанию 5)

    Возвращает:
        bool: True если успешно отправлено, False иначе
    """
    for attempt in range(max_retries):
        try:
            with open(document_path, 'rb') as doc_file:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=doc_file,
                    filename=filename,
                    caption=caption,
                    parse_mode=parse_mode
                )
            logger.info(f"Документ {filename} успешно отправлен с попытки {attempt + 1}")
            return True

        except TimedOut as e:
            wait_time = (attempt + 1) * 3  # 3, 6, 9, 12, 15 секунд
            logger.warning(
                f"Попытка {attempt + 1}/{max_retries}: Таймаут отправки документа {filename}. "
                f"Ждем {wait_time} сек. перед следующей попыткой..."
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Не удалось отправить документ {filename} после {max_retries} попыток")

        except Exception as e:
            logger.error(f"Ошибка отправки документа {filename}: {e}")
            # Другие ошибки не retry'им
            break

    return False


@require_user_access
async def show_database_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню управления базами данных
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Состояние DB_SELECTION_MENU
    """
    # Получаем текущую БД пользователя
    user_id = update.effective_user.id
    current_db = database_manager.get_user_database(user_id)
    
    # Получаем список доступных баз данных
    available_databases = database_manager.get_available_databases()
    
    # Создаем клавиатуру
    keyboard = []
    
    # Кнопки выбора БД
    for db_name in available_databases:
        is_selected = '✅' if current_db == db_name else ''
        keyboard.append([InlineKeyboardButton(
            f"📊 {db_name} {is_selected}",
            callback_data=f"select_db:{db_name}"
        )])
    
    # Дополнительные опции
    keyboard.extend([
        [InlineKeyboardButton("🔧 Просмотр по типу оборудования", callback_data="equipment_types_menu")],
        [InlineKeyboardButton("📤 Экспорт базы данных", callback_data="export_db_menu")],
        [InlineKeyboardButton("🔙 Назад в главное меню", callback_data="back_to_main")]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🗄️ <b>Управление базами данных</b>\n\n"
        f"📋 <b>Текущая база:</b> {current_db}\n\n"
        f"Выберите действие:",
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    return States.DB_SELECTION_MENU


@handle_errors
async def handle_database_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает callback'и от меню управления БД
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    logger.info(f"[DATABASE] Получен callback: {callback_data}")
    
    if callback_data.startswith("select_db:"):
        # Выбор базы данных
        db_name = callback_data.split(":")[1]
        user_id = update.effective_user.id

        # Проверяем и сохраняем выбор (с ограничением доступа)
        success = database_manager.set_user_database(user_id, db_name)

        if not success:
            # Пользователь пытается переключиться на недоступную базу
            await query.answer()
            await query.edit_message_text(
                f"⛔ <b>Доступ запрещён</b>\n\n"
                f"Вы не можете переключиться на базу <b>{db_name}</b>.\n\n"
                f"Ваша назначенная база: <b>{database_manager.get_user_assigned_database(user_id) or 'Не назначена'}</b>",
                parse_mode='HTML'
            )
            return ConversationHandler.END

        context.user_data['selected_database'] = db_name

        await query.edit_message_text(
            f"✅ <b>База данных изменена</b>\n\n"
            f"📋 <b>Выбрана база:</b> {db_name}\n\n"
            f"Теперь все операции будут выполняться с этой базой данных.",
            parse_mode='HTML'
        )

        # Возвращаемся в главное меню
        import asyncio
        await asyncio.sleep(2)

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=Messages.MAIN_MENU,
            reply_markup=create_main_menu_keyboard()
        )

        return ConversationHandler.END
    
    elif callback_data == "equipment_types_menu":
        # Просмотр по типу оборудования
        return await show_equipment_types_menu(update, context)
    
    elif callback_data == "export_db_menu":
        # Экспорт базы данных
        return await show_export_database_menu(update, context)

    elif callback_data.startswith("export_db:"):
        # Обработка выбора базы для экспорта
        return await handle_export_database_callback(update, context)

    elif callback_data == "back_to_main":
        # Возврат в главное меню
        await query.edit_message_text("✅ Возврат в главное меню")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=Messages.MAIN_MENU,
            reply_markup=create_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    elif callback_data.startswith("eqtype:"):
        # Выбор типа оборудования по индексу
        try:
            type_idx = int(callback_data.split(":", 1)[1])
            equipment_types = context.user_data.get('equipment_types_list', [])
            
            if 0 <= type_idx < len(equipment_types):
                equipment_type = equipment_types[type_idx]
                return await show_equipment_by_type(update, context, equipment_type)
            else:
                await query.answer("Тип оборудования не найден", show_alert=True)
                return States.DB_VIEW_PAGINATION
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора типа: {e}")
            await query.answer("Ошибка обработки", show_alert=True)
            return States.DB_VIEW_PAGINATION
    
    elif callback_data == "branch_all":
        # Все филиалы
        equipment_type = context.user_data.get('equipment_type_filter')
        if equipment_type:
            return await show_equipment_by_type_and_branch(update, context, equipment_type, None)
    
    elif callback_data.startswith("branch:"):
        # Выбор конкретного филиала
        try:
            branch_idx = int(callback_data.split(":", 1)[1])
            equipment_type = context.user_data.get('equipment_type_filter')
            branches = context.user_data.get('branches_list', [])
            
            if equipment_type and 0 <= branch_idx < len(branches):
                branch_name = branches[branch_idx].get('BRANCH_NAME')
                return await show_equipment_by_type_and_branch(update, context, equipment_type, branch_name)
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора филиала: {e}")
            await query.answer("Ошибка обработки", show_alert=True)
            return States.DB_VIEW_PAGINATION
    
    elif callback_data == "types_prev":
        # Предыдущая страница типов
        _types_pagination_handler.handle_navigation(update, context, 'prev')
        return await show_equipment_types_menu(update, context)

    elif callback_data == "types_next":
        # Следующая страница типов
        _types_pagination_handler.handle_navigation(update, context, 'next')
        return await show_equipment_types_menu(update, context)
    
    elif callback_data == "back_to_db_menu":
        # Возврат в меню БД
        return await show_database_menu_from_callback(update, context)
    
    return States.DB_SELECTION_MENU


async def show_equipment_types_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню выбора типа оборудования с пагинацией
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Состояние DB_VIEW_PAGINATION
    """
    try:
        user_id = update.effective_user.id
        current_db = database_manager.get_user_database(user_id)
        
        # Создаем подключение к БД
        db = database_manager.create_database_connection(user_id)
        if not db:
            await update.callback_query.edit_message_text(
                "❌ Ошибка подключения к базе данных",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="back_to_db_menu")
                ]])
            )
            return States.DB_SELECTION_MENU
        
        # Получаем типы оборудования
        all_equipment_types = db.get_equipment_types()
        db.close_connection()
        
        if not all_equipment_types:
            await update.callback_query.edit_message_text(
                "❌ Типы оборудования не найдены",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="back_to_db_menu")
                ]])
            )
            return States.DB_SELECTION_MENU
        
        # Приоритетные типы
        priority_equipment_types = ['МФУ', 'Монитор', 'Системный блок', 'ИБП']
        
        # Сортируем: сначала приоритетные, потом остальные
        priority_types = []
        other_types = []
        
        for priority_type in priority_equipment_types:
            for db_type in all_equipment_types:
                if priority_type.upper() in db_type.upper():
                    if db_type not in priority_types:
                        priority_types.append(db_type)
        
        for db_type in all_equipment_types:
            if db_type not in priority_types and db_type not in other_types:
                other_types.append(db_type)
        
        equipment_types = priority_types + other_types

        # Сохраняем в контексте через PaginationHandler
        _types_pagination_handler.set_items(context, equipment_types)
        current_page = _types_pagination_handler.get_current_page(context)
        
        # Создаем клавиатуру с пагинацией
        reply_markup = generate_equipment_types_keyboard(equipment_types, current_page)
        
        await update.callback_query.edit_message_text(
            f"🔧 <b>Выбор типа оборудования</b>\n\n"
            f"📊 <b>База данных:</b> {current_db}\n"
            f"📋 <b>Найдено типов:</b> {len(equipment_types)}\n\n"
            f"Выберите тип оборудования для просмотра:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        return States.DB_VIEW_PAGINATION
        
    except Exception as e:
        logger.error(f"Ошибка при отображении типов оборудования: {e}")
        await update.callback_query.edit_message_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="back_to_db_menu")
            ]])
        )
        return States.DB_SELECTION_MENU


def generate_equipment_types_keyboard(equipment_types: list, current_page: int = 0) -> InlineKeyboardMarkup:
    """
    Генерирует клавиатуру с типами оборудования и пагинацией
    
    Параметры:
        equipment_types: Список типов оборудования
        current_page: Текущая страница
        
    Возвращает:
        InlineKeyboardMarkup: Клавиатура с кнопками
    """
    items_per_page = 8
    total_pages = (len(equipment_types) + items_per_page - 1) // items_per_page
    
    start_idx = current_page * items_per_page
    end_idx = start_idx + items_per_page
    page_types = equipment_types[start_idx:end_idx]
    
    keyboard = []
    
    # Кнопки типов оборудования (используем индексы для коротких callback)
    for idx, eq_type in enumerate(page_types):
        global_idx = start_idx + idx
        # Ограничиваем длину callback_data используя индекс
        keyboard.append([InlineKeyboardButton(
            f"🔧 {eq_type}",
            callback_data=f"eqtype:{global_idx}"
        )])
    
    # Навигация
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data="types_prev"))
    
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(
            f"📄 {current_page + 1}/{total_pages}",
            callback_data="types_page_info"
        ))
    
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data="types_next"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопка возврата
    keyboard.append([InlineKeyboardButton("🔙 Назад в меню БД", callback_data="back_to_db_menu")])
    
    return InlineKeyboardMarkup(keyboard)


async def show_equipment_by_type(update: Update, context: ContextTypes.DEFAULT_TYPE, equipment_type: str) -> int:
    """
    Отображает выбор филиала для оборудования выбранного типа
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        equipment_type: Тип оборудования
        
    Возвращает:
        int: Состояние DB_VIEW_PAGINATION
    """
    try:
        # Сохраняем выбранный тип
        context.user_data['equipment_type_filter'] = equipment_type
        
        user_id = update.effective_user.id
        current_db = database_manager.get_user_database(user_id)
        
        # Создаем подключение к БД
        db = database_manager.create_database_connection(user_id)
        if not db:
            await update.callback_query.edit_message_text(
                "❌ Ошибка подключения к базе данных",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="equipment_types_menu")
                ]])
            )
            return States.DB_VIEW_PAGINATION
        
        # Получаем список филиалов
        branches = db.get_branches()
        db.close_connection()
        
        # Сохраняем список филиалов
        context.user_data['branches_list'] = branches
        
        if not branches:
            # Если филиалов нет, показываем все оборудование
            return await show_equipment_by_type_and_branch(update, context, equipment_type, None)
        
        # Создаем клавиатуру с филиалами
        keyboard = []
        
        # Кнопка "Все филиалы"
        keyboard.append([InlineKeyboardButton(
            "🌐 Все филиалы",
            callback_data="branch_all"
        )])
        
        # Кнопки для каждого филиала (используем короткие индексы)
        for idx, branch in enumerate(branches):
            branch_name = branch.get('BRANCH_NAME', 'Неизвестен')
            keyboard.append([InlineKeyboardButton(
                f"🏢 {branch_name}",
                callback_data=f"branch:{idx}"
            )])
        
        # Кнопки возврата
        keyboard.extend([
            [InlineKeyboardButton("🔙 К типам оборудования", callback_data="equipment_types_menu")],
            [InlineKeyboardButton("🏠 В меню БД", callback_data="back_to_db_menu")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            f"🏢 <b>Выберите филиал для типа оборудования: {equipment_type}</b>\n\n"
            f"Выберите филиал, чтобы увидеть оборудование только этого филиала:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        return States.DB_VIEW_PAGINATION
        
    except Exception as e:
        logger.error(f"Ошибка при получении филиалов для типа '{equipment_type}': {e}")
        await update.callback_query.edit_message_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="equipment_types_menu")
            ]])
        )
        return States.DB_VIEW_PAGINATION


async def show_equipment_by_type_and_branch(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                            equipment_type: str, branch_name: str = None) -> int:
    """
    Отображает оборудование выбранного типа и филиала
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        equipment_type: Тип оборудования
        branch_name: Название филиала (None для всех)
        
    Возвращает:
        int: Состояние DB_VIEW_PAGINATION
    """
    try:
        user_id = update.effective_user.id
        
        # Создаем подключение к БД
        db = database_manager.create_database_connection(user_id)
        if not db:
            await update.callback_query.edit_message_text(
                "❌ Ошибка подключения к базе данных",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="equipment_types_menu")
                ]])
            )
            return States.DB_VIEW_PAGINATION
        
        # Получаем оборудование
        equipment_list = db.get_equipment_by_type(equipment_type, branch_name=branch_name)
        db.close_connection()
        
        if not equipment_list:
            await update.callback_query.edit_message_text(
                f"❌ Оборудование типа <b>{equipment_type}</b> не найдено",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="equipment_types_menu")
                ]])
            )
            return States.DB_VIEW_PAGINATION
        
        # Сортируем весь список по локации ДО пагинации
        def equipment_sort_key(equipment):
            """Сортировка оборудования по локации"""
            location = equipment.get('LOCATION', 'Не указана')
            if not location or location.strip() == '':
                location = 'Не указана'
            
            # "Не указана" в конце, остальные по алфавиту
            if location == 'Не указана':
                return (1, '')
            return (0, location.lower())
        
        equipment_list = sorted(equipment_list, key=equipment_sort_key)

        # Сохраняем отсортированный список для пагинации через PaginationHandler
        _equipment_pagination_handler.set_items(context, equipment_list)
        _equipment_pagination_handler.reset_pagination(context)
        context.user_data['equipment_type_filter'] = equipment_type
        context.user_data['equipment_branch_filter'] = branch_name
        
        # Показываем первую страницу
        await show_equipment_page(update, context)
        
        return States.DB_VIEW_PAGINATION
        
    except Exception as e:
        logger.error(f"Ошибка при отображении оборудования: {e}")
        await update.callback_query.edit_message_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="equipment_types_menu")
            ]])
        )
        return States.DB_VIEW_PAGINATION


async def show_equipment_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает страницу с оборудованием

    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
    """
    equipment_list = _equipment_pagination_handler.get_items(context)
    equipment_type = context.user_data.get('equipment_type_filter', 'Неизвестен')
    branch_filter = context.user_data.get('equipment_branch_filter')

    # Пагинация через PaginationHandler
    page_items, current_page, total_pages, has_prev, has_next = _equipment_pagination_handler.get_page_data(context)
    
    # Формируем сообщение
    message_lines = [
        f"🔧 <b>Тип:</b> {equipment_type}",
    ]
    
    if branch_filter:
        message_lines.append(f"🏢 <b>Филиал:</b> {branch_filter}")
    else:
        message_lines.append(f"🏢 <b>Филиал:</b> Все")
    
    message_lines.extend([
        f"📋 <b>Найдено единиц:</b> {len(equipment_list)}",
        f"📄 <b>Страница:</b> {current_page + 1} из {total_pages}\n"
    ])
    
    # Выводим оборудование (уже отсортировано при загрузке)
    for i, equipment in enumerate(page_items, 1):
        item_num = current_page * _equipment_pagination_handler.items_per_page + i
        message_lines.append(f"<b>{item_num}.</b>")
        message_lines.append(format_equipment_info(equipment))
        message_lines.append("")
    
    message_text = "\n".join(message_lines)
    
    # Создаем клавиатуру навигации
    keyboard = []
    nav_buttons = []
    
    if has_prev:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data="eq_prev"))
    
    nav_buttons.append(InlineKeyboardButton(f"📄 {current_page+1}/{total_pages}", callback_data="page_info"))
    
    if has_next:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data="eq_next"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 К типам оборудования", callback_data="equipment_types_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        message_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

    return States.DB_VIEW_PAGINATION


@handle_errors
async def handle_equipment_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает навигацию по страницам оборудования
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Состояние DB_VIEW_PAGINATION
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data == "eq_prev":
        _equipment_pagination_handler.handle_navigation(update, context, 'prev')
        return await show_equipment_page(update, context)

    elif callback_data == "eq_next":
        _equipment_pagination_handler.handle_navigation(update, context, 'next')
        return await show_equipment_page(update, context)

    else:
        # Обработка неизвестных callback_data
        logger.warning(f"Неизвестный callback в handle_equipment_pagination: {callback_data}")
        await query.answer("Неизвестная команда", show_alert=True)

    return States.DB_VIEW_PAGINATION


async def show_database_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает статистику баз данных
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Состояние DB_SELECTION_MENU
    """
    try:
        # Получаем статистику всех БД
        all_stats = database_manager.get_all_statistics()
        
        if not all_stats:
            await update.callback_query.edit_message_text(
                "❌ Не удалось получить статистику баз данных",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="back_to_db_menu")
                ]])
            )
            return States.DB_SELECTION_MENU
        
        # Формируем сообщение
        message_lines = ["📈 <b>Статистика баз данных</b>\n"]
        
        for stat in all_stats:
            db_name = stat.get('database', 'Неизвестно')
            total_items = stat.get('total_items', 0)
            total_employees = stat.get('total_employees', 0)
            
            message_lines.append(f"📊 <b>{db_name}</b>")
            message_lines.append(f"  • Единиц оборудования: {total_items}")
            message_lines.append(f"  • Сотрудников: {total_employees}\n")
        
        message_text = "\n".join(message_lines)
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_db_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            message_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        return States.DB_SELECTION_MENU
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await update.callback_query.edit_message_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="back_to_db_menu")
            ]])
        )
        return States.DB_SELECTION_MENU


async def show_database_menu_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню БД из callback'а
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Состояние DB_SELECTION_MENU
    """
    user_id = update.effective_user.id
    current_db = database_manager.get_user_database(user_id)
    
    available_databases = database_manager.get_available_databases()
    
    keyboard = []
    
    for db_name in available_databases:
        is_selected = '✅' if current_db == db_name else ''
        keyboard.append([InlineKeyboardButton(
            f"📊 {db_name} {is_selected}",
            callback_data=f"select_db:{db_name}"
        )])
    
    keyboard.extend([
        [InlineKeyboardButton("🔧 Просмотр по типу оборудования", callback_data="equipment_types_menu")],
        [InlineKeyboardButton("📤 Экспорт базы данных", callback_data="export_db_menu")],
        [InlineKeyboardButton("🔙 Назад в главное меню", callback_data="back_to_main")]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        f"🗄️ <b>Управление базами данных</b>\n\n"
        f"📋 <b>Текущая база:</b> {current_db}\n\n"
        f"Выберите действие:",
        parse_mode='HTML',
        reply_markup=reply_markup
    )

    return States.DB_SELECTION_MENU


@handle_errors
async def show_export_database_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню выбора базы данных для экспорта в CSV

    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения

    Возвращает:
        int: Состояние DB_SELECTION_MENU
    """
    # Получаем список доступных баз данных
    available_databases = database_manager.get_available_databases()

    # Создаем клавиатуру с кнопками для каждой базы
    keyboard = []

    for db_name in available_databases:
        keyboard.append([InlineKeyboardButton(
            f"📊 {db_name}",
            callback_data=f"export_db:{db_name}"
        )])

    # Кнопка назад
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_db_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(
        "📤 <b>Экспорт базы данных</b>\n\n"
        "Выберите базу данных для экспорта:",
        parse_mode='HTML',
        reply_markup=reply_markup
    )

    return States.DB_SELECTION_MENU


@handle_errors
async def handle_export_database_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор базы данных для экспорта

    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения

    Возвращает:
        int: Состояние DB_SELECTION_MENU
    """
    query = update.callback_query
    await query.answer()

    callback_data = query.data

    if callback_data.startswith("export_db:"):
        # Экспорт выбранной базы
        db_name = callback_data.split(":")[1]

        await query.edit_message_text(
            f"⏳ Экспортирую базу <b>{db_name}</b> в Excel...\n\n"
            f"Это может занять некоторое время.",
            parse_mode='HTML'
        )

        # Экспортируем базу
        excel_path = await export_database_to_excel(db_name)

        if excel_path:
            # Отправляем файл с автоматическим повтором при таймауте
            import os
            record_count = count_records_in_excel(excel_path)
            filename = os.path.basename(excel_path)

            caption = f"✅ Экспорт базы <b>{db_name}</b>\n\nВсего записей: {record_count}"

            sent = await send_document_with_retry(
                context=context,
                chat_id=query.message.chat_id,
                document_path=excel_path,
                filename=filename,
                caption=caption,
                parse_mode='HTML',
                max_retries=5
            )

            if not sent:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Не удалось отправить файл после нескольких попыток. Попробуйте позже."
                )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Ошибка при экспорте базы данных"
            )

        # Возвращаемся в меню БД
        return await show_database_menu_from_callback(update, context)

    return States.DB_SELECTION_MENU


async def export_database_to_excel(db_name: str) -> str:
    """
    Экспортирует все данные из базы данных в Excel файл с группировкой

    Параметры:
        db_name: Имя базы данных для экспорта

    Возвращает:
        str: Путь к созданному Excel файлу или None в случае ошибки
    """
    from bot.services.excel_service import DatabaseExcelExporter, count_excel_records

    try:
        # Получаем конфиг базы данных
        config = database_manager.get_database_config(db_name)
        if not config:
            logger.error(f"Конфиг базы данных {db_name} не найден")
            return None

        # Создаем подключение к базе
        db = UniversalInventoryDB(config)
        conn = db._get_connection()
        cursor = conn.cursor()

        # SQL запрос для получения всех данных (с LOCATIONS и BRANCHES)
        query_with_location = """
        SELECT
            i.INV_NO,
            o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
            t.TYPE_NAME,
            i.SERIAL_NO,
            i.HW_SERIAL_NO,
            i.PART_NO,
            m.MODEL_NAME,
            v.VENDOR_NAME as MANUFACTURER,
            l.DESCR as LOCATION,
            i.EMPL_NO,
            o.OWNER_DEPT as EMPLOYEE_DEPT,
            b.BRANCH_NAME as BRANCH,
            s.DESCR as STATUS,
            i.DESCR as DESCRIPTION
        FROM ITEMS i
        LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
        LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
        LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
        LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
        LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
        LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
        LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
        ORDER BY b.BRANCH_NAME, l.DESCR, i.SERIAL_NO
        """

        # Fallback запрос без BRANCHES и LOCATIONS
        query_without_location = """
        SELECT
            i.INV_NO,
            o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
            t.TYPE_NAME,
            i.SERIAL_NO,
            i.HW_SERIAL_NO,
            i.PART_NO,
            m.MODEL_NAME,
            v.VENDOR_NAME as MANUFACTURER,
            'Не указано' as LOCATION,
            i.EMPL_NO,
            o.OWNER_DEPT as EMPLOYEE_DEPT,
            'Не указан' as BRANCH,
            s.DESCR as STATUS,
            i.DESCR as DESCRIPTION
        FROM ITEMS i
        LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
        LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
        LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
        LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
        LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
        ORDER BY i.SERIAL_NO
        """

        # Пробуем выполнить запрос с fallback
        try:
            cursor.execute(query_with_location)
            rows = cursor.fetchall()
        except Exception as e:
            error_msg = str(e).lower()
            if 'branches' in error_msg or 'locations' in error_msg or 'permission' in error_msg or 'запрещено' in error_msg:
                logger.warning(f"Нет доступа к BRANCHES/LOCATIONS, используем fallback: {e}")
                cursor.execute(query_without_location)
                rows = cursor.fetchall()
            else:
                raise e

        cursor.close()

        if not rows:
            logger.warning(f"Нет данных для экспорта в базе {db_name}")
            return None

        # Создаем экспортер и экспортируем данные
        exporter = DatabaseExcelExporter()
        excel_file = exporter.export_database(rows, db_name)

        return excel_file

    except Exception as e:
        logger.error(f"Ошибка при экспорте базы {db_name}: {e}", exc_info=True)
        return None


def count_records_in_excel(excel_path: str) -> int:
    """
    Подсчитывает количество записей в Excel файле

    Параметры:
        excel_path: Путь к Excel файлу

    Возвращает:
        int: Количество записей оборудования
    """
    from bot.services.excel_service import count_excel_records
    return count_excel_records(excel_path)
