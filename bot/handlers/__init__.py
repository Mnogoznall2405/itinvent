"""
Обработчики команд и событий для IT-invent Bot

Модули с обработчиками для различных функций бота.
"""

from .start import start, help_command, cancel, return_to_main_menu
from .search import ask_find_equipment, find_by_serial_input
from .employee import (
    ask_find_by_employee,
    find_by_employee_input,
    handle_employee_pagination
)
from .unfound import (
    start_unfound_equipment,
    unfound_employee_input,
    unfound_type_input,
    unfound_model_input,
    unfound_description_input,
    unfound_inventory_input,
    unfound_ip_input,
    unfound_location_input,
    unfound_status_input,
    unfound_branch_input,
    handle_unfound_confirmation,
    handle_skip_callback
)
from .transfer import (
    start_transfer,
    receive_transfer_photos,
    receive_new_employee,
    handle_transfer_confirmation
)
from .database import (
    show_database_menu,
    handle_database_callback,
    show_equipment_types_menu,
    handle_equipment_pagination
)
from .export import (
    show_export_menu,
    handle_export_type,
    handle_export_period,
    handle_export_database,
    handle_delivery,
    handle_email_input
)

__all__ = [
    # Start commands
    'start',
    'help_command',
    'cancel',
    'return_to_main_menu',
    # Search handlers
    'ask_find_equipment',
    'find_by_serial_input',
    # Employee handlers
    'ask_find_by_employee',
    'find_by_employee_input',
    'handle_employee_pagination',
    # Unfound equipment handlers
    'start_unfound_equipment',
    'unfound_employee_input',
    'unfound_type_input',
    'unfound_model_input',
    'unfound_description_input',
    'unfound_inventory_input',
    'unfound_ip_input',
    'unfound_location_input',
    'unfound_status_input',
    'unfound_branch_input',
    'handle_unfound_confirmation',
    'handle_skip_callback',
    # Transfer handlers
    'start_transfer',
    'receive_transfer_photos',
    'receive_new_employee',
    'handle_transfer_confirmation',
    # Database handlers
    'show_database_menu',
    'handle_database_callback',
    'show_equipment_types_menu',
    'handle_equipment_pagination',
    # Export handlers
    'show_export_menu',
    'handle_export_type',
    'handle_export_period',
    'handle_export_database',
    'handle_delivery',
    'handle_email_input',
]
