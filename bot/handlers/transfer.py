#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчики перемещения оборудования с актом приема-передачи
Загрузка фотографий, распознавание серийных номеров, генерация PDF-акта.
"""
import asyncio
import logging
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import TimedOut

from bot.config import States, Messages, StorageKeys
from bot.utils.decorators import require_user_access, handle_errors
from bot.services.ocr_service import extract_serial_from_image
from bot.services.validation import validate_employee_name
from database_manager import database_manager
from equipment_data_manager import EquipmentDataManager

logger = logging.getLogger(__name__)

# Глобальный менеджер данных
equipment_manager = EquipmentDataManager()


async def send_document_with_retry(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    document_path: str,
    filename: str,
    caption: str,
    max_retries: int = 3
) -> bool:
    """
    Отправляет документ с автоматическим повтором при timed out ошибке

    Параметры:
        context: Контекст выполнения бота
        chat_id: ID чата для отправки
        document_path: Путь к файлу
        filename: Имя файла
        caption: Подпись к документу
        max_retries: Максимальное количество попыток

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
                    caption=caption
                )
            logger.info(f"Документ успешно отправлен с попытки {attempt + 1}")
            return True

        except TimedOut as e:
            logger.warning(f"Попытка {attempt + 1}/{max_retries}: Таймаут отправки документа {filename}")
            if attempt < max_retries - 1:
                # Ждем перед следующей попыткой
                wait_time = (attempt + 1) * 2  # 2, 4, 6 секунд
                logger.info(f"Ждем {wait_time} сек. перед повторной попыткой...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Не удалось отправить документ после {max_retries} попыток")

        except Exception as e:
            logger.error(f"Ошибка отправки документа {filename}: {e}")
            # Другие ошибки не retry'им
            break

    return False


