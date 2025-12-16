#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчики поиска оборудования по серийному номеру

Содержит функции для поиска оборудования по серийному номеру или фото.
"""

import logging
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import States, Messages, StorageKeys
from bot.utils.decorators import require_user_access, handle_errors
from bot.utils.formatters import format_equipment_info
from bot.services.ocr_service import extract_serial_from_image
from bot.services.validation import validate_serial_number
from database_manager import database_manager

logger = logging.getLogger(__name__)


@require_user_access
async def ask_find_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик запроса поиска оборудования
    
    Переводит бота в режим ожидания ввода серийного номера или фотографии.
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Состояние FIND_WAIT_INPUT
    """
    await update.message.reply_text(
        "📝 Отправьте серийный номер или фото с серийным номером для поиска.",
        reply_markup=ReplyKeyboardRemove()
    )
    return States.FIND_WAIT_INPUT


@handle_errors
async def find_by_serial_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик ввода серийного номера или фото
    
    Обрабатывает текстовый ввод или фотографию для поиска оборудования.
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: ConversationHandler.END
    """
    from telegram.ext import ConversationHandler
    
    serial_number = None
    
    # Обработка фотографии
    if update.message.photo:
        processing_msg = await update.message.reply_text(Messages.PROCESSING_PHOTO)
        
        try:
            # Скачиваем фото
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            file_path = f"temp_{update.effective_user.id}.jpg"
            await file.download_to_drive(file_path)
            
            # Распознаем серийный номер
            serial_number = await extract_serial_from_image(file_path)
            
            # Удаляем временный файл
            import os
            if os.path.exists(file_path):
                os.remove(file_path)
            
            await processing_msg.delete()
            
            if not serial_number:
                await update.message.reply_text(
                    "❌ Не удалось распознать серийный номер на фото.\n"
                    "Попробуйте ввести серийный номер вручную."
                )
                return ConversationHandler.END
                
        except Exception as e:
            logger.error(f"Ошибка обработки фото: {e}")
            await update.message.reply_text(
                "❌ Ошибка при обработке фото. Попробуйте ввести серийный номер вручную."
            )
            return ConversationHandler.END
    
    # Обработка текстового ввода
    elif update.message.text:
        serial_number = update.message.text.strip()
    
    if not serial_number:
        await update.message.reply_text("❌ Серийный номер не указан.")
        return ConversationHandler.END
    
    # Валидация серийного номера
    if not validate_serial_number(serial_number):
        await update.message.reply_text(
            "❌ Некорректный формат серийного номера.\n"
            "Серийный номер должен содержать только буквы, цифры и символы: - _ . :"
        )
        return ConversationHandler.END
    
    # Поиск в базе данных
    try:
        user_id = update.effective_user.id
        db = database_manager.create_database_connection(user_id)
        
        if not db:
            await update.message.reply_text(
                "❌ Ошибка подключения к базе данных."
            )
            return ConversationHandler.END
        
        # Поиск оборудования
        equipment = db.find_by_serial_number(serial_number)
        
        # Если не найдено, пробуем варианты с заменой O↔0
        if not equipment:
            from bot.services.ocr_service import generate_serial_variants
            variants = generate_serial_variants(serial_number)
            
            # Пробуем каждый вариант (кроме оригинала, который уже проверили)
            for variant in variants:
                if variant != serial_number:
                    logger.info(f"Пробуем вариант: {variant}")
                    equipment = db.find_by_serial_number(variant)
                    if equipment:
                        logger.info(f"✅ Найдено по варианту: {variant} (оригинал: {serial_number})")
                        # Обновляем serial_number для отображения
                        serial_number = variant
                        break
        
        if equipment:
            # Форматируем и отправляем информацию
            info_text = f"✅ <b>Оборудование найдено!</b>\n\n{format_equipment_info(equipment)}"
            
            # Добавляем кнопку для повторного поиска
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Обработать еще", callback_data="search_again")]
            ])
            
            await update.message.reply_text(
                info_text, 
                parse_mode='HTML',
                reply_markup=keyboard
            )
        else:
            # Сохраняем серийный номер для возможного добавления
            context.user_data['last_search_serial'] = serial_number
            
            # Предлагаем добавить информацию и повторный поиск
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Добавить информацию об оборудовании", callback_data="add_unfound")],
                [InlineKeyboardButton("🔄 Обработать еще", callback_data="search_again")]
            ])
            
            await update.message.reply_text(
                f"❌ Оборудование с серийным номером <b>{serial_number}</b> не найдено в базе данных.\n\n"
                f"Вы можете добавить информацию об этом оборудовании:",
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        db.close_connection()
        
    except Exception as e:
        logger.error(f"Ошибка поиска оборудования: {e}")
        await update.message.reply_text(
            "❌ Ошибка при поиске в базе данных. Попробуйте позже."
        )
    
    return ConversationHandler.END



@handle_errors
async def handle_search_again(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик кнопки "🔄 Обработать еще"
    
    Возвращает пользователя в режим ожидания ввода серийного номера или фото.
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        int: Состояние FIND_WAIT_INPUT
    """
    query = update.callback_query
    await query.answer()
    
    # Удаляем предыдущее сообщение с результатом
    try:
        await query.message.delete()
    except:
        pass
    
    # Отправляем новое приглашение для поиска
    await query.message.reply_text(
        "📝 Отправьте серийный номер или фото с серийным номером для поиска.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    return States.FIND_WAIT_INPUT
