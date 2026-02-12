#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис автоподсказок для сотрудников и моделей оборудования
"""
import logging
from typing import List
from bot.database_manager import database_manager

logger = logging.getLogger(__name__)


def get_employee_suggestions(query: str, user_id: int, limit: int = 8) -> List[str]:
    """
    Возвращает список уникальных ФИО по подстроке
    
    Сортировка: сначала имена, начинающиеся с подстроки, затем содержащие её
    Если по оборудованию ничего не найдено, выполняется fallback по таблице OWNERS
    
    Параметры:
        query: Подстрока для поиска
        user_id: ID пользователя для определения БД
        limit: Максимальное количество подсказок
        
    Возвращает:
        List[str]: Список ФИО сотрудников
    """
    logger.info(f"[SUGGESTIONS] Запрос подсказок для '{query}', user_id={user_id}, limit={limit}")
    
    try:
        user_db = database_manager.create_database_connection(user_id)
        if not user_db:
            logger.warning(f"[SUGGESTIONS] Не удалось создать подключение к БД для user_id={user_id}")
            return []
        
        results = user_db.find_by_employee(query)
        logger.info(f"[SUGGESTIONS] Найдено результатов из find_by_employee: {len(results) if results else 0}")
    except Exception as e:
        logger.error(f"[SUGGESTIONS] Ошибка получения подсказок сотрудников: {e}", exc_info=True)
        return []
    
    uniq = []
    seen = set()
    q = query.casefold()
    
    for item in results:
        name = (item.get('EMPLOYEE_NAME') or item.get('employee_name'))
        if not name or name == 'Не назначен':
            continue
        name = name.strip()
        if name and name not in seen:
            seen.add(name)
            uniq.append(name)
    
    # Fallback: если по оборудованию ничего не нашли, пробуем OWNERS
    if not uniq:
        logger.info(f"[SUGGESTIONS] Fallback на таблицу OWNERS для '{query}'")
        try:
            conn = user_db._get_connection()
            cursor = conn.cursor()
            param = f"%{query}%"
            cursor.execute(
                """
                SELECT DISTINCT o.OWNER_DISPLAY_NAME
                FROM OWNERS o
                WHERE o.OWNER_DISPLAY_NAME LIKE ?
                ORDER BY o.OWNER_DISPLAY_NAME
                """,
                (param,)
            )
            for row in cursor.fetchall():
                name = (row[0] or '').strip()
                if not name or name.lower() in {'не назначен', 'не указан', 'неизвестно'}:
                    continue
                if name not in seen:
                    seen.add(name)
                    uniq.append(name)
            logger.info(f"[SUGGESTIONS] Найдено из OWNERS: {len(uniq)} записей")
        except Exception as e:
            logger.error(f"[SUGGESTIONS] Ошибка получения подсказок из OWNERS: {e}", exc_info=True)
        finally:
            try:
                cursor.close()
            except Exception:
                pass
    
    # Сортировка: сначала начинающиеся с query, потом содержащие
    starts = [n for n in uniq if n.casefold().startswith(q)]
    contains = [n for n in uniq if not n.casefold().startswith(q) and q in n.casefold()]
    
    final_result = (starts + contains)[:limit]
    logger.info(f"[SUGGESTIONS] Возвращаем {len(final_result)} подсказок для '{query}'")
    
    return final_result


def get_model_suggestions(query: str, user_id: int, limit: int = 8, equipment_type: str = "all") -> List[str]:
    """
    Возвращает список уникальных моделей по подстроке с фильтрацией по типу оборудования

    Улучшенный поиск:
    - Разделяет запрос на слова и ищет по каждому
    - Приоритет моделям, содержащим все слова из запроса
    - Поддерживает поиск по части слова (минимум 2 символа)
    - Фильтрация по типу оборудования (принтеры, МФУ, или все)

    Параметры:
        query: Подстрока для поиска
        user_id: ID пользователя
        limit: Максимальное количество подсказок
        equipment_type: Тип оборудования ('printers', 'printers_mfu', или 'all')

    Возвращает:
        List[str]: Список моделей оборудования
    """
    logger.info(f"[SUGGESTIONS] Запрос подсказок моделей для '{query}', user_id={user_id}, type={equipment_type}")

    def is_printer_or_mfp(item: dict) -> bool:
        """Проверяет, является ли оборудование принтером или МФУ"""
        model = (item.get('model') or item.get('MODEL_NAME') or '').lower()
        equipment_type_name = (item.get('equipment_type_name') or item.get('EQUIPMENT_TYPE_NAME') or '').lower()
        serial_number = (item.get('serial_number') or item.get('SERIAL_NUMBER') or '').lower()
        inventory_number = (item.get('inventory_number') or item.get('INVENTORY_NUMBER') or '').lower()

        # Все поля для анализа
        all_fields = f"{model} {equipment_type_name} {serial_number} {inventory_number}"

        # Ключевые слова для принтеров и МФУ
        printer_keywords = [
            'printer', 'принтер', 'laserjet', 'laser', 'deskjet', 'officejet',
            'color laserjet', 'hp ', 'canon', 'xerox', 'brother', 'samsung',
            'kyocera', 'epson', 'ricoh', 'lexmark', 'panasonic', 'sharp',
            'mf', 'mfc', 'mfp', 'муфта', 'scan', 'copy', 'print',
            'versalink', 'workcentre', 'i-sensys', 'imageclass'
        ]

        mfp_keywords = [
            'mfp', 'mfc', 'муфта', 'multifunction', 'all-in-one', 'aio',
            'workcentre', 'imageclass', 'maxify'
        ]

        # Проверяем наличие ключевых слов
        is_printer_related = any(keyword in all_fields for keyword in printer_keywords)

        if equipment_type == 'printers':
            # Только принтеры (не МФУ)
            return is_printer_related and not any(keyword in all_fields for keyword in mfp_keywords)
        elif equipment_type == 'printers_mfu':
            # Принтеры и МФУ
            return is_printer_related
        else:
            # Все типы оборудования
            return True

    try:
        user_db = database_manager.create_database_connection(user_id)
        if not user_db:
            logger.warning(f"[SUGGESTIONS] Не удалось создать подключение к БД для user_id={user_id}")
            return []

        # Для коротких запросов (< 3 символов) используем стандартный поиск
        if len(query.strip()) < 3:
            logger.info(f"[SUGGESTIONS] Короткий запрос '{query}', используем стандартный поиск")
            results = user_db.search_equipment(query)
        else:
            # Для длинных запросов пробуем несколько стратегий поиска
            all_results = []

            # 1. Стандартный поиск по всему запросу
            standard_results = user_db.search_equipment(query)
            all_results.extend(standard_results)
            logger.info(f"[SUGGESTIONS] Стандартный поиск нашел {len(standard_results)} результатов")

            # 2. Поиск по отдельным словам из запроса
            query_words = [w.strip() for w in query.split() if len(w.strip()) >= 2]
            if len(query_words) > 1:
                logger.info(f"[SUGGESTIONS] Поиск по отдельным словам: {query_words}")
                for word in query_words:
                    word_results = user_db.search_equipment(word)
                    all_results.extend(word_results)
                    logger.info(f"[SUGGESTIONS] Поиск по слову '{word}' нашел {len(word_results)} результатов")

            results = all_results

    except Exception as e:
        logger.error(f"Ошибка получения подсказок моделей: {e}")
        return []

    # Фильтруем результаты по типу оборудования
    filtered_results = [item for item in results if is_printer_or_mfp(item)]
    logger.info(f"[SUGGESTIONS] После фильтрации ({equipment_type}): {len(filtered_results)} из {len(results)}")

    uniq = []
    seen = set()
    q = query.casefold()
    query_words = [w.strip() for w in q.split() if len(w.strip()) >= 2]

    for item in filtered_results:
        model = (item.get('model') or item.get('MODEL_NAME'))
        if not model or model == 'Не указана' or len(model.strip()) < 3:
            continue
        if model not in seen:
            seen.add(model)
            uniq.append(model)

    # Улучшенная сортировка с рейтингом релевантности
    def calculate_relevance(model_name):
        model_lower = model_name.casefold()
        score = 0

        # Максимальный балл если содержит весь запрос целиком
        if q in model_lower:
            score += 100
        elif model_lower.startswith(q):
            score += 90

        # Баллы за совпадение отдельных слов
        matched_words = sum(1 for word in query_words if word in model_lower)
        score += matched_words * 20

        # Дополнительные баллы за совпадение в начале слов модели
        model_words = model_lower.split()
        for query_word in query_words:
            for model_word in model_words:
                if model_word.startswith(query_word):
                    score += 10
                    break

        # Штраф за слишком длинные модели при коротком запросе
        if len(q) < 5 and len(model_name) > 30:
            score -= 5

        return score

    # Сортируем по релевантности
    scored_models = [(model, calculate_relevance(model)) for model in uniq]
    scored_models.sort(key=lambda x: x[1], reverse=True)

    # Возвращаем только названия моделей
    result = [model for model, score in scored_models if score > 0][:limit]

    logger.info(f"[SUGGESTIONS] Возвращаем {len(result)} подсказок моделей для '{query}'")
    return result



def get_location_suggestions(query: str, user_id: int, limit: int = 8, branch: str = None) -> List[str]:
    """
    Возвращает список уникальных локаций по подстроке с опциональной фильтрацией по филиалу

    Параметры:
        query: Подстрока для поиска
        user_id: ID пользователя
        limit: Максимальное количество подсказок
        branch: Филиал для фильтрации (опционально)

    Возвращает:
        List[str]: Список локаций
    """
    try:
        user_db = database_manager.create_database_connection(user_id)
        if not user_db:
            return []

        conn = user_db._get_connection()
        cursor = conn.cursor()
        param = f"%{query}%"

        # Получаем локации через таблицу LOCATIONS для получения читаемых названий
        try:
            if branch:
                # Фильтруем по филиалу через таблицу BRANCHES
                cursor.execute(
                    """
                    SELECT DISTINCT l.DESCR
                    FROM ITEMS i
                    JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
                    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
                    WHERE l.DESCR LIKE ? AND l.DESCR IS NOT NULL AND b.BRANCH_NAME = ?
                    ORDER BY l.DESCR
                    """,
                    (param, branch)
                )
            else:
                # Без фильтрации по филиалу
                cursor.execute(
                    """
                    SELECT DISTINCT l.DESCR
                    FROM LOCATIONS l
                    WHERE l.DESCR LIKE ?
                    ORDER BY l.DESCR
                    """,
                    (param,)
                )
            # Преобразуем в строку перед обработкой (DESCR может быть числом)
            locations = [str(row[0]).strip() for row in cursor.fetchall() if row[0] and str(row[0]).strip()]

        except Exception as e:
            logger.error(f"Ошибка при получении локаций: {e}")
            locations = []

        cursor.close()

        # Фильтруем и сортируем
        uniq = []
        seen = set()
        q = query.casefold()

        for loc in locations:
            if loc and loc not in seen:
                seen.add(loc)
                uniq.append(loc)

        starts = [l for l in uniq if l.casefold().startswith(q)]
        contains = [l for l in uniq if not l.casefold().startswith(q) and q in l.casefold()]

        return (starts + contains)[:limit]

    except Exception as e:
        logger.error(f"Ошибка получения подсказок локаций: {e}")
        return []


def get_branch_suggestions(user_id: int) -> List[str]:
    """
    Возвращает список всех филиалов

    Параметры:
        user_id: ID пользователя

    Возвращает:
        List[str]: Список филиалов
    """
    try:
        user_db = database_manager.create_database_connection(user_id)
        if not user_db:
            return []

        branches = user_db.get_branches()
        return [b.get('BRANCH_NAME', '') for b in branches if b.get('BRANCH_NAME')]

    except Exception as e:
        logger.error(f"Ошибка получения подсказок филиалов: {e}")
        return []


def get_locations_by_branch(user_id: int, branch: str) -> List[str]:
    """
    Возвращает список всех локаций для указанного филиала

    Параметры:
        user_id: ID пользователя
        branch: Название филиала

    Возвращает:
        List[str]: Список локаций
    """
    try:
        user_db = database_manager.create_database_connection(user_id)
        if not user_db:
            return []

        conn = user_db._get_connection()
        cursor = conn.cursor()

        # Получаем локации для конкретного филиала через таблицу LOCATIONS
        cursor.execute(
            """
            SELECT DISTINCT l.DESCR
            FROM ITEMS i
            JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
            LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
            WHERE i.LOC_NO IS NOT NULL AND i.LOC_NO != '' AND b.BRANCH_NAME = ?
                AND l.DESCR IS NOT NULL AND l.DESCR != ''
            ORDER BY l.DESCR
            """,
            (branch,)
        )

        # Преобразуем в строку перед обработкой (DESCR может быть числом)
        locations = [str(row[0]).strip() for row in cursor.fetchall() if row[0] and str(row[0]).strip()]
        cursor.close()

        logger.info(f"[SUGGESTIONS] Получено {len(locations)} локаций для филиала '{branch}'")
        return locations

    except Exception as e:
        logger.error(f"Ошибка получения локаций по филиалу: {e}", exc_info=True)
        return []



def get_equipment_type_suggestions(user_id: int, limit: int = 15) -> List[str]:
    """
    Возвращает список типов оборудования из базы данных
    
    Параметры:
        user_id: ID пользователя
        limit: Максимальное количество типов (по умолчанию 15)
        
    Возвращает:
        List[str]: Список типов оборудования
    """
    try:
        user_db = database_manager.create_database_connection(user_id)
        if not user_db:
            return []
        
        # Получаем все типы оборудования из БД
        all_types = user_db.get_equipment_types()
        
        # Возвращаем первые N типов
        return all_types[:limit] if all_types else []
        
    except Exception as e:
        logger.error(f"Ошибка получения типов оборудования: {e}")
        return []



def get_equipment_type_suggestions_by_query(query: str, user_id: int, limit: int = 8) -> List[str]:
    """
    Возвращает список типов оборудования по подстроке (как для моделей)
    
    Параметры:
        query: Подстрока для поиска
        user_id: ID пользователя
        limit: Максимальное количество подсказок
        
    Возвращает:
        List[str]: Список типов оборудования
    """
    try:
        user_db = database_manager.create_database_connection(user_id)
        if not user_db:
            return []
        
        # Получаем все типы оборудования из БД
        all_types = user_db.get_equipment_types()
        
        if not all_types:
            return []
        
        # Фильтруем и сортируем
        uniq = []
        seen = set()
        q = query.casefold()
        
        for eq_type in all_types:
            if eq_type and eq_type not in seen:
                seen.add(eq_type)
                uniq.append(eq_type)
        
        # Сортировка: сначала начинающиеся с query, потом содержащие
        starts = [t for t in uniq if t.casefold().startswith(q)]
        contains = [t for t in uniq if not t.casefold().startswith(q) and q in t.casefold()]
        
        return (starts + contains)[:limit]
        
    except Exception as e:
        logger.error(f"Ошибка получения подсказок типов оборудования по запросу: {e}")
        return []