@require_user_access
async def start_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начало процесса перемещения оборудования
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Состояние TRANSFER_WAIT_PHOTOS
    """
    # Инициализируем контекст для хранения данных о перемещении
    context.user_data[StorageKeys.TEMP_PHOTOS] = []
    context.user_data[StorageKeys.TEMP_SERIALS] = []
    
    await update.message.reply_text(
        "📦 <b>Перемещение оборудования с актом</b>\n\n"
        "Отправьте фотографии оборудования (до 10 штук).\n"
        "Можете отправить несколько фото подряд.\n\n"
        "ℹ️ <i>Оборудование будет автоматически сгруппировано по текущим владельцам.\n"
        "Для каждого старого сотрудника будет создан отдельный акт приема-передачи.</i>\n\n"
        "После загрузки всех фото отправьте команду /done для продолжения.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='HTML'
    )
    return States.TRANSFER_WAIT_PHOTOS


@handle_errors
async def receive_transfer_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик получения фотографий для перемещения
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    # Обработка команды /done
    if update.message and update.message.text and update.message.text.startswith('/done'):
        photos = context.user_data.get(StorageKeys.TEMP_PHOTOS, [])
        serials_data = context.user_data.get(StorageKeys.TEMP_SERIALS, [])
        
        if not photos:
            await update.message.reply_text(
                "❌ Вы не загрузили ни одной фотографии.\n"
                "Отправьте хотя бы одно фото оборудования."
            )
            return States.TRANSFER_WAIT_PHOTOS
        
        # Группируем оборудование для предварительного просмотра
        from bot.services.equipment_grouper import group_equipment_by_employee
        grouped_equipment = group_equipment_by_employee(serials_data)
        groups_count = len(grouped_equipment)
        
        # Переходим к запросу нового сотрудника
        await update.message.reply_text(
            f"✅ Загружено {len(photos)} фото.\n"
            f"📦 Распознано единиц оборудования: {len(serials_data)}\n"
            f"👥 Будет создано актов: {groups_count}\n\n"
            "Теперь укажите ФИО нового сотрудника, которому будет передано оборудование:"
        )
        return States.TRANSFER_NEW_EMPLOYEE
    
    # Обработка текстовых сообщений (не команд)
    if update.message and update.message.text and not update.message.text.startswith('/'):
        await update.message.reply_text(
            "Пожалуйста, отправьте фотографию оборудования или команду /done для завершения."
        )
        return States.TRANSFER_WAIT_PHOTOS
    
    # Обработка фотографий
    if update.message and update.message.photo:
        try:
            # Проверяем лимит фотографий
            current_photos = context.user_data.get(StorageKeys.TEMP_PHOTOS, [])
            from bot.config import config
            max_photos = config.transfer.max_photos
            
            if len(current_photos) >= max_photos:
                await update.message.reply_text(
                    f"⚠️ Достигнут лимит фотографий ({max_photos}).\n"
                    "Отправьте /done для продолжения."
                )
                return States.TRANSFER_WAIT_PHOTOS
            
            # Получаем фото наилучшего качества
            photo = update.message.photo[-1]
            photo_file = await context.bot.get_file(photo.file_id)
            
            await update.message.reply_text("🛠️ Фото обрабатывается, пожалуйста, подождите...")
            
            # Создаем временный путь для сохранения фото
            photo_path = f"temp_transfer_{photo.file_id}.jpg"
            await photo_file.download_to_drive(photo_path)
            
            # Обрабатываем изображение для извлечения серийного номера
            serial = await extract_serial_from_image(photo_path)
            
            # Если серийный номер не распознан — не используем фото
            if not serial:
                cleanup_temp_file(photo_path)
                await update.message.reply_text(
                    "📷 Фото получено, но серийный номер не распознан.\n"
                    "Фото не будет использовано. Отправьте другое фото."
                )
                return States.TRANSFER_WAIT_PHOTOS
            
            # Проверяем наличие оборудования в базе
            user_id = update.effective_user.id
            db = database_manager.create_database_connection(user_id)
            
            if not db:
                cleanup_temp_file(photo_path)
                await update.message.reply_text(
                    "⚠️ Не удалось подключиться к базе данных.\n"
                    "Фото не будет использовано. Попробуйте позже."
                )
                return States.TRANSFER_WAIT_PHOTOS
            
            try:
                equipment = db.find_by_serial_number(serial)
                
                # Если не найдено, пробуем варианты с заменой O↔0
                if not equipment:
                    from bot.services.ocr_service import generate_serial_variants
                    variants = generate_serial_variants(serial)
                    
                    # Пробуем каждый вариант (кроме оригинала, который уже проверили)
                    for variant in variants:
                        if variant != serial:
                            logger.info(f"Пробуем вариант: {variant}")
                            equipment = db.find_by_serial_number(variant)
                            if equipment:
                                logger.info(f"✅ Найдено по варианту: {variant} (оригинал: {serial})")
                                # Обновляем serial для отображения
                                serial = variant
                                break
                
            except Exception as e:
                logger.warning(f"Ошибка поиска оборудования {serial}: {e}")
                equipment = None
            finally:
                db.close_connection()
            
            if equipment:
                # Оборудование найдено - добавляем в список
                employee_name = equipment.get('EMPLOYEE_NAME') or 'Не указан'
                if employee_name and employee_name != 'Не указан':
                    employee_name = employee_name.strip() or 'Не указан'
                
                context.user_data[StorageKeys.TEMP_PHOTOS].append(photo_path)
                context.user_data[StorageKeys.TEMP_SERIALS].append({
                    'serial': serial,
                    'current_employee': employee_name,
                    'equipment': equipment
                })
                
                await update.message.reply_text(
                    f"✅ Оборудование найдено в базе!\n"
                    f"🔢 Серийный номер: <b>{serial}</b>\n"
                    f"👤 Числится на: <b>{employee_name}</b>\n"
                    f"📦 Всего фото: {len(context.user_data[StorageKeys.TEMP_PHOTOS])}\n\n"
                    "Отправьте еще фото или /done для продолжения.",
                    parse_mode='HTML'
                )
            else:
                # Оборудование не найдено - не используем
                cleanup_temp_file(photo_path)
                await update.message.reply_text(
                    f"❌ Оборудование с серийным номером <b>{serial}</b> не найдено в базе.\n"
                    "Фото не будет использовано. Отправьте другое фото.",
                    parse_mode='HTML'
                )
            
            return States.TRANSFER_WAIT_PHOTOS
            
        except Exception as e:
            logger.error(f"Ошибка обработки фото для перемещения: {e}")
            await update.message.reply_text(
                "❌ Ошибка обработки фотографии. Попробуйте еще раз."
            )
            return States.TRANSFER_WAIT_PHOTOS
    
    # Если получено что-то другое
    await update.message.reply_text(
        "Пожалуйста, отправьте фотографию оборудования или команду /done для завершения."
    )
    return States.TRANSFER_WAIT_PHOTOS


@handle_errors
async def receive_new_employee(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода нового сотрудника
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    if not update.message or not update.message.text:
        await update.message.reply_text("Пожалуйста, введите ФИО нового сотрудника.")
        return States.TRANSFER_NEW_EMPLOYEE
    
    from bot.handlers.suggestions_handler import show_employee_suggestions
    
    new_employee = update.message.text.strip()
    
    # Показываем подсказки если есть совпадения
    if await show_employee_suggestions(
        update, context, new_employee,
        mode='transfer',
        pending_key='pending_transfer_employee_input',
        suggestions_key='transfer_employee_suggestions'
    ):
        return States.TRANSFER_NEW_EMPLOYEE
    
    # Валидация ФИО
    if not validate_employee_name(new_employee):
        await update.message.reply_text(
            "❌ ФИО должно содержать только буквы и пробелы.\n"
            "Пожалуйста, введите корректное ФИО."
        )
        return States.TRANSFER_NEW_EMPLOYEE
    
    # Сохраняем нового сотрудника
    context.user_data['new_employee'] = new_employee
    
    # Получаем отдел нового сотрудника из БД
    await get_employee_department(update, context, new_employee)
    
    # Показываем подтверждение
    await show_transfer_confirmation(update, context)
    
    return States.TRANSFER_CONFIRMATION


async def show_transfer_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отображает данные для подтверждения перемещения с группировкой по сотрудникам
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
    """
    from bot.services.equipment_grouper import group_equipment_by_employee
    
    new_employee = context.user_data.get('new_employee', 'Не указан')
    serials_data = context.user_data.get(StorageKeys.TEMP_SERIALS, [])
    
    # Группируем оборудование по старым сотрудникам
    grouped_equipment = group_equipment_by_employee(serials_data)
    
    # Фильтруем пустые группы (edge case)
    grouped_equipment = {k: v for k, v in grouped_equipment.items() if v}
    
    # Проверка на пустые данные
    if not grouped_equipment:
        error_text = "❌ Нет данных для перемещения. Попробуйте снова."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_text)
        else:
            await update.message.reply_text(error_text)
        return
    
    # Проверка на превышение лимита актов (edge case)
    MAX_ACTS_PER_TRANSFER = 10
    if len(grouped_equipment) > MAX_ACTS_PER_TRANSFER:
        error_text = (
            f"⚠️ Слишком много групп ({len(grouped_equipment)}).\n"
            f"Максимум: {MAX_ACTS_PER_TRANSFER} актов за одну операцию.\n\n"
            "Пожалуйста, разделите перемещение на несколько операций."
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(error_text)
        else:
            await update.message.reply_text(error_text)
        return
    
    # Сохраняем сгруппированные данные в контексте
    context.user_data['grouped_equipment'] = grouped_equipment
    
    # Подсчитываем общее количество единиц и групп
    total_count = len(serials_data)
    groups_count = len(grouped_equipment)
    
    # Формируем сообщение с группами
    confirmation_text = (
        "📋 <b>Подтверждение перемещения оборудования</b>\n\n"
        f"👤 <b>Новый сотрудник:</b> {new_employee}\n"
        f"📦 <b>Всего единиц:</b> {total_count}\n"
        f"👥 <b>Количество актов:</b> {groups_count}\n\n"
    )
    
    # Добавляем информацию о каждой группе
    for act_num, (old_employee, equipment_list) in enumerate(grouped_equipment.items(), 1):
        confirmation_text += f"📄 <b>Акт {act_num}: От {old_employee}</b>\n"
        confirmation_text += f"🔢 Серийные номера ({len(equipment_list)} шт.):\n"
        
        for i, item in enumerate(equipment_list, 1):
            serial = item.get('serial', 'Неизвестен')
            confirmation_text += f"{i}. {serial}\n"
        
        confirmation_text += "\n"
    
    confirmation_text += "Подтвердите перемещение оборудования?"
    
    # Создаем клавиатуру подтверждения
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_transfer"),
            InlineKeyboardButton("❌ Отменить", callback_data="cancel_transfer")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            confirmation_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            confirmation_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )


