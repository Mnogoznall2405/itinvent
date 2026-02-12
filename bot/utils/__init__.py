"""
Утилиты для IT-invent Bot

Вспомогательные функции, декораторы и инструменты.
"""

from .decorators import require_user_access, log_execution_time, handle_errors
from .keyboards import (
    create_main_menu_keyboard,
    create_pagination_keyboard,
    create_confirmation_keyboard,
    create_back_button,
    create_cancel_button
)
from .formatters import (
    format_equipment_info,
    format_employee_equipment_list,
    format_database_statistics
)
from .pagination import (
    paginate_results,
    get_page_items,
    calculate_total_pages,
    PaginationHandler,
    create_pagination_handler
)
from .maintenance import (
    cleanup_temp_files_on_startup,
    cleanup_old_temp_files,
    create_json_backup,
    start_maintenance,
    stop_maintenance,
    MaintenanceScheduler
)

__all__ = [
    # Decorators
    'require_user_access',
    'log_execution_time',
    'handle_errors',
    # Keyboards
    'create_main_menu_keyboard',
    'create_pagination_keyboard',
    'create_confirmation_keyboard',
    'create_back_button',
    'create_cancel_button',
    # Formatters
    'format_equipment_info',
    'format_employee_equipment_list',
    'format_database_statistics',
    # Pagination
    'paginate_results',
    'get_page_items',
    'calculate_total_pages',
    'PaginationHandler',
    'create_pagination_handler',
    # Maintenance
    'cleanup_temp_files_on_startup',
    'cleanup_old_temp_files',
    'create_json_backup',
    'start_maintenance',
    'stop_maintenance',
    'MaintenanceScheduler',
]
