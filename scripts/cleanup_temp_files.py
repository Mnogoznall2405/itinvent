#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для очистки временных файлов

Удаляет временные файлы, созданные при работе бота:
- temp_*.jpg (временные фото для OCR)
- Старые файлы актов перемещения (опционально)
- Временные файлы экспорта

Использование:
    python scripts/cleanup_temp_files.py
    python -m scripts.cleanup_temp_files --hours 24
"""

import os
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
PROJECT_ROOT = Path(__file__).parent.parent
TEMP_PATTERNS = [
    "temp_*.jpg",
    "temp_*.jpeg",
    "temp_*.png",
    "temp_battery_*.jpg",
    "temp_pc_cleaning_*.jpg",
    "temp_component_replacement_*.jpg",
    "temp_transfer_*.jpg",
]

# Директории для проверки
DIRECTORIES_TO_CHECK = [
    PROJECT_ROOT,  # Корень проекта
    PROJECT_ROOT / "transfer_acts",  # Акты перемещения
]


class TempFileCleanup:
    """Класс для очистки временных файлов"""

    def __init__(self, max_age_hours: int = 24, dry_run: bool = False):
        """
        Args:
            max_age_hours: Удалять файлы старше указанного количества часов
            dry_run: Если True, только показать что будет удалено, не удаляя
        """
        self.max_age_hours = max_age_hours
        self.dry_run = dry_run
        self.cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

    def find_temp_files(self) -> list[Path]:
        """Находит все временные файлы"""
        temp_files = []

        for directory in DIRECTORIES_TO_CHECK:
            if not directory.exists():
                continue

            for pattern in TEMP_PATTERNS:
                for file_path in directory.glob(pattern):
                    temp_files.append(file_path)

        return temp_files

    def should_delete_file(self, file_path: Path) -> tuple[bool, str]:
        """
        Проверяет, следует ли удалить файл

        Returns:
            tuple: (should_delete, reason)
        """
        if not file_path.exists():
            return False, "Файл не существует"

        if file_path.is_dir():
            return False, "Это директория"

        # Проверяем возраст файла
        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        if file_mtime < self.cutoff_time:
            age_hours = (datetime.now() - file_mtime).total_seconds() / 3600
            return True, f"Файл старше {age_hours:.1f} часов"

        return False, f"Файл слишком новый ({(datetime.now() - file_mtime).total_seconds() / 3600:.1f} часов)"

    def cleanup(self) -> dict:
        """
        Выполняет очистку временных файлов

        Returns:
            dict: Статистика очистки
        """
        temp_files = self.find_temp_files()
        stats = {
            "total_found": len(temp_files),
            "deleted": 0,
            "skipped": 0,
            "total_size_mb": 0,
            "deleted_files": [],
            "skipped_files": []
        }

        logger.info(f"Найдено временных файлов: {len(temp_files)}")

        for file_path in temp_files:
            should_delete, reason = self.should_delete_file(file_path)

            if should_delete:
                file_size = file_path.stat().st_size
                stats["total_size_mb"] += file_size / (1024 * 1024)
                stats["deleted_files"].append({
                    "path": str(file_path),
                    "size_mb": file_size / (1024 * 1024),
                    "reason": reason
                })

                if not self.dry_run:
                    try:
                        file_path.unlink()
                        stats["deleted"] += 1
                        logger.info(f"Удален: {file_path.name} ({reason})")
                    except Exception as e:
                        logger.error(f"Ошибка удаления {file_path}: {e}")
                        stats["skipped"] += 1
                else:
                    stats["deleted"] += 1
                    logger.info(f"[DRY RUN] Будет удален: {file_path.name} ({reason})")
            else:
                stats["skipped"] += 1
                stats["skipped_files"].append({
                    "path": str(file_path),
                    "reason": reason
                })
                logger.debug(f"Пропущен: {file_path.name} ({reason})")

        return stats


def cleanup_old_transfer_acts(days: int = 30, dry_run: bool = False) -> dict:
    """
    Очищает старые файлы актов перемещения

    Args:
        days: Удалять файлы старее указанного количества дней
        dry_run: Если True, только показать что будет удалено

    Returns:
        dict: Статистика очистки
    """
    transfer_dir = PROJECT_ROOT / "transfer_acts"
    if not transfer_dir.exists():
        return {"deleted": 0, "skipped": 0, "total_size_mb": 0}

    cutoff_time = datetime.now() - timedelta(days=days)
    stats = {"deleted": 0, "skipped": 0, "total_size_mb": 0, "deleted_files": []}

    for file_path in transfer_dir.glob("*.pdf"):
        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

        if file_mtime < cutoff_time:
            file_size = file_path.stat().st_size
            stats["total_size_mb"] += file_size / (1024 * 1024)
            stats["deleted_files"].append(str(file_path))

            if not dry_run:
                try:
                    file_path.unlink()
                    stats["deleted"] += 1
                    logger.info(f"Удален акт: {file_path.name}")
                except Exception as e:
                    logger.error(f"Ошибка удаления {file_path}: {e}")
            else:
                stats["deleted"] += 1
                logger.info(f"[DRY RUN] Будет удален акт: {file_path.name}")
        else:
            stats["skipped"] += 1

    return stats


def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(description="Очистка временных файлов IT-invent Bot")
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Удалять файлы старше указанного количества часов (по умолчанию: 24)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Удалять акты старше указанного количества дней (по умолчанию: 30)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать что будет удалено, не удаляя файлы"
    )
    parser.add_argument(
        "--include-acts",
        action="store_true",
        help="Включить акты перемещения в очистку"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Очистка временных файлов")
    logger.info(f"Максимальный возраст файлов: {args.hours} часов")
    logger.info(f"Режим: {'DRY RUN (без удаления)' if args.dry_run else 'УДАЛЕНИЕ'}")
    logger.info("=" * 60)

    # Очистка временных файлов
    cleaner = TempFileCleanup(max_age_hours=args.hours, dry_run=args.dry_run)
    stats = cleaner.cleanup()

    logger.info("-" * 60)
    logger.info("Статистика по временным файлам:")
    logger.info(f"  Найдено файлов: {stats['total_found']}")
    logger.info(f"  Удалено файлов: {stats['deleted']}")
    logger.info(f"  Пропущено файлов: {stats['skipped']}")
    logger.info(f"  Освобождено места: {stats['total_size_mb']:.2f} MB")

    # Очистка старых актов (если указано)
    if args.include_acts:
        logger.info("-" * 60)
        logger.info("Очистка старых актов перемещения:")
        acts_stats = cleanup_old_transfer_acts(days=args.days, dry_run=args.dry_run)
        logger.info(f"  Удалено актов: {acts_stats['deleted']}")
        logger.info(f"  Освобождено места: {acts_stats['total_size_mb']:.2f} MB")

    logger.info("=" * 60)
    logger.info("Очистка завершена")

    return 0


if __name__ == "__main__":
    exit(main())
