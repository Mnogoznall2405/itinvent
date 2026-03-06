#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчики поиска оборудования.

Порядок обработки:
1) Проверка QR (фото или текст QR payload),
2) Поиск по INV_NO / SERIAL_NO из QR,
3) Fallback на старую логику поиска по серийному номеру.
"""

import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import Messages, States
from bot.database_manager import database_manager
from bot.services.input_identifier_service import detect_identifiers_from_image, detect_identifiers_from_text
from bot.services.validation import validate_serial_number
from bot.utils.decorators import handle_errors, require_user_access
from bot.utils.formatters import format_equipment_info

logger = logging.getLogger(__name__)


@require_user_access
async def ask_find_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрашивает ввод номера/фото для поиска."""
    await update.message.reply_text(
        "📝 Отправьте серийный номер, QR-code (текст/фото) или изображение с номером.\n"
        "Для QR лучше отправлять как файл (документ) без сжатия.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return States.FIND_WAIT_INPUT


@handle_errors
async def find_by_serial_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает входные данные для поиска оборудования.
    Сначала пытается разобрать QR, затем работает по старой логике.
    """
    search_inv_no: str | None = None
    search_serial_no: str | None = None
    qr_payload_text: str | None = None
    source_label = "manual"
    user_id = update.effective_user.id if update.effective_user else None

    logger.info(
        "[SEARCH] start user_id=%s has_photo=%s has_document=%s has_text=%s",
        user_id,
        bool(update.message.photo if update.message else False),
        bool(update.message.document if update.message else False),
        bool(update.message.text if update.message else False),
    )

    if update.message.photo:
        processing_msg = await update.message.reply_text(Messages.PROCESSING_PHOTO)
        file_path = f"temp_{update.effective_user.id}.jpg"
        try:
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            await file.download_to_drive(file_path)

            detection = await detect_identifiers_from_image(file_path)
            search_inv_no = detection.get("inv_no")
            search_serial_no = detection.get("serial_no")
            qr_payload_text = detection.get("qr_payload_text")

            if detection.get("detector") == "qr":
                source_label = "qr_photo"
                logger.info(
                    "[SEARCH][QR] detected_from_photo user_id=%s inv_no=%s serial_no=%s payload_len=%s",
                    user_id,
                    search_inv_no or "-",
                    search_serial_no or "-",
                    len(qr_payload_text or ""),
                )
            elif detection.get("detector") == "ocr":
                source_label = "ocr_photo"
                logger.info(
                    "[SEARCH][OCR] fallback_from_photo user_id=%s serial=%s",
                    user_id,
                    search_serial_no or "-",
                )
            else:
                logger.info("[SEARCH][QR] not_detected_from_photo user_id=%s", user_id)

        except Exception as e:
            logger.error(f"Ошибка обработки фото: {e}")
            await update.message.reply_text(
                "❌ Ошибка при обработке фото. Попробуйте ввести номер вручную."
            )
            return ConversationHandler.END
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
            try:
                await processing_msg.delete()
            except Exception:
                pass

    elif update.message.document and str(update.message.document.mime_type or "").startswith("image/"):
        processing_msg = await update.message.reply_text(Messages.PROCESSING_PHOTO)
        original_name = str(update.message.document.file_name or "qr_image").strip()
        ext = os.path.splitext(original_name)[1] or ".jpg"
        file_path = f"temp_doc_{update.effective_user.id}{ext}"
        try:
            logger.info(
                "[SEARCH] received_document_image user_id=%s name=%s mime=%s size=%s",
                user_id,
                original_name,
                update.message.document.mime_type,
                update.message.document.file_size,
            )
            file = await context.bot.get_file(update.message.document.file_id)
            await file.download_to_drive(file_path)

            detection = await detect_identifiers_from_image(file_path)
            search_inv_no = detection.get("inv_no")
            search_serial_no = detection.get("serial_no")
            qr_payload_text = detection.get("qr_payload_text")

            if detection.get("detector") == "qr":
                source_label = "qr_document"
                logger.info(
                    "[SEARCH][QR] detected_from_document user_id=%s inv_no=%s serial_no=%s payload_len=%s",
                    user_id,
                    search_inv_no or "-",
                    search_serial_no or "-",
                    len(qr_payload_text or ""),
                )
            elif detection.get("detector") == "ocr":
                source_label = "ocr_document"
                logger.info(
                    "[SEARCH][OCR] fallback_from_document user_id=%s serial=%s",
                    user_id,
                    search_serial_no or "-",
                )
            else:
                logger.info("[SEARCH][QR] not_detected_from_document user_id=%s", user_id)

        except Exception as e:
            logger.error(f"Ошибка обработки фото: {e}")
            await update.message.reply_text(
                "❌ Ошибка при обработке фото. Попробуйте ввести номер вручную."
            )
            return ConversationHandler.END
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
            try:
                await processing_msg.delete()
            except Exception:
                pass

    elif update.message.text:
        text_input = update.message.text.strip()
        if text_input:
            detection = detect_identifiers_from_text(text_input)
            if detection.get("detector") == "qr":
                qr_payload_text = text_input
                search_inv_no = detection.get("inv_no")
                search_serial_no = detection.get("serial_no")
                source_label = "qr_text"
                logger.info(
                    "[SEARCH][QR] detected_from_text user_id=%s inv_no=%s serial_no=%s text_len=%s",
                    user_id,
                    search_inv_no or "-",
                    search_serial_no or "-",
                    len(text_input),
                )
            elif detection.get("detector") == "manual":
                search_serial_no = detection.get("serial_no")
                source_label = "manual_text"
                logger.info(
                    "[SEARCH][QR] not_detected_from_text user_id=%s fallback_manual_serial=%s",
                    user_id,
                    search_serial_no or "-",
                )

    if not search_inv_no and not search_serial_no:
        logger.info("[SEARCH] no_identifiers user_id=%s source=%s", user_id, source_label)
        await update.message.reply_text(
            "❌ Не удалось определить номер для поиска. "
            "Отправьте QR-code или серийный номер."
        )
        return ConversationHandler.END

    # Валидация только для обычного ввода серийного номера (без QR).
    if (
        not search_inv_no
        and search_serial_no
        and source_label in {"manual_text", "ocr_photo", "ocr_document"}
        and not validate_serial_number(search_serial_no)
    ):
        logger.info(
            "[SEARCH] serial_validation_failed user_id=%s serial=%s source=%s",
            user_id,
            search_serial_no or "-",
            source_label,
        )
        await update.message.reply_text(
            "❌ Некорректный формат серийного номера.\n"
            "Серийный номер должен содержать только буквы, цифры и символы: - _ . :"
        )
        return ConversationHandler.END

    try:
        db = database_manager.create_database_connection(user_id)
        if not db:
            logger.error("[SEARCH] db_connection_failed user_id=%s", user_id)
            await update.message.reply_text("❌ Ошибка подключения к базе данных.")
            return ConversationHandler.END

        equipment = {}
        search_hint = ""

        # 1) Поиск по INV_NO из QR.
        if search_inv_no:
            search_hint = f"инвентарным номером <b>{search_inv_no}</b>"
            logger.info("[SEARCH] try_inv_lookup user_id=%s inv_no=%s", user_id, search_inv_no)
            equipment = db.find_by_inventory_number(search_inv_no)
            logger.info("[SEARCH] inv_lookup_result user_id=%s found=%s", user_id, bool(equipment))

        # 2) Если по INV_NO не нашли — пробуем по SERIAL_NO.
        if not equipment and search_serial_no:
            search_hint = f"серийным номером <b>{search_serial_no}</b>"
            logger.info("[SEARCH] try_serial_lookup user_id=%s serial=%s", user_id, search_serial_no)
            equipment = db.find_by_serial_number(search_serial_no)
            logger.info("[SEARCH] serial_lookup_result user_id=%s found=%s", user_id, bool(equipment))

        if equipment:
            logger.info(
                "[SEARCH] success user_id=%s source=%s inv_no=%s serial_no=%s",
                user_id,
                source_label,
                search_inv_no or "-",
                search_serial_no or "-",
            )
            info_prefix = "✅ <b>Оборудование найдено!</b>"
            if source_label.startswith("qr"):
                info_prefix += "\n🔎 Источник: QR-code"

            info_text = f"{info_prefix}\n\n{format_equipment_info(equipment)}"
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔄 Обработать еще", callback_data="search_again")]]
            )
            await update.message.reply_text(
                info_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            logger.info(
                "[SEARCH] not_found user_id=%s source=%s inv_no=%s serial_no=%s",
                user_id,
                source_label,
                search_inv_no or "-",
                search_serial_no or "-",
            )
            # Сохраняем только serial, чтобы сценарий add_unfound не получил INV вместо serial.
            if search_serial_no:
                context.user_data["last_search_serial"] = search_serial_no
            else:
                context.user_data.pop("last_search_serial", None)

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📝 Добавить информацию об оборудовании",
                            callback_data="add_unfound",
                        )
                    ],
                    [InlineKeyboardButton("🔄 Обработать еще", callback_data="search_again")],
                ]
            )

            target_label = search_hint or "переданным данным"
            extra = ""
            if source_label.startswith("qr") and qr_payload_text:
                extra = "\n\nℹ️ QR распознан, но оборудование в текущей БД не найдено."
            elif source_label == "ocr_photo":
                extra = (
                    "\n\nℹ️ QR на сжатом фото не распознан. "
                    "Отправьте QR как файл (документ), так распознавание точнее."
                )

            await update.message.reply_text(
                f"❌ Оборудование с {target_label} не найдено в базе данных.{extra}\n\n"
                f"Вы можете добавить информацию об этом оборудовании:",
                parse_mode="HTML",
                reply_markup=keyboard,
            )

        db.close_connection()
        logger.info("[SEARCH] end user_id=%s", user_id)

    except Exception as e:
        logger.error("[SEARCH] error user_id=%s source=%s: %s", user_id, source_label, e)
        await update.message.reply_text(
            "❌ Ошибка при поиске в базе данных. Попробуйте позже."
        )

    return ConversationHandler.END


@handle_errors
async def handle_search_again(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Повторный запуск поиска без возврата в главное меню."""
    query = update.callback_query
    await query.answer()

    try:
        await query.message.delete()
    except Exception:
        pass

    await query.message.reply_text(
        "📝 Отправьте серийный номер, QR-code (текст/фото) или изображение с номером.\n"
        "Для QR лучше отправлять как файл (документ) без сжатия.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return States.FIND_WAIT_INPUT
