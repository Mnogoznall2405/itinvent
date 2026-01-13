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
        [InlineKeyboardButton("🔧 Замена комплектующих МФУ", callback_data="work:cartridge")],
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
            "🔧 <b>Замена комплектующих МФУ</b>\n\n"
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
        logger.info(f"[WORK] Запрос модели принтера для замены комплектующих МФУ")
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
    from bot.services.enhanced_printer_detector import enhanced_detector

    model = update.message.text.strip()

    # Показываем подсказки если есть совпадения
    try:
        if await show_model_suggestions(
            update, context, model,
            mode='work',
            pending_key='pending_work_printer_model',
            suggestions_key='work_printer_model_suggestions',
            equipment_type='printers_mfu'
        ):
            return States.WORK_PRINTER_MODEL_INPUT
    except Exception as e:
        logger.error(f"Ошибка при показе подсказок моделей принтеров: {e}")
        # Продолжаем выполнение даже если подсказки не сработали

    context.user_data['work_printer_model'] = model

    # Отправляем сообщение о проверке компонентов
    source_text = ""

    # Отправляем статусное сообщение
    status_msg = await update.message.reply_text("🔍 Анализирую модель принтера и доступные компоненты...")

    try:
        # Используем базу данных картриджей вместо LLM
        from bot.services.cartridge_database import cartridge_database

        # Проверяем наличие принтера в базе данных картриджей
        compatibility = cartridge_database.find_printer_compatibility(model)

        if compatibility:
            # Данные найдены в базе данных картриджей
            components_data = {
                'color': compatibility.is_color,
                'components': {comp: True for comp in compatibility.components},
                'component_list': compatibility.components,
                'cartridges': [
                    {
                        'model': cart.model,
                        'color': cart.color,
                        'description': cart.description,
                        'page_yield': cart.page_yield,
                        'oem_part': cart.oem_part,
                        'is_oem': cart.model == compatibility.oem_cartridge
                    }
                    for cart in compatibility.compatible_models
                ],
                'oem_cartridge': compatibility.oem_cartridge,
                'source': 'database'
            }

            source_text = f"\n🎯 Информация из базы данных картриджей"
            if compatibility.oem_cartridge:
                source_text += f"\n📦 OEM картридж: {compatibility.oem_cartridge}"

            logger.info(f"Found printer {model} in cartridge database: {len(compatibility.compatible_models)} cartridges")
        else:
            # Принтер не найден в базе, используем улучшенный детектор как запасной вариант
            logger.info(f"Printer {model} not found in cartridge database, using enhanced detector")
            components_data = enhanced_detector.detect_printer_components(model)
            source_text = "\n⚠️ Модель не найдена в базе данных, использован AI-анализ"

        # Сохраняем результат определения
        context.user_data['printer_components'] = components_data
        context.user_data['printer_is_color'] = components_data['color']
        context.user_data['printer_cartridges'] = components_data.get('cartridges', [])
        context.user_data['detection_source'] = components_data.get('source', 'unknown')

    except Exception as e:
        logger.error(f"Error detecting components for {model}: {e}")
        source_text = "\n❌ Ошибка определения, используются базовые компоненты"

        # При ошибке используем базовые компоненты
        components_data = {
            "color": False,
            "components": {
                "cartridge": True,
                "fuser": True,
                "drum": True
            },
            "component_list": ["cartridge", "fuser", "drum"],
            "source": "fallback"
        }

        context.user_data['printer_components'] = components_data
        context.user_data['printer_is_color'] = False
        context.user_data['printer_cartridges'] = []
        context.user_data['detection_source'] = 'fallback'

    # Удаляем статусное сообщение
    try:
        await status_msg.delete()
    except:
        pass

    # Если есть точные данные о картриджах, покажем их
    if context.user_data.get('printer_cartridges') and context.user_data.get('detection_source') == 'database':
        await update.message.reply_text(
            f"✅ Модель определена{source_text}"
        )
        return await show_cartridge_selection_with_models(update, context)
    else:
        await update.message.reply_text(
            f"✅ Модель определена{source_text}"
        )
        # Показываем выбор компонентов
        return await show_component_selection(update, context, components_data)

        # Удаляем сообщение о проверке
        try:
            await status_msg.delete()
        except:
            pass

        # При ошибке используем базовые компоненты
        components_data = {
            "color": False,
            "components": {
                "cartridge": True,
                "fuser": True,
                "drum": True
            },
            "component_list": ["cartridge", "fuser", "drum"]
        }

        context.user_data['printer_components'] = components_data
        context.user_data['printer_is_color'] = False

        await update.message.reply_text(
            "⚠️ Не удалось получить полную информацию о компонентаах.\n"
            "Доступны базовые компоненты: картридж, фьюзер, фотобарабан."
        )

        return await show_component_selection(update, context, components_data)


