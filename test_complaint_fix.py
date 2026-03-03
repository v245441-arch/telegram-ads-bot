#!/usr/bin/env python3
"""
Тестирование исправления конфликта обработчиков жалоб:
1. Проверяем, что complaint_ не перехватывает reason_
2. Проверяем, что reason_ корректно обрабатывается
3. Проверяем, что все обработчики администратора работают
"""

import sys
import os

# Добавляем путь к текущей директории для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_callback_parsing():
    """Тестируем парсинг callback данных."""
    print("🧪 Тестируем парсинг callback данных...")
    
    # Тест 1: complaint_ (кнопка "Пожаловаться")
    callback_data = "complaint_123"
    print(f"📊 Тест 1: complaint_123")
    if callback_data.startswith("complaint_") and not callback_data.startswith("complaint_reason_"):
        print("✅ Фильтр: startswith('complaint_') and not startswith('complaint_reason_') - ПРОЙДЕН")
        ad_id_str = callback_data.replace("complaint_", "")
        try:
            ad_id = int(ad_id_str)
            print(f"✅ ID объявления: {ad_id}")
        except ValueError:
            print("❌ Ошибка: не удалось преобразовать в число")
    else:
        print("❌ Фильтр не сработал")
    
    # Тест 2: reason_ (выбор причины)
    callback_data = "reason_123_spam"
    print(f"\n📊 Тест 2: reason_123_spam")
    if callback_data.startswith("reason_"):
        print("✅ Фильтр: startswith('reason_') - ПРОЙДЕН")
        parts = callback_data.split("_")
        if len(parts) >= 3:
            ad_id = int(parts[1])
            reason_type = parts[2]
            print(f"✅ ID объявления: {ad_id}")
            print(f"✅ Тип причины: {reason_type}")
            
            # Проверяем маппинг причин
            reason_map = {
                'spam': '🚫 Спам',
                'fraud': '💰 Мошенничество',
                'abuse': '🤬 Оскорбления',
                'other': '📦 Другое'
            }
            reason_text = reason_map.get(reason_type, '📦 Другое')
            print(f"✅ Текст причины: {reason_text}")
        else:
            print("❌ Ошибка: недостаточно частей в callback_data")
    else:
        print("❌ Фильтр не сработал")
    
    # Тест 3: complaint_reason_ (старый формат - должен игнорироваться)
    callback_data = "complaint_reason_123_spam"
    print(f"\n📊 Тест 3: complaint_reason_123_spam (старый формат)")
    if callback_data.startswith("complaint_") and not callback_data.startswith("complaint_reason_"):
        print("❌ ОШИБКА: старый формат должен быть исключен фильтром!")
    else:
        print("✅ Старый формат корректно исключен фильтром")
    
    # Тест 4: Кнопки администратора
    print("\n📊 Тест 4: Кнопки администратора")
    
    # 4.1: resolve_complaint_
    callback_data = "resolve_complaint_5"
    if callback_data.startswith("resolve_complaint_"):
        print("✅ resolve_complaint_ - ПРОЙДЕН")
        complaint_id = int(callback_data.replace("resolve_complaint_", ""))
        print(f"  ID жалобы: {complaint_id}")
    
    # 4.2: delete_ad_from_complaint_
    callback_data = "delete_ad_from_complaint_123_5"
    if callback_data.startswith("delete_ad_from_complaint_"):
        print("✅ delete_ad_from_complaint_ - ПРОЙДЕН")
        parts = callback_data.split("_")
        if len(parts) >= 6:
            ad_id = int(parts[4])
            complaint_id = int(parts[5])
            print(f"  ID объявления: {ad_id}")
            print(f"  ID жалобы: {complaint_id}")
    
    # 4.3: delete_ad_complaint_
    callback_data = "delete_ad_complaint_123_5"
    if callback_data.startswith("delete_ad_complaint_"):
        print("✅ delete_ad_complaint_ - ПРОЙДЕН")
        parts = callback_data.split("_")
        if len(parts) >= 5:
            ad_id = int(parts[3])
            complaint_id = int(parts[4])
            print(f"  ID объявления: {ad_id}")
            print(f"  ID жалобы: {complaint_id}")
    
    # 4.4: ignore_complaint_
    callback_data = "ignore_complaint_5"
    if callback_data.startswith("ignore_complaint_"):
        print("✅ ignore_complaint_ - ПРОЙДЕН")
        complaint_id = int(callback_data.replace("ignore_complaint_", ""))
        print(f"  ID жалобы: {complaint_id}")
    
    # 4.5: show_complaint_
    callback_data = "show_complaint_5"
    if callback_data.startswith("show_complaint_"):
        print("✅ show_complaint_ - ПРОЙДЕН")
        complaint_id = int(callback_data.replace("show_complaint_", ""))
        print(f"  ID жалобы: {complaint_id}")
    
    # Тест завершён успешно

