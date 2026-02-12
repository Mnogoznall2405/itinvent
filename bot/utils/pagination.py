#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилиты для пагинации результатов

Функции и классы для разбиения списков на страницы и управления навигацией.
"""

import logging
from typing import List, Tuple, Any, Callable, Optional, Dict
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def paginate_results(
    results: List[Any],
    page: int = 0,
    items_per_page: int = 5
) -> Tuple[List[Any], int, bool, bool]:
    """
    Разбивает список результатов на страницы
    
    Параметры:
        results: Полный список результатов
        page: Номер текущей страницы (начиная с 0)
        items_per_page: Количество элементов на странице
        
    Возвращает:
        Tuple из 4 элементов:
            - List: Элементы для текущей страницы
            - int: Общее количество страниц
            - bool: Есть ли предыдущая страница
            - bool: Есть ли следующая страница
    """
    if not results:
        return [], 0, False, False
    
    total_pages = (len(results) + items_per_page - 1) // items_per_page
    
    # Проверяем корректность номера страницы
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    
    page_items = results[start_idx:end_idx]
    has_prev = page > 0
    has_next = page < total_pages - 1
    
    return page_items, total_pages, has_prev, has_next


def get_page_items(
    results: List[Any],
    page: int,
    items_per_page: int = 5
) -> List[Any]:
    """
    Получает элементы для конкретной страницы
    
    Параметры:
        results: Полный список результатов
        page: Номер страницы (начиная с 0)
        items_per_page: Количество элементов на странице
        
    Возвращает:
        List: Элементы для указанной страницы
    """
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    return results[start_idx:end_idx]


def calculate_total_pages(total_items: int, items_per_page: int = 5) -> int:
    """
    Вычисляет общее количество страниц

    Параметры:
        total_items: Общее количество элементов
        items_per_page: Количество элементов на странице

    Возвращает:
        int: Количество страниц
    """
    if total_items == 0:
        return 0
    return (total_items + items_per_page - 1) // items_per_page


# ============================ УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ПАГИНАЦИИ ============================

class PaginationHandler:
    """
    Универсальный обработчик пагинации для списков в Telegram боте.

    Управляет состоянием пагинации в context.user_data и обрабатывает навигацию.
    """

    def __init__(
        self,
        page_key: str,
        items_key: str,
        items_per_page: int = 8,
        callback_prefix: str = "page"
    ):
        """
        Инициализирует обработчик пагинации

        Параметры:
            page_key: Ключ для хранения номера страницы в context.user_data
            items_key: Ключ для хранения списка элементов в context.user_data
            items_per_page: Количество элементов на странице
            callback_prefix: Префикс для callback_data кнопок навигации
        """
        self.page_key = page_key
        self.items_key = items_key
        self.items_per_page = items_per_page
        self.callback_prefix = callback_prefix

    def get_current_page(self, context: ContextTypes.DEFAULT_TYPE) -> int:
        """
        Получает текущий номер страницы

        Параметры:
            context: Контекст выполнения

        Возвращает:
            int: Номер текущей страницы (начиная с 0)
        """
        return context.user_data.get(self.page_key, 0)

    def set_current_page(self, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
        """
        Устанавливает номер страницы

        Параметры:
            context: Контекст выполнения
            page: Номер страницы (начиная с 0)
        """
        context.user_data[self.page_key] = page

    def get_items(self, context: ContextTypes.DEFAULT_TYPE) -> List[Any]:
        """
        Получает список элементов из контекста

        Параметры:
            context: Контекст выполнения

        Возвращает:
            List: Список элементов
        """
        return context.user_data.get(self.items_key, [])

    def set_items(self, context: ContextTypes.DEFAULT_TYPE, items: List[Any]) -> None:
        """
        Сохраняет список элементов в контекст

        Параметры:
            context: Контекст выполнения
            items: Список элементов
        """
        context.user_data[self.items_key] = items

    def get_page_data(self, context: ContextTypes.DEFAULT_TYPE) -> Tuple[List[Any], int, int, bool, bool]:
        """
        Получает данные для текущей страницы

        Параметры:
            context: Контекст выполнения

        Возвращает:
            Tuple из 5 элементов:
                - List: Элементы текущей страницы
                - int: Номер текущей страницы
                - int: Общее количество страниц
                - bool: Есть ли предыдущая страница
                - bool: Есть ли следующая страница
        """
        items = self.get_items(context)
        current_page = self.get_current_page(context)

        page_items, total_pages, has_prev, has_next = paginate_results(
            items, current_page, self.items_per_page
        )

        return page_items, current_page, total_pages, has_prev, has_next

    def handle_navigation(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        direction: str
    ) -> Optional[int]:
        """
        Обрабатывает навигацию по страницам

        Параметры:
            update: Объект обновления от Telegram API
            context: Контекст выполнения
            direction: Направление навигации ('prev' или 'next')

        Возвращает:
            Optional[int]: Новый номер страницы или None если навигация невозможна
        """
        items = self.get_items(context)
        logger.info(f"[HANDLE_NAV] {self.page_key} direction={direction}, items_count={len(items) if items else 0}")

        if not items:
            logger.warning(f"Список элементов пуст для ключа {self.items_key}")
            return None

        total_pages = calculate_total_pages(len(items), self.items_per_page)
        current_page = self.get_current_page(context)
        logger.info(f"[HANDLE_NAV] current_page={current_page}, total_pages={total_pages}")

        if direction == 'prev' and current_page > 0:
            new_page = current_page - 1
            self.set_current_page(context, new_page)
            logger.info(f"[HANDLE_NAV] {self.page_key}: страница {current_page} -> {new_page}")
            return new_page

        elif direction == 'next' and current_page < total_pages - 1:
            new_page = current_page + 1
            self.set_current_page(context, new_page)
            logger.info(f"[HANDLE_NAV] {self.page_key}: страница {current_page} -> {new_page}")
            return new_page

        logger.warning(f"[HANDLE_NAV] {self.page_key}: нет страниц в направлении {direction}")
        return None

    def reset_pagination(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Сбрасывает пагинацию на первую страницу

        Параметры:
            context: Контекст выполнения
        """
        self.set_current_page(context, 0)

    def get_callback_data(self, action: str) -> str:
        """
        Генерирует callback_data для кнопки навигации

        Параметры:
            action: Действие ('prev', 'next', 'info')

        Возвращает:
            str: Callback data для кнопки
        """
        if action == 'info':
            return 'page_info'
        return f"{self.callback_prefix}_{action}"


def create_pagination_handler(
    page_key: str,
    items_key: str,
    items_per_page: int = 8,
    callback_prefix: str = "page"
) -> PaginationHandler:
    """
    Фабричная функция для создания обработчика пагинации

    Параметры:
        page_key: Ключ для хранения номера страницы
        items_key: Ключ для хранения списка элементов
        items_per_page: Количество элементов на странице
        callback_prefix: Префикс для callback_data

    Возвращает:
        PaginationHandler: Экземпляр обработчика пагинации
    """
    return PaginationHandler(page_key, items_key, items_per_page, callback_prefix)
