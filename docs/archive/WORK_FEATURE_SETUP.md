# Настройка функции "Работы"

## Что уже сделано:

✅ Создан модуль `bot/handlers/work.py`  
✅ Добавлены состояния в `bot/config.py`  
✅ Добавлена кнопка "🔧 Работы" в главное меню  
✅ Созданы JSON файлы для хранения данных:
- `cartridge_replacements.json` - замены картриджей
- `equipment_installations.json` - установки оборудования
✅ **Добавлено сохранение базы данных (db_name)** - см. [WORK_DB_FILTER_UPDATE.md](WORK_DB_FILTER_UPDATE.md)  
✅ **Добавлена фильтрация по БД при экспорте** - можно выбрать конкретную БД или все сразу

## Что нужно сделать:

### 1. Зарегистрировать обработчики в `bot/main.py`

Добавить импорты:
```python
from bot.handlers.work import (
    start_work,
    handle_work_type,
    work_branch_input,
    work_location_input,
    work_printer_model_input,
    work_equipment_type_input,
    work_equipment_model_input,
    handle_cartridge_color,
    handle_work_confirmation
)
```

Создать ConversationHandler:
```python
work_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^🔧 Работы$"), start_work)
    ],
    states={
        States.WORK_TYPE_SELECTION: [
            CallbackQueryHandler(handle_work_type, pattern="^work:")
        ],
        States.WORK_BRANCH_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, work_branch_input)
        ],
        States.WORK_LOCATION_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, work_location_input)
        ],
        States.WORK_PRINTER_MODEL_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, work_printer_model_input)
        ],
        States.WORK_CARTRIDGE_COLOR_SELECTION: [
            CallbackQueryHandler(handle_cartridge_color, pattern="^cartridge_color:")
        ],
        States.WORK_EQUIPMENT_TYPE_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, work_equipment_type_input)
        ],
        States.WORK_EQUIPMENT_MODEL_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, work_equipment_model_input)
        ],
        States.WORK_CONFIRMATION: [
            CallbackQueryHandler(handle_work_confirmation, pattern="^(confirm|cancel)_work$")
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    name="work_conversation",
    persistent=False
)
```

Зарегистрировать:
```python
application.add_handler(work_conv_handler)
```

### 2. Добавить функцию экспорта в Excel

Создать в `bot/handlers/export.py` функции:
- `export_cartridge_replacements()` - экспорт замен картриджей
- `export_equipment_installations()` - экспорт установок оборудования

### 3. Добавить подсказки для филиалов в работах

В `bot/handlers/suggestions_handler.py` добавить:
```python
async def show_branch_suggestions_for_work(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    branch: str,
    pending_key: str,
    suggestions_key: str
) -> bool:
    # Аналогично show_location_suggestions
    pass
```

### 4. Добавить обработчики для подсказок

Нужно добавить обработчики callback для:
- Выбор филиала из подсказок
- Выбор локации из подсказок
- Выбор модели принтера из подсказок
- Выбор типа оборудования из подсказок
- Выбор модели оборудования из подсказок

## Структура данных

### cartridge_replacements.json
```json
[
  {
    "branch": "Москва",
    "location": "Офис 301",
    "printer_model": "HP LaserJet Pro M404dn",
    "cartridge_color": "Черный",
    "timestamp": "2024-10-21T22:30:00"
  }
]
```

### equipment_installations.json
```json
[
  {
    "branch": "Москва",
    "location": "Офис 301",
    "equipment_type": "Монитор",
    "equipment_model": "Dell P2422H",
    "timestamp": "2024-10-21T22:30:00"
  }
]
```

## Тестирование

1. Запустить бота
2. Нажать "🔧 Работы"
3. Выбрать "🖨️ Замена картриджа"
4. Ввести филиал
5. Ввести локацию
6. Ввести модель принтера
7. Выбрать цвет картриджа
8. Подтвердить
9. Проверить `cartridge_replacements.json`

## Следующие шаги

После регистрации обработчиков нужно будет протестировать весь процесс и добавить функции экспорта в Excel.