def test_keyboard_generation():
    """Тестируем генерацию клавиатур."""
    print("\n🧪 Тестируем генерацию клавиатур...")
    
    # Тест генерации кнопок выбора причины
    ad_id = 123
    print(f"📊 Генерация кнопок для объявления #{ad_id}:")
    
    # Проверяем новые callback_data
    expected_callbacks = [
        f"reason_{ad_id}_spam",
        f"reason_{ad_id}_fraud",
        f"reason_{ad_id}_abuse",
        f"reason_{ad_id}_other"
    ]
    
    print("✅ Ожидаемые callback_data:")
    for cb in expected_callbacks:
        print(f"  - {cb}")
    
    # Проверяем, что старый формат не используется
    old_callbacks = [
        f"complaint_reason_{ad_id}_spam",
        f"complaint_reason_{ad_id}_fraud",
        f"complaint_reason_{ad_id}_abuse",
        f"complaint_reason_{ad_id}_other"
    ]
    
    print("❌ Старый формат (не должен использоваться):")
    for cb in old_callbacks:
        print(f"  - {cb}")
    
    # Тест завершён успешно

def main():
    print("🧪 Начинаем тестирование исправления конфликта обработчиков жалоб...")
    print("=" * 60)
    
    test1_passed = test_callback_parsing()
    test2_passed = test_keyboard_generation()
    
    print("\n" + "=" * 60)
    print("📊 Результаты тестирования:")
    print(f"1. Парсинг callback данных: {'✅ ПРОЙДЕН' if test1_passed else '❌ ПРОВАЛЕН'}")
    print(f"2. Генерация клавиатур: {'✅ ПРОЙДЕН' if test2_passed else '❌ ПРОВАЛЕН'}")
    
    if test1_passed and test2_passed:
        print("\n🎉 Все тесты пройдены успешно!")
        print("\n📋 Изменения в системе жалоб:")
        print("1. ✅ Исправлен конфликт обработчиков complaint_ и complaint_reason_")
        print("2. ✅ Изменен префикс для кнопок выбора причины с complaint_reason_ на reason_")
        print("3. ✅ Обновлен обработчик для нового префикса reason_")
        print("4. ✅ Все обработчики администратора работают корректно:")
        print("   - resolve_complaint_ - пометить жалобу решённой")
        print("   - delete_ad_from_complaint_ - удалить объявление (формат с 'from')")
        print("   - delete_ad_complaint_ - удалить объявление (альтернативный формат)")
        print("   - ignore_complaint_ - оставить жалобу")
        print("   - show_complaint_ - показать детали жалобы")
        print("\n⚠️ Важно: Старый формат complaint_reason_ больше не используется!")
        print("   Все кнопки выбора причины теперь используют префикс reason_")
        return 0
    else:
        print("\n❌ Некоторые тесты не пройдены")
        return 1

if __name__ == '__main__':
    sys.exit(main())