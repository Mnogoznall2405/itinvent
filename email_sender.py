import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Dict, Optional
import logging
from datetime import datetime
import mimetypes
import urllib.parse
import re

logger = logging.getLogger(__name__)

class EmailSender:
    def __init__(self, smtp_server: str = None, smtp_port: int = 587, 
                 email: str = None, password: str = None, use_auth: bool = None):
        """
        Инициализация отправителя электронной почты
        
        Args:
            smtp_server: SMTP сервер (например, smtp.gmail.com или локальный)
            smtp_port: Порт SMTP сервера
            email: Email отправителя
            password: Пароль или app password (не требуется для локальных серверов)
            use_auth: Использовать аутентификацию (автоопределение если None)
        """
        # Получаем настройки из переменных окружения или используем переданные
        self.smtp_server = smtp_server or os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', '587'))
        self.email = email or os.getenv('EMAIL_ADDRESS')
        self.password = password or os.getenv('EMAIL_PASSWORD')
        
        # Автоопределение необходимости аутентификации
        if use_auth is None:
            # Локальные IP адреса обычно не требуют аутентификации
            self.use_auth = not (self.smtp_server.startswith('10.') or 
                               self.smtp_server.startswith('192.168.') or 
                               self.smtp_server.startswith('172.') or
                               self.smtp_server == 'localhost' or
                               self.smtp_server == '127.0.0.1')
        else:
            self.use_auth = use_auth
        
        # Проверяем настройки
        if not self.smtp_server or not self.email:
            logger.warning("Не указаны обязательные настройки: SMTP сервер и email отправителя.")
        
        if self.use_auth and not self.password:
            logger.warning("Для аутентификации требуется пароль.")
    
    def send_csv_export(self, recipient_email, csv_files: Dict[str, str], 
                       subject: Optional[str] = None, body: Optional[str] = None) -> bool:
        """
        Отправка CSV файлов по электронной почте
        
        Args:
            recipient_email: Email получателя (str) или список получателей (List[str])
            csv_files: Словарь с типами файлов и путями к ним
            subject: Тема письма
            body: Текст письма
            
        Returns:
            bool: True если отправка успешна, False в противном случае
        """
        try:
            # Создаем сообщение
            msg = MIMEMultipart()
            msg['From'] = self.email
            
            # Обрабатываем получателей (один или несколько)
            if isinstance(recipient_email, list):
                recipients = recipient_email
                msg['To'] = ', '.join(recipients)
            else:
                recipients = [recipient_email]
                msg['To'] = recipient_email
            
            # Устанавливаем тему по умолчанию
            if not subject:
                timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
                subject = f"Экспорт данных оборудования - {timestamp}"
            msg['Subject'] = subject
            
            # Устанавливаем текст письма по умолчанию
            if not body:
                file_list = "\n".join([f"- {file_type}: {os.path.basename(file_path)}" 
                                      for file_type, file_path in csv_files.items()])
                body = f"""Добрый день!

Во вложении находятся экспортированные данные оборудования:

{file_list}

Дата экспорта: {datetime.now().strftime("%d.%m.%Y %H:%M")}

С уважением,
Система учета оборудования"""
            
            # Добавляем текст письма
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # Прикрепляем CSV файлы с корректным MIME, именем и кодировкой
            for file_type, file_path in csv_files.items():
                if os.path.exists(file_path):
                    filename = os.path.basename(file_path)
                    ascii_filename = re.sub(r'[^A-Za-z0-9_.-]', '_', filename)
                    ext = os.path.splitext(filename)[1].lower()
                    with open(file_path, 'rb') as attachment:
                        if ext == '.xls':
                            part = MIMEBase('application', 'vnd.ms-excel')
                            part.set_payload(attachment.read())
                            encoders.encode_base64(part)
                            part.add_header('Content-Type', f'application/vnd.ms-excel; name="{ascii_filename}"')
                        else:
                            part = MIMEBase('text', 'csv')
                            part.set_payload(attachment.read())
                            encoders.encode_base64(part)
                            part.add_header('Content-Type', f'text/csv; charset=windows-1251; name="{ascii_filename}"')
                    part.add_header('Content-Disposition', f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{urllib.parse.quote(filename)}')
                    msg.attach(part)
                    logger.info(f"Прикреплен файл: {filename}")
                else:
                    logger.warning(f"Файл не найден: {file_path}")
            
            # Отправляем письмо
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                if self.use_auth:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.email, self.password)
                    logger.info("Используется аутентификация SMTP")
                else:
                    logger.info("Отправка без аутентификации (локальный сервер)")
                server.sendmail(self.email, recipients, msg.as_string())
                
                if isinstance(recipient_email, list):
                    logger.info(f"Письмо успешно отправлено на {len(recipients)} получателей: {', '.join(recipients)}")
                else:
                    logger.info(f"Письмо успешно отправлено на {recipient_email}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при отправке письма: {str(e)}")
            return False

    def send_files(self, recipient_email, files: Dict[str, str], 
                    subject: Optional[str] = None, body: Optional[str] = None) -> bool:
        """
        Отправка произвольных файлов (PDF, DOCX, изображения и т.д.) по email.
        
        Args:
            recipient_email: Email получателя (str) или список (List[str])
            files: Словарь {"метка": "путь_к_файлу"}
            subject: Тема письма
            body: Текст письма
        Returns:
            bool: Результат отправки
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email

            if isinstance(recipient_email, list):
                recipients = recipient_email
                msg['To'] = ', '.join(recipients)
            else:
                recipients = [recipient_email]
                msg['To'] = recipient_email

            if not subject:
                timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
                subject = f"Файлы из системы учета оборудования - {timestamp}"
            msg['Subject'] = subject

            if not body:
                file_list = "\n".join([f"- {label}: {os.path.basename(path)}" for label, path in files.items()])
                body = f"""Добрый день!

