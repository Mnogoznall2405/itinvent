#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для управления данными о ненайденном оборудовании и перемещениях сотрудников.
Обрабатывает случаи, когда серийный номер не найден в базе данных,
и управляет данными о перемещениях техники между сотрудниками.
"""

import json
import csv
import os
import html
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EquipmentDataManager:
    """
    Класс для управления данными о ненайденном оборудовании и перемещениях.
    """
    
    def __init__(self, 
                 unfound_file: str = "data/unfound_equipment.json",
                 transfers_file: str = "data/equipment_transfers.json",
                 export_state_file: str = "data/export_state.json"):
        """
        Инициализация менеджера данных.
        
        Args:
            unfound_file: Путь к файлу с данными о ненайденном оборудовании
            transfers_file: Путь к файлу с данными о перемещениях
        """
        self.unfound_file = unfound_file
        self.transfers_file = transfers_file
        self.export_state_file = export_state_file
        
        # Создаем файлы, если они не существуют
        self._ensure_files_exist()
    
    def _ensure_files_exist(self):
        """Создает файлы данных, если они не существуют."""
        for file_path in [self.unfound_file, self.transfers_file]:
            if not os.path.exists(file_path):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
                logger.info(f"Создан файл: {file_path}")
        # Файл состояния экспорта
        if not os.path.exists(self.export_state_file):
            try:
                with open(self.export_state_file, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
                logger.info(f"Создан файл: {self.export_state_file}")
            except Exception as e:
                logger.error(f"Ошибка создания файла состояния экспорта {self.export_state_file}: {e}")
    
    def _load_data(self, file_path: str) -> List[Dict[str, Any]]:
        """Загружает данные из JSON файла."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка загрузки данных из {file_path}: {e}")
            return []
    
    def _save_data(self, file_path: str, data: List[Dict[str, Any]]):
        """Сохраняет данные в JSON файл."""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Данные сохранены в {file_path}")
        except Exception as e:
            logger.error(f"Ошибка сохранения данных в {file_path}: {e}")
            raise


    
    def validate_employee_name(self, name: str) -> bool:
        """
        Валидация ФИО сотрудника.
        
        Args:
            name: ФИО сотрудника
            
        Returns:
            bool: True если ФИО валидно
        """
        if not name or not isinstance(name, str):
            return False
        
        # Удаляем лишние пробелы
        name = name.strip()
        
        # Проверяем длину
        if len(name) < 2 or len(name) > 100:
            return False
        
        # Проверяем на опасные символы
        dangerous_chars = ['<', '>', '"', "'", '&', ';', '|', '`', '$']
        if any(char in name for char in dangerous_chars):
            return False
        
        # Проверяем на SQL ключевые слова
        sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'UNION', 'EXEC']
        name_upper = name.upper()
        if any(keyword in name_upper for keyword in sql_keywords):
            return False
        
        return True
    
    def validate_serial_number(self, serial: str) -> bool:
        """
        Валидация серийного номера.
        
        Args:
            serial: Серийный номер
            
        Returns:
            bool: True если серийный номер валиден
        """
        if not serial or not isinstance(serial, str):
            return False
        
        # Удаляем лишние пробелы
        serial = serial.strip()
        
        # Проверяем длину
        if len(serial) < 1 or len(serial) > 50:
            return False
        
        # Проверяем допустимые символы (буквы, цифры, дефис, подчеркивание, точка, пробел, двоеточие)
        import re
        if not re.match(r'^[a-zA-Z0-9_\-\. :]+$', serial):
            return False
        
        return True
    
    def validate_ip_address(self, ip: str) -> bool:
        """
        Валидация IP адреса.
        
        Args:
            ip: IP адрес
            
        Returns:
            bool: True если IP адрес валиден
        """
        if not ip or not isinstance(ip, str):
            return False
        
        ip = ip.strip()
        
        # Проверяем формат IPv4
        import re
        ipv4_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        if re.match(ipv4_pattern, ip):
            return True
        
        # Проверяем формат IPv6 (упрощенная проверка)
        ipv6_pattern = r'^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$'
        if re.match(ipv6_pattern, ip):
            return True
        
        return False
    
    def validate_inventory_number(self, inv_num: str) -> bool:
        """
        Валидация инвентарного номера.
        """
        if not inv_num or not isinstance(inv_num, str):
            return False
        inv_num = inv_num.strip()
        if len(inv_num) < 1 or len(inv_num) > 30:
            return False
        # Разрешаем буквы, цифры, дефис, подчёркивание, точку и ПРОБЕЛ
        import re
        if not re.match(r'^[a-zA-Z0-9._\- ]+$', inv_num):
            return False
        return True
    
    def extract_serial_value(self, serial_input: str) -> str:
        """
        Приводит сырой ввод к «чистому» серийному номеру:
        удаляет типовые префиксы (Serial Number, S/N, SN, Service Tag, Серийный номер и т.п.).
        """
        import re
        if not serial_input or not isinstance(serial_input, str):
            return ''
        s = serial_input.strip()
        prefix_re = re.compile(
            r'^\s*(?:serial\s*number|serial\s*no\.?|serial\s*#|s/?n|sn|service\s*tag|серийный\s*номер|серийный)\s*[:#\-]?\s*',
            re.IGNORECASE
        )
        s = prefix_re.sub('', s)
        return s.strip()
    
    def exists_unfound_serial(self, serial_number: str) -> bool:
        """
        Проверяет, существует ли запись с данным серийным номером в файле ненайденного оборудования.
        Использует очистку префиксов для корректного сравнения.
        """
        cleaned = self.extract_serial_value(serial_number)
        if not cleaned:
            return False
        data = self._load_data(self.unfound_file)
        for record in data:
            if record.get('serial_number') == cleaned:
                return True
        return False
    
    def add_unfound_equipment(self, 
                             serial_number: str, 
                             model_name: str, 
                             employee_name: str,
                             location: str = None,
                             equipment_type: str = None,
                             description: str = None,
                             inventory_number: str = None,
                             batch_number: str = None,
                             ip_address: str = None,
                             status: str = None,
                             branch: str = None,
                             company: str = None,
                             additional_data: Optional[Dict] = None) -> bool:
        """
        Добавляет запись о ненайденном оборудовании.
        
        Args:
            serial_number: Серийный номер
            model_name: Название модели
            employee_name: ФИО сотрудника

            location: Локация оборудования
            equipment_type: Тип оборудования
            description: Описание оборудования
            inventory_number: Инвентарный номер (не обязателен)
            ip_address: IP адрес
            status: Статус оборудования
            branch: Филиал
            company: Компания
            additional_data: Дополнительные данные
            
        Returns:
            bool: True если запись добавлена успешно
        """
        # Валидация входных данных
        cleaned_serial = self.extract_serial_value(serial_number)
        if not self.validate_serial_number(cleaned_serial):
            logger.error(f"Невалидный серийный номер: {serial_number}")
            return False
        
        if not self.validate_employee_name(employee_name):
            logger.error(f"Невалидное ФИО сотрудника: {employee_name}")
            return False
        
        if not model_name or len(model_name.strip()) == 0:
            logger.error("Название модели не может быть пустым")
            return False
        
        # Валидация IP адреса если указан
        if ip_address and not self.validate_ip_address(ip_address):
            logger.error(f"Невалидный IP адрес: {ip_address}")
            return False
        
        # Валидация инвентарного номера если указан
        if inventory_number and not self.validate_inventory_number(inventory_number):
            logger.error(f"Невалидный инвентарный номер: {inventory_number}")
            return False
        
        # Загружаем существующие данные
        data = self._load_data(self.unfound_file)
        
        # Проверяем, не существует ли уже такая запись
        for record in data:
            if record.get('serial_number') == cleaned_serial:
                logger.warning(f"Запись с серийным номером {cleaned_serial} уже существует")
                return False
        
        # Создаем новую запись (без brand_name)
        new_record = {
            'serial_number': cleaned_serial.strip(),
            'model_name': model_name.strip(),
            'employee_name': employee_name.strip(),
            'location': location.strip() if location else '',
            'equipment_type': equipment_type.strip() if equipment_type else '',
            'description': description.strip() if description else '',
            'inventory_number': inventory_number.strip() if inventory_number else '',
            'batch_number': batch_number.strip() if batch_number else '',
            'ip_address': ip_address.strip() if ip_address else '',
            'status': status.strip() if status else '',
            'branch': branch.strip() if branch else '',
            'company': (company.strip() if company else 'ООО "Запсибгазпром-Газификация"'),
            'timestamp': datetime.now().isoformat(),
            'additional_data': additional_data or {},
            'db_name': (additional_data or {}).get('db_name', '')
        }
        
        # Добавляем запись
        data.append(new_record)
        
        # Сохраняем данные
        self._save_data(self.unfound_file, data)
        
        logger.info(f"Добавлена запись о ненайденном оборудовании: {serial_number}")
        return True
    
    def add_equipment_transfer(self, 
                             serial_number: str, 
                             new_employee: str,
                             old_employee: Optional[str] = None,
                             additional_data: Optional[Dict] = None,
                             act_pdf_path: Optional[str] = None) -> bool:
        """
        Добавляет запись о перемещении оборудования.
        
        Args:
            serial_number: Серийный номер
            new_employee: ФИО нового сотрудника
            old_employee: ФИО предыдущего сотрудника
            additional_data: Дополнительные данные
            act_pdf_path: Путь к PDF-акту приема-передачи (опционально)
            
        Returns:
            bool: True если запись добавлена успешно
        """
        # Валидация входных данных
        cleaned_serial = self.extract_serial_value(serial_number)
        if not self.validate_serial_number(cleaned_serial):
            logger.error(f"Невалидный серийный номер: {serial_number}")
            return False
        
        if not self.validate_employee_name(new_employee):
            logger.error(f"Невалидное ФИО нового сотрудника: {new_employee}")
            return False
        
        if old_employee and not self.validate_employee_name(old_employee):
            logger.error(f"Невалидное ФИО предыдущего сотрудника: {old_employee}")
            return False
        
        # Загружаем существующие данные
        data = self._load_data(self.transfers_file)
        
        # Создаем новую запись
        new_record = {
            'serial_number': cleaned_serial.strip(),
            'new_employee': new_employee.strip(),
            'old_employee': old_employee.strip() if old_employee else None,
            'timestamp': datetime.now().isoformat(),
            'additional_data': additional_data or {},
            'db_name': (additional_data or {}).get('db_name', ''),
            'act_pdf_path': act_pdf_path if act_pdf_path else None
        }
        
        # Добавляем запись
        data.append(new_record)
        
        # Сохраняем данные
        self._save_data(self.transfers_file, data)
        
        logger.info(f"Добавлена запись о перемещении оборудования: {serial_number} -> {new_employee}" + 
                   (f" (акт: {act_pdf_path})" if act_pdf_path else ""))
        return True
    
    def get_unfound_equipment(self) -> List[Dict[str, Any]]:
        """Возвращает список ненайденного оборудования."""
        return self._load_data(self.unfound_file)
    
    def get_equipment_transfers(self) -> List[Dict[str, Any]]:
        """Возвращает список перемещений оборудования."""
        return self._load_data(self.transfers_file)
    
    def export_to_csv(self, output_dir: str = "exports", date_filter: str = None, db_filter: Optional[str] = None, only_new: bool = False) -> Dict[str, str]:
        """
        Экспортирует данные в CSV файлы.
        
        Args:
            output_dir: Директория для сохранения файлов
            date_filter: Фильтр по дате в формате YYYY-MM-DD (только для текущего дня)
            db_filter: Имя базы для фильтрации
            only_new: Экспортировать только новые записи (с момента последней выгрузки)
            
        Returns:
            Dict с путями к созданным файлам
        """
        # Создаем директорию, если она не существует
        os.makedirs(output_dir, exist_ok=True)
        
        # Формируем имя файла в формате "export_дата"
        current_date = datetime.now().strftime("%Y-%m-%d")
        files_created = {}
        
        # Экспорт ненайденного оборудования
        unfound_data = self.get_unfound_equipment()
        # Фильтр по дате
        if date_filter and unfound_data:
            unfound_data = [r for r in unfound_data 
                            if r.get('timestamp', '').startswith(date_filter)]
        # Фильтр по базе
        if db_filter:
            unfound_data = [r for r in unfound_data 
                            if r.get('db_name') == db_filter]
        # Экспорт только новых записей, если указано
        if only_new:
            last_ts = self._get_last_export_ts('unfound', db_filter)
            if last_ts:
                try:
                    from datetime import datetime as dt
                    last_dt = dt.fromisoformat(last_ts)
                    unfound_data = [r for r in unfound_data if r.get('timestamp') and dt.fromisoformat(r['timestamp']) > last_dt]
                except Exception:
                    # В случае ошибки парсинга даты не фильтруем
                    pass
        
        if unfound_data:
            suffix = f"_{db_filter}" if db_filter else ""
            # Используем формат Excel (.xls) - старый формат
            unfound_xls = os.path.join(output_dir, f"export_{current_date}_unfound{suffix}.xls")

            # Создаем заголовки и данные для Excel (без brand_name)
            headers = ['Компания', 'Тип', 'Модель', 'Описание', 'Серийный Номер', 'Инвентарный Номер', 'Сотрудник', 'IP Адрес', 'Статус', 'Местоположение', 'Филиал']
            rows = []
            for record in unfound_data:
                row_values = [
                    record.get('company', ''),
                    record.get('equipment_type', ''),
                    record.get('model_name', ''),
                    record.get('description', ''),
                    record.get('serial_number', ''),
                    record.get('inventory_number', ''),
                    record.get('employee_name', ''),
                    record.get('ip_address', ''),
                    record.get('status', ''),
                    record.get('location', ''),
                    record.get('branch', ''),
                ]
                rows.append(row_values)

            # Используем xlwt напрямую для создания файла формата Excel (.xls)
            try:
                import xlwt
                # Создаем книгу и лист
                workbook = xlwt.Workbook(encoding='utf-8')
                worksheet = workbook.add_sheet('Ненайденное оборудование')
                
                # Записываем заголовки
                for col, header in enumerate(headers):
                    worksheet.write(0, col, header)
                
                # Записываем данные
                for row, row_data in enumerate(rows, start=1):
                    for col, cell_data in enumerate(row_data):
                        worksheet.write(row, col, cell_data)
                
                # Сохраняем файл
                workbook.save(unfound_xls)
                
                # Фиксируем последнюю выгрузку
                try:
                    latest_ts = max((r.get('timestamp') or '') for r in unfound_data)
                    if latest_ts:
                        self._set_last_export_ts('unfound', db_filter, latest_ts)
                except Exception:
                    pass
                files_created['unfound'] = unfound_xls
            except ImportError:
                # Если xlwt не доступен, используем pandas с openpyxl для создания .xlsx файла
                try:
                    import pandas as pd
                    df = pd.DataFrame(rows, columns=headers)
                    # Создаем файл с расширением .xlsx
                    unfound_xlsx = os.path.join(output_dir, f"export_{current_date}_unfound{suffix}.xlsx")
                    df.to_excel(unfound_xlsx, index=False, engine='openpyxl')
                    
                    # Фиксируем последнюю выгрузку
                    try:
                        latest_ts = max((r.get('timestamp') or '') for r in unfound_data)
                        if latest_ts:
                            self._set_last_export_ts('unfound', db_filter, latest_ts)
                    except Exception:
                        pass
                    files_created['unfound'] = unfound_xlsx
                except ImportError:
                    # Если pandas не доступен, создаем CSV файл как запасной вариант
                    unfound_csv = os.path.join(output_dir, f"export_{current_date}_unfound{suffix}.csv")
                    import csv
                    with open(unfound_csv, 'w', newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f, delimiter=';')
                        writer.writerow(headers)
                        writer.writerows(rows)
                    
                    # Фиксируем последнюю выгрузку
                    try:
                        latest_ts = max((r.get('timestamp') or '') for r in unfound_data)
                        if latest_ts:
                            self._set_last_export_ts('unfound', db_filter, latest_ts)
                    except Exception:
                        pass
                    files_created['unfound'] = unfound_csv
        
        logger.info(f"Экспорт завершен. Созданы файлы: {files_created}")
        return files_created


    
    def export_transfers_to_text(self, output_dir: str = "exports", date_filter: str = None, db_filter: Optional[str] = None, only_new: bool = False) -> str:
        """
        Экспортирует данные о перемещениях в текстовый файл.
        
        Args:
            output_dir: Директория для сохранения файлов
            date_filter: Фильтр по дате в формате YYYY-MM-DD (только для текущего дня)
            db_filter: Имя базы для фильтрации
            only_new: Экспортировать только новые записи (с момента последней выгрузки)
            
        Returns:
            str: Путь к созданному файлу
        """
        # Создаем директорию, если она не существует
        os.makedirs(output_dir, exist_ok=True)
        
        # Загружаем данные о перемещениях
        transfers_data = self.get_equipment_transfers()
        
        # Фильтруем данные по дате, если указан фильтр
        if date_filter and transfers_data:
            transfers_data = [r for r in transfers_data if r.get('timestamp', '').startswith(date_filter)]
        # Фильтр по базе
        if db_filter:
            transfers_data = [r for r in transfers_data if r.get('db_name') == db_filter]
        # Экспорт только новых записей, если указано
        if only_new:
            last_ts = self._get_last_export_ts('transfers', db_filter)
            if last_ts:
                try:
                    from datetime import datetime as dt
                    last_dt = dt.fromisoformat(last_ts)
                    transfers_data = [r for r in transfers_data if r.get('timestamp') and dt.fromisoformat(r['timestamp']) > last_dt]
                except Exception:
                    # В случае ошибки парсинга даты не фильтруем
                    pass
        
        if not transfers_data:
            logger.warning("Нет данных о перемещениях для экспорта")
            return ""
        
        # Формируем имя файла
        current_date = datetime.now().strftime("%Y-%m-%d")
        suffix = f"_{db_filter}" if db_filter else ""
        output_file = os.path.join(output_dir, f"transfers_{current_date}{suffix}.txt")
        
        # Создаем текстовый файл
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("Отчет о перемещении оборудования\n")
            f.write("=" * 50 + "\n\n")
            for record in transfers_data:
                serial_number = record.get('serial_number', 'Неизвестно')
                new_employee = record.get('new_employee', 'Неизвестно')
                old_employee = record.get('old_employee', 'Неизвестно')
                timestamp = record.get('timestamp', '')
                formatted_date = timestamp
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00')) if timestamp else None
                    if dt:
                        formatted_date = dt.strftime("%d.%m.%Y %H:%M")
                except Exception:
                    pass
                f.write(f"Серийный номер: {serial_number}\n")
                f.write(f"Новый сотрудник: {new_employee}\n")
                f.write(f"Предыдущий сотрудник: {old_employee}\n")
                f.write(f"Дата: {formatted_date}\n")
                f.write("-" * 40 + "\n")
        
        # Фиксируем последнюю выгрузку
        try:
            latest_ts = max((r.get('timestamp') or '') for r in transfers_data)
            if latest_ts:
                self._set_last_export_ts('transfers', db_filter, latest_ts)
        except Exception:
            pass
        
        logger.info(f"Текстовый отчет о перемещениях создан: {output_file}")
        return output_file
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Возвращает статистику по данным.
        
        Returns:
            Dict со статистикой
        """
        unfound_data = self.get_unfound_equipment()
        transfers_data = self.get_equipment_transfers()
        
        return {
            'unfound_count': len(unfound_data),
            'transfers_count': len(transfers_data),
            'total_records': len(unfound_data) + len(transfers_data),
            'last_unfound': unfound_data[-1]['timestamp'] if unfound_data else None,
            'last_transfer': transfers_data[-1]['timestamp'] if transfers_data else None
        }
    def _load_export_state(self) -> Dict[str, Any]:
        """Загрузка состояния последней выгрузки из JSON."""
        try:
            with open(self.export_state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Если файл отсутствует или повреждён — возвращаем пустое состояние
            return {}

    def _save_export_state(self, state: Dict[str, Any]) -> None:
        """Сохранение состояния последней выгрузки в JSON."""
        try:
            with open(self.export_state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния экспорта: {e}")

    def _get_last_export_ts(self, data_type: str, db_name: Optional[str]) -> Optional[str]:
        """Вернуть ISO‑timestamp последней выгрузки для типа данных и базы."""
        state = self._load_export_state()
        bucket = state.get(data_type, {})
        key = db_name or '__all__'
        return bucket.get(key)

    def _set_last_export_ts(self, data_type: str, db_name: Optional[str], ts: str) -> None:
        """Записать ISO‑timestamp последней выгрузки для типа данных и базы."""
        state = self._load_export_state()
        bucket = state.get(data_type, {})
        key = db_name or '__all__'
        bucket[key] = ts
        state[data_type] = bucket
        self._save_export_state(state)

# Удобные функции для использования
def add_unfound_equipment_record(serial: str, model: str, employee: str, 
                               data_file: str = "data/unfound_equipment.json") -> bool:
    """
    Удобная функция для добавления записи о ненайденном оборудовании.
    
    Args:
        serial: Серийный номер
        model: Название модели
        employee: ФИО сотрудника
        data_file: Путь к файлу данных
        
    Returns:
        bool: True если запись добавлена успешно
    """
    manager = EquipmentDataManager(unfound_file=data_file)
    return manager.add_unfound_equipment(serial, model, employee)

def add_transfer_record(serial: str, new_employee: str, old_employee: str = None,
                       data_file: str = "data/equipment_transfers.json",
                       act_pdf_path: str = None) -> bool:
    """
    Удобная функция для добавления записи о перемещении.
    
    Args:
        serial: Серийный номер
        new_employee: ФИО нового сотрудника
        old_employee: ФИО предыдущего сотрудника
        data_file: Путь к файлу данных
        act_pdf_path: Путь к PDF-акту приема-передачи (опционально)
        
    Returns:
        bool: True если запись добавлена успешно
    """
    manager = EquipmentDataManager(transfers_file=data_file)
    return manager.add_equipment_transfer(serial, new_employee, old_employee, act_pdf_path=act_pdf_path)

# Пример использования
if __name__ == "__main__":
    # Создаем менеджер данных
    manager = EquipmentDataManager()
    
    # Пример добавления ненайденного оборудования
    success = manager.add_unfound_equipment(
        serial_number="ABC123",
        model_name="Laptop Dell Latitude",
        employee_name="Иванов Иван Иванович"
    )
    print(f"Добавление ненайденного оборудования: {success}")
    
    # Пример добавления перемещения
    success = manager.add_equipment_transfer(
        serial_number="XYZ789",
        new_employee="Петров Петр Петрович",
        old_employee="Сидоров Сидор Сидорович"
    )
    print(f"Добавление перемещения: {success}")
    
    # Получение статистики
    stats = manager.get_statistics()
    print(f"Статистика: {stats}")
    
    # Экспорт в CSV
    exported_files = manager.export_to_csv()
    print(f"Экспортированные файлы: {exported_files}")

