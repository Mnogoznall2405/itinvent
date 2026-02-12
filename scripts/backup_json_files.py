#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для создания резервных копий JSON файлов

Создаёт zip-архив с резервными копиями всех JSON файлов из папки data/
Имя архива содержит временную метку для идентификации

Использование:
    python scripts/backup_json_files.py
    python -m scripts.backup_json_files
"""

import os
import zipfile
import shutil
from pathlib import Path
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
BACKUP_DIR = PROJECT_ROOT / "backups" / "json"
MAX_BACKUPS = 30  # Хранить максимум 30 резервных копий

# JSON файлы для резервирования
JSON_FILES = [
    "unfound_equipment.json",
    "equipment_transfers.json",
    "cartridge_replacements.json",
    "battery_replacements.json",
    "pc_cleanings.json",
    "component_replacements.json",
    "user_db_selection.json",
    "export_state.json",
    "printer_color_cache.json",
    "printer_component_cache.json",
    "employee_suggestions_cache.json",
    "equipment_list_cache.json",
    "equipment_models_cache.json",
]


def create_backup() -> Path:
    """
    Создаёт резервную копию JSON файлов

    Returns:
        Path: Путь к созданному архиву
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"json_backup_{timestamp}.zip"
    backup_path = BACKUP_DIR / backup_filename

    # Создаём директорию для резервных копий
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Создаём zip-архив
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for json_file in JSON_FILES:
            source_path = DATA_DIR / json_file
            if source_path.exists():
                # Добавляем файл в архив с относительным путём
                arcname = f"data/{json_file}"
                zipf.write(source_path, arcname)
                logger.info(f"Добавлен в архив: {json_file}")
            else:
                logger.warning(f"Файл не найден: {json_file}")

    logger.info(f"Резервная копия создана: {backup_path}")
    return backup_path


def cleanup_old_backups():
    """
    Удаляет старые резервные копии, оставляя только MAX_BACKUPS последних
    """
    if not BACKUP_DIR.exists():
        return

    # Получаем все zip-архивы резервных копий
    backup_files = sorted(
        BACKUP_DIR.glob("json_backup_*.zip"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )

    # Удаляем старые копии
    files_to_delete = backup_files[MAX_BACKUPS:]
    for old_backup in files_to_delete:
        old_backup.unlink()
        logger.info(f"Удалена старая копия: {old_backup.name}")

    logger.info(f"Осталось резервных копий: {len(backup_files) - len(files_to_delete)}/{MAX_BACKUPS}")


def get_backup_info() -> dict:
    """
    Возвращает информацию о резервных копиях

    Returns:
        dict: Информация о резервных копиях
    """
    if not BACKUP_DIR.exists():
        return {"total": 0, "files": [], "total_size_mb": 0}

    backup_files = list(BACKUP_DIR.glob("json_backup_*.zip"))
    total_size = sum(f.stat().st_size for f in backup_files)

    return {
        "total": len(backup_files),
        "files": [
            {
                "name": f.name,
                "size_mb": f.stat().st_size / (1024 * 1024),
                "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            }
            for f in sorted(backup_files, key=lambda x: x.stat().st_mtime, reverse=True)
        ],
        "total_size_mb": total_size / (1024 * 1024),
        "backup_dir": str(BACKUP_DIR)
    }


def restore_backup(backup_path: Path):
    """
    Восстанавливает JSON файлы из резервной копии

    Args:
        backup_path: Путь к zip-архиву резервной копии
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"Резервная копия не найдена: {backup_path}")

    # Создаём временную директорию для распаковки
    temp_dir = PROJECT_ROOT / "temp_restore"
    temp_dir.mkdir(exist_ok=True)

    try:
        # Распаковываем архив
        with zipfile.ZipFile(backup_path, 'r') as zipf:
            zipf.extractall(temp_dir)

        # Копируем файлы из data/ в основную директорию
        restore_source = temp_dir / "data"
        if restore_source.exists():
            for json_file in restore_source.glob("*.json"):
                dest_path = DATA_DIR / json_file.name
                shutil.copy2(json_file, dest_path)
                logger.info(f"Восстановлен: {json_file.name}")

        logger.info(f"Восстановление завершено из: {backup_path}")

    finally:
        # Удаляем временную директорию
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    """Главная функция"""
    logger.info("=" * 60)
    logger.info("Создание резервной копии JSON файлов")
    logger.info("=" * 60)

    try:
        # Создаём резервную копию
        backup_path = create_backup()

        # Очищаем старые копии
        cleanup_old_backups()

        # Показываем информацию
        info = get_backup_info()
        logger.info(f"Всего резервных копий: {info['total']}")
        logger.info(f"Общий размер: {info['total_size_mb']:.2f} MB")

        logger.info("Резервное копирование завершено успешно")

    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