@handle_errors
async def handle_transfer_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик подтверждения/отмены перемещения с генерацией множественных актов
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: ConversationHandler.END
    """
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_transfer":
        # Получаем сгруппированные данные
        grouped_equipment = context.user_data.get('grouped_equipment', {})
        
        if not grouped_equipment:
            await query.edit_message_text("❌ Ошибка: данные о группировке не найдены.")
            clear_transfer_data(context)
            return ConversationHandler.END
        
        # Генерируем акты приема-передачи
        await query.edit_message_text("🛠️ Создание актов приема-передачи...")
        
        try:
            # Получаем данные
            new_employee = context.user_data.get('new_employee', '')
            new_employee_dept = context.user_data.get('new_employee_dept', '')
            user_id = update.effective_user.id
            db_name = database_manager.get_user_database(user_id)
            
            # Генерируем множественные PDF-акты
            from bot.services.pdf_generator import generate_multiple_transfer_acts
            
            acts_info = await generate_multiple_transfer_acts(
                new_employee=new_employee,
                new_employee_dept=new_employee_dept,
                grouped_equipment=grouped_equipment,
                db_name=db_name
            )
            
            # Отправляем каждый созданный PDF в Telegram
            successful_acts = []
            failed_acts = []
            
            for idx, act_info in enumerate(acts_info, 1):
                old_employee = act_info.get('old_employee', 'Неизвестен')
                equipment_count = act_info.get('equipment_count', 0)
                
                # Показываем прогресс с деталями
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"🛠️ Создание акта {idx} из {len(acts_info)}...\n"
                         f"От: {old_employee}\n"
                         f"Единиц оборудования: {equipment_count}"
                )
                
                if act_info.get('success') and act_info.get('pdf_path'):
                    pdf_path = act_info['pdf_path']

                    if os.path.exists(pdf_path):
                        # Отправляем PDF с автоматическим retry при timed out
                        caption = f"✅ Акт приема-передачи\nОт: {old_employee}\nКому: {new_employee}"
                        filename = act_info.get('filename', os.path.basename(pdf_path))

                        sent = await send_document_with_retry(
                            context=context,
                            chat_id=query.message.chat_id,
                            document_path=pdf_path,
                            filename=filename,
                            caption=caption,
                            max_retries=3
                        )

                        if sent:
                            successful_acts.append(act_info)

                            # Сохраняем информацию о перемещениях для этой группы
                            equipment_list = grouped_equipment.get(old_employee, [])
                            for item in equipment_list:
                                # Добавляем db_name в additional_data
                                additional_data = item.get('equipment', {}).copy()
                                additional_data['db_name'] = db_name

                                equipment_manager.add_equipment_transfer(
                                    serial_number=item.get('serial', ''),
                                    new_employee=new_employee,
                                    old_employee=old_employee,
                                    additional_data=additional_data,
                                    act_pdf_path=pdf_path
                                )
                        else:
                            # Не удалось отправить ни одной попыткой
                            logger.error(f"Не удалось отправить акт для {old_employee} после всех попыток")
                            failed_acts.append(old_employee)
                    else:
                        logger.error(f"PDF файл не найден: {pdf_path}")
                        failed_acts.append(old_employee)
                else:
                    # Акт не был создан
                    error_msg = act_info.get('error', 'Неизвестная ошибка')
                    logger.error(f"Не удалось создать акт для {old_employee}: {error_msg}")
                    failed_acts.append(old_employee)
            
            # Сохраняем информацию о всех актах для возможной отправки на email
            if successful_acts:
                context.user_data['act_files_info'] = {
                    'acts': successful_acts,
                    'new_employee': new_employee,
                    'new_employee_dept': new_employee_dept,
                    'total_equipment': sum(act.get('equipment_count', 0) for act in successful_acts),
                    'db_name': db_name
                }
            
            # Формируем итоговое сообщение
            if successful_acts and not failed_acts:
                # Все акты созданы успешно
                total_equipment = sum(act.get('equipment_count', 0) for act in successful_acts)
                result_text = (
                    f"✅ <b>Перемещение оборудования завершено!</b>\n\n"
                    f"📄 Создано актов: {len(successful_acts)}\n"
                    f"📦 Всего единиц оборудования: {total_equipment}\n"
                    f"👤 Новый владелец: {new_employee}\n\n"
                    "Все акты отправлены вам в чат.\n\n"
                    "Хотите отправить все акты на email?"
                )
                
                # Предлагаем отправить акты на email
                keyboard = [
                    [InlineKeyboardButton("📧 Отправить старым владельцам", callback_data="act:email_owners")],
                    [InlineKeyboardButton("✉️ Ввести email вручную", callback_data="act:email")],
                    [InlineKeyboardButton("⏭ Пропустить", callback_data="act:skip")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=result_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            elif successful_acts and failed_acts:
                # Частичный успех
                total_equipment = sum(act.get('equipment_count', 0) for act in successful_acts)
                result_text = (
                    f"⚠️ <b>Перемещение завершено с ошибками</b>\n\n"
                    f"✅ Создано актов: {len(successful_acts)}\n"
                    f"📦 Перемещено единиц: {total_equipment}\n"
                    f"❌ Не удалось создать акты для:\n"
                )
                for failed_emp in failed_acts:
                    result_text += f"  • {failed_emp}\n"
                
                result_text += (
                    "\n💡 <i>Рекомендация: Попробуйте создать акты для этих сотрудников отдельно.</i>\n\n"
                    "Хотите отправить созданные акты на email?"
                )
                
                # Предлагаем отправить успешные акты на email
                keyboard = [
                    [InlineKeyboardButton("📧 Отправить старым владельцам", callback_data="act:email_owners")],
                    [InlineKeyboardButton("✉️ Ввести email вручную", callback_data="act:email")],
                    [InlineKeyboardButton("⏭ Пропустить", callback_data="act:skip")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=result_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                # Все акты не созданы
                result_text = (
                    "❌ <b>Не удалось создать ни одного акта</b>\n\n"
                    "Возможные причины:\n"
                    "• Проблемы с шаблоном акта\n"
                    "• Ошибка конвертации в PDF\n"
                    "• Недостаточно прав доступа\n\n"
                    "💡 <i>Рекомендация: Попробуйте позже или обратитесь к администратору.</i>"
                )
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=result_text,
                    parse_mode='HTML'
                )
            
        except Exception as e:
            logger.error(f"Ошибка при создании актов: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    "❌ <b>Произошла критическая ошибка при создании актов</b>\n\n"
                    "Возможные причины:\n"
                    "• Проблемы с подключением к базе данных\n"
                    "• Ошибка в данных оборудования\n"
                    "• Технические неполадки\n\n"
                    "💡 <i>Рекомендация: Попробуйте выполнить операцию заново через несколько минут.\n"
                    "Если ошибка повторяется, обратитесь к администратору.</i>"
                ),
                parse_mode='HTML'
            )
        finally:
            # Очищаем временные данные
            clear_transfer_data(context)
    
    elif query.data == "cancel_transfer":
        await query.edit_message_text("❌ Перемещение оборудования отменено.")
        clear_transfer_data(context)
    
    return ConversationHandler.END


async def generate_transfer_act(new_employee: str, new_employee_dept: str, serials_data: list, db_name: str) -> str:
    """
    Генерирует PDF-акт приема-передачи
    
    Параметры:
        new_employee: ФИО нового сотрудника
        new_employee_dept: Отдел нового сотрудника
        serials_data: Список данных об оборудовании
        db_name: Название базы данных
        
    Возвращает:
        str: Путь к созданному PDF-файлу
    """
    from bot.services.pdf_generator import generate_transfer_act_pdf
    
    try:
        pdf_path = await generate_transfer_act_pdf(new_employee, new_employee_dept, serials_data, db_name)
        return pdf_path
        
    except Exception as e:
        logger.error(f"Ошибка генерации акта: {e}", exc_info=True)
        return None


def cleanup_temp_file(file_path: str) -> None:
    """
    Удаляет временный файл
    
    Параметры:
        file_path: Путь к файлу
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Временный файл {file_path} удален")
    except Exception as e:
        logger.warning(f"Не удалось удалить временный файл {file_path}: {e}")


