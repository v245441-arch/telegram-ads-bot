#!/usr/bin/env python3
"""
Тест для проверки функционала поддержки.
Запуск: python test_support.py
"""

import asyncio
import os
import sys
import sqlite3
from unittest.mock import patch, MagicMock

# Добавляем путь к боту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Импортируем функции из bot.py
from bot import (
    process_support_message,
    admin_reply_finish,
    cmd_cancel,
    Support,
    get_main_keyboard
)

# Мокаем бота
mock_bot = MagicMock()

# Тестовые данные
TEST_USER_ID = 123456789
TEST_ADMIN_ID = 987654321
TEST_USERNAME = "testuser"
TEST_MESSAGE_TEXT = "Помогите, у меня проблема с объявлением!"
TEST_REPLY_TEXT = "Спасибо за обращение! Мы поможем вам."

class MockMessage:
    def __init__(self, text, user_id=None, username=None):
        self.text = text
        self.from_user = MagicMock()
        self.from_user.id = user_id or TEST_USER_ID
        self.from_user.username = username or TEST_USERNAME

class MockCallbackQuery:
    def __init__(self, data, user_id=None):
        self.data = data
        self.from_user = MagicMock()
        self.from_user.id = user_id or TEST_ADMIN_ID
        self.message = MagicMock()
        self.message.edit_reply_markup = MagicMock()
        self.message.answer = MagicMock()
        self.answer = MagicMock()

class MockState:
    def __init__(self):
        self.data = {}
        self.current_state = None
    
    async def get_state(self):
        return self.current_state
    
    async def set_state(self, state):
        self.current_state = state
    
    async def update_data(self, **kwargs):
        self.data.update(kwargs)
    
    async def get_data(self):
        return self.data
    
    async def clear(self):
        self.data = {}
        self.current_state = None

async def test_support_flow():
    """Тестируем полный цикл поддержки: сообщение -> ответ админа."""
    print("🧪 Тестируем функционал поддержки...")
    
    # Инициализируем БД
    from bot import init_db
    init_db()
    
    # 1. Пользователь отправляет сообщение в поддержку
    print("1. Пользователь отправляет сообщение в поддержку...")
    message = MockMessage(TEST_MESSAGE_TEXT)
    state = MockState()
    state.current_state = Support.waiting_for_message
    
    # Мокаем bot.send_message для проверки отправки админу
    with patch('bot.bot', mock_bot):
        await process_support_message(message, state)
    
    # Проверяем, что сообщение отправлено админу
    mock_bot.send_message.assert_called_once()
    call_args = mock_bot.send_message.call_args
    assert call_args[1]['chat_id'] == TEST_ADMIN_ID
    assert TEST_MESSAGE_TEXT in call_args[1]['text']
    assert '✏️ Ответить' in str(call_args[1]['reply_markup'])
    
    # Проверяем, что пользователю отправлено подтверждение
    message.answer.assert_called_once_with(
        "✅ Ваше сообщение отправлено администратору. Ожидайте ответа.",
        reply_markup=get_main_keyboard()
    )
    
    # Проверяем, что состояние очищено
    assert state.data == {}
    assert state.current_state is None
    
    print("✅ Сообщение в поддержку отправлено успешно")
    
    # 2. Админ нажимает "Ответить"
    print("2. Админ нажимает 'Ответить'...")
    callback = MockCallbackQuery(f"reply_to_{TEST_USER_ID}")
    state = MockState()
    
    # Мокаем callback.message.answer
    callback.message.answer = MagicMock()
    
    # Имитируем обработчик reply_to (вручную устанавливаем состояние)
    await state.update_data(reply_to_user=TEST_USER_ID)
    state.current_state = Support.admin_waiting_for_reply
    
    # Проверяем, что сообщение об ответе отправлено
    callback.message.answer.assert_called_once_with(
        "✏️ Введите ответ пользователю. Отправьте /cancel для отмены."
    )
    
    print("✅ Админ начал процесс ответа")
    
    # 3. Админ отправляет ответ
    print("3. Админ отправляет ответ...")
    reply_message = MockMessage(TEST_REPLY_TEXT, user_id=TEST_ADMIN_ID)
    state = MockState()
    await state.update_data(reply_to_user=TEST_USER_ID)
    state.current_state = Support.admin_waiting_for_reply
    
    with patch('bot.bot', mock_bot):
        await admin_reply_finish(reply_message, state)
    
    # Проверяем, что ответ отправлен пользователю
    mock_bot.send_message.assert_called_with(
        TEST_USER_ID,
        f"✉️ Ответ от администратора:\n\n{TEST_REPLY_TEXT}",
        parse_mode='HTML'
    )
    
    # Проверяем, что админу отправлено подтверждение
    reply_message.answer.assert_called_once_with(
        "✅ Ответ отправлен пользователю.",
        reply_markup=get_main_keyboard()
    )
    
    # Проверяем, что состояние очищено
    assert state.data == {}
    assert state.current_state is None
    
    print("✅ Ответ админа отправлен пользователю")
    
    # 4. Тест /cancel
    print("4. Тест команды /cancel...")
    cancel_message = MockMessage("/cancel")
    state = MockState()
    state.current_state = Support.waiting_for_message  # Имитируем активное состояние
    
    await cmd_cancel(cancel_message, state)
    
    # Проверяем, что состояние очищено
    assert state.data == {}
    assert state.current_state is None
    
    # Проверяем сообщение об отмене
    cancel_message.answer.assert_called_once_with(
        "❌ Действие отменено.",
        reply_markup=get_main_keyboard()
    )
    
    print("✅ Команда /cancel работает")
    
    print("\n🎉 Все тесты пройдены! Функционал поддержки работает корректно.")

if __name__ == "__main__":
    asyncio.run(test_support_flow())
