# Миграция JSON файлов в папку data

## Дата: 2025-10-21

## Описание изменений

Все JSON файлы с данными перенесены из корня проекта в отдельную папку `data/` для лучшей организации структуры проекта.

## Что изменилось

### Структура папок

**Было:**
```
itinvent-bot/
├── bot/
├── docs/
├── unfound_equipment.json          ← В корне
├── equipment_transfers.json        ← В корне
├── cartridge_replacements.json     ← В корне
├── equipment_installations.json    ← В корне
├── export_state.json               ← В корне
├── user_db_selection.json          ← В корне
└── ...
```

**Стало:**
```
itinvent-bot/
├── bot/
├── data/                           ← Новая папка
│   ├── unfound_equipment.json
│   ├── equipment_transfers.json
│   ├── cartridge_replacements.json
│   ├── equipment_installations.json
│   ├── export_state.json
│   ├── user_db_selection.json
│   ├── .gitignore
│   └── README.md
├── docs/
└── ...
```

## Изменения в коде

### equipment_data_manager.py

**Было:**
```python
def __init__(self, 
             unfound_file: str = "unfound_equipment.json",
             transfers_file: str = "equipment_transfers.json",
             export_state_file: str = "export_state.json"):
```

**Стало:**
```python
def __init__(self, 
             unfound_file: str = "data/unfound_equipment.json",
             transfers_file: str = "data/equipment_transfers.json",
             export_state_file: str = "data/export_state.json"):
```

### database_manager.py

**Было:**
```python
self.user_selection_file = "user_db_selection.json"
```

**Стало:**
```python
self.user_selection_file = "data/user_db_selection.json"
```

### bot/handlers/work.py

**Было:**
```python
file_path = Path("cartridge_replacements.json")
file_path = Path("equipment_installations.json")
```

**Стало:**
```python
file_path = Path("data/cartridge_replacements.json")
file_path = Path("data/equipment_installations.json")
```

### bot/handlers/export.py

**Было:**
```python
file_path = Path("cartridge_replacements.json")
file_path = Path("equipment_installations.json")
```

**Стало:**
```python
file_path = Path("data/cartridge_replacements.json")
file_path = Path("data/equipment_installations.json")
```

## Новые файлы

### data/.gitignore
```gitignore
# Игнорируем все JSON файлы с данными
*.json

# Но оставляем примеры (если будут)
!*_example.json
!*_template.json
```

### data/README.md
Документация по структуре JSON файлов и работе с данными.

## Преимущества

✅ **Чистота корня проекта** - все данные в одной папке  
✅ **Легче управлять** - проще делать backup и restore  
✅ **Безопасность** - .gitignore в папке data предотвращает случайный коммит данных  
✅ **Масштабируемость** - легко добавлять новые типы данных  
✅ **Документация** - README.md прямо в папке с данными  

## Миграция существующих установок

Если у вас уже работает бот, выполните следующие шаги:

### Автоматическая миграция (рекомендуется)

```bash
# 1. Остановите бота

# 2. Создайте папку data
mkdir data

# 3. Переместите JSON файлы
# Windows
move unfound_equipment.json data\
move equipment_transfers.json data\
move cartridge_replacements.json data\
move equipment_installations.json data\
move export_state.json data\
move user_db_selection.json data\

# Linux/Mac
mv unfound_equipment.json data/
mv equipment_transfers.json data/
mv cartridge_replacements.json data/
mv equipment_installations.json data/
mv export_state.json data/
mv user_db_selection.json data/

# 4. Обновите код (git pull или скопируйте новые файлы)

# 5. Запустите бота
python -m bot.main
```

### Ручная миграция

Если автоматическая миграция не подходит:

1. Создайте папку `data/` в корне проекта
2. Скопируйте (не перемещайте) все JSON файлы в `data/`
3. Обновите код
4. Запустите бота и убедитесь, что всё работает
5. Удалите старые JSON файлы из корня

## Проверка после миграции

### 1. Проверьте структуру папок

```bash
# Windows
dir data

# Linux/Mac
ls -la data/
```

**Ожидаемый результат:**
```
data/
├── cartridge_replacements.json
├── equipment_installations.json
├── equipment_transfers.json
├── export_state.json
├── unfound_equipment.json
├── user_db_selection.json
├── .gitignore
└── README.md
```

### 2. Проверьте работу бота

1. Запустите бота
2. Выполните поиск оборудования
3. Зарегистрируйте работу (замена картриджа)
4. Проверьте, что данные сохраняются в `data/cartridge_replacements.json`

### 3. Проверьте логи

```bash
# Windows
type bot.log | findstr "data"

# Linux/Mac
grep "data" bot.log
```

Не должно быть ошибок типа "File not found".

## Откат изменений

Если что-то пошло не так:

```bash
# 1. Остановите бота

# 2. Переместите файлы обратно
# Windows
move data\*.json .

# Linux/Mac
mv data/*.json .

# 3. Откатите код на предыдущую версию

# 4. Запустите бота
```

## Резервное копирование

Теперь резервное копирование стало проще:

```bash
# Backup всех данных одной командой
# Windows
xcopy data backup\data_%date:~-4,4%%date:~-7,2%%date:~-10,2%\ /E /I

# Linux/Mac
cp -r data/ backup/data_$(date +%Y%m%d)/
```

## Восстановление

```bash
# Restore из backup
# Windows
xcopy backup\data_20251021\* data\ /E /Y

# Linux/Mac
cp -r backup/data_20251021/* data/
```

## Часто задаваемые вопросы

### Нужно ли переносить старые данные?

Да, если вы хотите сохранить историю. Если нет - бот создаст новые пустые файлы автоматически.

### Что если я забыл перенести файлы?

Бот создаст новые пустые файлы в `data/`. Старые данные останутся в корне и не будут использоваться.

### Можно ли изменить путь к папке data?

Да, но нужно будет изменить пути во всех файлах, где они используются. Не рекомендуется.

### Нужно ли добавлять data/ в .gitignore?

Нет, в самой папке `data/` есть свой `.gitignore`, который игнорирует JSON файлы.

## Связанные документы

- [data/README.md](../data/README.md) - Документация по структуре данных
- [CHANGELOG.md](CHANGELOG.md) - История изменений
- [README.md](../README.md) - Основная документация проекта

## Поддержка

При возникновении проблем с миграцией:
1. Проверьте логи бота (`bot.log`)
2. Убедитесь, что папка `data/` существует
3. Проверьте права доступа к папке
4. Обратитесь к администратору системы