def clear_transfer_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Очищает временные данные перемещения из контекста
    
    Параметры:
        context: Контекст выполнения
    """
    # Удаляем временные фотографии
    photos = context.user_data.get(StorageKeys.TEMP_PHOTOS, [])
    for photo_path in photos:
        cleanup_temp_file(photo_path)
    
    # Очищаем данные из контекста
    keys_to_clear = [
        StorageKeys.TEMP_PHOTOS,
        StorageKeys.TEMP_SERIALS,
        'new_employee',
        'new_employee_dept',
        'grouped_equipment'
    ]
    
    for key in keys_to_clear:
        context.user_data.pop(key, None)



@handle_errors
async def handle_employee_suggestion_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора сотрудника из подсказок для перемещения
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Следующее состояние
    """
    from bot.handlers.suggestions_handler import handle_employee_suggestion_generic
    
    query = update.callback_query
    data = query.data
    suggestions = context.user_data.get('transfer_employee_suggestions', [])
    
    # Обработка выбора конкретного сотрудника
    if data.startswith('transfer_emp:') and not data.endswith((':manual', ':refresh')):
        try:
            idx = int(data.split(':', 1)[1])
            if 0 <= idx < len(suggestions):
                selected_name = suggestions[idx]
                context.user_data['new_employee'] = selected_name
                
                # Получаем отдел выбранного сотрудника
                await get_employee_department(update, context, selected_name)
                
                await query.answer()
                await query.edit_message_text(f"✅ Выбран сотрудник: {selected_name}")
                await show_transfer_confirmation_after_callback(query, context)
                
                return States.TRANSFER_CONFIRMATION
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки выбора сотрудника: {e}")
    
    # Обработка "Ввести как есть"
    elif data == 'transfer_emp:manual':
        pending = context.user_data.get('pending_transfer_employee_input', '').strip()
        
        if not pending:
            await query.answer()
            await query.edit_message_text(
                "❌ Не найден введённый текст. Пожалуйста, введите ФИО заново."
            )
            return States.TRANSFER_NEW_EMPLOYEE
        
        if not validate_employee_name(pending):
            await query.answer()
            await query.edit_message_text(
                "❌ ФИО должно содержать только буквы и пробелы.\n"
                "Пожалуйста, введите корректное ФИО."
            )
            return States.TRANSFER_NEW_EMPLOYEE
        
        context.user_data['new_employee'] = pending
        
        # Получаем отдел введенного сотрудника
        await get_employee_department(update, context, pending)
        
        await query.answer()
        await query.edit_message_text(f"✅ Принято: {pending}")
        await show_transfer_confirmation_after_callback(query, context)
        
        return States.TRANSFER_CONFIRMATION
    
    # Обработка "Обновить список" - используем универсальный обработчик
    return await handle_employee_suggestion_generic(
        update=update,
        context=context,
        mode='transfer',
        storage_key='new_employee',
        pending_key='pending_transfer_employee_input',
        suggestions_key='transfer_employee_suggestions',
        next_state=States.TRANSFER_NEW_EMPLOYEE,
        next_message=None
    )