@handle_errors
async def show_cartridge_selection_with_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показывает меню выбора картриджей с конкретными моделями из базы данных
    """
    from bot.services.enhanced_printer_detector import enhanced_detector

    model = context.user_data.get('work_printer_model', 'неизвестная модель')
    cartridges = context.user_data.get('printer_cartridges', [])
    is_color = context.user_data.get('printer_is_color', False)

    # Группируем картриджи по цветам
    cartridges_by_color = {}
    for cart in cartridges:
        color = cart['color']
        if color not in cartridges_by_color:
            cartridges_by_color[color] = []
        cartridges_by_color[color].append(cart)

    # Формируем сообщение
    message_text = (
        f"🖨️ Модель принтера: {model}\n"
        f"📊 Тип: {'🎨 Цветной принтер' if is_color else '⚫ Черно-белый принтер'}\n"
        f"🎯 Информация из базы данных картриджей\n\n"
        f"📦 Выберите картридж для замены:"
    )

    # Создаем клавиатуру с картриджами
    keyboard = []

    # Показываем картриджи по цветам
    for color, color_cartridges in cartridges_by_color.items():
        for cart in color_cartridges:
            oem_mark = " (OEM)" if cart.get('is_oem') else ""
            yield_info = f" - {cart.get('page_yield', '?')} стр." if cart.get('page_yield') else ""

            button_text = f"📦 {cart['model']}{oem_mark}\n  {color}{yield_info}"
            callback_data = f"cartridge_model:{cart['model']}:{color}"

            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    # Добавляем другие компоненты
    components = context.user_data.get('printer_components', {}).get('components', {})
    if components.get('fuser'):
        keyboard.append([InlineKeyboardButton("🔥 Фьюзер (печка)", callback_data="component:fuser")])
    if components.get('photoconductor'):
        keyboard.append([InlineKeyboardButton("🥁 Фотобарабан (ОПК)", callback_data="component:photoconductor")])
    if components.get('waste_toner'):
        keyboard.append([InlineKeyboardButton("🗑️ Контейнер отраб. тонера", callback_data="component:waste_toner")])
    if components.get('transfer_belt'):
        keyboard.append([InlineKeyboardButton("📼 Трансферный ремень", callback_data="component:transfer_belt")])

    # Кнопка отмены
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="component:cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(message_text, reply_markup=reply_markup)

    return States.WORK_COMPONENT_SELECTION


@handle_errors
async def show_component_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, components_data: dict) -> int:
    """
    Показывает меню выбора компонентов на основе детекции
    """
    from bot.services.printer_component_detector import component_detector

    model = context.user_data.get('work_printer_model', 'неизвестная модель')
    is_color = components_data.get('color', False)
    available_components = components_data.get('component_list', [])

    # Формируем сообщение с информацией о принтере
    printer_type_text = "🎨 Цветной принтер" if is_color else "⚫ Черно-белый принтер"

    # Определяем источник информации
    if components_data.get('from_cache'):
        source_info = " (из кэша)"
    elif components_data.get('error'):
        source_info = " (базовый анализ)"
    else:
        source_info = " (AI-анализ)"

    message_text = (
        f"🖨️ Модель принтера: {model}\n"
        f"📊 Тип: {printer_type_text}{source_info}\n\n"
        f"🔧 Выберите компонент для замены:"
    )

    # Создаем клавиатуру с доступными компонентами
    keyboard = []

    # Проверяем какие компоненты доступны
    if 'cartridge' in available_components:
        keyboard.append([
            InlineKeyboardButton(
                component_detector.get_component_display_name('cartridge'),
                callback_data="component:cartridge"
            )
        ])

    if 'fuser' in available_components:
        keyboard.append([
            InlineKeyboardButton(
                component_detector.get_component_display_name('fuser'),
                callback_data="component:fuser"
            )
        ])

    if 'photoconductor' in available_components:
        keyboard.append([
            InlineKeyboardButton(
                component_detector.get_component_display_name('photoconductor'),
                callback_data="component:photoconductor"
            )
        ])

    # Дополнительные компоненты
    additional_components = ['waste_toner', 'transfer_belt']
    for comp in additional_components:
        if comp in available_components:
            keyboard.append([
                InlineKeyboardButton(
                    component_detector.get_component_display_name(comp),
                    callback_data=f"component:{comp}"
                )
            ])

    # Кнопка отмены
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="component:cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Определяем как отправить сообщение - через callback или обычное сообщение
    if update.callback_query:
        await update.callback_query.message.reply_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

    return States.WORK_COMPONENT_SELECTION


@handle_errors
async def work_component_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода компонента (если пользователь решит ввести текстом)
    """
    component_input = update.message.text.strip().lower()

    # Маппинг текстовых вариантов к типам компонентов
    component_mapping = {
        'картридж': 'cartridge',
        'картриджи': 'cartridge',
        'чернила': 'cartridge',
        'тонер': 'cartridge',
        'фьюзер': 'fuser',
        'печка': 'fuser',
        'нагревательный элемент': 'fuser',
        'барабан': 'photoconductor',  # Обратная совместимость
        'фотооптический барабан': 'photoconductor',
        'фотобарабан': 'photoconductor',
        'опк': 'photoconductor',
        'opc': 'photoconductor',
        'контейнер': 'waste_toner',
        'отработанный тонер': 'waste_toner',
        'трансферный ремень': 'transfer_belt',
        'ремень переноса': 'transfer_belt'
    }

    component_type = component_mapping.get(component_input)

    if not component_type:
        await update.message.reply_text(
            "❌ Неизвестный компонент. Пожалуйста, используйте кнопки для выбора."
        )
        return States.WORK_COMPONENT_SELECTION

    # Сохраняем выбранный компонент
    context.user_data['work_component_type'] = component_type

    # Обрабатываем выбор компонента
    return await handle_component_selection_logic(update, context, component_type)


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
            suggestions_key='work_equipment_model_suggestions',
            equipment_type='all'
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
async def handle_component_selection_logic(update: Update, context: ContextTypes.DEFAULT_TYPE, component_type: str) -> int:
    """
    Обрабатывает логику после выбора компонента
    """
    from bot.services.printer_component_detector import component_detector

    model = context.user_data.get('work_printer_model', 'неизвестная модель')
    is_color = context.user_data.get('printer_is_color', False)

    # Получаем отображаемое имя компонента
    component_name = component_detector.get_component_display_name(component_type)

    if component_type == 'cartridge':
        # Для картриджа нужно выбрать цвет
        if is_color:
            # Цветной принтер - 4 цвета
            keyboard = [
                [InlineKeyboardButton("⚫ Черный", callback_data="cartridge_color:black")],
                [InlineKeyboardButton("🔵 Синий (Cyan)", callback_data="cartridge_color:cyan")],
                [InlineKeyboardButton("🟡 Желтый (Yellow)", callback_data="cartridge_color:yellow")],
                [InlineKeyboardButton("🔴 Пурпурный (Magenta)", callback_data="cartridge_color:magenta")]
            ]
        else:
            # Черно-белый принтер
            keyboard = [
                [InlineKeyboardButton("⚫ Черный", callback_data="cartridge_color:black")]
            ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = (
            f"✅ Выбран компонент: {component_name}\n\n"
            f"🎨 Выберите цвет установленного картриджа:"
        )

        # Отправляем сообщение
        if update.callback_query:
            await update.callback_query.message.reply_text(message_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup)

        return States.WORK_CARTRIDGE_COLOR_SELECTION
    else:
        # Для фьюзера, фотобарабана и других компонентов цвет не важен
        context.user_data['work_component_color'] = 'Универсальный'

        message_text = (
            f"✅ Выбран компонент: {component_name}\n\n"
            f"⚙️ Для этого компонента цвет не важен (универсальный)."
        )

        # Отправляем сообщение и показываем подтверждение
        if update.callback_query:
            await update.callback_query.message.reply_text(message_text)
        else:
            await update.message.reply_text(message_text)

        # Показываем подтверждение
        return await show_work_confirmation(update, context, component_type, 'Универсальный')


@handle_errors
async def lookup_component_model(printer_model: str, component_type: str) -> str:
    """
    Ищет модель компонента в базе данных картриджей

    Args:
        printer_model: Модель принтера
        component_type: Тип компонента (fuser, photoconductor, waste_toner, transfer_belt)

    Returns:
        Модель компонента или пустая строка если не найдена
    """
    try:
        from bot.services.cartridge_database import cartridge_database

        # Ищем совместимость принтера
        compatibility = cartridge_database.find_printer_compatibility(printer_model)

        if compatibility:
            # Выбираем соответствующее поле в зависимости от типа компонента
            if component_type == 'fuser':
                if compatibility.fuser_models and len(compatibility.fuser_models) > 0:
                    return compatibility.fuser_models[0]
            elif component_type in ['photoconductor', 'drum']:
                if compatibility.photoconductor_models and len(compatibility.photoconductor_models) > 0:
                    return compatibility.photoconductor_models[0]
            elif component_type == 'waste_toner':
                if compatibility.waste_toner_models and len(compatibility.waste_toner_models) > 0:
                    return compatibility.waste_toner_models[0]
            elif component_type == 'transfer_belt':
                if compatibility.transfer_belt_models and len(compatibility.transfer_belt_models) > 0:
                    return compatibility.transfer_belt_models[0]

        logger.warning(f"Модель для компонента {component_type} принтера {printer_model} не найдена")
        return ''

    except Exception as e:
        logger.error(f"Ошибка при поиске модели компонента {component_type} для {printer_model}: {e}")
        return ''


@handle_errors
async def handle_component_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора компонента из callback
    """
    query = update.callback_query
    await query.answer()

    data = query.data

    # Обработка выбора конкретной модели картриджа
    if data.startswith('cartridge_model:'):
        parts = data.split(':', 2)
        if len(parts) >= 3:
            cartridge_model = parts[1]
            cartridge_color = parts[2]

            # Сохраняем выбранный картридж
            context.user_data['work_component_type'] = 'cartridge'
            context.user_data['work_cartridge_model'] = cartridge_model
            context.user_data['work_cartridge_color'] = cartridge_color

            # Показываем подтверждение
            return await show_cartridge_model_confirmation(update, context, cartridge_model, cartridge_color)

    # Обработка обычных компонентов
    if data.startswith('component:'):
        component_type = data.split(':')[1]

        if component_type == 'cancel':
            # Отмена операции
            await query.edit_message_text("❌ Операция отменена")
            return ConversationHandler.END

        # Обратная совместимость: конвертируем drum в photoconductor
        if component_type == 'drum':
            component_type = 'photoconductor'

        # Сохраняем выбранный компонент
        context.user_data['work_component_type'] = component_type

        # Ищем модель компонента в базе данных для non-cartridge компонентов
        if component_type != 'cartridge':
            printer_model = context.user_data.get('work_printer_model', '')
            component_model = await lookup_component_model(printer_model, component_type)
            if component_model:
                context.user_data['work_cartridge_model'] = component_model
                logger.info(f"Найдена модель {component_type} для {printer_model}: {component_model}")

        # Обрабатываем выбор компонента
        return await handle_component_selection_logic(update, context, component_type)

    return States.WORK_COMPONENT_SELECTION


@handle_errors
async def show_cartridge_model_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, cartridge_model: str, cartridge_color: str) -> int:
    """
    Показывает подтверждение для выбора конкретной модели картриджа
    """
    branch = context.user_data.get('work_branch', '')
    location = context.user_data.get('work_location', '')
    printer_model = context.user_data.get('work_printer_model', '')

    confirmation_text = (
        "📋 <b>Подтверждение замены картриджа</b>\n\n"
        f"📍 <b>Филиал:</b> {branch}\n"
        f"📍 <b>Локация:</b> {location}\n"
        f"🖨️ <b>Модель принтера:</b> {printer_model}\n"
        f"📦 <b>Модель картриджа:</b> {cartridge_model}\n"
        f"🎨 <b>Цвет:</b> {cartridge_color}\n\n"
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

    return States.WORK_CONFIRMATION


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

    # Определяем модель картриджа для выбранного цвета
    cartridge_model = ''
    try:
        from bot.services.cartridge_database import cartridge_database
        printer_model = context.user_data.get('work_printer_model', '')
        selected_color = color_names.get(color, color)

        if printer_model:
            cartridges = cartridge_database.get_cartridges_for_printer(printer_model)

            # Пробуем разные варианты названий цветов (как в export.py)
            color_variants = [selected_color]
            if selected_color == 'Синий (Cyan)':
                color_variants.extend(['Синий', 'Cyan'])
            elif selected_color == 'Желтый (Yellow)':
                color_variants.extend(['Желтый', 'Yellow'])
            elif selected_color == 'Пурпурный (Magenta)':
                color_variants.extend(['Пурпурный', 'Magenta'])

            color_cartridges = []
            for color_variant in color_variants:
                found = [cart for cart in cartridges if cart.color.lower() == color_variant.lower()]
                if found:
                    color_cartridges.extend(found)
                    break

            if color_cartridges:
                cartridge_model = color_cartridges[0].model
                context.user_data['work_cartridge_model'] = cartridge_model
                context.user_data['detection_source'] = 'database'  # Указываем, что данные из базы
                logger.info(f"Selected cartridge model for {printer_model} ({selected_color}): {cartridge_model}")
                logger.info(f"Found match using color variant: {color_variant}")
    except Exception as e:
        logger.error(f"Error determining cartridge model for color {color}: {e}")
        cartridge_model = ''

    await query.edit_message_text(f"✅ Выбран цвет: {color_names.get(color, color)}" +
                                   (f"\n📦 Модель картриджа: {cartridge_model}" if cartridge_model else ""))
    
    # Показываем подтверждение
    if context.user_data.get('work_component_type') == 'cartridge':
        await show_cartridge_confirmation(update, context)
    else:
        component_type = context.user_data.get('work_component_type', '')
        component_color = context.user_data.get('work_component_color', '')
        await show_work_confirmation(update, context, component_type, component_color)

    return States.WORK_CONFIRMATION


async def show_work_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, component_type: str = None, component_color: str = None):
    """
    Показывает подтверждение для замены компонента
    """
    from bot.services.printer_component_detector import component_detector

    branch = context.user_data.get('work_branch', '')
    location = context.user_data.get('work_location', '')
    printer_model = context.user_data.get('work_printer_model', '')

    # Если компонент и цвет не переданы, берем из user_data
    if component_type is None:
        component_type = context.user_data.get('work_component_type', 'cartridge')
    if component_color is None:
        component_color = context.user_data.get('work_cartridge_color', context.user_data.get('work_component_color', ''))

    # Получаем отображаемое имя компонента
    component_name = component_detector.get_component_display_name(component_type)

    # Определяем заголовок и текст в зависимости от типа компонента
    if component_type == 'cartridge':
        title = "замены картриджа"
        color_field = f"🎨 <b>Цвет картриджа:</b> {component_color}"
    else:
        title = f"замены {component_name.lower()}"
        color_field = f"⚙️ <b>Тип компонента:</b> {component_name}"

    # Добавляем модель компонента если есть
    component_model = context.user_data.get('work_cartridge_model', '')
    model_field = ""
    if component_model:
        model_field = f"📦 <b>Модель {component_name.lower()}:</b> {component_model}\n"

    confirmation_text = (
        f"📋 <b>Подтверждение {title}</b>\n\n"
        f"📍 <b>Филиал:</b> {branch}\n"
        f"📍 <b>Локация:</b> {location}\n"
        f"🖨️ <b>Модель принтера:</b> {printer_model}\n"
        f"{color_field}\n"
        f"{model_field}"
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

    # Важно: функция должна возвращать состояние WORK_CONFIRMATION
    return States.WORK_CONFIRMATION


async def show_cartridge_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показывает подтверждение для замены картриджа
    """
    branch = context.user_data.get('work_branch', '')
    location = context.user_data.get('work_location', '')
    printer_model = context.user_data.get('work_printer_model', '')
    cartridge_color = context.user_data.get('work_cartridge_color', '')
    cartridge_model = context.user_data.get('work_cartridge_model', '')

    confirmation_text = (
        "📋 <b>Подтверждение замены комплектующих</b>\n\n"
        f"📍 <b>Филиал:</b> {branch}\n"
        f"📍 <b>Локация:</b> {location}\n"
        f"🖨️ <b>Модель принтера:</b> {printer_model}\n"
        f"🎨 <b>Цвет картриджа:</b> {cartridge_color}\n"
        + (f"📦 <b>Модель картриджа:</b> {cartridge_model}\n" if cartridge_model else "") +
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

    # Важно: функция должна возвращать состояние WORK_CONFIRMATION
    return States.WORK_CONFIRMATION


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
            success = await save_component_replacement(context)  # Используем новую универсальную функцию
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


async def save_component_replacement(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Сохраняет данные о замене компонента в JSON
    """
    import json
    from pathlib import Path
    from database_manager import database_manager

    try:
        file_path = Path("data/cartridge_replacements.json")  # Оставляем старое имя файла для обратной совместимости

        # Загружаем существующие данные
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = []

        # Получаем текущую БД пользователя
        user_id = context._user_id if hasattr(context, '_user_id') else None
        db_name = database_manager.get_user_database(user_id) if user_id else 'ITINVENT'

        # Определяем тип компонента и цвет
        component_type = context.user_data.get('work_component_type', 'cartridge')

        if component_type == 'cartridge':
            component_color = context.user_data.get('work_cartridge_color', '')
        else:
            component_color = context.user_data.get('work_component_color', 'Универсальный')

        # Создаем новую запись с расширенной информацией о картриджах
        record = {
            'branch': context.user_data.get('work_branch', ''),
            'location': context.user_data.get('work_location', ''),
            'printer_model': context.user_data.get('work_printer_model', ''),
            'component_type': component_type,  # NEW
            'component_color': component_color,  # Переименовано с cartridge_color
            # Добавляем модель картриджа если есть
            'cartridge_model': context.user_data.get('work_cartridge_model', ''),
            # Добавляем детальную информацию о картридже из базы данных
            'detection_source': context.user_data.get('detection_source', 'unknown'),
            'printer_is_color': context.user_data.get('printer_is_color', False),
            # Для обратной совместимости оставляем старое поле
            'cartridge_color': component_color if component_type == 'cartridge' else '',
            'db_name': db_name,
            'timestamp': datetime.now().isoformat()
        }

        data.append(record)

        # Сохраняем
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Логируем с информацией о типе компонента
        component_name = {
            'cartridge': 'картриджа',
            'fuser': 'фьюзера (печки)',
            'drum': 'фотобарабана',  # Обратная совместимость
            'photoconductor': 'фотобарабана',
            'waste_toner': 'контейнера отработанного тонера',
            'transfer_belt': 'трансферного ремня'
        }.get(component_type, 'компонента')

        logger.info(f"Сохранена замена {component_name}: {record}")
        return True

    except Exception as e:
        logger.error(f"Ошибка сохранения замены компонента: {e}")
        return False


# Для обратной совместимости оставляем старую функцию
async def save_cartridge_replacement(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Сохраняет данные о замене картриджа в JSON (обратная совместимость)
    """
    return await save_component_replacement(context)


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
            # Пропускаем обработку для refresh и manual
            action = data.split(':', 1)[1] if ':' in data else ''
            if action in ['refresh', 'manual']:
                # Эти действия обрабатываются отдельно выше
                pass
            else:
                idx = int(action)
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
            # Пропускаем обработку для refresh и manual
            action = data.split(':', 1)[1] if ':' in data else ''
            if action in ['refresh', 'manual']:
                # Эти действия обрабатываются отдельно выше
                pass
            else:
                idx = int(action)
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
    # Старый импорт больше не нужен - используем component_detector
    
    query = update.callback_query
    await query.answer()
    
    data = query.data
    work_type = context.user_data.get('work_type')
    
    if data == 'work_model:manual':
        if work_type == 'cartridge':
            pending = context.user_data.get('pending_work_printer_model', '').strip()
            context.user_data['work_printer_model'] = pending
            await query.edit_message_text(f"✅ Принято: {pending}")

            # Используем новую компонентную детекцию
            from bot.services.printer_component_detector import component_detector

            # Отправляем сообщение о проверке компонентов
            status_msg = await query.message.reply_text(
                "🔍 Анализирую модель принтера и доступные компоненты..."
            )

            # Определяем доступные компоненты через LLM
            try:
                components_data = component_detector.detect_printer_components(pending)

                # Сохраняем результат определения
                context.user_data['printer_components'] = components_data
                context.user_data['printer_is_color'] = components_data['color']

                # Удаляем сообщение о проверке
                try:
                    await status_msg.delete()
                except:
                    pass

                # Показываем выбор компонентов
                return await show_component_selection(update, context, components_data)

            except Exception as e:
                logger.error(f"Error detecting components for {pending}: {e}")

                # Удаляем сообщение о проверке
                try:
                    await status_msg.delete()
                except:
                    pass

                # При ошибке используем базовые компоненты
                components_data = {
                    "color": False,
                    "components": {
                        "cartridge": True,
                        "fuser": True,
                        "drum": True
                    },
                    "component_list": ["cartridge", "fuser", "drum"]
                }

                context.user_data['printer_components'] = components_data
                context.user_data['printer_is_color'] = False

                await query.message.reply_text(
                    "⚠️ Не удалось получить полную информацию о компонентах.\n"
                    "Доступны базовые компоненты: картридж, фьюзер, фотобарабан."
                )

                return await show_component_selection(update, context, components_data)
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
                            suggestions_key='work_printer_model_suggestions',
                            equipment_type='printers_mfu'
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
                            suggestions_key='work_equipment_model_suggestions',
                            equipment_type='all'
                        ):
                            return States.WORK_EQUIPMENT_MODEL_INPUT
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении подсказок: {e}")
        try:
            # Пропускаем обработку для refresh и manual
            action = data.split(':', 1)[1] if ':' in data else ''
            if action not in ['refresh', 'manual']:
                idx = int(action)

                if work_type == 'cartridge':
                    suggestions = context.user_data.get('work_printer_model_suggestions', [])
                    if 0 <= idx < len(suggestions):
                        selected_model = suggestions[idx]
                        context.user_data['work_printer_model'] = selected_model
                        await query.edit_message_text(f"✅ Выбрана модель: {selected_model}")

                        # Используем новую компонентную детекцию
                        from bot.services.printer_component_detector import component_detector

                        # Отправляем сообщение о проверке компонентов
                        status_msg = await query.message.reply_text(
                            "🔍 Анализирую модель принтера и доступные компоненты..."
                        )

                        # Определяем доступные компоненты через LLM
                        try:
                        components_data = component_detector.detect_printer_components(selected_model)

                        # Сохраняем результат определения
                        context.user_data['printer_components'] = components_data
                        context.user_data['printer_is_color'] = components_data['color']

                        # Удаляем сообщение о проверке
                        try:
                            await status_msg.delete()
                        except:
                            pass

                        # Показываем выбор компонентов
                        return await show_component_selection(update, context, components_data)

                    except Exception as e:
                        logger.error(f"Error detecting components for {selected_model}: {e}")

                        # Удаляем сообщение о проверке
                        try:
                            await status_msg.delete()
                        except:
                            pass

                        # При ошибке используем базовые компоненты
                        components_data = {
                            "color": False,
                            "components": {
                                "cartridge": True,
                                "fuser": True,
                                "drum": True
                            },
                            "component_list": ["cartridge", "fuser", "drum"]
                        }

                        context.user_data['printer_components'] = components_data
                        context.user_data['printer_is_color'] = False

                        await query.message.reply_text(
                            "⚠️ Не удалось получить полную информацию о компонентах.\n"
                            "Доступны базовые компоненты: картридж, фьюзер, фотобарабан."
                        )

                        return await show_component_selection(update, context, components_data)
                elif work_type == 'equipment':
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
