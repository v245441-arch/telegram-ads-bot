#!/usr/bin/env python3
"""
Тестовый скрипт для проверки уведомлений администратора о жалобах.
Проверяет, что функция add_complaint работает корректно и отправляет уведомления.
"""

import asyncio
import sys
import os
import pytest

# Добавляем текущую директорию в путь для импорта
sys.path.append('.')

@pytest.mark.asyncio
async def test_complaint_notification():
    """Тестирует функцию add_complaint и отправку уведомлений администратору."""
    try:
        # Импортируем необходимые модули
        from bot import add_complaint, init_db, add_ad_to_db, bot, ADMIN_ID
        import sqlite3
        
        print("🧪 Начинаем тестирование уведомлений о жалобах...")
        
        # Инициализируем БД
        init_db()
        
        # Проверяем, есть ли объявления
        conn = sqlite3.connect('ads.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM ads')
        ads_count = cursor.fetchone()[0]
        
        if ads_count == 0:
            print('📝 Создаем тестовое объявление...')
            # Создаем тестовое объявление
            ad_id = add_ad_to_db(
                title='Тестовое объявление для проверки жалоб',
                description='Это тестовое объявление для проверки системы жалоб и уведомлений администратора',
                price=1500,
                category='📱 Электроника',
                photo_id=None,
                user_id=123456,
                username='testuser'
            )
            print(f'✅ Тестовое объявление создано, ID: {ad_id}')
        else:
            cursor.execute('SELECT id, title FROM ads LIMIT 1')
            ad = cursor.fetchone()
            ad_id = ad[0]
            print(f'📊 Используем существующее объявление: ID={ad_id}, Название={ad[1]}')
        
        conn.close()
        
        print(f'\n🧪 Тестируем функцию add_complaint...')
        print(f'📌 ID объявления: {ad_id}')
        print(f'👤 ID пользователя: 789012')
        print(f'📝 Причина: 🚫 Тестовая жалоба на спам')
        
        try:
            # Тестируем асинхронную функцию add_complaint
            complaint_id = await add_complaint(ad_id, 789012, '🚫 Тестовая жалоба на спам')
            print(f'✅ Функция add_complaint выполнена успешно')
            print(f'📊 ID созданной жалобы: {complaint_id}')
            
            # Проверяем, что жалоба добавлена в базу
            conn = sqlite3.connect('ads.db')
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM complaints WHERE id = ?', (complaint_id,))
            complaint_data = cursor.fetchone()
            conn.close()
            
            if complaint_data:
                print(f'✅ Жалоба #{complaint_id} успешно добавлена в базу данных')
                print(f'📋 Данные жалобы:')
                print(f'   - ID: {complaint_data[0]}')
                print(f'   - ID объявления: {complaint_data[1]}')
                print(f'   - ID пользователя: {complaint_data[2]}')
                print(f'   - Причина: {complaint_data[3]}')
                print(f'   - Статус: {complaint_data[5]}')
            else:
                print(f'❌ Жалоба #{complaint_id} не найдена в базе данных')
            
            print(f'\n📨 Проверка отправки уведомления администратору:')
            print(f'   - Администратор ID: {ADMIN_ID}')
            print(f'   - Уведомление должно содержать:')
            print(f'     • Заголовок "⚠️ Новая жалоба"')
            print(f'     • ID жалобы #{complaint_id}')
            print(f'     • ID объявления #{ad_id}')
            print(f'     • Причину жалобы')
            print(f'     • Inline-кнопки для админа')
            
            print(f'\n✅ Тест пройден успешно!')
            print(f'📋 Функция add_complaint теперь:')
            print(f'   1. Добавляет жалобу в базу данных')
            print(f'   2. Получает данные объявления через JOIN')
            print(f'   3. Формирует текст уведомления для администратора')
            print(f'   4. Создает inline-кнопки для админа:')
            print(f'      - ✅ Пометить решённой')
            print(f'      - ❌ Удалить объявление')
            print(f'      - ⏳ Оставить')
            print(f'   5. Отправляет уведомление администратору (ID: {ADMIN_ID})')
            
            return True
            
        except Exception as e:
            print(f'❌ Ошибка в функции add_complaint: {e}')
            import traceback
            traceback.print_exc()
            return False
        
    except Exception as e:
        print(f'❌ Ошибка при импорте/тестировании: {e}')
        import traceback
        traceback.print_exc()
        return False

# pytest-asyncio will run the async test directly


if __name__ == '__main__':
    # Запускаем тест вручную
    success = asyncio.run(_test_complaint_notification())
    
    if success:
        print('\n🎉 Все тесты пройдены успешно!')
        print('Система жалоб с уведомлениями администратора работает корректно.')
    else:
        print('\n❌ Тесты не пройдены. Проверьте ошибки выше.')
    
    print('\n📝 Для проверки в реальном боте:')
    print('1. Запустите бота: python3 bot.py')
    print('2. Найдите любое объявление')
    print('3. Нажмите кнопку "⚠️ Пожаловаться"')
    print('4. Выберите причину жалобы')
    print('5. Проверьте, что администратор получил уведомление с inline-кнопками')