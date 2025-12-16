#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Декораторы для обработчиков бота

Содержит декораторы для проверки доступа, логирования и обработки ошибок.
"""

import time
import logging
from functools import wraps
from typing import Callable, Any

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from cache_manager import user_access_cache

logger = logging.getLogger(__name__)


async def check_user_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Проверяет доступ пользователя к боту с кэшированием
    
    Параметры:
        update: Объект обновления от Telegram API
        context: Контекст выполнения
        
    Возвращает:
        bool: True если доступ разрешен
    """
    from bot.config import config
    
    user_id = str(update.effective_user.id)
    
    # Проверяем кэш
    cached_access = user_access_cache.get(user_id)
    if cached_access is not None:
        return cached_access
    
    # Проверяем список разрешенных пользователей
    if user_id in config.telegram.allowed_users:
        user_access_cache.set(user_id, True, ttl=86400)
        return True
    
    # Проверяем членство в группе
    if config.telegram.allowed_group_id:
        try:
            member = await context.bot.get_chat_member(
                chat_id=config.telegram.allowed_group_id,
                user_id=update.effective_user.id,
                read_timeout=2
            )
            access_granted = member.status in ['member', 'administrator', 'creator']
            
            if access_granted:
                user_access_cache.set(user_id, True, ttl=3600)
            else:
                user_access_cache.set(user_id, False, ttl=120)
            
            return access_granted
        except Exception as e:
            error_msg = str(e)
            if "Timed out" in error_msg or "timeout" in error_msg.lower():
                logger.warning(f"Таймаут при проверке членства в группе для пользователя {user_id}")
            elif "Chat not found" in error_msg:
                logger.error(f"Группа {config.telegram.allowed_group_id} не найдена")
            elif "Bot was kicked" in error_msg:
                logger.error(f"Бот исключен из группы {config.telegram.allowed_group_id}")
            else:
                logger.warning(f"Ошибка проверки членства: {e}")
            
            user_access_cache.set(user_id, False, ttl=120)
            return False
    
    user_access_cache.set(user_id, False)
    return False


async def send_access_denied(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение об отказе в доступе"""
    from bot.config import Messages
    await update.message.reply_text(Messages.ACCESS_DENIED)


def require_user_access(func: Callable) -> Callable:
    """
    Декоратор для проверки доступа пользователя к боту
    
    Использование:
        @require_user_access
        async def my_handler(update, context):
            ...
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs) -> Any:
        if not await check_user_access(update, context):
            await send_access_denied(update, context)
            return ConversationHandler.END if hasattr(func, '__conversation_handler__') else None
        return await func(update, context, *args, **kwargs)
    return wrapper


def log_execution_time(func: Callable) -> Callable:
    """
    Декоратор для логирования времени выполнения функции
    
    Использование:
        @log_execution_time
        async def slow_operation(update, context):
            ...
    """
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            logger.info(f"{func.__name__} выполнен за {duration:.2f}с")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"{func.__name__} завершился с ошибкой за {duration:.2f}с: {e}")
            raise
    return wrapper


def handle_errors(func: Callable) -> Callable:
    """
    Декоратор для обработки ошибок в обработчиках
    
    Использование:
        @handle_errors
        async def my_handler(update, context):
            ...
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs) -> Any:
        try:
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в {func.__name__}: {e}", exc_info=True)
            
            # Отправляем пользователю понятное сообщение
            try:
                if update.message:
                    await update.message.reply_text(
                        "❌ Произошла ошибка при выполнении операции.\n"
                        "Попробуйте позже или обратитесь к администратору."
                    )
                elif update.callback_query:
                    await update.callback_query.answer(
                        "❌ Произошла ошибка",
                        show_alert=True
                    )
            except Exception:
                pass
            
            return ConversationHandler.END
    return wrapper
