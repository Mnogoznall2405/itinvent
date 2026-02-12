# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **IT-invent Bot** - a Python-based Telegram bot for IT equipment inventory management with automatic serial number recognition and PDF document generation. The bot helps track IT equipment, generate transfer acts, manage cartridge replacements, battery replacements, PC cleanings, and manage inventory across multiple databases.

**Version:** 2.2.0 (modular architecture with unified location handling)

## Common Development Commands

### Running the Bot
```bash
# Primary method - run from project root
python -m bot.main

# Alternative method
python bot/main.py
```

### Testing and Verification
```bash
# Quick import verification
python -c "from bot.config import config; print('OK')"
python -c "from bot.handlers import start; print('OK')"
python -c "from docx import Document; print('OK')"

# Test module imports
python -m py_compile bot/handlers/location.py
```

### Log Management
```bash
# View logs in real-time (PowerShell)
Get-Content bot.log -Wait -Tail 50

# View last 100 lines
Get-Content bot.log -Tail 100
```

## Project Architecture

### High-Level Structure

The project uses a **modular architecture** that separates concerns into distinct modules:

```
bot/                          # Main bot package
├── main.py                  # Entry point with handler registration
├── config.py                # Centralized configuration (dataclasses)
├── cache_manager.py         # User access caching
├── database_manager.py      # Database connection management
├── universal_database.py    # Universal DB interface
├── email_sender.py          # Email notifications
├── equipment_data_manager.py # Equipment data management
├── handlers/                # Command handlers
│   ├── location.py          # Universal location selection with pagination
│   ├── suggestions_handler.py # Smart suggestions for employees/models
│   ├── start.py             # /start, /help, /cancel
│   ├── search.py            # Equipment search
│   ├── employee.py          # Search by employee
│   ├── transfer.py          # Equipment transfer with PDF
│   ├── unfound.py           # Equipment not in DB
│   ├── work.py              # Maintenance works (cartridge, battery, PC cleaning)
│   ├── database.py          # Database management
│   ├── export.py            # Data export
│   └── act_email.py         # Email notifications
├── services/                # Business logic
│   ├── ocr_service.py       # OCR via OpenRouter API
│   ├── pdf_generator.py     # PDF act generation
│   ├── validation.py        # Input validation
│   ├── excel_service.py     # Excel export (unified)
│   ├── suggestions.py       # AI-powered suggestions
│   ├── cartridge_database.py # Cartridge inventory
│   └── printer_*_detector.py # Printer detection
└── utils/                   # Utilities
    ├── pagination.py        # PaginationHandler class (universal)
    ├── decorators.py        # @require_user_access, @log_execution_time, @handle_errors
    ├── keyboards.py         # Keyboard creation
    ├── formatters.py        # Message formatting
    └── maintenance.py       # Maintenance functions
```

### Key Architectural Patterns

#### 1. **Universal Pagination System** (`bot/utils/pagination.py`)
- `PaginationHandler` class for unified pagination across all modules
- Each mode has its own handler instance (unfound, transfer, work)
- `handle_navigation()` for prev/next navigation
- Used for: equipment search, employee lists, location selection

#### 2. **Universal Location Selection** (`bot/handlers/location.py`)
- Single source for location selection with pagination
- Supports multiple modes: `unfound`, `transfer`, `work`
- `show_location_buttons()` - shows all locations for a branch with pagination
- `handle_location_navigation_universal()` - handles navigation for all modes
- Import in other handlers: `from bot.handlers.location import show_location_buttons, handle_location_navigation_universal`

#### 3. **Suggestions Pattern** (`bot/handlers/suggestions_handler.py`)
- `show_employee_suggestions()` - employee name suggestions with filtering
- `show_location_suggestions()` - location suggestions (legacy, being replaced)
- `show_model_suggestions()` - model suggestions with database integration
- `handle_employee_suggestion_generic()` - universal employee selection handler
- Pattern: user types text → suggestions shown → user selects or types manually

#### 4. **Handler Registration** (`bot/main.py`)
- All handlers registered in `register_handlers()` function
- ConversationHandler states defined in `bot/config.py` (States class)
- CallbackQueryHandler patterns must match callback_data exactly
- **Important**: Navigation buttons like `mode_location_prev` need pattern `^mode_location` (without colon)