async def get_employee_department(update: Update, context: ContextTypes.DEFAULT_TYPE, employee_name: str) -> None:
    """
    Получает отдел сотрудника из БД и сохраняет в context
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        employee_name: ФИО сотрудника
    """
    user_id = update.effective_user.id
    db = database_manager.create_database_connection(user_id)
    
    new_employee_dept = ''
    if db:
        try:
            # Сначала пробуем точное совпадение
            new_employee_dept = db.get_owner_dept(employee_name, strict=True)
            logger.info(f"Поиск отдела (strict=True) для '{employee_name}': {new_employee_dept}")
            
            # Если не нашли - пробуем нечеткий поиск
            if not new_employee_dept:
                new_employee_dept = db.get_owner_dept(employee_name, strict=False)
                logger.info(f"Поиск отдела (strict=False) для '{employee_name}': {new_employee_dept}")
            
            # Если все еще не нашли - пробуем через find_by_employee
            if not new_employee_dept:
                logger.warning(f"Отдел не найден через get_owner_dept, пробуем find_by_employee")
                employees = db.find_by_employee(employee_name, strict=False)
                if employees and len(employees) > 0:
                    # Берем отдел из первой записи оборудования
                    new_employee_dept = employees[0].get('OWNER_DEPT', '')
                    logger.info(f"Отдел найден через find_by_employee: {new_employee_dept}")
            
            context.user_data['new_employee_dept'] = new_employee_dept if new_employee_dept else ''
            logger.info(f"Итоговый отдел для '{employee_name}': '{new_employee_dept}'")
            
        except Exception as e:
            logger.error(f"Ошибка при получении отдела сотрудника '{employee_name}': {e}", exc_info=True)
            context.user_data['new_employee_dept'] = ''
    else:
        logger.warning("Не удалось создать подключение к БД")
        context.user_data['new_employee_dept'] = ''


