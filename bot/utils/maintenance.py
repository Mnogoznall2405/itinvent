#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилиты для обслуживания бота

Очистка временных файлов, резервное копирование и другие задачи обслуживания
"""

import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
import threading
import time

logger = logging.getLogger(__name__)

# Корневая директория проекта
PROJECT_ROOT = Path(__file__).parent.parent.parent


def cleanup_temp_files_on_startup():
    """
    Выполняет быструю очистку временных файлов при запуске бота

    Удаляет временные файлы старше 1 часа для быстрой очистки
    """
    temp_patterns = [
        "temp_*.jpg",
        "temp_*.jpeg",
        "temp_*.png",
        "temp_battery_*.jpg",
        "temp_pc_cleaning_*.jpg",
        "temp_component_replacement_*.jpg",
        "temp_transfer_*.jpg",
    ]

    cutoff_time = datetime.now() - timedelta(hours=1)
    deleted_count = 0
    total_size = 0

    try:
        for pattern in temp_patterns:
            for file_path in PROJECT_ROOT.glob(pattern):
                if file_path.is_file():
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

                    if file_mtime < cutoff_time:
                        try:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            deleted_count += 1
                            total_size += file_size
                            logger.debug(f"Удален временный файл: {file_path.name}")
                        except Exception as e:
                            logger.warning(f"Не удалось удалить {file_path}: {e}")

        if deleted_count > 0:
            logger.info(f"Очистка временных файлов: удалено {deleted_count} файлов, освобождено {total_size / (1024*1024):.2f} MB")
        else:
            logger.debug("Временные файлы не требуют очистки")

    except Exception as e:
        logger.error(f"Ошибка при очистке временных файлов: {e}")


def cleanup_old_temp_files(hours: int = 24):
    """
    Полная очистка старых временных файлов

    Args:
        hours: Удалять файлы старше указанного количества часов
    """
    from scripts.cleanup_temp_files import TempFileCleanup

    try:
        cleaner = TempFileCleanup(max_age_hours=hours, dry_run=False)
        stats = cleaner.cleanup()

        if stats['deleted'] > 0:
            logger.info(
                f"Очистка старых временных файлов: удалено {stats['deleted']} файлов, "
                f"освобождено {stats['total_size_mb']:.2f} MB"
            )
        else:
            logger.debug("Старые временные файлы не найдены")

    except Exception as e:
        logger.error(f"Ошибка при очистке старых файлов: {e}")


def create_json_backup():
    """
    Создаёт резервную копию JSON файлов
    """
    from scripts.backup_json_files import create_backup, cleanup_old_backups

    try:
        backup_path = create_backup()
        cleanup_old_backups()
        logger.info(f"Создана резервная копия: {backup_path.name}")
    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии: {e}")


class MaintenanceScheduler:
    """
    Планировщик задач обслуживания

    Запускает задачи резервного копирования и очистки по расписанию
    """

    def __init__(self):
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()

        # Интервалы в секундах
        self.backup_interval = 6 * 3600  # Каждые 6 часов
        self.cleanup_interval = 2 * 3600  # Каждые 2 часа

    def _maintenance_loop(self):
        """Основной цикл планировщика"""
        logger.info("Планировщик обслуживания запущен")

        last_backup = time.time()
        last_cleanup = time.time()

        while not self._stop_event.is_set():
            try:
                current_time = time.time()

                # Резервное копирование
                if current_time - last_backup >= self.backup_interval:
                    create_json_backup()
                    last_backup = current_time

                # Очистка
                if current_time - last_cleanup >= self.cleanup_interval:
                    cleanup_old_temp_files(hours=24)
                    last_cleanup = current_time

                # Спим между проверками
                self._stop_event.wait(60)  # Проверка каждую минуту

            except Exception as e:
                logger.error(f"Ошибка в планировщике обслуживания: {e}")

        logger.info("Планировщик обслуживания остановлен")

    def start(self):
        """Запускает планировщик в отдельном потоке"""
        if self._running:
            logger.warning("Планировщик уже запущен")
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self._thread.start()
        logger.info("Планировщик обслуживания запущен в фоновом режиме")

    def stop(self):
        """Останавливает планировщик"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=5)

        logger.info("Планировщик обслуживания остановлен")


# Глобальный экземпляр планировщика
_maintenance_scheduler = None


def start_maintenance():
    """
    Запускает фоновые задачи обслуживания

    Выполняет быструю очистку при запуске и запускает планировщик
    """
    global _maintenance_scheduler

    # Быстрая очистка при запуске
    cleanup_temp_files_on_startup()

    # Запуск планировщика
    _maintenance_scheduler = MaintenanceScheduler()
    _maintenance_scheduler.start()

    logger.info("Задачи обслуживания запущены")


def stop_maintenance():
    """Останавливает задачи обслуживания"""
    global _maintenance_scheduler

    if _maintenance_scheduler:
        _maintenance_scheduler.stop()
        _maintenance_scheduler = None
