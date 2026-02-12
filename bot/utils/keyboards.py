#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Создание клавиатур для Telegram бота

Функции для генерации Reply и Inline клавиатур.
"""

from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton
from typing import List, Tuple


def create_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Создает клавиатуру главного меню
    
    Возвращает:
        ReplyKeyboardMarkup: Клавиатура с основными функциями бота
    """
    keyboard = [
        [
            KeyboardButton("🔎 Добавить или Найти"),
            KeyboardButton("👤 Найти по сотруднику")
        ],
        [
            KeyboardButton("📦 Перемещение оборудования с актом")
        ],
        [
            KeyboardButton("🔧 Работы"),
            KeyboardButton("📊 Экспорт данных")
        ],
        [
            KeyboardButton("🗄️ Управление базами данных")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def create_pagination_keyboard(
    page: int,
    total_pages: int,
    has_prev: bool,
    has_next: bool,
    callback_prefix: str = "page"
) -> InlineKeyboardMarkup:
    """
    Создает inline клавиатуру для пагинации
    
    Параметры:
        page: Номер текущей страницы (начиная с 0)
        total_pages: Общее количество страниц
        has_prev: Есть ли предыдущая страница
        has_next: Есть ли следующая страница
        callback_prefix: Префикс для callback_data
        
    Возвращает:
        InlineKeyboardMarkup: Клавиатура с кнопками навигации
    """
    keyboard = []
    nav_buttons = []
    
    if has_prev:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"{callback_prefix}_prev"))
    
    nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="page_info"))
    
    if has_next:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"{callback_prefix}_next"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    return InlineKeyboardMarkup(keyboard)


def create_confirmation_keyboard(
    confirm_callback: str = "confirm",
    cancel_callback: str = "cancel"
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру подтверждения действия
    
    Параметры:
        confirm_callback: Callback data для кнопки подтверждения
        cancel_callback: Callback data для кнопки отмены
        
    Возвращает:
        InlineKeyboardMarkup: Клавиатура с кнопками Да/Нет
    """
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data=confirm_callback),
            InlineKeyboardButton("❌ Нет", callback_data=cancel_callback)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_back_button(callback_data: str = "back") -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с одной кнопкой "Назад"
    
    Параметры:
        callback_data: Callback data для кнопки
        
    Возвращает:
        InlineKeyboardMarkup: Клавиатура с кнопкой назад
    """
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=callback_data)]]
    return InlineKeyboardMarkup(keyboard)


def create_cancel_button() -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопкой отмены
    
    Возвращает:
        InlineKeyboardMarkup: Клавиатура с кнопкой отмены
    """
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]]
    return InlineKeyboardMarkup(keyboard)


def create_employee_suggestions_keyboard(
    suggestions: List[str],
    mode: str = "transfer"
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с подсказками сотрудников
    
    Параметры:
        suggestions: Список ФИО сотрудников
        mode: Режим работы (transfer, unfound, change, search)
        
    Возвращает:
        InlineKeyboardMarkup: Клавиатура с кнопками выбора сотрудника
    """
    keyboard = []
    
    # Добавляем кнопки с ФИО (по одной на строку)
    for idx, name in enumerate(suggestions):
        # Ограничиваем длину текста кнопки
        display_name = name if len(name) <= 40 else name[:37] + "..."
        keyboard.append([
            InlineKeyboardButton(
                display_name,
                callback_data=f"{mode}_emp:{idx}"
            )
        ])
    
    # Добавляем кнопку "Ввести как есть"
    keyboard.append([
        InlineKeyboardButton(
            "✏️ Ввести как есть",
            callback_data=f"{mode}_emp:manual"
        )
    ])
    
    # Добавляем кнопку "Обновить список"
    keyboard.append([
        InlineKeyboardButton(
            "🔄 Обновить список",
            callback_data=f"{mode}_emp:refresh"
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)


def create_model_suggestions_keyboard(
    suggestions: List[str],
    mode: str = "unfound"
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с подсказками моделей оборудования
    
    Параметры:
        suggestions: Список моделей
        mode: Режим работы
        
    Возвращает:
        InlineKeyboardMarkup: Клавиатура с кнопками выбора модели
    """
    keyboard = []
    
    # Добавляем кнопки с моделями (по одной на строку)
    for idx, model in enumerate(suggestions):
        # Ограничиваем длину текста кнопки
        display_model = model if len(model) <= 40 else model[:37] + "..."
        keyboard.append([
            InlineKeyboardButton(
                display_model,
                callback_data=f"{mode}_model:{idx}"
            )
        ])
    
    # Добавляем кнопку "Ввести как есть"
    keyboard.append([
        InlineKeyboardButton(
            "✏️ Ввести как есть",
            callback_data=f"{mode}_model:manual"
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)