#### 5. **State Management**
- ConversationHandler states in `States` class (config.py)
- Temporary data stored in `context.user_data` during conversations
- Persistent storage in JSON files (data/ directory)
- Each feature has its own state keys (e.g., `work_branch`, `work_location`)

### Database Architecture

- **Multi-database support**: Can work with multiple SQL Server databases via ODBC
- **Database Manager** (`database_manager.py`): Handles switching between databases
- **Universal DB** (`universal_database.py`): Consistent interface across databases
- **JSON Data Storage**: For temporary data, user preferences, unfound equipment

## Key Features

1. **Equipment Search**: By serial number (text/photo OCR) or by employee
2. **OCR Integration**: OpenRouter API with multiple models for serial recognition
3. **PDF Document Generation**: Transfer acts using DOCX templates
4. **Multi-Database Management**: Switch between different inventory databases
5. **Export Functionality**: Excel/CSV export with email delivery
6. **Cartridge Management**: Track replacements with LLM component detection
7. **Battery Replacement**: Full UPS battery replacement cycle
8. **PC Cleaning**: Track computer cleanings with history
9. **Unfound Equipment**: Track equipment not in main database
10. **Work Management**: Register maintenance works

## Development Guidelines

### Adding New Location Selection

Use the universal location system from `bot/handlers/location.py`:

```python
from bot.handlers.location import show_location_buttons

# After branch selection, show locations
user_id = update.effective_user.id
context._user_id = user_id
await show_location_buttons(
    message=update.message,
    context=context,
    mode='your_mode',  # Add handler to location.py first
    branch=branch
)
```

To add a new mode to location handling:
1. Add `PaginationHandler` instance in `location.py`
2. Add to `_PAGINATION_HANDLERS` dictionary
3. Add to `_NAVIGATION_RETURN_STATES` dictionary
4. Update `show_location_buttons()` to handle the mode
5. Create callback handler with pattern `^your_mode_location`

### Adding New Handlers

1. Create file in `bot/handlers/`
2. Import utilities from `bot/utils/`
3. Add to `bot/handlers/__init__.py`
4. Register in `bot/main.py`'s `register_handlers()` function
5. Add conversation states to `bot/config.py`

### Error Handling

Use decorators from `bot/utils/decorators.py`:
- `@require_user_access` - checks user permissions
- `@log_execution_time` - logs function execution time
- `@handle_errors` - graceful error handling

### Callback Handler Patterns

**Critical**: Navigation button patterns must match callback_data exactly:
- Buttons: `mode_location_prev`, `mode_location_next` (no colon after prefix)
- Pattern: `^mode_location` (without colon requirement)
- Selection buttons: `mode_location:0`, `mode_location:manual` (colon present)

Example:
```python
# WRONG - won't catch navigation buttons
CallbackQueryHandler(handler, pattern="^mode_location:")

# CORRECT - catches all mode_location callbacks
CallbackQueryHandler(handler, pattern="^mode_location")
```

### Code Reuse Principles

- **DO**: Use existing universal functions from `location.py`, `pagination.py`, `suggestions_handler.py`
- **DON'T**: Duplicate pagination, navigation, or location selection code
- If you need similar functionality, extend the universal handlers

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
EMAIL_PASSWORD=your_email_password

# AI Models Configuration
OCR_MODEL=qwen/qwen3-vl-8b-instruct
CARTRIDGE_ANALYSIS_MODEL=anthropic/claude-3.5-sonnet
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

## File Structure Notes

- `data/` - JSON files for equipment data, transfers, user preferences
- `templates/` - DOCX templates for PDF document generation
- `transfer_acts/` - Generated PDF transfer acts
- `exports/` - Exported Excel/CSV files
- `documentation/` - Complete documentation (in Russian)
- `tests/` - Unit tests
- `backups/` - JSON file backups
- `archive/` - Archived files

## Recent Architecture Changes (v2.2.0)

- **Unified Location System**: Created `bot/handlers/location.py` for all location selection
- **Universal Pagination**: `PaginationHandler` class replaces ~200 lines of duplicate code
- **Work Management**: Added cartridge, battery, and PC cleaning tracking
- **Excel Service Unification**: Single `ExcelService` class for all export operations
- **Enhanced Detection**: LLM-powered printer component and color detection
