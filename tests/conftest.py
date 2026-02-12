#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Общие фикстуры для всех тестов IT-invent Bot
"""
import pytest
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock, MagicMock
import tempfile
import shutil

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_dir():
    """Временная директория для тестов"""
    temp = tempfile.mkdtemp()
    yield temp
    shutil.rmtree(temp, ignore_errors=True)


@pytest.fixture
def temp_json_file(temp_dir):
    """Временный JSON файл"""
    return Path(temp_dir) / "test_data.json"


@pytest.fixture
def mock_update():
    """Mock Telegram Update"""
    update = AsyncMock()
    update.effective_user = Mock()
    update.effective_user.id = 123456
    update.effective_user.username = "test_user"
    update.message = AsyncMock()
    update.message.photo = None
    update.message.text = ""
    update.message.reply_text = AsyncMock()
    update.callback_query = None
    return update


@pytest.fixture
def mock_context():
    """Mock Telegram Context"""
    context = AsyncMock()
    context.user_data = {}
    context._user_id = 123456
    context.bot = AsyncMock()
    context.bot.send_message = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    return update


@pytest.fixture
def mock_database():
    """Mock подключения к базе данных"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.__enter__ = Mock(return_value=mock_cursor)
    mock_conn.__exit__ = Mock(return_value=None)
    mock_conn.cursor.return_value = mock_conn
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    mock_cursor.execute.return_value = None
    return mock_conn, mock_cursor


@pytest.fixture
def sample_equipment():
    """Образец оборудования для тестов"""
    return {
        'ID': 123,
        'SERIAL_NO': 'PF12345',
        'HW_SERIAL_NO': '',
        'MODEL_NAME': 'Dell OptiPlex 7090',
        'BRANCH_NAME': 'Офис Москва',
        'LOCATION': 'Офис 301',
        'EMPLOYEE_NAME': 'Иванов И.И.',
        'DESCRIPTION': 'Test description',
        'CI_TYPE_ID': 1,
        'CI_STATUS_ID': 1
    }


@pytest.fixture
def sample_unfound_equipment():
    """Образец ненайденного оборудования"""
    return {
        'serial_no': 'UNKNOWN123',
        'employee_name': 'Тестовый Тест',
        'type_name': 'Компьютер',
        'model_name': 'Unknown Model',
        'description': 'Test',
        'inventory_number': 'INV001',
        'ip_address': '192.168.1.1',
        'location': 'Office',
        'status_name': 'В эксплуатации',
        'branch_name': 'Москва',
        'timestamp': '2024-01-01T12:00:00'
    }


# Патчи для общих зависимостей
@pytest.fixture(autouse=True)
def mock_config(monkeypatch):
    """Мок конфигурации для тестов"""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_key")
    monkeypatch.setenv("SQL_SERVER_HOST", "localhost")
    monkeypatch.setenv("SQL_SERVER_DATABASE", "test_db")
    monkeypatch.setenv("SQL_SERVER_USERNAME", "test_user")
    monkeypatch.setenv("SQL_SERVER_PASSWORD", "test_pass")
    monkeypatch.setenv("ALLOWED_USERS", "123456")


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Мок переменных окружения"""
    env_vars = {
        "TELEGRAM_BOT_TOKEN": "test_token",
        "OPENROUTER_API_KEY": "test_key",
        "SQL_SERVER_HOST": "localhost",
        "SQL_SERVER_DATABASE": "test_db",
        "SQL_SERVER_USERNAME": "test_user",
        "SQL_SERVER_PASSWORD": "test_pass",
        "ALLOWED_USERS": "123456"
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars
