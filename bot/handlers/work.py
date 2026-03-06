#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчики для регистрации выполненных работ
"""
import json
import logging
import os
import re
import traceback
from datetime import datetime
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import States, Messages
from bot.utils.decorators import handle_errors
from bot.utils.keyboards import create_main_menu_keyboard
from bot.handlers.suggestions_handler import (
    show_branch_suggestions_for_work,
    show_location_suggestions,
    show_model_suggestions
)
from bot.handlers.location import (
    show_location_buttons,
    handle_location_navigation_universal
)
from bot.services.cartridge_database import cartridge_database
from bot.services.enhanced_printer_detector import enhanced_detector
from bot.services.input_identifier_service import (
    detect_identifiers_from_image,
    detect_identifiers_from_text,
)
from bot.services.validation import validate_serial_number
from bot.services.printer_component_detector import component_detector
from bot.database_manager import database_manager
from bot.universal_database import UniversalInventoryDB
from bot.local_json_store import append_json_data, load_json_data

logger = logging.getLogger(__name__)


async def handle_serial_input_with_ocr(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    temp_file_prefix: str,
    user_data_serial_key: str,
    user_data_equipment_key: str,
    error_state: str,
    equipment_type_name: str,
    confirmation_handler: callable
) -> int:
    """
    Универсальный обработчик ввода серийного номера с поддержкой OCR

    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        temp_file_prefix: Префикс временного файла (например, "temp_battery_")
        user_data_serial_key: Ключ для сохранения серийного номера в user_data
        user_data_equipment_key: Ключ для сохранения оборудования в user_data
        error_state: Состояние для возврата при ошибке
        equipment_type_name: Название типа оборудования (например, "ИБП", "ПК")
        confirmation_handler: Функция-обработчик подтверждения

    Возвращает:
        int: Следующее состояние
    """
    user_id = update.effective_user.id
    search_inv_no = None
    search_serial_no = None
    source_label = "manual"

    is_photo_message = bool(update.message and update.message.photo)
    is_document_image_message = bool(
        update.message
        and update.message.document
        and str(update.message.document.mime_type or "").startswith("image/")
    )
    is_text_message = bool(update.message and update.message.text)

    if is_photo_message or is_document_image_message:
        status_msg = await update.message.reply_text("🔍 Анализирую изображение...")
        file_path = None
        source_kind = "photo" if is_photo_message else "document"
        try:
            if is_photo_message:
                photo = update.message.photo[-1]
                incoming_file = await context.bot.get_file(photo.file_id)
                file_id = photo.file_id
                file_ext = ".jpg"
            else:
                document = update.message.document
                incoming_file = await context.bot.get_file(document.file_id)
                file_id = document.file_id
                original_name = str(document.file_name or "work_qr_image").strip()
                file_ext = os.path.splitext(original_name)[1] or ".jpg"
                logger.info(
                    "[WORK] received_document_image user_id=%s name=%s mime=%s size=%s",
                    user_id,
                    original_name,
                    document.mime_type,
                    document.file_size,
                )

            file_path = f"{temp_file_prefix}{file_id}{file_ext}"
            await incoming_file.download_to_drive(file_path)

            detection = await detect_identifiers_from_image(file_path)
            search_inv_no = detection.get("inv_no")
            search_serial_no = detection.get("serial_no")

            if detection.get("detector") == "qr":
                source_label = f"qr_{source_kind}"
                logger.info(
                    "[WORK][QR] detected_from_%s user_id=%s inv_no=%s serial_no=%s",
                    source_kind,
                    user_id,
                    search_inv_no or "-",
                    search_serial_no or "-",
                )
            elif detection.get("detector") == "ocr":
                source_label = f"ocr_{source_kind}"
                logger.info(
                    "[WORK][OCR] fallback_from_%s user_id=%s serial=%s",
                    source_kind,
                    user_id,
                    search_serial_no or "-",
                )
            else:
                logger.info("[WORK][QR] not_detected_from_%s user_id=%s", source_kind, user_id)

        except Exception as e:
            logger.error(f"Error processing image in work flow: {e}")
            await update.message.reply_text(
                "❌ Не удалось распознать QR/серийный номер.\n"
                "Пожалуйста, попробуйте другое изображение или введите номер вручную."
            )
            return error_state
        finally:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
            try:
                await status_msg.delete()
            except Exception:
                pass

    elif is_text_message:
        text_input = update.message.text.strip()
        detection = detect_identifiers_from_text(text_input)
        if detection.get("detector") == "qr":
            search_inv_no = detection.get("inv_no")
            search_serial_no = detection.get("serial_no")
            source_label = "qr_text"
            logger.info(
                "[WORK][QR] detected_from_text user_id=%s inv_no=%s serial_no=%s text_len=%s",
                user_id,
                search_inv_no or "-",
                search_serial_no or "-",
                len(text_input),
            )
        elif detection.get("detector") == "manual":
            search_serial_no = detection.get("serial_no")
            source_label = "manual_text"
            logger.info(
                "[WORK][QR] not_detected_from_text user_id=%s fallback_manual_serial=%s",
                user_id,
                search_serial_no or "-",
            )

    if not search_inv_no and not search_serial_no:
        await update.message.reply_text(
            "❌ Не удалось определить номер.\n"
            "Отправьте QR-code (фото/документ/текст) или серийный номер:"
        )
        return error_state

    if (
        not search_inv_no
        and search_serial_no
        and source_label in {"manual_text", "ocr_photo", "ocr_document"}
        and not validate_serial_number(search_serial_no)
    ):
        await update.message.reply_text(
            f"⚠️ Неверный формат серийного номера: {search_serial_no}\n\n"
            "Серийный номер должен содержать только буквы, цифры и символы: - _ . :\n"
            "Попробуйте еще раз:"
        )
        return error_state

    # Поиск оборудования в базе данных
    db_name = database_manager.get_user_database(user_id)
    config = database_manager.get_database_config(db_name)

    if config:
        db = UniversalInventoryDB(config)

        result = None
        if search_inv_no:
            logger.info("[WORK] try_inv_lookup user_id=%s inv_no=%s", user_id, search_inv_no)
            result = db.find_by_inventory_number(search_inv_no)
            logger.info("[WORK] inv_lookup_result user_id=%s found=%s", user_id, bool(result))

        if not result and search_serial_no:
            logger.info("[WORK] try_serial_lookup user_id=%s serial=%s", user_id, search_serial_no)
            result = db.find_by_serial_number(search_serial_no)
            logger.info("[WORK] serial_lookup_result user_id=%s found=%s", user_id, bool(result))

        # Проверяем тип результата - может быть список или одиночная запись
        equipment = None
        if isinstance(result, list):
            if result and len(result) > 0:
                equipment = result[0]
        elif result is not None:
            equipment = result

        if equipment:
            # Найдено оборудование - сохраняем данные
            serial_to_save = (
                equipment.get('SERIAL_NO')
                or equipment.get('HW_SERIAL_NO')
                or search_serial_no
                or search_inv_no
                or ''
            )
            context.user_data[user_data_serial_key] = serial_to_save
            context.user_data[user_data_equipment_key] = equipment

            # Показываем информацию для подтверждения
            return await confirmation_handler(update, context, equipment)
        else:
            # Оборудование не найдено
            target = search_inv_no or search_serial_no or "-"
            await update.message.reply_text(
                f"⚠️ {equipment_type_name} с номером <b>{target}</b> не найден в базе данных.\n\n"
                f"📊 База: {db_name}\n\n"
                "Проверьте номер и попробуйте снова:",
                parse_mode='HTML'
            )
            return error_state
    else:
        await update.message.reply_text("❌ Ошибка подключения к базе данных")
        return ConversationHandler.END


@handle_errors
async def start_work(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начало процесса регистрации работы
    """
    logger.info(f"[WORK] Начало процесса регистрации работы, user_id={update.effective_user.id}")
    
    keyboard = [
        [InlineKeyboardButton("🔧 Замена комплектующих МФУ", callback_data="work:cartridge")],
        [InlineKeyboardButton("🔋 Замена батареи ИБП", callback_data="work:battery_replacement")],
        [InlineKeyboardButton("🖥️ Замена компонентов ПК", callback_data="work:component_replacement")],
        [InlineKeyboardButton("🧹 Чистка ПК", callback_data="work:pc_cleaning")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info(f"[WORK] Создана клавиатура с кнопками: cartridge, battery_replacement, pc_cleaning, back_to_main")
    
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
        message_text = (
            "🔧 <b>Замена комплектующих МФУ</b>\n\n"
            "📍 Введите местоположение (филиал):"
        )
        await query.edit_message_text(message_text, parse_mode='HTML')
        return States.WORK_BRANCH_INPUT

    elif work_type == 'battery_replacement':
        context.user_data['work_type'] = 'battery_replacement'
        message_text = (
            "🔋 <b>Замена батареи ИБП</b>\n\n"
            "📷 Отправьте фото/документ с QR или серийным номером\n"
            "Или отправьте QR payload/серийный номер текстом:"
        )
        await query.edit_message_text(message_text, parse_mode='HTML')
        return States.WORK_BATTERY_SERIAL_INPUT

    elif work_type == 'component_replacement':
        context.user_data['work_type'] = 'component_replacement'
        message_text = (
            "🖥️ <b>Замена компонентов ПК</b>\n\n"
            "📷 Отправьте фото/документ с QR или серийным номером\n"
            "Или отправьте QR payload/серийный номер текстом:"
        )
        await query.edit_message_text(message_text, parse_mode='HTML')
        return States.WORK_COMPONENT_SERIAL_INPUT

    elif work_type == 'pc_cleaning':
        context.user_data['work_type'] = 'pc_cleaning'
        message_text = (
            "🖥️ <b>Чистка ПК</b>\n\n"
            "📷 Отправьте фото/документ с QR или серийным номером\n"
            "Или отправьте QR payload/серийный номер текстом:"
        )
        await query.edit_message_text(message_text, parse_mode='HTML')
        return States.WORK_PC_CLEANING_SERIAL_INPUT

    return States.WORK_TYPE_SELECTION


@handle_errors
async def handle_back_to_main_external(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик для кнопки "Главное меню" - вызывается извне ConversationHandler
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    current_db = database_manager.get_user_database(user_id)

    logger.info(f"[WORK] Возврат в главное меню (внешний обработчик)")

    await query.edit_message_text("✅ Возврат в главное меню")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"{Messages.MAIN_MENU}\n\n📊 <b>Текущая база данных:</b> {current_db}",
        parse_mode='HTML',
        reply_markup=create_main_menu_keyboard()
    )


@handle_errors
async def handle_restart_work(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик для кнопки "Обработать ещё" - запускает новую работу после завершения предыдущей
    Вызывается извне ConversationHandler
    """
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    work_type = callback_data.split(':', 1)[1] if ':' in callback_data else ''

    logger.info(f"[WORK RESTART] Перезапуск работы: {work_type}")

    # Очищаем старые данные
    clear_work_data(context)

    # Отправляем сообщение в зависимости от типа работы
    if work_type == 'pc_cleaning':
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🖥️ <b>Чистка ПК</b>\n\n📷 Отправьте фото/документ с QR или серийным номером\nИли отправьте QR payload/серийный номер текстом:",
            parse_mode='HTML'
        )
    elif work_type == 'battery_replacement':
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🔋 <b>Замена батареи ИБП</b>\n\n📷 Отправьте фото/документ с QR или серийным номером\nИли отправьте QR payload/серийный номер текстом:",
            parse_mode='HTML'
        )
    elif work_type == 'component_replacement':
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🖥️ <b>Замена компонентов ПК</b>\n\n📷 Отправьте фото/документ с QR или серийным номером\nИли отправьте QR payload/серийный номер текстом:",
            parse_mode='HTML'
        )
    elif work_type == 'cartridge':
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🔧 <b>Замена комплектующих МФУ</b>\n\n📍 Введите местоположение (филиал):",
            parse_mode='HTML'
        )
    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Неизвестный тип работы"
        )
        return

    # Устанавливаем work_type для последующих обработчиков
    context.user_data['work_type'] = work_type


@handle_errors
async def work_branch_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода филиала с подсказками
    """
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

    # Показываем кнопки локаций для выбранного филиала
    user_id = update.effective_user.id
    context._user_id = user_id
    await show_location_buttons(
        message=update.message,
        context=context,
        mode='work',
        branch=branch
    )

    return States.WORK_LOCATION_INPUT


@handle_errors
async def work_location_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода локации с подсказками
    """
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
    else:
        logger.error(f"[WORK] Неизвестный тип работы в work_location_input: {work_type}")
        await update.message.reply_text("❌ Ошибка: неизвестный тип работы")
        return ConversationHandler.END


@handle_errors
async def work_printer_model_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода модели принтера с подсказками
    """
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

            logger.info(f"[DEBUG] Model: {model}, components: {components_data['components']}")
            logger.info(f"[DEBUG] compatibility.components: {compatibility.components}")

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
async def work_battery_serial_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода серийного номера ИБП с поддержкой OCR
    """
    return await handle_serial_input_with_ocr(
        update=update,
        context=context,
        temp_file_prefix="temp_battery_",
        user_data_serial_key="battery_serial_no",
        user_data_equipment_key="battery_equipment",
        error_state=States.WORK_BATTERY_SERIAL_INPUT,
        equipment_type_name="ИБП",
        confirmation_handler=show_battery_confirmation
    )


async def show_battery_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, equipment: dict) -> int:
    """
    Показывает подтверждение для замены батареи ИБП
    """
    serial_no = equipment.get('SERIAL_NO', 'N/A')
    hw_serial_no = equipment.get('HW_SERIAL_NO', '')
    model_name = equipment.get('MODEL_NAME', 'Неизвестная модель')
    branch = equipment.get('BRANCH_NAME', 'Не указан')
    location = equipment.get('LOCATION', 'Не указано')
    employee = equipment.get('EMPLOYEE_NAME', 'Не назначен')

    # Формируем текст подтверждения
    serial_display = f"{serial_no} / {hw_serial_no}" if hw_serial_no else serial_no

    confirmation_text = (
        "📋 <b>Подтверждение замены батареи ИБП</b>\n\n"
        f"🔢 <b>Серийный номер:</b> {serial_display}\n"
        f"🖥️ <b>Модель:</b> {model_name}\n"
        f"🏢 <b>Филиал:</b> {branch}\n"
        f"📍 <b>Локация:</b> {location}\n"
        f"👤 <b>Сотрудник:</b> {employee}\n\n"
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

    return States.WORK_BATTERY_CONFIRMATION


@handle_errors
async def work_pc_cleaning_serial_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода серийного номера ПК с поддержкой OCR
    """
    return await handle_serial_input_with_ocr(
        update=update,
        context=context,
        temp_file_prefix="temp_pc_cleaning_",
        user_data_serial_key="pc_cleaning_serial_no",
        user_data_equipment_key="pc_cleaning_equipment",
        error_state=States.WORK_PC_CLEANING_SERIAL_INPUT,
        equipment_type_name="ПК",
        confirmation_handler=show_pc_cleaning_confirmation
    )


async def show_pc_cleaning_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, equipment: dict) -> int:
    """
    Показывает подтверждение для чистки ПК с информацией о последней чистке
    """
    serial_no = equipment.get('SERIAL_NO', 'N/A')
    hw_serial_no = equipment.get('HW_SERIAL_NO', '')
    model_name = equipment.get('MODEL_NAME', 'Неизвестная модель')
    branch = equipment.get('BRANCH_NAME', 'Не указан')
    location = equipment.get('LOCATION', 'Не указано')
    employee = equipment.get('EMPLOYEE_NAME', 'Не назначен')

    # Ищем последнюю чистку этого ПК
    last_cleaning_section = ""
    file_path = Path("data/pc_cleanings.json")

    try:
        cleanings = load_json_data(str(file_path), default_content=[])
        if not isinstance(cleanings, list):
            cleanings = []

        # Ищем чистки для этого серийного номера
        pc_cleanings = [
            c for c in cleanings
            if c.get('serial_no') == serial_no or c.get('serial_no') == hw_serial_no
        ]

        if pc_cleanings:
            pc_cleanings.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            last_cleaning = pc_cleanings[0]
            last_date = datetime.fromisoformat(last_cleaning['timestamp'])

            now = datetime.now()
            days_ago = (now - last_date).days
            if days_ago == 0:
                time_ago = "сегодня"
            elif days_ago == 1:
                time_ago = "вчера"
            elif days_ago < 7:
                time_ago = f"{days_ago} дн. назад"
            elif days_ago < 30:
                time_ago = f"{days_ago // 7} нед. назад"
            elif days_ago < 365:
                time_ago = f"{days_ago // 30} мес. назад"
            else:
                time_ago = f"{days_ago // 365} г. назад"

            last_cleaning_section = (
                "\n"
                f"🧹 <b>История чисток</b>\n"
                f"📅 <b>Последняя:</b> {last_date.strftime('%d.%m.%Y')} в {last_date.strftime('%H:%M')}\n"
                f"🕒 <b>Давность:</b> {time_ago}\n"
                f"🔁 <b>Всего чисток:</b> {len(pc_cleanings)}\n"
            )
    except Exception as e:
        logger.error(f"Error reading pc_cleanings data: {e}")

    serial_display = f"{serial_no} / {hw_serial_no}" if hw_serial_no else serial_no

    confirmation_text = (
        "📋 <b>Подтверждение чистки ПК</b>\n\n"
        f"🔢 <b>Серийный номер:</b> {serial_display}\n"
        f"🖥️ <b>Модель:</b> {model_name}\n"
        f"🏢 <b>Филиал:</b> {branch}\n"
        f"📍 <b>Локация:</b> {location}\n"
        f"👤 <b>Сотрудник:</b> {employee}\n"
        f"{last_cleaning_section}"
        "❓ Сохранить новую чистку?"
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

    return States.WORK_PC_CLEANING_CONFIRMATION


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
            success = await save_component_replacement(context)
        elif work_type == 'battery_replacement':
            success = await save_battery_replacement(context)
        elif work_type == 'pc_cleaning':
            success = await save_pc_cleaning(context)
        elif work_type == 'component_replacement':
            success = await save_component_replacement_pc(context)
        else:
            success = False
            logger.error(f"Неизвестный тип работы: {work_type}")

        if success:
            # Получаем work_type до очистки данных
            work_type = context.user_data.get('work_type', '')

            # Создаем клавиатуру с кнопками
            keyboard = []
            if work_type == 'pc_cleaning':
                keyboard.append([
                    InlineKeyboardButton("🔄 Обработать еще", callback_data="work:pc_cleaning"),
                    InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
                ])
            elif work_type == 'battery_replacement':
                keyboard.append([
                    InlineKeyboardButton("🔄 Обработать еще", callback_data="work:battery_replacement"),
                    InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
                ])
            elif work_type == 'component_replacement':
                keyboard.append([
                    InlineKeyboardButton("🔄 Обработать еще", callback_data="work:component_replacement"),
                    InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
                ])
            elif work_type == 'cartridge':
                keyboard.append([
                    InlineKeyboardButton("🔄 Обработать еще", callback_data="work:cartridge"),
                    InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
                ])
            else:
                keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")])

            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                "✅ Данные успешно сохранены!\n"
                "Информация о выполненной работе добавлена.",
                reply_markup=reply_markup
            )

            # НЕ очищаем work_type - он нужен для кнопки "Обработать еще"
            # Очищаем только данные оборудования
            context.user_data.pop('battery_equipment', None)
            context.user_data.pop('pc_cleaning_equipment', None)
            context.user_data.pop('component_replacement_equipment', None)
            context.user_data.pop('battery_serial_no', None)
            context.user_data.pop('pc_cleaning_serial_no', None)
            context.user_data.pop('component_replacement_serial_no', None)
            context.user_data.pop('pc_component_type', None)
            context.user_data.pop('pc_component_name', None)

            # Переходим в состояние успеха - разговор остается активным
            return States.WORK_SUCCESS
        else:
            await query.edit_message_text(
                "❌ Ошибка при сохранении данных.\n"
                "Попробуйте еще раз."
            )
            clear_work_data(context)
            return ConversationHandler.END

    elif query.data == "cancel_work":
        await query.edit_message_text("❌ Операция отменена.")
        clear_work_data(context)

        return ConversationHandler.END

    return States.WORK_CONFIRMATION


@handle_errors
async def handle_work_success_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик действий из состояния успеха (кнопки "Обработать еще" и "Главное меню")
    """
    query = update.callback_query
    await query.answer()

    callback_data = query.data

    # Обработка кнопки "Назад в главное меню"
    if callback_data == 'back_to_main':
        user_id = update.effective_user.id
        current_db = database_manager.get_user_database(user_id)

        await query.edit_message_text("✅ Возврат в главное меню")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"{Messages.MAIN_MENU}\n\n📊 <b>Текущая база данных:</b> {current_db}",
            parse_mode='HTML',
            reply_markup=create_main_menu_keyboard()
        )

        clear_work_data(context)
        return ConversationHandler.END

    # Обработка кнопки "Обработать еще"
    if callback_data.startswith('work:'):
        work_type = callback_data.split(':', 1)[1] if ':' in callback_data else ''

        logger.info(f"[WORK SUCCESS] Перезапуск работы: {work_type}")

        # Очищаем старые данные оборудования, но оставляем work_type
        context.user_data.pop('battery_equipment', None)
        context.user_data.pop('pc_cleaning_equipment', None)
        context.user_data.pop('component_replacement_equipment', None)
        context.user_data.pop('battery_serial_no', None)
        context.user_data.pop('pc_cleaning_serial_no', None)
        context.user_data.pop('component_replacement_serial_no', None)
        context.user_data.pop('work_branch', None)
        context.user_data.pop('work_location', None)
        context.user_data.pop('work_printer_model', None)
        context.user_data.pop('work_cartridge_color', None)
        context.user_data.pop('work_component_type', None)
        context.user_data.pop('pc_component_type', None)
        context.user_data.pop('pc_component_name', None)

        # Устанавливаем work_type
        context.user_data['work_type'] = work_type

        # Отправляем сообщение в зависимости от типа работы
        if work_type == 'pc_cleaning':
            await query.edit_message_text(
                "🖥️ <b>Чистка ПК</b>\n\n"
                "📷 Отправьте фото/документ с QR или серийным номером\n"
                "Или отправьте QR payload/серийный номер текстом:",
                parse_mode='HTML'
            )
            return States.WORK_PC_CLEANING_SERIAL_INPUT
        elif work_type == 'battery_replacement':
            await query.edit_message_text(
                "🔋 <b>Замена батареи ИБП</b>\n\n"
                "📷 Отправьте фото/документ с QR или серийным номером\n"
                "Или отправьте QR payload/серийный номер текстом:",
                parse_mode='HTML'
            )
            return States.WORK_BATTERY_SERIAL_INPUT
        elif work_type == 'component_replacement':
            await query.edit_message_text(
                "🖥️ <b>Замена компонентов ПК</b>\n\n"
                "📷 Отправьте фото/документ с QR или серийным номером\n"
                "Или отправьте QR payload/серийный номер текстом:",
                parse_mode='HTML'
            )
            return States.WORK_COMPONENT_SERIAL_INPUT
        elif work_type == 'cartridge':
            await query.edit_message_text(
                "🔧 <b>Замена комплектующих МФУ</b>\n\n"
                "📍 Введите местоположение (филиал):",
                parse_mode='HTML'
            )
            return States.WORK_BRANCH_INPUT

    return States.WORK_SUCCESS


async def save_component_replacement(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Сохраняет данные о замене компонента в JSON
    """
    try:
        file_path = Path("data/cartridge_replacements.json")  # Оставляем старое имя файла для обратной совместимости

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

        # Сохраняем запись напрямую в SQLite-backed store
        saved = append_json_data(str(file_path), record)
        if not saved:
            logger.error("Не удалось сохранить замену компонента в локальное хранилище: file=%s", file_path.name)
            return False

        # Логируем с информацией о типе компонента
        component_name = {
            'cartridge': 'картриджа',
            'fuser': 'фьюзера (печки)',
            'drum': 'фотобарабана',  # Обратная совместимость
            'photoconductor': 'фотобарабана',
            'waste_toner': 'контейнера отработанного тонера',
            'transfer_belt': 'трансферного ремня'
        }.get(component_type, 'компонента')

        logger.info(
            "Сохранена замена %s: storage=sqlite file=%s db_name=%s",
            component_name,
            file_path.name,
            db_name,
        )
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


async def save_battery_replacement(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Сохраняет данные о замене батареи ИБП в JSON и обновляет описание в базе данных
    """
    try:
        file_path = Path("data/battery_replacements.json")

        # Получаем текущую БД пользователя
        user_id = context._user_id if hasattr(context, '_user_id') else None
        db_name = database_manager.get_user_database(user_id) if user_id else 'ITINVENT'

        # Получаем данные об ИБП
        equipment = context.user_data.get('battery_equipment', {})
        equipment_id = equipment.get('ID')
        current_description = equipment.get('DESCRIPTION') or ''

        # Формируем строку с датой замены батареи
        replacement_date = datetime.now().strftime("%d.%m.%Y %H:%M")
        replacement_note = f"\r\nПоследняя замена батареи: {replacement_date} (IT-BOT)"

        # Обновляем описание в базе данных
        if equipment_id:
            config = database_manager.get_database_config(db_name)
            if config:
                db = UniversalInventoryDB(config)

                # Проверяем, есть ли уже запись о замене батареи в описании
                if "Последняя замена батареи:" in current_description:
                    # Обновляем последнюю запись о замене
                    new_description = re.sub(
                        r'Последняя замена батареи:.*?\(IT-BOT\)',
                        f'Последняя замена батареи: {replacement_date} (IT-BOT)',
                        current_description
                    )
                else:
                    # Добавляем новую запись к описанию
                    new_description = current_description + replacement_note

                # UPDATE в базе
                try:
                    with db._get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE ITEMS
                            SET DESCR = ?, CH_DATE = GETDATE(), CH_USER = 'IT-BOT'
                            WHERE ID = ?
                        """, (new_description, equipment_id))
                        conn.commit()
                        logger.info(f"Обновлено описание для ID={equipment_id}: добавлена замена батареи от {replacement_date}")
                except Exception as e:
                    logger.error(f"Ошибка обновления описания: {e}")

        # Создаем запись для JSON
        record = {
            'serial_no': context.user_data.get('battery_serial_no', ''),
            'hw_serial_no': equipment.get('HW_SERIAL_NO', ''),
            'model_name': equipment.get('MODEL_NAME', ''),
            'manufacturer': equipment.get('MANUFACTURER', ''),
            'branch': equipment.get('BRANCH_NAME', ''),
            'location': equipment.get('LOCATION', ''),
            'employee': equipment.get('EMPLOYEE_NAME', ''),
            'inv_no': equipment.get('INV_NO', ''),
            'db_name': db_name,
            'timestamp': datetime.now().isoformat()
        }

        saved = append_json_data(str(file_path), record)
        if not saved:
            logger.error("Не удалось сохранить замену батареи в локальное хранилище: file=%s", file_path.name)
            return False

        logger.info("Сохранена замена батареи ИБП: storage=sqlite file=%s db_name=%s", file_path.name, db_name)
        return True

    except Exception as e:
        logger.error(f"Ошибка сохранения замены батареи: {e}")
        traceback.print_exc()
        return False


async def save_pc_cleaning(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Сохраняет данные о чистке ПК в JSON и обновляет описание в базе данных
    """
    try:
        file_path = Path("data/pc_cleanings.json")

        # Получаем текущую БД пользователя
        user_id = context._user_id if hasattr(context, '_user_id') else None
        db_name = database_manager.get_user_database(user_id) if user_id else 'ITINVENT'

        # Получаем данные о ПК
        equipment = context.user_data.get('pc_cleaning_equipment', {})
        equipment_id = equipment.get('ID')
        current_description = equipment.get('DESCRIPTION') or ''

        # Формируем строку с датой чистки (используем \r\n для переноса строки в SQL Server)
        cleaning_date = datetime.now().strftime("%d.%m.%Y %H:%M")
        cleaning_note = f"\r\nПоследняя чистка: {cleaning_date} (IT-BOT)"

        # Обновляем описание в базе данных
        if equipment_id:
            config = database_manager.get_database_config(db_name)
            if config:
                db = UniversalInventoryDB(config)

                # Проверяем, есть ли уже запись о чистке в описании
                if "Последняя чистка:" in current_description:
                    # Обновляем последнюю запись о чистке
                    # Заменяем последнюю запись о чистке на новую
                    new_description = re.sub(
                        r'Последняя чистка:.*?\(IT-BOT\)',
                        f'Последняя чистка: {cleaning_date} (IT-BOT)',
                        current_description
                    )
                else:
                    # Добавляем новую запись к описанию
                    new_description = current_description + cleaning_note

                # UPDATE в базе
                try:
                    with db._get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE ITEMS
                            SET DESCR = ?, CH_DATE = GETDATE(), CH_USER = 'IT-BOT'
                            WHERE ID = ?
                        """, (new_description, equipment_id))
                        conn.commit()
                        logger.info(f"Обновлено описание для ID={equipment_id}: добавлена чистка от {cleaning_date}")
                except Exception as e:
                    logger.error(f"Ошибка обновления описания: {e}")

        # Создаем запись для JSON
        record = {
            'serial_no': context.user_data.get('pc_cleaning_serial_no', ''),
            'hw_serial_no': equipment.get('HW_SERIAL_NO', ''),
            'model_name': equipment.get('MODEL_NAME', ''),
            'manufacturer': equipment.get('MANUFACTURER', ''),
            'branch': equipment.get('BRANCH_NAME', ''),
            'location': equipment.get('LOCATION', ''),
            'employee': equipment.get('EMPLOYEE_NAME', ''),
            'inv_no': equipment.get('INV_NO', ''),
            'db_name': db_name,
            'timestamp': datetime.now().isoformat()
        }

        saved = append_json_data(str(file_path), record)
        if not saved:
            logger.error("Не удалось сохранить чистку ПК в локальное хранилище: file=%s", file_path.name)
            return False

        logger.info("Сохранена чистка ПК: storage=sqlite file=%s db_name=%s", file_path.name, db_name)
        return True

    except Exception as e:
        logger.error(f"Ошибка сохранения чистки ПК: {e}")
        traceback.print_exc()
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
        'pending_work_equipment_model', 'work_equipment_model_suggestions',
        'battery_serial_no', 'battery_equipment',
        'pc_cleaning_serial_no', 'pc_cleaning_equipment',
        'component_replacement_serial_no', 'component_replacement_equipment',
        'pc_component_type', 'pc_component_name'
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

        # Показываем кнопки локаций для выбранного филиала
        context._user_id = query.from_user.id
        await show_location_buttons(
            message=query.message,
            context=context,
            mode='work',
            branch=pending,
            query=query
        )
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

                    # Показываем кнопки локаций для выбранного филиала
                    context._user_id = query.from_user.id
                    await show_location_buttons(
                        message=query.message,
                        context=context,
                        mode='work',
                        branch=selected_branch,
                        query=query
                    )
                    return States.WORK_LOCATION_INPUT
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора филиала: {e}")

    return States.WORK_BRANCH_INPUT


@handle_errors
async def handle_work_location_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора локации из подсказок с поддержкой пагинации
    """
    query = update.callback_query
    await query.answer()

    data = query.data
    work_type = context.user_data.get('work_type')

    # Обработка пагинации через универсальный обработчик
    if data in ('work_location_prev', 'work_location_next'):
        return await handle_location_navigation_universal(update, context, mode='work') or States.WORK_LOCATION_INPUT

    # Обработка "Ввести вручную"
    if data == 'work_location:manual':
        # Для работы через location.py нужно запросить ввод вручную
        await query.edit_message_text("📍 Введите локацию:")
        return States.WORK_LOCATION_INPUT

    # Обработка выбора конкретной локации
    elif data.startswith('work_location:'):
        try:
            idx = int(data.split(':', 1)[1])
            from bot.handlers.location import _work_location_pagination_handler
            suggestions = _work_location_pagination_handler.get_items(context)

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

    # Обратная совместимость со старым форматом (work_loc:)
    elif data == 'work_loc:manual':
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
            action = data.split(':', 1)[1] if ':' in data else ''
            if action not in ['refresh', 'manual']:
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
            # Неизвестный тип работы
            logger.error(f"Неизвестный тип работы в handle_work_model_suggestion (manual): {work_type}")
            await query.edit_message_text("❌ Ошибка: неизвестный тип работы")
            return ConversationHandler.END

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
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора модели: {e}")

    if work_type == 'cartridge':
        return States.WORK_PRINTER_MODEL_INPUT
    else:
        logger.error(f"Неизвестный тип работы в handle_work_model_suggestion: {work_type}")
        return ConversationHandler.END


@handle_errors
async def work_component_serial_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода серийного номера ПК для замены компонента с поддержкой OCR
    """
    return await handle_serial_input_with_ocr(
        update=update,
        context=context,
        temp_file_prefix="temp_component_replacement_",
        user_data_serial_key="component_replacement_serial_no",
        user_data_equipment_key="component_replacement_equipment",
        error_state=States.WORK_COMPONENT_SERIAL_INPUT,
        equipment_type_name="ПК",
        confirmation_handler=show_component_selection_pc
    )


async def show_component_selection_pc(update: Update, context: ContextTypes.DEFAULT_TYPE, equipment: dict) -> int:
    """
    Показывает меню выбора компонента ПК для замены
    """
    serial_no = equipment.get('SERIAL_NO', 'N/A')
    hw_serial_no = equipment.get('HW_SERIAL_NO', '')
    model_name = equipment.get('MODEL_NAME', 'Неизвестная модель')

    # Формируем текст с информацией о ПК
    serial_display = f"{serial_no} / {hw_serial_no}" if hw_serial_no else serial_no

    message_text = (
        f"🖥️ <b>Замена компонентов ПК</b>\n\n"
        f"🔢 <b>Серийный номер:</b> {serial_display}\n"
        f"💻 <b>Модель:</b> {model_name}\n\n"
        f"🔧 Выберите компонент для замены:"
    )

    # Создаем клавиатуру с компонентами ПК
    keyboard = [
        [InlineKeyboardButton("💾 HDD/SSD (Накопитель)", callback_data="pc_component:hdd_ssd")],
        [InlineKeyboardButton("❄️ Кулер (Охлаждение)", callback_data="pc_component:cooler")],
        [InlineKeyboardButton("🔲 Материнская плата", callback_data="pc_component:motherboard")],
        [InlineKeyboardButton("🎮 Оперативная память (RAM)", callback_data="pc_component:ram")],
        [InlineKeyboardButton("⚡ Блок питания (PSU)", callback_data="pc_component:psu")],
        [InlineKeyboardButton("📺 Видеокарта (GPU)", callback_data="pc_component:gpu")],
        [InlineKeyboardButton("🔧 Другое", callback_data="pc_component:other")],
        [InlineKeyboardButton("❌ Отмена", callback_data="pc_component:cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    return States.WORK_COMPONENT_SELECTION


@handle_errors
async def handle_pc_component_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора компонента ПК для замены
    """
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith('pc_component:'):
        component_type = data.split(':', 1)[1] if ':' in data else ''

        if component_type == 'cancel':
            await query.edit_message_text("❌ Операция отменена")
            clear_work_data(context)
            return ConversationHandler.END

        # Маппинг типов компонентов к их отображаемым именам
        component_names = {
            'hdd_ssd': 'HDD/SSD (Накопитель)',
            'cooler': 'Кулер (Охлаждение)',
            'motherboard': 'Материнская плата',
            'ram': 'Оперативная память (RAM)',
            'psu': 'Блок питания (PSU)',
            'gpu': 'Видеокарта (GPU)',
            'other': 'Другое'
        }

        component_name = component_names.get(component_type, component_type)
        context.user_data['pc_component_type'] = component_type
        context.user_data['pc_component_name'] = component_name

        # Показываем подтверждение
        return await show_component_confirmation_pc(update, context)

    return States.WORK_COMPONENT_SELECTION

@handle_errors
async def show_component_confirmation_pc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показывает подтверждение для замены компонента ПК
    """
    equipment = context.user_data.get('component_replacement_equipment', {})
    component_name = context.user_data.get('pc_component_name', 'Неизвестный компонент')

    serial_no = equipment.get('SERIAL_NO', 'N/A')
    hw_serial_no = equipment.get('HW_SERIAL_NO', '')
    model_name = equipment.get('MODEL_NAME', 'Неизвестная модель')
    branch = equipment.get('BRANCH_NAME', 'Не указан')
    location = equipment.get('LOCATION', 'Не указано')
    employee = equipment.get('EMPLOYEE_NAME', 'Не назначен')

    # Ищем последнюю замену этого компонента для этого ПК
    last_replacement_section = ""
    file_path = Path("data/component_replacements.json")

    component_type = context.user_data.get('pc_component_type', '')

    try:
        replacements = load_json_data(str(file_path), default_content=[])
        if not isinstance(replacements, list):
            replacements = []

        pc_replacements = [
            r for r in replacements
            if (r.get('serial_no') == serial_no or r.get('serial_no') == hw_serial_no)
            and r.get('component_type') == component_type
        ]

        if pc_replacements:
            pc_replacements.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            last_replacement = pc_replacements[0]
            last_date = datetime.fromisoformat(last_replacement['timestamp'])

            days_ago = (datetime.now() - last_date).days
            if days_ago == 0:
                time_ago = "сегодня"
            elif days_ago == 1:
                time_ago = "вчера"
            elif days_ago < 7:
                time_ago = f"{days_ago} дн. назад"
            elif days_ago < 30:
                time_ago = f"{days_ago // 7} нед. назад"
            elif days_ago < 365:
                time_ago = f"{days_ago // 30} мес. назад"
            else:
                time_ago = f"{days_ago // 365} г. назад"

            last_replacement_section = (
                "\n"
                f"🧾 <b>История замен</b>\n"
                f"📅 <b>Последняя:</b> {last_date.strftime('%d.%m.%Y')} в {last_date.strftime('%H:%M')}\n"
                f"🕒 <b>Давность:</b> {time_ago}\n"
                f"🔁 <b>Всего замен:</b> {len(pc_replacements)}\n"
            )
    except Exception as e:
        logger.error(f"Error reading component_replacements data: {e}")

    serial_display = f"{serial_no} / {hw_serial_no}" if hw_serial_no else serial_no

    confirmation_text = (
        "📋 <b>Подтверждение замены компонента ПК</b>\n\n"
        f"🔢 <b>Серийный номер:</b> {serial_display}\n"
        f"💻 <b>Модель:</b> {model_name}\n"
        f"🏢 <b>Филиал:</b> {branch}\n"
        f"📍 <b>Локация:</b> {location}\n"
        f"👤 <b>Сотрудник:</b> {employee}\n"
        f"🔧 <b>Компонент:</b> {component_name}\n"
        f"{last_replacement_section}"
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

    return States.WORK_COMPONENT_CONFIRMATION


async def save_component_replacement_pc(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Сохраняет данные о замене компонента ПК в JSON и обновляет описание в базе данных
    """
    try:
        file_path = Path("data/component_replacements.json")

        # Получаем текущую БД пользователя
        user_id = context._user_id if hasattr(context, '_user_id') else None
        db_name = database_manager.get_user_database(user_id) if user_id else 'ITINVENT'

        # Получаем данные о ПК
        equipment = context.user_data.get('component_replacement_equipment', {})
        equipment_id = equipment.get('ID')
        current_description = equipment.get('DESCRIPTION') or ''

        component_name = context.user_data.get('pc_component_name', 'Неизвестный компонент')
        component_type = context.user_data.get('pc_component_type', 'other')

        # Формируем строку с датой замены компонента (используем \r\n для переноса строки)
        replacement_date = datetime.now().strftime("%d.%m.%Y %H:%M")
        replacement_note = f"\r\nЗамена {component_name}: {replacement_date} (IT-BOT)"

        # Обновляем описание в базе данных
        if equipment_id:
            config = database_manager.get_database_config(db_name)
            if config:
                db = UniversalInventoryDB(config)

                # Проверяем, есть ли уже запись о замене этого компонента в описании
                # Используем regex для поиска существующей записи
                pattern = rf'Замена {re.escape(component_name)}:.*?\(IT-BOT\)'
                if re.search(pattern, current_description):
                    # Обновляем последнюю запись о замене
                    new_description = re.sub(
                        pattern,
                        f'Замена {component_name}: {replacement_date} (IT-BOT)',
                        current_description
                    )
                else:
                    # Добавляем новую запись к описанию
                    new_description = current_description + replacement_note

                # UPDATE в базе
                try:
                    with db._get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE ITEMS
                            SET DESCR = ?, CH_DATE = GETDATE(), CH_USER = 'IT-BOT'
                            WHERE ID = ?
                        """, (new_description, equipment_id))
                        conn.commit()
                        logger.info(f"Обновлено описание для ID={equipment_id}: добавлена замена {component_name} от {replacement_date}")
                except Exception as e:
                    logger.error(f"Ошибка обновления описания: {e}")

        # Создаем запись для JSON
        record = {
            'serial_no': context.user_data.get('component_replacement_serial_no', ''),
            'hw_serial_no': equipment.get('HW_SERIAL_NO', ''),
            'model_name': equipment.get('MODEL_NAME', ''),
            'manufacturer': equipment.get('MANUFACTURER', ''),
            'branch': equipment.get('BRANCH_NAME', ''),
            'location': equipment.get('LOCATION', ''),
            'employee': equipment.get('EMPLOYEE_NAME', ''),
            'inv_no': equipment.get('INV_NO', ''),
            'component_type': component_type,
            'component_name': component_name,
            'db_name': db_name,
            'timestamp': datetime.now().isoformat()
        }

        saved = append_json_data(str(file_path), record)
        if not saved:
            logger.error("Не удалось сохранить замену компонента ПК в локальное хранилище: file=%s", file_path.name)
            return False

        logger.info("Сохранена замена компонента ПК: storage=sqlite file=%s db_name=%s", file_path.name, db_name)
        return True

    except Exception as e:
        logger.error(f"Ошибка сохранения замены компонента ПК: {e}")
        traceback.print_exc()
        return False
