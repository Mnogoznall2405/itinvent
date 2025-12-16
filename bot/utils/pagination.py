#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилиты для пагинации результатов

Функции для разбиения списков на страницы.
"""

from typing import List, Tuple, Any


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
