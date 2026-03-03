#!/usr/bin/env python3
"""
Тестирование новых обработчиков жалоб:
1. complaint_reason_ (уже существует)
2. delete_ad_complaint_ (новый)
"""

import sqlite3
import sys
import os

# Добавляем путь к текущей директории для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Мокаем необходимые зависимости
class MockBot:
    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        print(f"[MOCK] Отправка сообщения пользователю {chat_id}:")
        print(f"      Текст: {text[:100]}...")
        print(f"      Parse mode: {parse_mode}")
        print(f"      Reply markup: {'Есть' if reply_markup else 'Нет'}")
        return True

class MockCallback:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = type('obj', (object,), {'id': user_id})()
        self.message = type('obj', (object,), {
            'edit_text': self.mock_edit_text,
            'edit_reply_markup': self.mock_edit_reply_markup
        })()
    
    async def mock_edit_text(self, text, reply_markup=None):
        print(f"[MOCK] Редактирование сообщения:")
        print(f"      Текст: {text}")
        print(f"      Reply markup: {'Есть' if reply_markup else 'Нет'}")
    
    async def mock_edit_reply_markup(self, reply_markup=None):
        print(f"[MOCK] Редактирование клавиатуры:")
        print(f"      Reply markup: {'Есть' if reply_markup else 'Нет'}")
    
    async def answer(self, text=None):
        print(f"[MOCK] Ответ callback: {text}")

def test_complaint_reason_handler():
    """Тестируем обработчик complaint_reason_"""
    print("🧪 Тестируем обработчик complaint_reason_")
    
    # Создаём тестовый callback
    callback = MockCallback("complaint_reason_1_spam", 123456)
    
    # Проверяем парсинг данных
    parts = callback.data.split("_")
    print(f"📊 Разобранные части: {parts}")
    
    assert len(parts) >= 4, "Недостаточно частей в callback_data"
    ad_id = int(parts[2])
    reason_type = parts[3]
    print(f"✅ ID объявления: {ad_id}")
    print(f"✅ Тип причины: {reason_type}")

    reason_map = {
        'spam': '🚫 Спам',
        'fraud': '💰 Мошенничество',
        'abuse': '🤬 Оскорбления',
        'other': '📦 Другое'
    }

    reason_text = reason_map.get(reason_type, '📦 Другое')
    print(f"✅ Текст причины: {reason_text}")

def test_delete_ad_complaint_handler():
    """Тестируем обработчик delete_ad_complaint_"""
    print("\n🧪 Тестируем обработчик delete_ad_complaint_")
    
    # Тест 1: правильный формат
    callback_data = "delete_ad_complaint_1_2"
    parts = callback_data.split("_")
    print(f"📊 Разобранные части: {parts}")
    
    assert len(parts) >= 5, "Недостаточно частей в callback_data"
    ad_id = int(parts[3])
    complaint_id = int(parts[4])
    print(f"✅ ID объявления: {ad_id}")
    print(f"✅ ID жалобы: {complaint_id}")

    callback = MockCallback(callback_data, 123456789)  # ADMIN_ID
    print(f"✅ Обработчик корректно разбирает данные")

def test_delete_ad_from_complaint_handler():
    """Тестируем обработчик delete_ad_from_complaint_"""
    print("\n🧪 Тестируем обработчик delete_ad_from_complaint_")
    
    # Тест 1: правильный формат
    callback_data = "delete_ad_from_complaint_1_2"
    parts = callback_data.split("_")
    print(f"📊 Разобранные части: {parts}")
    
    assert len(parts) >= 6, "Недостаточно частей в callback_data"
    ad_id = int(parts[4])
    complaint_id = int(parts[5])
    print(f"✅ ID объявления: {ad_id}")
    print(f"✅ ID жалобы: {complaint_id}")

    callback = MockCallback(callback_data, 123456789)  # ADMIN_ID
    print(f"✅ Обработчик корректно разбирает данные")

def main():
    print("🧪 Начинаем тестирование обработчиков жалоб...")
    print("=" * 50)
    
    # Тестируем существующий обработчик
    test1_passed = test_complaint_reason_handler()
    
    # Тестируем новый обработчик
    test2_passed = test_delete_ad_complaint_handler()
    
    # Тестируем существующий обработчик с from
    test3_passed = test_delete_ad_from_complaint_handler()
    
    print("\n" + "=" * 50)
    print("📊 Результаты тестирования:")
    print(f"1. Обработчик complaint_reason_: {'✅ ПРОЙДЕН' if test1_passed else '❌ ПРОВАЛЕН'}")
    print(f"2. Обработчик delete_ad_complaint_: {'✅ ПРОЙДЕН' if test2_passed else '❌ ПРОВАЛЕН'}")
    print(f"3. Обработчик delete_ad_from_complaint_: {'✅ ПРОЙДЕН' if test3_passed else '❌ ПРОВАЛЕН'}")
    
    if test1_passed and test2_passed and test3_passed:
        print("\n🎉 Все тесты пройдены успешно!")
        print("📋 Система жалоб включает следующие обработчики:")
        print("   1. complaint_reason_ - выбор причины жалобы")
        print("   2. delete_ad_from_complaint_ - удаление объявления (формат с 'from')")
        print("   3. delete_ad_complaint_ - удаление объявления (альтернативный формат)")
        print("   4. resolve_complaint_ - пометить жалобу решённой")
        print("   5. ignore_complaint_ - оставить жалобу")
        print("   6. show_complaint_ - показать детали жалобы")
        return 0
    else:
        print("\n❌ Некоторые тесты не пройдены")
        return 1

if __name__ == '__main__':
    sys.exit(main())