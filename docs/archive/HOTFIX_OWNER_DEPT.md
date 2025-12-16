# Hotfix: Получение отдела сотрудника для актов

## Дата: 2025-10-21

## Проблема

При генерации актов приема-передачи колонка "Отдел" оставалась пустой, хотя должна была содержать отдел получателя оборудования.

## Причина

1. Функция `get_owner_dept()` не всегда находила сотрудника (проблемы с точным совпадением ФИО)
2. Fallback через `find_by_employee()` не работал, так как в результатах не было поля `OWNER_DEPT`

## Решение

### 1. Создана универсальная функция get_employee_department (bot/handlers/transfer.py)

**Добавлена многоуровневая стратегия поиска:**

```python
async def get_employee_department(update, context, employee_name):
    # 1. Точное совпадение
    new_employee_dept = db.get_owner_dept(employee_name, strict=True)
    
    # 2. Нечеткий поиск (если не нашли)
    if not new_employee_dept:
        new_employee_dept = db.get_owner_dept(employee_name, strict=False)
    
    # 3. Через оборудование сотрудника (если все еще не нашли)
    if not new_employee_dept:
        employees = db.find_by_employee(employee_name, strict=False)
        if employees and len(employees) > 0:
            new_employee_dept = employees[0].get('OWNER_DEPT', '')
```

**Функция вызывается в трех местах:**
1. При текстовом вводе ФИО (`transfer_new_employee_input`)
2. При выборе из подсказок (`handle_transfer_employee_suggestion` - callback)
3. При ручном вводе через "Ввести как есть" (`transfer_emp:manual` - callback)

### 2. Добавлено поле OWNER_DEPT в find_by_employee (universal_database.py)

**Было:**
```sql
SELECT DISTINCT
    i.ID,
    i.SERIAL_NO,
    ...
    o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
    COALESCE(b.BRANCH_NAME, 'Не указан') as DEPARTMENT,  -- Только филиал
    COALESCE(l.DESCR, 'Не указана') as LOCATION
FROM ITEMS i
...
```

**Стало:**
```sql
SELECT DISTINCT
    i.ID,
    i.SERIAL_NO,
    ...
    o.OWNER_DISPLAY_NAME as EMPLOYEE_NAME,
    COALESCE(o.OWNER_DEPT, '') as OWNER_DEPT,  -- ← Добавлено поле отдела
    COALESCE(b.BRANCH_NAME, 'Не указан') as DEPARTMENT,
    COALESCE(l.DESCR, 'Не указана') as LOCATION
FROM ITEMS i
...
```

### 3. Добавлено подробное логирование

```python
logger.info(f"Поиск отдела (strict=True) для '{new_employee}': {new_employee_dept}")
logger.info(f"Поиск отдела (strict=False) для '{new_employee}': {new_employee_dept}")
logger.info(f"Отдел найден через find_by_employee: {new_employee_dept}")
logger.info(f"Итоговый отдел для '{new_employee}': '{new_employee_dept}'")
```

## Тестирование

### Проверка логов

После создания акта проверьте логи:

```bash
type bot.log | findstr "Поиск отдела"
type bot.log | findstr "Итоговый отдел"
```

**Ожидаемый вывод:**
```
INFO - Поиск отдела (strict=True) для 'Иванов Иван Иванович': IT-отдел
INFO - Итоговый отдел для 'Иванов Иван Иванович': 'IT-отдел'
```

**Если отдел не найден:**
```
INFO - Поиск отдела (strict=True) для 'Иванов Иван Иванович': None
INFO - Поиск отдела (strict=False) для 'Иванов Иван Иванович': IT-отдел
INFO - Итоговый отдел для 'Иванов Иван Иванович': 'IT-отдел'
```

**Если отдел найден через оборудование:**
```
INFO - Поиск отдела (strict=True) для 'Иванов Иван Иванович': None
INFO - Поиск отдела (strict=False) для 'Иванов Иван Иванович': None
WARNING - Отдел не найден через get_owner_dept, пробуем find_by_employee
INFO - Отдел найден через find_by_employee: IT-отдел
INFO - Итоговый отдел для 'Иванов Иван Иванович': 'IT-отдел'
```

### Проверка в БД

Проверьте, есть ли у сотрудника отдел в таблице OWNERS:

```sql
SELECT 
    OWNER_DISPLAY_NAME,
    OWNER_DEPT
FROM OWNERS
WHERE OWNER_DISPLAY_NAME LIKE '%Иванов%'
```

### Проверка в акте

1. Создайте акт перемещения
2. Откройте PDF
3. Проверьте колонку "Отдел" в таблице
4. Убедитесь, что отдел заполнен

## Возможные проблемы

### Проблема: Отдел все еще пустой

**Причина 1:** У сотрудника нет отдела в БД

**Решение:** Проверьте в БД:
```sql
SELECT * FROM OWNERS WHERE OWNER_DISPLAY_NAME = 'Точное ФИО'
```

**Причина 2:** ФИО не совпадает с БД

**Решение:** Проверьте логи - там будет видно, какое ФИО ищется

**Причина 3:** У сотрудника нет оборудования

**Решение:** Fallback через `find_by_employee` не сработает. Нужно заполнить OWNER_DEPT в таблице OWNERS.

### Проблема: Ошибка в логах

**Ошибка:** `'OWNER_DEPT' not found in columns`

**Решение:** Обновите код `universal_database.py` - добавьте поле OWNER_DEPT в SELECT

## Файлы изменены

- ✅ `bot/handlers/transfer.py` - улучшена логика поиска отдела
- ✅ `universal_database.py` - добавлено поле OWNER_DEPT в find_by_employee

## Преимущества

✅ **Надежность** - три уровня поиска отдела  
✅ **Логирование** - видно, на каком этапе найден отдел  
✅ **Fallback** - если один способ не работает, пробуется другой  
✅ **Совместимость** - работает даже если OWNER_DEPT пустой  

## Связанные документы

- [PDF_ACT_IMPROVEMENTS.md](PDF_ACT_IMPROVEMENTS.md) - основные улучшения актов
- [SUMMARY_PDF_ACT_UPDATE.md](SUMMARY_PDF_ACT_UPDATE.md) - сводка изменений
- [CHANGELOG.md](CHANGELOG.md) - история изменений
