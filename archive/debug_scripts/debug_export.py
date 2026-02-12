#!/usr/bin/env python3
import json
import sys
sys.path.append('.')
from bot.services.cartridge_database import cartridge_database

# Тестовая запись
item = {
    "branch": "г.Тюмень, Первомайская 19",
    "location": "19_105",
    "printer_model": "xerox versalink c7120",
    "component_type": "fuser",
    "component_color": "Универсальный",
    "cartridge_model": "",
    "detection_source": "unknown",
    "printer_is_color": True,
    "cartridge_color": "",
    "db_name": "ITINVENT",
    "timestamp": "2025-12-22T17:25:51.998273"
}

print("=== Анализ записи ===")
print(f"Printer: {item.get('printer_model')}")
print(f"Component type: {item.get('component_type')}")
print(f"Cartridge model: '{item.get('cartridge_model')}'")

# Шаг 1: Проверяем, есть ли сохраненная модель
print("\n=== Шаг 1: Проверка сохраненной модели ===")
if item.get('cartridge_model'):
    print("Найдена сохраненная модель:", item.get('cartridge_model'))
else:
    print("Сохраненная модель пустая, ищем в базе данных")

# Шаг 2: Ищем в базе данных
print("\n=== Шаг 2: Поиск в базе данных ===")
printer_model = item.get('printer_model', '')
component_type = item.get('component_type', '')

try:
    compatibility = cartridge_database.find_printer_compatibility(printer_model)

    if compatibility:
        print(f"Найдена совместимость для {printer_model}")
        print(f"Доступные компоненты: {compatibility.components}")
        print(f"Модели фьюзеров: {getattr(compatibility, 'fuser_models', 'N/A')}")

        # Шаг 3: Проверяем поле
        print("\n=== Шаг 3: Проверка поля fuser_models ===")
        fuser_models = compatibility.fuser_models
        print(f"compatibility.fuser_models = {fuser_models}")
        print(f"len(fuser_models) = {len(fuser_models) if fuser_models else 'None'}")

        if fuser_models and len(fuser_models) > 0:
            print(f"РЕЗУЛЬТАТ: {fuser_models[0]}")
        else:
            print("ОШИБКА: Модели фьюзеров не найдены!")

        # Проверяем все поля
        print("\n=== Все поля compatibility ===")
        for attr in ['fuser_models', 'photoconductor_models', 'waste_toner_models']:
            value = getattr(compatibility, attr, 'N/A')
            print(f"{attr}: {value}")

    else:
        print(f"ОШИБКА: Совместимость не найдена для {printer_model}")

except Exception as e:
    print(f"ИСКЛЮЧЕНИЕ: {e}")
    import traceback
    traceback.print_exc()

# Шаг 4: Проверяем размерность
print("\n=== Шаг 4: Проверка размерности ===")
try:
    from bot.services.cartridge_database import cartridge_database
    all_data = cartridge_database.cartridge_db

    # Ищем принтер в базе
    found = None
    for key, value in all_data.items():
        if 'c7120' in key.lower():
            found = (key, value)
            break

    if found:
        key, value = found
        print(f"Найден ключ: '{key}'")
        print(f"JSON данные:")
        if hasattr(value, '__dict__'):
            print(f"  fuser_models из dict: {value.__dict__.get('fuser_models', 'N/A')}")
        else:
            print(f"  Тип value: {type(value)}")
    else:
        print("Принтер не найден в базе")

except Exception as e:
    print(f"Ошибка: {e}")