Во вложении файлы:

{file_list}

Дата: {datetime.now().strftime("%d.%m.%Y %H:%M")}

С уважением,
Система учета оборудования"""

            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            for label, path in files.items():
                if not path or not os.path.exists(path):
                    logger.warning(f"Файл не найден и будет пропущен: {path}")
                    continue
                filename = os.path.basename(path)
                ascii_filename = re.sub(r'[^A-Za-z0-9_.-]', '_', filename)
                mime_type, _ = mimetypes.guess_type(path)
                if (mime_type == 'text/csv') or filename.lower().endswith('.csv'):
                    with open(path, 'rb') as f:
                        part = MIMEBase('text', 'csv')
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Type', f'text/csv; charset=windows-1251; name="{ascii_filename}"')
                elif filename.lower().endswith('.xls'):
                    with open(path, 'rb') as f:
                        part = MIMEBase('application', 'vnd.ms-excel')
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Type', f'application/vnd.ms-excel; name="{ascii_filename}"')
                elif mime_type and mime_type.startswith('text/'):
                    with open(path, 'r', encoding='utf-8', errors='replace') as f:
                        part = MIMEText(f.read(), _subtype=mime_type.split('/')[-1], _charset='utf-8')
                else:
                    main, sub = ('application', 'octet-stream') if not mime_type else mime_type.split('/', 1)
                    with open(path, 'rb') as f:
                        part = MIMEBase(main, sub)
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{urllib.parse.quote(filename)}')
                msg.attach(part)
                logger.info(f"Прикреплен файл: {filename}")

            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                if self.use_auth:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.email, self.password)
                    logger.info("Используется аутентификация SMTP")
                else:
                    logger.info("Отправка без аутентификации (локальный сервер)")
                server.sendmail(self.email, recipients, msg.as_string())
                logger.info("Письмо с файлами успешно отправлено")
            return True
        except Exception as e:
            logger.error(f"Ошибка при отправке письма с файлами: {e}")
            return False
    
    def test_connection(self) -> bool:
        """
        Тестирование подключения к SMTP серверу
        
        Returns:
            bool: True если подключение успешно
        """
        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            
            if self.use_auth:
                server.starttls()
                server.login(self.email, self.password)
                logger.info("Подключение к SMTP серверу с аутентификацией успешно")
            else:
                logger.info("Подключение к локальному SMTP серверу успешно")
            
            server.quit()
            return True
        except Exception as e:
            logger.error(f"Ошибка подключения к SMTP серверу: {str(e)}")
            return False

# Функция для быстрой отправки
def send_export_email(recipient, csv_files: Dict[str, str], 
                     subject: str = None, body: str = None) -> bool:
    """
    Быстрая отправка экспорта по email
    
    Args:
        recipient: Email получателя (str) или список получателей (List[str])
        csv_files: Словарь с CSV файлами
        subject: Тема письма
        body: Текст письма
        
    Returns:
        bool: Результат отправки
    """
    sender = EmailSender()
    return sender.send_csv_export(recipient, csv_files, subject, body)