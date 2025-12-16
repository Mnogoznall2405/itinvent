# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **IT-invent Bot** - a Python-based Telegram bot for IT equipment inventory management with automatic serial number recognition and PDF document generation. The bot helps track IT equipment, generate transfer acts, and manage inventory across multiple databases.

**Version:** 2.0.1 (modular architecture)

## Common Development Commands

### Running the Bot
```bash
# Primary method - run from project root
python -m bot.main

# Alternative method
python bot/main.py

# Using batch scripts
start_bot.bat              # Interactive start with error handling
start_bot_minimized.bat    # Start minimized (Windows)
start_bot_hidden.vbs       # Start completely hidden (Windows)
```

### Testing and Development
```bash
# Test OCR functionality (compares 7 models, time-intensive)
test_ocr.bat

# View recent logs
view_logs.bat              # Shows last 50 lines of bot.log

# Quick installation verification
python -c "from docx import Document; print('OK')"
python -c "from bot.config import config; print('OK')"
```

### Log Management
```bash
# View logs in real-time
powershell Get-Content bot.log -Wait -Tail 50

# View last 100 lines
powershell Get-Content bot.log -Tail 100
```

## Project Architecture

### High-Level Structure

The project uses a **modular architecture** that separates concerns into distinct modules:

```
bot/                     # Main bot package
├── handlers/            # Command handlers (search, transfer, export, etc.)
├── services/           # Business logic (OCR, PDF generation, validation)
├── utils/              # Utilities (decorators, keyboards, formatters)
├── config.py           # Centralized configuration
└── main.py            # Entry point with handler registration
```

### Key Components

1. **Entry Point**: `bot/main.py` - Initializes bot, registers all handlers, manages logging with rotation
2. **Configuration**: `bot/config.py` - Uses dataclasses for structured config loaded from `.env`
3. **Database Layer**: `database_manager.py` + `universal_database.py` - Handles multiple database connections
4. **Handler System**: Each major feature has its own handler in `bot/handlers/`
5. **Services**: Business logic separated from handlers (OCR, PDF generation, etc.)

### Database Architecture

- **Multi-database support**: Can work with multiple SQL Server databases via ODBC
- **Database Manager**: Handles switching between databases, connection pooling
- **JSON Data Storage**: Uses JSON files for temporary data, user preferences, and unfound equipment

### State Management

- **ConversationHandlers**: Uses python-telegram-bot's conversation states extensively
- **User Context**: Stores temporary data in `context.user_data` during conversations
- **Persistent Storage**: JSON files for equipment lists, transfers, cartridge replacements

## Key Features

1. **Equipment Search**: Search by serial number (text/photo OCR) or by employee
2. **OCR Integration**: Uses OpenRouter API with multiple models for serial number recognition
3. **PDF Document Generation**: Creates transfer acts using DOCX templates converted to PDF
4. **Multi-Database Management**: Switch between different inventory databases
5. **Export Functionality**: Export data to Excel/CSV with email delivery
6. **Unfound Equipment**: Track equipment not in main database
7. **Work Management**: Track maintenance and installation work

## Development Guidelines

### Adding New Handlers

1. Create file in `bot/handlers/`
2. Import utilities from `bot/utils/`
3. Add to `bot/handlers/__init__.py`
4. Register in `bot/main.py`'s `register_handlers()` function
5. Add conversation states to `bot/config.py` if needed

### Configuration

All configuration is centralized in `bot/config.py` using dataclasses:
- Environment variables loaded from `.env` file
- Type validation on startup
- Separated into logical groups (telegram, api, database, etc.)

### Error Handling

- Uses decorators `@require_user_access` and `@log_execution_time` from `bot/utils/decorators.py`
- Logging with rotation (10MB, 5 backup files)
- Graceful error handling with user-friendly messages

### Database Operations

- Use `database_manager.py` for database connections
- Follow the `UniversalInventoryDB` pattern in `universal_database.py`
- Always validate database names and SQL parameters to prevent injection

## Environment Setup

### Required Environment Variables (.env)
```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token
OPENROUTER_API_KEY=your_openrouter_key
ALLOWED_GROUP_ID=your_group_id
ALLOWED_USERS=user_id1,user_id2

# Main Database
SQL_SERVER_HOST=your_server
SQL_SERVER_DATABASE=ITINVENT
SQL_SERVER_USERNAME=your_username
SQL_SERVER_PASSWORD=your_password

# Additional Databases (optional)
ITINVENT2_HOST=server2
ITINVENT2_DATABASE=ITINVENT2

# Optional: SMTP for email features
SMTP_SERVER=your_smtp_server
EMAIL_ADDRESS=bot@example.com
```

### Dependencies

Key dependencies (see `requirements.txt`):
- `python-telegram-bot[job-queue]==21.9` - Telegram Bot API
- `openai>=1.99.0` - OpenRouter API for OCR
- `python-docx>=0.8.11` - DOCX document creation
- `docx2pdf>=0.1.8` - PDF conversion
- `pyodbc>=4.0.0` - SQL Server connectivity
- `pandas>=2.0.0` - Data manipulation
- `openpyxl>=3.1.0` - Excel export

## Testing

- OCR testing: Use `test_ocr.py` for comprehensive OCR model comparison
- Function testing: Each handler can be tested individually via imports
- Bot testing: Use `start_bot.bat` for interactive testing
- Log monitoring: Use `view_logs.bat` to monitor bot activity

## File Structure Notes

- `data/` - JSON files for equipment data, transfers, user preferences
- `templates/` - DOCX templates for PDF document generation
- `transfer_acts/` - Generated PDF transfer acts
- `exports/` - Exported Excel/CSV files
- `docs/` - Comprehensive documentation (in Russian)
- `__pycache__/` - Python bytecode files (can be ignored)