async def show_transfer_confirmation_after_callback(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отображает подтверждение перемещения после callback с группировкой по сотрудникам
    
    Параметры:
        query: Callback query
        context: Контекст выполнения
    """
    from bot.services.equipment_grouper import group_equipment_by_employee
    
    new_employee = context.user_data.get('new_employee', 'Не указан')
    serials_data = context.user_data.get(StorageKeys.TEMP_SERIALS, [])
    
    # Группируем оборудование по старым сотрудникам
    grouped_equipment = group_equipment_by_employee(serials_data)
    
    # Фильтруем пустые группы (edge case)
    grouped_equipment = {k: v for k, v in grouped_equipment.items() if v}
    
    # Проверка на пустые данные
    if not grouped_equipment:
        await query.message.reply_text("❌ Нет данных для перемещения. Попробуйте снова.")
        return
    
    # Проверка на превышение лимита актов (edge case)
    MAX_ACTS_PER_TRANSFER = 10
    if len(grouped_equipment) > MAX_ACTS_PER_TRANSFER:
        error_text = (
            f"⚠️ Слишком много групп ({len(grouped_equipment)}).\n"
            f"Максимум: {MAX_ACTS_PER_TRANSFER} актов за одну операцию.\n\n"
            "Пожалуйста, разделите перемещение на несколько операций."
        )
        await query.message.reply_text(error_text)
        return
    
    # Сохраняем сгруппированные данные в контексте
    context.user_data['grouped_equipment'] = grouped_equipment
    
    # Подсчитываем общее количество единиц и групп
    total_count = len(serials_data)
    groups_count = len(grouped_equipment)
    
    # Формируем сообщение с группами
    confirmation_text = (
        "📋 <b>Подтверждение перемещения оборудования</b>\n\n"
        f"👤 <b>Новый сотрудник:</b> {new_employee}\n"
        f"📦 <b>Всего единиц:</b> {total_count}\n"
        f"👥 <b>Количество актов:</b> {groups_count}\n\n"
    )
    
    # Добавляем информацию о каждой группе
    for act_num, (old_employee, equipment_list) in enumerate(grouped_equipment.items(), 1):
        confirmation_text += f"📄 <b>Акт {act_num}: От {old_employee}</b>\n"
        confirmation_text += f"🔢 Серийные номера ({len(equipment_list)} шт.):\n"
        
        for i, item in enumerate(equipment_list, 1):
            serial = item.get('serial', 'Неизвестен')
            confirmation_text += f"{i}. {serial}\n"
        
        confirmation_text += "\n"
    
    confirmation_text += "Подтвердите перемещение оборудования?"
    
    # Создаем клавиатуру подтверждения
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_transfer"),
            InlineKeyboardButton("❌ Отменить", callback_data="cancel_transfer")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        confirmation_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
