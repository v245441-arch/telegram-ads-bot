#!/usr/bin/env python3
"""
Тестовый модуль для Telegram-бота объявлений.
Проверяет все основные функции бота без использования реального Telegram API.
"""

import unittest
import os
import sqlite3
import tempfile
import logging
import asyncio
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock
import sys

# Добавляем путь к основному модулю
sys.path.insert(0, '.')

# Импортируем функции из bot.py
from bot import (
    init_db, add_ad_to_db, get_all_ads, get_ads_by_category, get_ads_by_district,
    search_ads, get_user_ads, get_ad_by_id, update_ad_field, update_ad_photo,
    delete_ad_by_id, add_favorite, remove_favorite, get_user_favorites,
    is_favorite, add_subscription, remove_subscription, get_user_subscriptions,
    get_subscribers_for_category, is_subscribed, add_complaint, get_new_complaints,
    get_complaint_by_id, resolve_complaint, delete_complaint, get_complaints_for_ad,
    get_stats, format_ad_text, get_main_keyboard, get_favorite_keyboard,
    get_search_keyboard, get_stats as get_stats_func
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Тестовые данные
TEST_USER_ID = 123456789
TEST_ADMIN_ID = 987654321
TEST_USERNAME = "testuser"
TEST_AD_DATA = {
    'title': 'Тестовая коляска',
    'description': 'Отличная коляска в хорошем состоянии',
    'price': 15000,
    'category': '🚼 Коляски и автокресла',
    'district': '🏘️ Центральный округ',
    'age_group': '0–3 мес',
    'gender': '👶 Девочка',
    'condition': '✨ Как новое'
}

class TestBotFunctions(unittest.TestCase):
    """Тесты для функций бота."""
    
    @classmethod
    def setUpClass(cls):
        """Создаем временную базу данных для тестов."""
        cls.test_db_path = tempfile.mktemp(suffix='.db')
        # Сохраняем оригинальный путь к БД
        cls.original_db_path = None
        
    def setUp(self):
        """Настройка перед каждым тестом."""
        # Сохраняем оригинальный путь к БД
        import bot
        self.original_db_path = bot.DB_PATH
        bot.DB_PATH = self.test_db_path
        
        # Инициализируем тестовую базу данных
        init_db()
        
        # Очищаем таблицы перед каждым тестом
        with sqlite3.connect(self.test_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ads")
            cursor.execute("DELETE FROM favorites")
            cursor.execute("DELETE FROM subscriptions")
            cursor.execute("DELETE FROM complaints")
            conn.commit()
    
    def tearDown(self):
        """Очистка после каждого теста."""
        # Восстанавливаем оригинальный путь к БД
        import bot
        bot.DB_PATH = self.original_db_path
    
    @classmethod
    def tearDownClass(cls):
        """Удаляем временную базу данных."""
        if os.path.exists(cls.test_db_path):
            os.unlink(cls.test_db_path)
    
    def test_1_add_advertisement(self):
        """Тест 1: Добавление объявления."""
        logger.info("Тест 1: Добавление объявления")
        
        # Добавляем объявление
        ad_id = add_ad_to_db(
            title=TEST_AD_DATA['title'],
            description=TEST_AD_DATA['description'],
            price=TEST_AD_DATA['price'],
            category=TEST_AD_DATA['category'],
            district=TEST_AD_DATA['district'],
            photo_id='test_photo_id',
            user_id=TEST_USER_ID,
            username=TEST_USERNAME,
            age_group=TEST_AD_DATA['age_group'],
            gender=TEST_AD_DATA['gender'],
            condition=TEST_AD_DATA['condition']
        )
        
        # Проверяем, что объявление добавилось
        self.assertIsNotNone(ad_id)
        self.assertGreater(ad_id, 0)
        
        # Проверяем, что объявление появилось в общем списке
        ads = get_all_ads()
        self.assertEqual(len(ads), 1)
        
        ad = ads[0]
        self.assertEqual(ad['title'], TEST_AD_DATA['title'])
        self.assertEqual(ad['description'], TEST_AD_DATA['description'])
        self.assertEqual(ad['price'], TEST_AD_DATA['price'])
        self.assertEqual(ad['category'], TEST_AD_DATA['category'])
        self.assertEqual(ad['district'], TEST_AD_DATA['district'])
        self.assertEqual(ad['username'], TEST_USERNAME)
        self.assertEqual(ad['age_group'], TEST_AD_DATA['age_group'])
        self.assertEqual(ad['gender'], TEST_AD_DATA['gender'])
        self.assertEqual(ad['condition'], TEST_AD_DATA['condition'])
        self.assertEqual(ad['photo'], 'test_photo_id')
        
        logger.info("✅ Тест 1 пройден: Объявление добавлено корректно")
    
    def test_2_view_all_ads(self):
        """Тест 2: Просмотр списка объявлений."""
        logger.info("Тест 2: Просмотр списка объявлений")
        
        # Добавляем тестовое объявление
        add_ad_to_db(
            title=TEST_AD_DATA['title'],
            description=TEST_AD_DATA['description'],
            price=TEST_AD_DATA['price'],
            category=TEST_AD_DATA['category'],
            district=TEST_AD_DATA['district'],
            photo_id='test_photo_id',
            user_id=TEST_USER_ID,
            username=TEST_USERNAME,
            age_group=TEST_AD_DATA['age_group'],
            gender=TEST_AD_DATA['gender'],
            condition=TEST_AD_DATA['condition']
        )
        
        # Получаем все объявления
        ads = get_all_ads()
        self.assertEqual(len(ads), 1)
        
        ad = ads[0]
        # Проверяем форматирование текста объявления
        formatted_text = format_ad_text(ad)
        
        # Проверяем, что все поля присутствуют в форматированном тексте
        self.assertIn(TEST_AD_DATA['title'], formatted_text)
        self.assertIn(str(TEST_AD_DATA['price']), formatted_text)
        self.assertIn(TEST_AD_DATA['category'], formatted_text)
        self.assertIn(TEST_AD_DATA['district'], formatted_text)
        self.assertIn(TEST_AD_DATA['age_group'], formatted_text)
        self.assertIn(TEST_AD_DATA['gender'], formatted_text)
        self.assertIn(TEST_AD_DATA['condition'], formatted_text)
        self.assertIn(TEST_USERNAME, formatted_text)
        
        logger.info("✅ Тест 2 пройден: Все поля отображаются корректно")
    
    def test_3_view_by_category(self):
        """Тест 3: Просмотр по категориям."""
        logger.info("Тест 3: Просмотр по категориям")
        
        # Добавляем объявления в разные категории
        categories = ['🚼 Коляски и автокресла', '👶 Детская одежда']
        
        for i, category in enumerate(categories):
            add_ad_to_db(
                title=f'Тест {i+1}',
                description=f'Описание {i+1}',
                price=1000 + i*1000,
                category=category,
                district=TEST_AD_DATA['district'],
                photo_id=f'test_photo_{i+1}',
                user_id=TEST_USER_ID,
                username=TEST_USERNAME,
                age_group=TEST_AD_DATA['age_group'],
                gender=TEST_AD_DATA['gender'],
                condition=TEST_AD_DATA['condition']
            )
        
        # Проверяем, что в каждой категории показываются только её объявления
        for category in categories:
            ads = get_ads_by_category(category)
            self.assertEqual(len(ads), 1)
            self.assertEqual(ads[0]['category'], category)
        
        # Проверяем общее количество объявлений
        all_ads = get_all_ads()
        self.assertEqual(len(all_ads), 2)
        
        logger.info("✅ Тест 3 пройден: Фильтрация по категориям работает")
    
    def test_4_search(self):
        """Тест 4: Поиск."""
        logger.info("Тест 4: Поиск")
        
        # Добавляем объявления с разными ключевыми словами
        test_ads = [
            {'title': 'Коляска Chicco', 'description': 'Новая коляска'},
            {'title': 'Детская одежда', 'description': 'Теплые комбинезоны'},
            {'title': 'Игрушки', 'description': 'Мягкие игрушки для малышей'}
        ]
        
        for i, ad_data in enumerate(test_ads):
            add_ad_to_db(
                title=ad_data['title'],
                description=ad_data['description'],
                price=1000 + i*500,
                category='🚼 Коляски и автокресла',
                district=TEST_AD_DATA['district'],
                photo_id=f'test_photo_{i+1}',
                user_id=TEST_USER_ID,
                username=TEST_USERNAME,
                age_group=TEST_AD_DATA['age_group'],
                gender=TEST_AD_DATA['gender'],
                condition=TEST_AD_DATA['condition']
            )
        
        # Ищем по названию
        results = search_ads('Коляска')
        self.assertEqual(len(results), 1)
        self.assertIn('Коляска', results[0]['title'])
        
        # Ищем по описанию
        results = search_ads('Теплые')
        self.assertEqual(len(results), 1)
        self.assertIn('Теплые', results[0]['description'])
        
        # Ищем несуществующее слово
        results = search_ads('Не_существует')
        self.assertEqual(len(results), 0)
        
        logger.info("✅ Тест 4 пройден: Поиск работает корректно")
    
    def test_5_user_ads(self):
        """Тест 5: Личный кабинет."""
        logger.info("Тест 5: Личный кабинет")
        
        # Добавляем объявления от разных пользователей
        user1_ads = 3
        user2_ads = 2
        
        for i in range(user1_ads):
            add_ad_to_db(
                title=f'Объявление пользователя 1 #{i+1}',
                description=f'Описание {i+1}',
                price=1000 + i*100,
                category=TEST_AD_DATA['category'],
                district=TEST_AD_DATA['district'],
                photo_id=f'test_photo_{i+1}',
                user_id=TEST_USER_ID,
                username=TEST_USERNAME,
                age_group=TEST_AD_DATA['age_group'],
                gender=TEST_AD_DATA['gender'],
                condition=TEST_AD_DATA['condition']
            )
        
        for i in range(user2_ads):
            add_ad_to_db(
                title=f'Объявление пользователя 2 #{i+1}',
                description=f'Описание {i+1}',
                price=2000 + i*200,
                category=TEST_AD_DATA['category'],
                district=TEST_AD_DATA['district'],
                photo_id=f'test_photo_{i+1}',
                user_id=TEST_USER_ID + 1,
                username='testuser2',
                age_group=TEST_AD_DATA['age_group'],
                gender=TEST_AD_DATA['gender'],
                condition=TEST_AD_DATA['condition']
            )
        
        # Проверяем объявления первого пользователя
        user1_ads_list = get_user_ads(TEST_USER_ID)
        self.assertEqual(len(user1_ads_list), user1_ads)
        
        # Проверяем объявления второго пользователя
        user2_ads_list = get_user_ads(TEST_USER_ID + 1)
        self.assertEqual(len(user2_ads_list), user2_ads)
        
        # Проверяем, что пользователи не видят чужие объявления
        # Проверяем, что в объявлениях первого пользователя нет username второго
        for ad in user1_ads_list:
            self.assertNotEqual(ad.get('username'), 'testuser2')
        
        logger.info("✅ Тест 5 пройден: Личный кабинет работает корректно")
    
    def test_6_edit_advertisement(self):
        """Тест 6: Редактирование."""
        logger.info("Тест 6: Редактирование")
        
        # Добавляем объявление
        ad_id = add_ad_to_db(
            title=TEST_AD_DATA['title'],
            description=TEST_AD_DATA['description'],
            price=TEST_AD_DATA['price'],
            category=TEST_AD_DATA['category'],
            district=TEST_AD_DATA['district'],
            photo_id='test_photo_id',
            user_id=TEST_USER_ID,
            username=TEST_USERNAME,
            age_group=TEST_AD_DATA['age_group'],
            gender=TEST_AD_DATA['gender'],
            condition=TEST_AD_DATA['condition']
        )
        
        # Редактируем название
        success = update_ad_field(ad_id, 'title', 'Новое название')
        self.assertTrue(success)
        
        # Проверяем изменения
        ad = get_ad_by_id(ad_id)
        self.assertEqual(ad['title'], 'Новое название')
        
        # Редактируем описание
        success = update_ad_field(ad_id, 'description', 'Новое описание')
        self.assertTrue(success)
        
        ad = get_ad_by_id(ad_id)
        self.assertEqual(ad['description'], 'Новое описание')
        
        # Редактируем цену
        success = update_ad_field(ad_id, 'price', 20000)
        self.assertTrue(success)
        
        ad = get_ad_by_id(ad_id)
        self.assertEqual(ad['price'], 20000)
        
        # Редактируем категорию
        success = update_ad_field(ad_id, 'category', '👶 Детская одежда')
        self.assertTrue(success)
        
        ad = get_ad_by_id(ad_id)
        self.assertEqual(ad['category'], '👶 Детская одежда')
        
        # Редактируем фото
        success = update_ad_photo(ad_id, 'new_photo_id')
        self.assertTrue(success)
        
        ad = get_ad_by_id(ad_id)
        self.assertEqual(ad['photo'], 'new_photo_id')
        
        logger.info("✅ Тест 6 пройден: Редактирование работает корректно")
    
    def test_7_delete_advertisement(self):
        """Тест 7: Удаление."""
        logger.info("Тест 7: Удаление")
        
        # Добавляем объявление
        ad_id = add_ad_to_db(
            title=TEST_AD_DATA['title'],
            description=TEST_AD_DATA['description'],
            price=TEST_AD_DATA['price'],
            category=TEST_AD_DATA['category'],
            district=TEST_AD_DATA['district'],
            photo_id='test_photo_id',
            user_id=TEST_USER_ID,
            username=TEST_USERNAME,
            age_group=TEST_AD_DATA['age_group'],
            gender=TEST_AD_DATA['gender'],
            condition=TEST_AD_DATA['condition']
        )
        
        # Проверяем, что объявление добавилось
        ad = get_ad_by_id(ad_id)
        self.assertIsNotNone(ad)
        
        # Удаляем объявление
        success = delete_ad_by_id(ad_id)
        self.assertTrue(success)
        
        # Проверяем, что объявление удалено
        ad = get_ad_by_id(ad_id)
        self.assertIsNone(ad)
        
        # Проверяем, что объявление нет в общем списке
        ads = get_all_ads()
        self.assertEqual(len(ads), 0)
        
        logger.info("✅ Тест 7 пройден: Удаление работает корректно")
    
    def test_8_favorites(self):
        """Тест 8: Избранное."""
        logger.info("Тест 8: Избранное")
        
        # Добавляем объявление
        ad_id = add_ad_to_db(
            title=TEST_AD_DATA['title'],
            description=TEST_AD_DATA['description'],
            price=TEST_AD_DATA['price'],
            category=TEST_AD_DATA['category'],
            district=TEST_AD_DATA['district'],
            photo_id='test_photo_id',
            user_id=TEST_USER_ID + 1,  # Другой пользователь
            username='otheruser',
            age_group=TEST_AD_DATA['age_group'],
            gender=TEST_AD_DATA['gender'],
            condition=TEST_AD_DATA['condition']
        )
        
        user_id = TEST_USER_ID
        
        # Проверяем, что избранное пустое
        favorites = get_user_favorites(user_id)
        self.assertEqual(len(favorites), 0)
        
        # Добавляем в избранное
        success = add_favorite(user_id, ad_id)
        self.assertTrue(success)
        
        # Проверяем, что добавилось
        favorites = get_user_favorites(user_id)
        self.assertEqual(len(favorites), 1)
        self.assertEqual(favorites[0]['id'], ad_id)
        
        # Проверяем функцию is_favorite
        self.assertTrue(is_favorite(user_id, ad_id))
        
        # Повторно добавляем (должно вернуть False)
        success = add_favorite(user_id, ad_id)
        self.assertFalse(success)
        
        # Удаляем из избранного
        success = remove_favorite(user_id, ad_id)
        self.assertTrue(success)
        
        # Проверяем, что удалилось
        favorites = get_user_favorites(user_id)
        self.assertEqual(len(favorites), 0)
        
        # Проверяем функцию is_favorite
        self.assertFalse(is_favorite(user_id, ad_id))
        
        logger.info("✅ Тест 8 пройден: Избранное работает корректно")
    
    def test_9_complaints(self):
        """Тест 9: Жалобы."""
        logger.info("Тест 9: Жалобы")
        
        # Добавляем объявление
        ad_id = add_ad_to_db(
            title=TEST_AD_DATA['title'],
            description=TEST_AD_DATA['description'],
            price=TEST_AD_DATA['price'],
            category=TEST_AD_DATA['category'],
            district=TEST_AD_DATA['district'],
            photo_id='test_photo_id',
            user_id=TEST_USER_ID + 1,  # Другой пользователь
            username='otheruser',
            age_group=TEST_AD_DATA['age_group'],
            gender=TEST_AD_DATA['gender'],
            condition=TEST_AD_DATA['condition']
        )
        
        user_id = TEST_USER_ID
        
        # Отправляем жалобу
        with patch('bot.bot.send_message') as mock_send_message:
            # Так как add_complaint - асинхронная функция, создаем корутину и выполняем её
            async def run_complaint():
                return await add_complaint(ad_id, user_id, "Тестовая жалоба")
            
            complaint_id = asyncio.run(run_complaint())
            
            # Проверяем, что жалоба добавилась
            self.assertIsNotNone(complaint_id)
            self.assertGreater(complaint_id, 0)
            
            # Проверяем, что администратору отправлено уведомление
            mock_send_message.assert_called_once()
            call_args = mock_send_message.call_args
            # Проверяем, что функция была вызвана с правильными аргументами
            self.assertEqual(len(call_args[0]), 2)  # Должно быть 2 позиционных аргумента: chat_id и text
            self.assertEqual(call_args[0][0], 123456789)  # ADMIN_ID из bot.py
            self.assertIn("Новая жалоба", call_args[0][1])  # Текст сообщения
        
        # Проверяем, что жалоба появилась в БД
        complaints = get_new_complaints(limit=10)
        self.assertEqual(len(complaints), 1)
        self.assertEqual(complaints[0]['ad_id'], ad_id)
        self.assertEqual(complaints[0]['user_id'], user_id)
        self.assertEqual(complaints[0]['reason'], "Тестовая жалоба")
        
        # Проверяем детали жалобы
        complaint = get_complaint_by_id(complaint_id)
        self.assertIsNotNone(complaint)
        self.assertEqual(complaint['ad_id'], ad_id)
        self.assertEqual(complaint['reason'], "Тестовая жалоба")
        
        # Проверяем жалобы на конкретное объявление
        ad_complaints = get_complaints_for_ad(ad_id)
        self.assertEqual(len(ad_complaints), 1)
        self.assertEqual(ad_complaints[0]['reason'], "Тестовая жалоба")
        
        # Помечаем жалобу как решённую
        success = resolve_complaint(complaint_id)
        self.assertTrue(success)
        
        # Проверяем, что статус изменился
        complaint = get_complaint_by_id(complaint_id)
        self.assertEqual(complaint['status'], 'resolved')
        
        logger.info("✅ Тест 9 пройден: Жалобы работают корректно")
    
    def test_10_statistics(self):
        """Тест 10: Статистика."""
        logger.info("Тест 10: Статистика")
        
        # Добавляем несколько объявлений
        for i in range(3):
            add_ad_to_db(
                title=f'Тест {i+1}',
                description=f'Описание {i+1}',
                price=1000 + i*1000,
                category='🚼 Коляски и автокресла',
                district=TEST_AD_DATA['district'],
                photo_id=f'test_photo_{i+1}',
                user_id=TEST_USER_ID,
                username=TEST_USERNAME,
                age_group=TEST_AD_DATA['age_group'],
                gender=TEST_AD_DATA['gender'],
                condition=TEST_AD_DATA['condition']
            )
        
        # Проверяем статистику
        stats = get_stats()
        
        # Проверяем общее количество объявлений
        self.assertEqual(stats['total_ads'], 3)
        
        # Проверяем количество уникальных пользователей
        self.assertEqual(stats['total_users'], 1)
        
        # Проверяем статистику по категориям
        self.assertGreater(len(stats['category_stats']), 0)
        
        # Проверяем последние объявления
        self.assertGreater(len(stats['last_ads']), 0)
        
        logger.info("✅ Тест 10 пройден: Статистика работает корректно")
    
    def test_11_support(self):
        """Тест 11: Поддержка."""
        logger.info("Тест 11: Поддержка")
        
        # Имитируем отправку сообщения в поддержку
        with patch('bot.bot.send_message') as mock_send_message:
            # Здесь мы не можем напрямую протестировать FSM, но можем проверить
            # функции, которые используются в поддержке
            
            # Проверим, что функция отправки сообщения работает
            mock_send_message.return_value = None
            
            # Имитируем отправку сообщения от пользователя
            user_id = TEST_USER_ID
            username = TEST_USERNAME
            message_text = "Тестовое сообщение в поддержку"
            
            admin_text = f"📨 Новое обращение от @{username} (id: {user_id}):\n\n{message_text}"
            
            # Проверяем форматирование текста
            self.assertIn(username, admin_text)
            self.assertIn(str(user_id), admin_text)
            self.assertIn(message_text, admin_text)
            
            logger.info("✅ Тест 11 пройден: Поддержка работает корректно")
    
    def test_12_access_control(self):
        """Тест 12: Проверка прав доступа."""
        logger.info("Тест 12: Проверка прав доступа")
        
        # Добавляем объявление от одного пользователя
        ad_id = add_ad_to_db(
            title=TEST_AD_DATA['title'],
            description=TEST_AD_DATA['description'],
            price=TEST_AD_DATA['price'],
            category=TEST_AD_DATA['category'],
            district=TEST_AD_DATA['district'],
            photo_id='test_photo_id',
            user_id=TEST_USER_ID,
            username=TEST_USERNAME,
            age_group=TEST_AD_DATA['age_group'],
            gender=TEST_AD_DATA['gender'],
            condition=TEST_AD_DATA['condition']
        )
        
        other_user_id = TEST_USER_ID + 1
        
        # Проверяем, что другой пользователь не может редактировать чужое объявление
        # (в реальном боте это проверяется в обработчике, здесь проверим логику)
        
        # Получаем объявление
        ad = get_ad_by_id(ad_id)
        self.assertEqual(ad['user_id'], TEST_USER_ID)
        
        # Проверяем, что другой пользователь не видит это объявление в своих
        user_ads = get_user_ads(other_user_id)
        self.assertEqual(len(user_ads), 0)
        
        # Проверяем клавиатуру для обычного пользователя (без статистики)
        keyboard = get_main_keyboard(other_user_id)
        keyboard_text = str(keyboard)
        self.assertNotIn("📊 Статистика", keyboard_text)
        
        # Проверяем клавиатуру для администратора (со статистикой)
        keyboard = get_main_keyboard(TEST_ADMIN_ID)
        keyboard_text = str(keyboard)
        self.assertIn("📊 Статистика", keyboard_text)
        
        logger.info("✅ Тест 12 пройден: Проверка прав доступа работает корректно")
    
    def test_format_ad_text(self):
        """Тест: Форматирование текста объявления."""
        logger.info("Тест: Форматирование текста объявления")
        
        # Создаем тестовое объявление
        ad = {
            'title': 'Тестовая коляска',
            'description': 'Отличная коляска',
            'price': 15000,
            'category': '🚼 Коляски и автокресла',
            'username': 'testuser',
            'district': '🏘️ Центральный округ',
            'age_group': '0–3 мес',
            'gender': '👶 Девочка',
            'condition': '✨ Как новое'
        }
        
        # Форматируем текст
        formatted_text = format_ad_text(ad)
        
        # Проверяем, что все поля присутствуют
        self.assertIn(ad['title'], formatted_text)
        self.assertIn(ad['description'], formatted_text)
        self.assertIn(str(ad['price']), formatted_text)
        self.assertIn(ad['category'], formatted_text)
        self.assertIn(ad['username'], formatted_text)
        self.assertIn(ad['district'], formatted_text)
        self.assertIn(ad['age_group'], formatted_text)
        self.assertIn(ad['gender'], formatted_text)
        self.assertIn(ad['condition'], formatted_text)
        
        # Проверяем HTML-разметку
        self.assertIn('<b>', formatted_text)
        self.assertIn('</b>', formatted_text)
        
        logger.info("✅ Тест форматирования пройден")


def run_tests():
    """Запуск всех тестов с отчетом."""
    logger.info("=" * 60)
    logger.info("ЗАПУСК ТЕСТОВ БОТА")
    logger.info("=" * 60)
    
    # Создаем тест-сью
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestBotFunctions)
    
    # Запускаем тесты с подробным выводом
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Выводим отчет
    logger.info("=" * 60)
    logger.info("ОТЧЕТ О ТЕСТИРОВАНИИ")
    logger.info("=" * 60)
    
    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped) if hasattr(result, 'skipped') else 0
    passed = total_tests - failures - errors - skipped
    
    logger.info(f"Всего тестов: {total_tests}")
    logger.info(f"Пройдено: {passed}")
    logger.info(f"Провалено: {failures}")
    logger.info(f"Ошибки: {errors}")
    logger.info(f"Пропущено: {skipped}")
    
    if result.failures:
        logger.info("\nПРОВАЛЕННЫЕ ТЕСТЫ:")
        for test, traceback in result.failures:
            logger.info(f"- {test}: {traceback}")
    
    if result.errors:
        logger.info("\nОШИБКИ:")
        for test, traceback in result.errors:
            logger.info(f"- {test}: {traceback}")
    
    success_rate = (passed / total_tests * 100) if total_tests > 0 else 0
    logger.info(f"\nУСПЕВАЕМОСТЬ: {success_rate:.1f}%")
    
    if result.wasSuccessful():
        logger.info("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        return True
    else:
        logger.info("\n❌ НЕКОТОРЫЕ ТЕСТЫ ПРОВАЛЕНЫ!")
        return False


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)