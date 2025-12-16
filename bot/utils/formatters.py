#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Форматирование сообщений для Telegram бота

Функции для форматирования данных в читаемый вид.
"""

import html
from typing import Dict, List, Any


def format_equipment_info(equipment: Dict[str, Any]) -> str:
    """
    Форматирует информацию об оборудовании для отображения
    
    Параметры:
        equipment: Словарь с данными об оборудовании
        
    Возвращает:
        str: Отформатированная строка с информацией
    """
    lines = []
    
    # Серийный номер
    serial = equipment.get('SERIAL_NO') or equipment.get('HW_SERIAL_NO') or equipment.get('serial_number')
    if serial:
        lines.append(f"🔢 <b>S/N:</b> {html.escape(str(serial))}")
    
    # Инвентарный номер
    inv_no = equipment.get('INV_NO') or equipment.get('inventory_number')
    if inv_no:
        lines.append(f"📋 <b>Инв.№:</b> {html.escape(str(inv_no))}")
    
    # Модель и производитель
    model = equipment.get('MODEL_NAME') or equipment.get('model_name')
    vendor = equipment.get('VENDOR_NAME') or equipment.get('vendor_name')
    if model:
        model_str = html.escape(str(model))
        if vendor:
            model_str += f" ({html.escape(str(vendor))})"
        lines.append(f"📱 <b>Модель:</b> {model_str}")
    
    # Тип оборудования
    eq_type = equipment.get('TYPE_NAME') or equipment.get('equipment_type')
    if eq_type:
        lines.append(f"🔧 <b>Тип:</b> {html.escape(str(eq_type))}")
    
    # Сотрудник
    employee = equipment.get('OWNER_DISPLAY_NAME') or equipment.get('EMPLOYEE_NAME') or equipment.get('employee_name')
    if employee:
        lines.append(f"👤 <b>Сотрудник:</b> {html.escape(str(employee))}")
    
    # Отдел
    department = equipment.get('OWNER_DEPT') or equipment.get('department')
    if department:
        lines.append(f"🏢 <b>Отдел:</b> {html.escape(str(department))}")
    
    # Филиал
    branch = equipment.get('BRANCH_NAME') or equipment.get('branch')
    if branch:
        lines.append(f"🏢 <b>Филиал:</b> {html.escape(str(branch))}")
    
    # Локация
    location = equipment.get('LOCATION') or equipment.get('location')
    if location:
        lines.append(f"📍 <b>Локация:</b> {html.escape(str(location))}")
    
    # IP адрес (для МФУ)
    ip_address = equipment.get('IP_ADDRESS') or equipment.get('ip_address')
    if ip_address:
        lines.append(f"🌐 <b>IP:</b> {html.escape(str(ip_address))}")
    
    # Статус
    status = equipment.get('STATUS') or equipment.get('status')
    if status:
        lines.append(f"📊 <b>Статус:</b> {html.escape(str(status))}")
    
    return "\n".join(lines) if lines else "Информация недоступна"


def format_employee_equipment_list(equipment_list: List[Dict[str, Any]], employee_name: str) -> str:
    """
    Форматирует список оборудования сотрудника
    
    Параметры:
        equipment_list: Список словарей с оборудованием
        employee_name: Имя сотрудника
        
    Возвращает:
        str: Отформатированная строка со списком
    """
    if not equipment_list:
        return f"У сотрудника <b>{html.escape(employee_name)}</b> не найдено оборудования."
    
    lines = [
        f"👤 <b>Сотрудник:</b> {html.escape(employee_name)}",
        f"📋 <b>Найдено единиц:</b> {len(equipment_list)}\n"
    ]
    
    for i, equipment in enumerate(equipment_list, 1):
        lines.append(f"<b>{i}.</b>")
        lines.append(format_equipment_info(equipment))
        lines.append("")  # Пустая строка между единицами
    
    return "\n".join(lines)


def format_database_statistics(stats: Dict[str, Any]) -> str:
    """
    Форматирует статистику базы данных
    
    Параметры:
        stats: Словарь со статистикой
        
    Возвращает:
        str: Отформатированная строка со статистикой
    """
    lines = []
    
    db_name = stats.get('display_name') or stats.get('name', 'Неизвестная БД')
    lines.append(f"🗄️ <b>{html.escape(db_name)}</b>")
    
    status = stats.get('status', 'Н/Д')
    lines.append(f"📊 <b>Статус:</b> {html.escape(status)}")
    
    total_items = stats.get('total_items', 'Н/Д')
    lines.append(f"📋 <b>Всего записей:</b> {total_items}")
    
    total_employees = stats.get('total_employees', 'Н/Д')
    lines.append(f"👥 <b>Всего сотрудников:</b> {total_employees}")
    
    # Типы оборудования
    equipment_types = stats.get('equipment_types', [])
    if equipment_types:
        lines.append("\n📱 <b>Топ-5 типов оборудования:</b>")
        for type_name, count in equipment_types[:5]:
            lines.append(f"• {html.escape(type_name)}: {count} шт.")
        if len(equipment_types) > 5:
            lines.append(f"... и еще {len(equipment_types) - 5} типов")
    
    return "\n".join(lines)


def escape_markdown(text: str) -> str:
    """
    Экранирует специальные символы для Markdown
    
    Параметры:
        text: Исходный текст
        
    Возвращает:
        str: Экранированный текст
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text
