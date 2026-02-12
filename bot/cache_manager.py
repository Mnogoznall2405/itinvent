#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль управления кэшем для Telegram-бота инвентаризации

Этот модуль предоставляет функциональность кэширования с TTL (Time To Live)
для оптимизации производительности бота и снижения нагрузки на базу данных
и внешние API.

Основные возможности:
- Кэш в памяти с автоматической очисткой устаревших записей
- Настраиваемое время жизни (TTL) для разных типов данных
- Потокобезопасность
- Статистика использования кэша
- Специализированные кэши для разных типов данных

Автор: AI Assistant
Версия: 1.0
"""

import time
import threading
from typing import Any, Optional, Dict, Callable
from functools import wraps
import logging

logger = logging.getLogger(__name__)

class TTLCache:
    """
    Кэш с поддержкой TTL (Time To Live) и автоматической очисткой.
    
    Потокобезопасный кэш, который автоматически удаляет устаревшие записи
    и предоставляет статистику использования.
    """
    
    def __init__(self, default_ttl: int = 300, max_size: int = 1000, cleanup_interval: int = 60):
        """
        Инициализация кэша.
        
        Параметры:
            default_ttl (int): Время жизни записей по умолчанию в секундах (300 = 5 минут)
            max_size (int): Максимальный размер кэша (1000 записей)
            cleanup_interval (int): Интервал очистки устаревших записей в секундах
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self.default_ttl = default_ttl
        self.max_size = max_size
        self.cleanup_interval = cleanup_interval
        
        # Статистика
        self._stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'cleanups': 0
        }
        
        # Запуск фонового потока очистки
        self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self._cleanup_thread.start()
    
    def get(self, key: str) -> Optional[Any]:
        """
        Получение значения из кэша.
        
        Параметры:
            key (str): Ключ для поиска
            
        Возвращает:
            Optional[Any]: Значение или None если ключ не найден или устарел
        """
        with self._lock:
            if key not in self._cache:
                self._stats['misses'] += 1
                return None
            
            entry = self._cache[key]
            current_time = time.time()
            
            # Проверяем, не устарела ли запись
            if current_time > entry['expires_at']:
                del self._cache[key]
                self._stats['misses'] += 1
                return None
            
            # Обновляем время последнего доступа
            entry['last_accessed'] = current_time
            self._stats['hits'] += 1
            return entry['value']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Сохранение значения в кэш.
        
        Параметры:
            key (str): Ключ для сохранения
            value (Any): Значение для сохранения
            ttl (Optional[int]): Время жизни в секундах (если None, используется default_ttl)
        """
        with self._lock:
            # Проверяем размер кэша и очищаем при необходимости
            if len(self._cache) >= self.max_size:
                self._evict_oldest()
            
            current_time = time.time()
            ttl = ttl or self.default_ttl
            
            self._cache[key] = {
                'value': value,
                'created_at': current_time,
                'last_accessed': current_time,
                'expires_at': current_time + ttl
            }
            
            self._stats['sets'] += 1
    
    def delete(self, key: str) -> bool:
        """
        Удаление записи из кэша.
        
        Параметры:
            key (str): Ключ для удаления
            
        Возвращает:
            bool: True если ключ был удален, False если не найден
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats['deletes'] += 1
                return True
            return False
    
    def clear(self) -> None:
        """
        Очистка всего кэша.
        """
        with self._lock:
            cleared_count = len(self._cache)
            self._cache.clear()
            self._stats['deletes'] += cleared_count
    
    def size(self) -> int:
        """
        Получение текущего размера кэша.
        
        Возвращает:
            int: Количество записей в кэше
        """
        with self._lock:
            return len(self._cache)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Получение статистики использования кэша.
        
        Возвращает:
            Dict[str, Any]: Словарь со статистикой
        """
        with self._lock:
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                **self._stats,
                'size': len(self._cache),
                'hit_rate': round(hit_rate, 2),
                'total_requests': total_requests
            }
    
    def _evict_oldest(self) -> None:
        """
        Удаление самой старой записи из кэша.
        """
        if not self._cache:
            return
        
        # Находим запись с самым старым временем последнего доступа
        oldest_key = min(self._cache.keys(), 
                        key=lambda k: self._cache[k]['last_accessed'])
        del self._cache[oldest_key]
        self._stats['deletes'] += 1
    
    def _cleanup_worker(self) -> None:
        """
        Фоновый поток для очистки устаревших записей.
        """
        while True:
            try:
                time.sleep(self.cleanup_interval)
                self._cleanup_expired()
            except Exception as e:
                logger.error(f"Ошибка в потоке очистки кэша: {e}")
    
    def _cleanup_expired(self) -> None:
        """
        Очистка устаревших записей.
        """
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, entry in self._cache.items()
                if current_time > entry['expires_at']
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                self._stats['cleanups'] += 1
                self._stats['deletes'] += len(expired_keys)
                logger.debug(f"Очищено {len(expired_keys)} устаревших записей из кэша")

def cache_result(cache_instance: TTLCache, ttl: Optional[int] = None, key_func: Optional[Callable] = None):
    """
    Декоратор для автоматического кэширования результатов функций.
    
    Параметры:
        cache_instance (TTLCache): Экземпляр кэша для использования
        ttl (Optional[int]): Время жизни кэша (если None, используется default_ttl кэша)
        key_func (Optional[Callable]): Функция для генерации ключа кэша
    
    Возвращает:
        Callable: Декорированная функция
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Генерируем ключ кэша
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Простая генерация ключа на основе имени функции и аргументов
                cache_key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Проверяем кэш
            cached_result = cache_instance.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Выполняем функцию и кэшируем результат
            result = func(*args, **kwargs)
            cache_instance.set(cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator

# Создание специализированных экземпляров кэша

# Кэш для проверки доступа пользователей (TTL: 1 час)
user_access_cache = TTLCache(
    default_ttl=3600,  # 1 час
    max_size=500,     # Максимум 500 пользователей
    cleanup_interval=60  # Очистка каждую минуту
)

# Кэш для данных об оборудовании (TTL: 2 минуты)
equipment_cache = TTLCache(
    default_ttl=120,  # 2 минуты
    max_size=1000,    # Максимум 1000 записей об оборудовании
    cleanup_interval=30  # Очистка каждые 30 секунд
)

# Кэш для результатов анализа изображений (TTL: 10 минут)
image_analysis_cache = TTLCache(
    default_ttl=600,  # 10 минут
    max_size=200,     # Максимум 200 анализов изображений
    cleanup_interval=120  # Очистка каждые 2 минуты
)

def get_cache_stats() -> Dict[str, Dict[str, Any]]:
    """
    Получение статистики всех кэшей.
    
    Возвращает:
        Dict[str, Dict[str, Any]]: Статистика всех кэшей
    """
    return {
        'user_access': user_access_cache.get_stats(),
        'equipment': equipment_cache.get_stats(),
        'image_analysis': image_analysis_cache.get_stats()
    }

def clear_all_caches() -> None:
    """
    Очистка всех кэшей.
    """
    user_access_cache.clear()
    equipment_cache.clear()
    image_analysis_cache.clear()
    logger.info("Все кэши очищены")

if __name__ == "__main__":
    # Пример использования
    cache = TTLCache(default_ttl=60, max_size=100)
    
    # Тестирование базовых операций
    cache.set("test_key", "test_value")
    print(f"Значение: {cache.get('test_key')}")
    print(f"Статистика: {cache.get_stats()}")
    
    # Тестирование декоратора
    @cache_result(cache, ttl=30)
    def expensive_function(x, y):
        time.sleep(1)  # Имитация долгой операции
        return x + y
    
    start_time = time.time()
    result1 = expensive_function(1, 2)
    print(f"Первый вызов: {result1}, время: {time.time() - start_time:.2f}с")
    
    start_time = time.time()
    result2 = expensive_function(1, 2)  # Должен быть из кэша
    print(f"Второй вызов: {result2}, время: {time.time() - start_time:.2f}с")