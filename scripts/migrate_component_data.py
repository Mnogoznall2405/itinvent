#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграционный скрипт для обновления JSON данных замены картриджей

Добавляет поддержку component_type и component_color поля,
оставляя обратную совместимость с существующими данными.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Добавляем корень проекта в Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def migrate_cartridge_replacements():
    """
    Мигрирует данные о заменах картриджей в новый формат
    """
    file_path = Path("data/cartridge_replacements.json")
    backup_path = Path("data/cartridge_replacements_backup.json")

    if not file_path.exists():
        print("❌ Файл cartridge_replacements.json не найден")
        return False

    print(f"📖 Читаю файл: {file_path}")

    # Создаем резервную копию
    if file_path.exists():
        import shutil
        shutil.copy2(file_path, backup_path)
        print(f"💾 Создана резервная копия: {backup_path}")

    try:
        # Загружаем существующие данные
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"📊 Найдено записей: {len(data)}")

        migrated_count = 0
        updated_count = 0

        for i, record in enumerate(data):
            # Пропускаем если уже мигрировано
            if 'component_type' in record:
                updated_count += 1
                continue

            # Добавляем component_type = 'cartridge' для существующих записей
            record['component_type'] = 'cartridge'

            # Переименовываем cartridge_color в component_color
            if 'cartridge_color' in record:
                cartridge_color = record['cartridge_color']
                record['component_color'] = cartridge_color
            else:
                record['component_color'] = ''  # Пустое значение если не было

            migrated_count += 1

        print(f"✅ Мигрировано записей: {migrated_count}")
        if updated_count > 0:
            print(f"ℹ️ Уже обновлено записей: {updated_count}")

        # Сохраняем обновленные данные
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"💾 Данные сохранены в: {file_path}")
        return True

    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")

        # Восстанавливаем из резервной копии при ошибке
        if backup_path.exists():
            shutil.copy2(backup_path, file_path)
            print(f"🔄 Восстановлено из резервной копии")

        return False


def validate_migration():
    """
    Проверяет результаты миграции
    """
    file_path = Path("data/cartridge_replacements.json")

    if not file_path.exists():
        print("❌ Файл не найден для валидации")
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        total_records = len(data)
        valid_records = 0
        cartridge_records = 0

        for record in data:
            if 'component_type' in record and 'component_color' in record:
                valid_records += 1

            if record.get('component_type') == 'cartridge':
                cartridge_records += 1

        print(f"📊 Валидация завершена:")
        print(f"   Всего записей: {total_records}")
        print(f"   Валидных записей: {valid_records}")
        print(f"   Записей с картриджами: {cartridge_records}")

        if valid_records == total_records:
            print("✅ Миграция прошла успешно!")
        else:
            print("⚠️ Некоторые записи могут быть не мигрированы")

    except Exception as e:
        print(f"❌ Ошибка валидации: {e}")


def main():
    """
    Главная функция миграции
    """
    print("🚀 Начинаю миграцию данных замены картриджей...")
    print("=" * 50)

    # Проверяем наличие файла
    file_path = Path("data/cartridge_replacements.json")
    if not file_path.exists():
        print("❌ Файл data/cartridge_replacements.json не найден")
        print("💡 Убедитесь что файл существует и содержит данные о заменах картриджей")
        return

    # Показываем статистику до миграции
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"📊 Текущее количество записей: {len(data)}")

        # Проверяем несколько примеров
        if data:
            sample = data[0]
            print(f"📋 Пример записи до миграции:")
            for key, value in sample.items():
                print(f"   {key}: {value}")
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")
        return

    print("\n" + "=" * 50)

    # Выполняем миграцию
    if migrate_cartridge_replacements():
        print("\n✅ Миграция успешно завершена!")
        print("\n" + "=" * 50)

        # Валидация результатов
        validate_migration()

        # Показываем пример после миграции
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if data:
                sample = data[0]
                print(f"\n📋 Пример записи после миграции:")
                for key, value in sample.items():
                    print(f"   {key}: {value}")
        except Exception as e:
            print(f"❌ Ошибка чтения файла после миграции: {e}")

        print(f"\n💡 Резервная копия сохранена в: data/cartridge_replacements_backup.json")
        print(f"🎯 Миграция добавлена поддержка component_type и component_color")
    else:
        print("\n❌ Миграция завершилась с ошибками")
        print("💡 Проверьте логи выше и повторите попытку")


if __name__ == "__main__":
    main()