import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
import openai
from aiohttp_socks import ProxyConnector
import aiohttp
try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv():
        return None

load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)

# --- Переменные окружения (prod settings optional) ---
# Use env or sensible defaults for tests/local runs
API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    logging.warning('BOT_TOKEN не задан — запускаем в тестовом/локальном режиме')

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
if DEEPSEEK_API_KEY:
    openai.api_key = DEEPSEEK_API_KEY
    openai.base_url = "https://api.deepseek.com/v1/"
else:
    logging.warning('DEEPSEEK_API_KEY не задан — OpenAI/DeepSeek функции отключены')
    openai.api_key = None

ADMIN_ID = os.getenv('ADMIN_ID')
if not ADMIN_ID:
    logging.warning('ADMIN_ID не задан — используем тестовый ADMIN_ID=123456789')
    ADMIN_ID = 123456789
else:
    ADMIN_ID = int(ADMIN_ID)

CHAT_ID = os.getenv('CHAT_ID')
if CHAT_ID:
    CHAT_ID = int(CHAT_ID)
    logging.info(f'CHAT_ID установлен: {CHAT_ID}')
else:
    logging.warning('CHAT_ID не задан — отправка в общий чат отключена')

SUPPORT_CHAT_ID = os.getenv('SUPPORT_CHAT_ID')
if SUPPORT_CHAT_ID:
    SUPPORT_CHAT_ID = int(SUPPORT_CHAT_ID)
    logging.info(f'SUPPORT_CHAT_ID установлен: {SUPPORT_CHAT_ID}')
else:
    logging.warning('SUPPORT_CHAT_ID не задан — используется старая логика поддержки')

# Создаём объект бота только если указан токен (в тестах обычно не нужен)
bot = Bot(token=API_TOKEN) if API_TOKEN else None
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- Список категорий ---
CATEGORIES = [
    "👶 Детская одежда",
    "🚼 Коляски и автокресла",
    "🛏️ Мебель для детей",
    "🧸 Игрушки",
    "📚 Книги и развивашки",
    "🍼 Товары для кормления",
    "🛁 Купание и гигиена",
    "👟 Детская обувь",
    "🎒 Школьные товары",
    "🤱 Услуги (няни, репетиторы)",
    "💬 Советы и обсуждения"
]

# --- Список районов Якутска ---
YAKUTSK_DISTRICTS = [
    "🏘️ Центральный округ",
    "🏘️ Автодорожный округ",
    "🏘️ Губинский округ",
    "🏘️ Октябрьский округ",
    "🏘️ Промышленный округ",
    "🏘️ Сайсарский округ",
    "🏘️ Строительный округ",
    "🏘️ Гагаринский округ",
    "🏘️ Мархинский округ",
    "🏘️ Кангаласский округ",
    "🏘️ Тулагино-Кильдямский наслег",
    "🏘️ Пригородный наслег",
    "🏘️ Хатасский наслег",
    "🏘️ Табагинский наслег",
    "🏘️ Маганский наслег",
    "📍 Другой район"
]

# --- Работа с базой данных SQLite ---
DB_PATH = "/app/data/ads.db"

def init_db():
    """Создаёт все необходимые таблицы, если их нет. НЕ удаляет существующие данные."""
    # Создаем директорию для базы данных, если её нет
    os.makedirs("/app/data", exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Таблица объявлений
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                price INTEGER NOT NULL,
                category TEXT NOT NULL,
                district TEXT,
                photo_id TEXT,
                user_id INTEGER NOT NULL,
                username TEXT
            )
        """)
        # Проверяем существование колонки district и добавляем её, если её нет
        try:
            cursor.execute("ALTER TABLE ads ADD COLUMN district TEXT")
        except sqlite3.OperationalError:
            pass  # колонка уже существует
        
        # Добавляем новые поля для детских объявлений
        try:
            cursor.execute("ALTER TABLE ads ADD COLUMN age_group TEXT")
        except sqlite3.OperationalError:
            pass  # поле уже существует
        
        try:
            cursor.execute("ALTER TABLE ads ADD COLUMN gender TEXT")
        except sqlite3.OperationalError:
            pass  # поле уже существует
        
        try:
            cursor.execute("ALTER TABLE ads ADD COLUMN condition TEXT")
        except sqlite3.OperationalError:
            pass  # поле уже существует
        # Таблица избранного
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ad_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ad_id) REFERENCES ads(id) ON DELETE CASCADE,
                UNIQUE(user_id, ad_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)")
        # Таблица подписок на категории
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, category)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id)")
        # Таблица жалоб
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'new',
                FOREIGN KEY (ad_id) REFERENCES ads(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_complaints_ad_id ON complaints(ad_id)")
        conn.commit()

def add_ad_to_db(title, description, price, category, district, photo_id, user_id, username, age_group=None, gender=None, condition=None):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ads (title, description, price, category, district, photo_id, user_id, username, age_group, gender, condition)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, description, price, category, district, photo_id, user_id, username, age_group, gender, condition))
        conn.commit()
        return cursor.lastrowid

def get_all_ads():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, description, price, category, district, photo_id, username, age_group, gender, condition FROM ads ORDER BY id DESC")
        rows = cursor.fetchall()
        ads = []
        for row in rows:
            ads.append({
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'price': row[3],
                'category': row[4],
                'district': row[5],
                'photo': row[6],
                'username': row[7],
                'age_group': row[8],
                'gender': row[9],
                'condition': row[10]
            })
        return ads

def get_ads_by_category(category):
    """Возвращает объявления указанной категории.""" 
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, description, price, category, district, photo_id, username, age_group, gender, condition FROM ads WHERE category = ? ORDER BY id DESC", (category,))
        rows = cursor.fetchall()
        ads = []
        for row in rows:
            ads.append({
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'price': row[3],
                'category': row[4],
                'district': row[5],
                'photo': row[6],
                'username': row[7],
                'age_group': row[8],
                'gender': row[9],
                'condition': row[10]
            })
        return ads

def get_ads_by_district(district):
    """Возвращает объявления указанного района.""" 
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, description, price, category, district, photo_id, username, age_group, gender, condition FROM ads WHERE district = ? ORDER BY id DESC", (district,))
        rows = cursor.fetchall()
        ads = []
        for row in rows:
            ads.append({
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'price': row[3],
                'category': row[4],
                'district': row[5],
                'photo': row[6],
                'username': row[7],
                'age_group': row[8],
                'gender': row[9],
                'condition': row[10]
            })
        return ads

def search_ads(keyword):
    """Ищет объявления по ключевому слову в названии и описании."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        pattern = f"%{keyword}%"
        cursor.execute("""
            SELECT id, title, description, price, category, district, photo_id, username, age_group, gender, condition
            FROM ads 
            WHERE title LIKE ? OR description LIKE ? 
            ORDER BY id DESC
        """, (pattern, pattern))
        rows = cursor.fetchall()
        ads = []
        for row in rows:
            ads.append({
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'price': row[3],
                'category': row[4],
                'district': row[5],
                'photo': row[6],
                'username': row[7],
                'age_group': row[8],
                'gender': row[9],
                'condition': row[10]
            })
        return ads

def get_user_ads(user_id):
    """Возвращает объявления конкретного пользователя."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, description, price, category, district, age_group, gender, condition, photo_id, username FROM ads WHERE user_id = ? ORDER BY id DESC", (user_id,))
        rows = cursor.fetchall()
        ads = []
        for row in rows:
            try:
                ad = {
                    'id': row[0],
                    'title': row[1],
                    'description': row[2],
                    'price': row[3],
                    'category': row[4],
                    'district': row[5],
                    'age_group': row[6],
                    'gender': row[7],
                    'condition': row[8],
                    'photo': row[9],
                    'username': row[10]
                }
                ads.append(ad)
            except Exception as e:
                logging.error(f"Ошибка при обработке объявления: {e}")
                continue
        return ads

def get_ad_by_id(ad_id):
    """Возвращает данные объявления по ID (для редактирования)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, description, price, category, district, photo_id, user_id, age_group, gender, condition FROM ads WHERE id = ?", (ad_id,))
        row = cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'price': row[3],
                'category': row[4],
                'district': row[5],
                'photo': row[6],
                'user_id': row[7],
                'age_group': row[8],
                'gender': row[9],
                'condition': row[10]
            }
        return None

def update_ad_field(ad_id, field, value):
    """Обновляет поле объявления (для редактирования)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE ads SET {field} = ? WHERE id = ?", (value, ad_id))
        conn.commit()
        return cursor.rowcount > 0

def update_ad_photo(ad_id, photo_id):
    """Обновляет фото объявления."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE ads SET photo_id = ? WHERE id = ?", (photo_id, ad_id))
        conn.commit()
        return cursor.rowcount > 0

def delete_ad_by_id(ad_id):
    """Удаляет объявление по ID."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ads WHERE id = ?", (ad_id,))
        conn.commit()
        return cursor.rowcount > 0

# --- Функции для работы с избранным ---
def add_favorite(user_id, ad_id):
    """Добавляет объявление в избранное пользователя."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO favorites (user_id, ad_id) VALUES (?, ?)", (user_id, ad_id))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Уже в избранном
            return False

def remove_favorite(user_id, ad_id):
    """Удаляет объявление из избранного пользователя."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM favorites WHERE user_id = ? AND ad_id = ?", (user_id, ad_id))
        conn.commit()
        return cursor.rowcount > 0

def get_user_favorites(user_id):
    """Возвращает список избранных объявлений пользователя."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.id, a.title, a.description, a.price, a.category, a.district, a.photo_id, a.username, a.age_group, a.gender, a.condition
            FROM ads a
            JOIN favorites f ON a.id = f.ad_id
            WHERE f.user_id = ?
            ORDER BY f.created_at DESC
        """, (user_id,))
        rows = cursor.fetchall()
        ads = []
        for row in rows:
            ads.append({
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'price': row[3],
                'category': row[4],
                'district': row[5],
                'photo': row[6],
                'username': row[7],
                'age_group': row[8],
                'gender': row[9],
                'condition': row[10]
            })
        return ads

def is_favorite(user_id, ad_id):
    """Проверяет, находится ли объявление в избранном у пользователя."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM favorites WHERE user_id = ? AND ad_id = ?", (user_id, ad_id))
        return cursor.fetchone() is not None

# --- Функции для работы с подписками ---
def add_subscription(user_id, category):
    """Подписывает пользователя на категорию."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO subscriptions (user_id, category) VALUES (?, ?)", (user_id, category))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Уже подписан
            return False

def remove_subscription(user_id, category):
    """Отписывает пользователя от категории."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscriptions WHERE user_id = ? AND category = ?", (user_id, category))
        conn.commit()
        return cursor.rowcount > 0

def get_user_subscriptions(user_id):
    """Возвращает список категорий, на которые подписан пользователь."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT category FROM subscriptions WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        rows = cursor.fetchall()
        return [row[0] for row in rows]

def get_subscribers_for_category(category):
    """Возвращает список user_id подписчиков данной категории."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM subscriptions WHERE category = ?", (category,))
        rows = cursor.fetchall()
        return [row[0] for row in rows]

def is_subscribed(user_id, category):
    """Проверяет, подписан ли пользователь на категорию."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM subscriptions WHERE user_id = ? AND category = ?", (user_id, category))
        return cursor.fetchone() is not None

# --- Функции для работы с жалобами ---
async def add_complaint(ad_id, user_id, reason=''):
    """Добавляет новую жалобу со статусом 'new'. Возвращает id жалобы и отправляет уведомление администратору."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO complaints (ad_id, user_id, reason, status)
            VALUES (?, ?, ?, 'new')
        """, (ad_id, user_id, reason))
        conn.commit()
        complaint_id = cursor.lastrowid
        
        # Получаем данные объявления для уведомления
        cursor.execute("""
            SELECT a.title, a.description, a.price, a.category, a.username, a.user_id
            FROM ads a WHERE a.id = ?
        """, (ad_id,))
        row = cursor.fetchone()
        
        if row:
            ad_title, ad_description, ad_price, ad_category, ad_username, ad_user_id = row
            
            # Формируем текст уведомления
            text = (
                f"⚠️ *Новая жалоба*\n\n"
                f"🆔 Жалоба #{complaint_id}\n"
                f"📌 Объявление #{ad_id}\n"
                f"👤 Автор объявления: @{ad_username} (id: {ad_user_id})\n"
                f"👤 Пожаловался пользователь: id {user_id}\n"
                f"📝 Причина: {reason}\n"
                f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"📌 *Объявление:*\n"
                f"<b>{ad_title}</b>\n"
                f"{ad_description}\n"
                f"💰 {ad_price} руб.\n"
                f"🏷️ Категория: {ad_category}"
            )
            
            # Создаём inline-клавиатуру для админа
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Пометить решённой", callback_data=f"resolve_complaint_{complaint_id}"),
                        InlineKeyboardButton(text="❌ Удалить объявление", callback_data=f"delete_ad_from_complaint_{ad_id}_{complaint_id}")
                    ],
                    [
                        InlineKeyboardButton(text="⏳ Оставить", callback_data=f"ignore_complaint_{complaint_id}")
                    ]
                ]
            )
            
            try:
                # Отправляем уведомление админу
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=text,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
                logging.info(f"Уведомление о жалобе #{complaint_id} отправлено администратору")
            except Exception as e:
                logging.error(f"Ошибка отправки уведомления админу: {e}")
        
        return complaint_id

def get_new_complaints(limit=10):
    """Возвращает список последних нерассмотренных жалоб (для админа)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, c.ad_id, c.user_id, c.reason, c.created_at, 
                   a.title, a.description, a.price, a.category, a.username
            FROM complaints c
            JOIN ads a ON c.ad_id = a.id
            WHERE c.status = 'new'
            ORDER BY c.created_at DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        complaints = []
        for row in rows:
            complaints.append({
                'id': row[0],
                'ad_id': row[1],
                'user_id': row[2],
                'reason': row[3],
                'created_at': row[4],
                'ad_title': row[5],
                'ad_description': row[6],
                'ad_price': row[7],
                'ad_category': row[8],
                'ad_username': row[9]
            })
        return complaints

def get_complaint_by_id(complaint_id):
    """Получить данные конкретной жалобы."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, c.ad_id, c.user_id, c.reason, c.status, c.created_at,
                   a.title, a.description, a.price, a.category, a.username
            FROM complaints c
            JOIN ads a ON c.ad_id = a.id
            WHERE c.id = ?
        """, (complaint_id,))
        row = cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'ad_id': row[1],
                'user_id': row[2],
                'reason': row[3],
                'status': row[4],
                'created_at': row[5],
                'ad_title': row[6],
                'ad_description': row[7],
                'ad_price': row[8],
                'ad_category': row[9],
                'ad_username': row[10]
            }
        return None

def resolve_complaint(complaint_id):
    """Меняет статус жалобы на 'resolved'."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE complaints SET status = 'resolved' WHERE id = ?", (complaint_id,))
        conn.commit()
        return cursor.rowcount > 0

def delete_complaint(complaint_id):
    """Полностью удаляет жалобу."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM complaints WHERE id = ?", (complaint_id,))
        conn.commit()
        return cursor.rowcount > 0

def get_complaints_for_ad(ad_id):
    """Все жалобы на конкретное объявление (для админа)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, c.user_id, c.reason, c.status, c.created_at
            FROM complaints c
            WHERE c.ad_id = ?
            ORDER BY c.created_at DESC
        """, (ad_id,))
        rows = cursor.fetchall()
        complaints = []
        for row in rows:
            complaints.append({
                'id': row[0],
                'user_id': row[1],
                'reason': row[2],
                'status': row[3],
                'created_at': row[4]
            })
        return complaints

# --- Статистика для админа ---
def get_stats():
    """Возвращает словарь со статистикой."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Общее количество объявлений
        cursor.execute("SELECT COUNT(*) FROM ads")
        total_ads = cursor.fetchone()[0]
        # Количество уникальных пользователей
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM ads")
        total_users = cursor.fetchone()[0]
        # Статистика по категориям
        cursor.execute("SELECT category, COUNT(*) FROM ads GROUP BY category ORDER BY COUNT(*) DESC")
        cat_stats = cursor.fetchall()
        # Последние 5 объявлений
        cursor.execute("SELECT id, title, price, username FROM ads ORDER BY id DESC LIMIT 5")
        last_ads = cursor.fetchall()
        return {
            'total_ads': total_ads,
            'total_users': total_users,
            'category_stats': cat_stats,
            'last_ads': last_ads
        }

# Инициализируем БД при запуске
init_db()

# --- Функция AI-модерации через DeepSeek ---
async def moderate_with_deepseek(text: str) -> bool:
    """Возвращает True, если объявление чистое, иначе False."""
    logging.info(f"Отправка текста на модерацию: {text[:50]}...")
    try:
        response = openai.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты модератор доски объявлений. Определи, содержит ли текст спам, нецензурную лексику, оскорбления или явное мошенничество. Если текст — обычное объявление о продаже товара (даже с ошибками или неполное), ответь 'ok'. Если есть явные нарушения, ответь 'fail'. Отвечай только одним словом."},
                {"role": "user", "content": text}
            ],
            temperature=0.1,
            max_tokens=20
        )
        full_answer = response.choices[0].message.content
        result = full_answer.strip().lower()
        first_word = result.split()[0] if result else ""
        first_word = first_word.rstrip('.,!?;:')
        logging.info(f"DeepSeek ответил: {result}, первое слово: {first_word}")
        return first_word == "ok"
    except Exception as e:
        logging.error(f"Ошибка DeepSeek API: {e}")
        return False

# --- Клавиатуры ---
def get_main_keyboard(user_id=None):
    """Главное меню с кнопками команд.""" 
    keyboard_buttons = [
        [KeyboardButton(text="📋 Список объявлений")],
        [KeyboardButton(text="➕ Добавить объявление")],
        [KeyboardButton(text="📁 Категории"), KeyboardButton(text="👤 Мои объявления")],
        [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="⭐ Избранное")],
        [KeyboardButton(text="🔔 Мои подписки"), KeyboardButton(text="📞 Поддержка")]
    ]
    # Добавляем кнопку статистики только для администратора
    if user_id == ADMIN_ID:
        keyboard_buttons.insert(-1, [KeyboardButton(text="📊 Статистика")])
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

def get_search_keyboard():
    """Клавиатура для режима поиска с кнопкой отмены."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

def get_favorite_keyboard(user_id, ad_id):
    """Создаёт inline-клавиатуру с кнопкой избранного и жалобы."""
    is_fav = is_favorite(user_id, ad_id)
    if is_fav:
        fav_button = InlineKeyboardButton(text="✅ В избранном", callback_data=f"fav_remove_{ad_id}")
    else:
        fav_button = InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_add_{ad_id}")
    
    complaint_button = InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data=f"complaint_{ad_id}")
    
    return InlineKeyboardMarkup(inline_keyboard=[[fav_button, complaint_button]])

def format_ad_text(ad):
    """Форматирует текст объявления с учётом новых полей."""
    text = f"<b>{ad['title']}</b> [{ad['category']}]\n{ad['description']}\n💰 {ad['price']} руб.\n👤 @{ad['username']}"
    
    # Добавляем информацию о районе, если она есть
    if ad.get('district'):
        text += f"\n📍 Район: {ad['district']}"
    
    # Добавляем возрастную группу, если она есть
    if ad.get('age_group'):
        text += f"\n👶 Возраст: {ad['age_group']}"
    
    # Добавляем пол, если он есть
    if ad.get('gender'):
        text += f"\n🚻 Пол: {ad['gender']}"
    
    # Добавляем состояние, если оно есть
    if ad.get('condition'):
        text += f"\n📦 Состояние: {ad['condition']}"
    
    return text

# --- Состояния FSM для добавления ---
class AddAd(StatesGroup):
    title = State()
    description = State()
    price = State()
    category = State()
    age_group = State()
    gender = State()
    condition = State()
    district = State()
    photo = State()

# --- Обработчики выбора категории ---
@dp.callback_query(lambda c: c.data and c.data.startswith('cat_'))
async def process_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace('cat_', '')
    await state.update_data(category=category)
    await callback.message.edit_reply_markup(reply_markup=None)
    # Показываем inline-кнопки для выбора возрастной группы
    age_groups = ["0–3 мес", "3–12 мес", "1–3 года", "3–7 лет", "7–12 лет"]
    builder = InlineKeyboardBuilder()
    for age in age_groups:
        builder.button(text=age, callback_data=f"age_{age}")
    builder.adjust(1)
    await callback.message.answer("Выберите возрастную группу:", reply_markup=builder.as_markup())
    await state.set_state(AddAd.age_group)
    await callback.answer()
    logging.info(f"Category selected: {category}, moving to age group")

# --- Обработчики выбора возрастной группы ---
@dp.callback_query(lambda c: c.data and c.data.startswith('age_'))
async def process_age(callback: types.CallbackQuery, state: FSMContext):
    age = callback.data.replace('age_', '')
    await state.update_data(age_group=age)
    await callback.message.edit_reply_markup(reply_markup=None)
    # Показываем inline-кнопки для выбора пола
    gender_options = ["👧 Девочка", "👦 Мальчик", "👪 Унисекс"]
    builder = InlineKeyboardBuilder()
    for gender in gender_options:
        builder.button(text=gender, callback_data=f"gender_{gender}")
    builder.adjust(1)
    await callback.message.answer("Выберите пол:", reply_markup=builder.as_markup())
    await state.set_state(AddAd.gender)
    await callback.answer()
    logging.info(f"Age selected: {age}, moving to gender")

# --- Обработчики выбора пола ---
@dp.callback_query(lambda c: c.data and c.data.startswith('gender_'))
async def process_gender(callback: types.CallbackQuery, state: FSMContext):
    gender = callback.data.replace('gender_', '')
    await state.update_data(gender=gender)
    await callback.message.edit_reply_markup(reply_markup=None)
    # Показываем inline-кнопки для выбора состояния
    condition_options = ["🆕 Новое", "✨ Как новое", "🔄 Б/у", "🔧 Требует ремонта"]
    builder = InlineKeyboardBuilder()
    for cond in condition_options:
        builder.button(text=cond, callback_data=f"cond_{cond}")
    builder.adjust(1)
    await callback.message.answer("Выберите состояние:", reply_markup=builder.as_markup())
    await state.set_state(AddAd.condition)
    await callback.answer()
    logging.info(f"Gender selected: {gender}, moving to condition")

# --- Обработчики выбора состояния ---
@dp.callback_query(lambda c: c.data and c.data.startswith('cond_'))
async def process_condition(callback: types.CallbackQuery, state: FSMContext):
    condition = callback.data.replace('cond_', '')
    await state.update_data(condition=condition)
    await callback.message.edit_reply_markup(reply_markup=None)
    # Переходим к выбору района (существующий шаг)
    builder = InlineKeyboardBuilder()
    for i, district in enumerate(YAKUTSK_DISTRICTS):
        builder.button(text=district, callback_data=f"district_{i}")
    builder.adjust(1)
    await callback.message.answer("Выберите район:", reply_markup=builder.as_markup())
    await state.set_state(AddAd.district)
    await callback.answer()
    logging.info(f"Condition selected: {condition}, moving to district")

# --- Обработчики выбора района ---
@dp.callback_query(lambda c: c.data and c.data.startswith('district_'))
async def process_district(callback: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split('_')
        idx = int(parts[1])
        district = YAKUTSK_DISTRICTS[idx]
        await state.update_data(district=district)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Отправьте фото товара (или /skip):")
        await state.set_state(AddAd.photo)
        await callback.answer()
        logging.info(f"District selected: {district}, moving to photo")
    except (IndexError, ValueError) as e:
        logging.error(f"Error parsing district callback: {callback.data}, error: {e}")
        await callback.answer("Ошибка выбора района", show_alert=True)

# --- Обработчики жалобы ---
@dp.callback_query(lambda c: c.data and c.data.startswith('complaint_'))
async def process_complaint(callback: types.CallbackQuery, state: FSMContext):
    try:
        ad_id = int(callback.data.replace('complaint_', ''))
        # Пока просто логируем и уведомляем пользователя
        logging.info(f"Complaint on ad {ad_id} from user {callback.from_user.id}")
        await callback.answer("⚠️ Жалоба отправлена администратору")
        
        # Отправляем уведомление админу (асинхронно)
        complaint_id = await add_complaint(ad_id, callback.from_user.id, "⚠️ Жалоба отправлена администратору")
        
    except ValueError:
        await callback.answer("Ошибка обработки жалобы", show_alert=True)

# --- Обработчики избранного ---
@dp.callback_query(lambda c: c.data and c.data.startswith('fav_add_'))
async def process_favorite_add(callback: types.CallbackQuery, state: FSMContext):
    try:
        ad_id = int(callback.data.replace('fav_add_', ''))
        user_id = callback.from_user.id
        
        # Проверяем, уже ли в избранном
        if is_favorite(user_id, ad_id):
            await callback.answer("✅ Уже в избранном")
            return
        
        # Добавляем в избранное
        success = add_favorite(user_id, ad_id)
        if success:
            await callback.answer("⭐ Добавлено в избранное", show_alert=True)
        else:
            await callback.answer("✅ Уже в избранном")
    except ValueError:
        await callback.answer("Ошибка добавления в избранное", show_alert=True)

# --- Логирование всех callback-запросов ---
# Удалено, чтобы не перехватывать callback-запросы для edit_ и del_

# --- Состояния FSM для редактирования ---
class EditAd(StatesGroup):
    choosing_field = State()
    editing_title = State()
    editing_description = State()
    editing_price = State()
    editing_category = State()
    editing_photo = State()

# --- Состояние для поиска ---
class SearchState(StatesGroup):
    waiting_for_query = State()

# --- Состояния для поддержки ---
class Support(StatesGroup):
    waiting_for_message = State()   # пользователь пишет сообщение админу
    admin_waiting_for_reply = State() # админ пишет ответ пользователю

# --- Команда /support ---
@dp.message(Command('support'))
async def cmd_support(message: types.Message, state: FSMContext):
    await state.set_state(Support.waiting_for_message)
    await message.answer(
        "📝 Опишите вашу проблему или вопрос. Администратор ответит вам в ближайшее время.\n"
        "Чтобы отменить, отправьте /cancel",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True,
            one_time_keyboard=False
        )
    )

@dp.message(lambda message: message.text == "📞 Поддержка")
async def handle_support_button(message: types.Message, state: FSMContext):
    await cmd_support(message, state)

@dp.message(Support.waiting_for_message)
async def process_support_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    text = message.text
    
    if SUPPORT_CHAT_ID:
        # Отправляем сообщение в чат поддержки
        support_text = f"📨 Новое обращение от @{username} (id: {user_id}):\n\n{text}"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Ответить", callback_data=f"reply_to_{user_id}")]
            ]
        )
        await bot.send_message(SUPPORT_CHAT_ID, support_text, reply_markup=kb)
        await message.answer("✅ Ваше сообщение отправлено в чат поддержки. Ожидайте ответа.", reply_markup=get_main_keyboard())
    else:
        # Старая логика - отправка админу
        admin_text = f"📨 Новое обращение от @{username} (id: {user_id}):\n\n{text}"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Ответить", callback_data=f"reply_to_{user_id}")]
            ]
        )
        await bot.send_message(ADMIN_ID, admin_text, reply_markup=kb)
        await message.answer("✅ Ваше сообщение отправлено администратору. Ожидайте ответа.", reply_markup=get_main_keyboard())
    
    await state.clear()

@dp.callback_query(lambda c: c.data and c.data.startswith('reply_to_'))
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.replace('reply_to_', ''))
    await state.update_data(reply_to_user=user_id, support_chat_id=callback.message.chat.id)
    await state.set_state(Support.admin_waiting_for_reply)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✏️ Введите ответ пользователю. Отправьте /cancel для отмены.")
    await callback.answer()

@dp.message(Support.admin_waiting_for_reply)
async def admin_reply_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('reply_to_user')
    support_chat_id = data.get('support_chat_id')
    
    if not user_id:
        await message.answer("❌ Ошибка: не удалось определить получателя.", reply_markup=get_main_keyboard())
        await state.clear()
        return
    
    # Проверяем, что сообщение пришло из чата поддержки
    if message.chat.id == SUPPORT_CHAT_ID and support_chat_id == SUPPORT_CHAT_ID:
        # Сообщение из чата поддержки - отправляем ответ пользователю
        reply_text = f"✉️ Ответ от администратора:\n\n{message.text}"
        try:
            await bot.send_message(user_id, reply_text, parse_mode='HTML')
            await message.answer("✅ Ответ отправлен пользователю.", reply_markup=get_main_keyboard())
            logging.info(f"Ответ админа из чата поддержки отправлен пользователю {user_id}")
        except Exception as e:
            await message.answer(f"❌ Не удалось отправить ответ: {e}", reply_markup=get_main_keyboard())
            logging.error(f"Ошибка отправки ответа из чата поддержки: {e}")
    else:
        # Сообщение из лички - стандартная логика
        reply_text = f"✉️ Ответ от администратора:\n\n{message.text}"
        try:
            await bot.send_message(user_id, reply_text, parse_mode='HTML')
            await message.answer("✅ Ответ отправлен пользователю.", reply_markup=get_main_keyboard())
            logging.info(f"Ответ админа из лички отправлен пользователю {user_id}")
        except Exception as e:
            await message.answer(f"❌ Не удалось отправить ответ: {e}", reply_markup=get_main_keyboard())
            logging.error(f"Ошибка отправки ответа из лички: {e}")
    
    await state.clear()

@dp.message(Command('cancel'))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("❌ Нечего отменять.", reply_markup=get_main_keyboard(message.from_user.id))
        return
    
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=get_main_keyboard(message.from_user.id))

# --- Команда /start ---
@dp.message(Command('start'))
async def cmd_start(message: types.Message, state: FSMContext):
    logging.info(f"Вызвана команда {message.text} от {message.from_user.id}")
    await state.clear()
    await message.answer(
        "👋 Привет, мамочка! 👶\n"
        "Это доска объявлений для мам и малышей. Здесь можно продать, купить, обменять детские вещи, найти няню или просто спросить совета.\n\n"
        "Все функции доступны через кнопки в меню ниже.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )
    if message.from_user.id == ADMIN_ID:
        await message.answer("🔧 Вы администратор. Статистика доступна.")

# --- Команда /stats (только для админа) ---
@dp.message(Command('stats'))
async def cmd_stats(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Эта команда только для администратора.", reply_markup=get_main_keyboard(message.from_user.id))
        return
    await state.clear()
    stats = get_stats()
    text = f"📊 <b>Статистика бота</b>\n\n"
    text += f"📝 Всего объявлений: {stats['total_ads']}\n"
    text += f"👥 Уникальных пользователей: {stats['total_users']}\n\n"
    text += "<b>По категориям:</b>\n"
    for cat, count in stats['category_stats']:
        text += f"  {cat}: {count}\n"
    text += "\n<b>Последние 5 объявлений:</b>\n"
    for ad_id, title, price, username in stats['last_ads']:
        text += f"  • {title} — {price} руб. (от @{username})\n"
    await message.answer(text, parse_mode='HTML', reply_markup=get_main_keyboard(message.from_user.id))

# --- Команда /search ---
@dp.message(Command('search'))
async def cmd_search(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(SearchState.waiting_for_query)
    await message.answer(
        "🔍 Режим поиска активирован.\n"
        "Введите слово или фразу для поиска.\n"
        "Чтобы выйти, используйте кнопку 'Отмена' или отправьте /exit",
        reply_markup=get_search_keyboard()
    )

# --- Команда /exit (выход из режима поиска) ---
@dp.message(Command('exit'))
async def cmd_exit(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == SearchState.waiting_for_query:
        await state.clear()
        await message.answer("🚪 Вы вышли из режима поиска.", reply_markup=get_main_keyboard(message.from_user.id))
    else:
        await message.answer("❓ Вы не в режиме поиска.", reply_markup=get_main_keyboard(message.from_user.id))

# --- Обработчики кнопок главного меню ---
@dp.message(lambda message: message.text == "📋 Список объявлений")
async def handle_list_button(message: types.Message, state: FSMContext):
    await state.clear()
    ads = get_all_ads()
    if not ads:
        await message.answer("📭 Пока нет объявлений.", reply_markup=get_main_keyboard(message.from_user.id))
        return
    for ad in ads:
        text = format_ad_text(ad)
        keyboard = get_favorite_keyboard(message.from_user.id, ad['id'])
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    await message.answer("🔍 Что ищем дальше?", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(lambda message: message.text == "➕ Добавить объявление")
async def handle_add_button(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Введите название товара:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(AddAd.title)

@dp.message(lambda message: message.text == "📁 Категории")
async def categories_button_handler(message: types.Message, state: FSMContext):
    await cmd_categories(message, state)

@dp.message(lambda message: message.text == "👤 Мои объявления")
async def handle_myads_button(message: types.Message, state: FSMContext):
    await state.clear()
    user_ads = get_user_ads(message.from_user.id)
    if not user_ads:
        await message.answer("📭 У вас пока нет объявлений.", reply_markup=get_main_keyboard(message.from_user.id))
        return
    for ad in user_ads:
        info = f"Возраст: {ad.get('age_group', 'Не указан')} | Пол: {ad.get('gender', 'Не указан')} | Состояние: {ad.get('condition', 'Не указано')}"
        text = f"<b>{ad['title']}</b> [{ad['category']}]\n{info}\n{ad['description']}\n💰 {ad['price']} руб.\n📍 Район: {ad.get('district', 'Не указан')}\n👤 @{ad.get('username', 'Не указан')}"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{ad['id']}"),
                    InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_{ad['id']}")
                ]
            ]
        )
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=kb)
        else:
            await message.answer(text, parse_mode='HTML', reply_markup=kb)
    await message.answer("Вот ваши объявления", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(lambda message: message.text == "🔍 Поиск")
async def handle_search_button(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(SearchState.waiting_for_query)
    await message.answer(
        "🔍 Режим поиска активирован.\n"
        "Введите слово или фразу для поиска.\n"
        "Чтобы выйти, используйте кнопку 'Отмена' или отправьте /exit",
        reply_markup=get_search_keyboard()
    )

@dp.message(lambda message: message.text == "⭐ Избранное")
async def handle_favorites_button(message: types.Message, state: FSMContext):
    await state.clear()
    favorites = get_user_favorites(message.from_user.id)
    if not favorites:
        await message.answer("⭐ У вас пока нет избранных объявлений.", reply_markup=get_main_keyboard(message.from_user.id))
        return
    await message.answer("⭐ Ваши избранные объявления:")
    for ad in favorites:
        text = format_ad_text(ad)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Удалить из избранного", callback_data=f"fav_remove_{ad['id']}")]]
        )
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    await message.answer("Вот ваши избранные объявления", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(lambda message: message.text == "🔔 Мои подписки")
async def handle_mysubs_button(message: types.Message, state: FSMContext):
    await state.clear()
    subscriptions = get_user_subscriptions(message.from_user.id)
    if not subscriptions:
        await message.answer("🔔 Вы пока не подписаны ни на одну категорию.", reply_markup=get_main_keyboard(message.from_user.id))
        return
    
    text = "🔔 <b>Ваши подписки:</b>\n\n"
    for category in subscriptions:
        text += f"• {category}\n"
    
    # Создаём inline-кнопки для отписки
    builder = InlineKeyboardBuilder()
    for category in subscriptions:
        builder.button(text=f"❌ Отписаться от {category}", callback_data=f"sub_remove_{category}")
    builder.adjust(1)
    
    await message.answer(text, parse_mode='HTML', reply_markup=builder.as_markup())

@dp.message(lambda message: message.text == "📊 Статистика")
async def handle_stats_button(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Эта кнопка только для администратора.", reply_markup=get_main_keyboard())
        return
    await state.clear()
    stats = get_stats()
    text = f"📊 <b>Статистика бота</b>\n\n"
    text += f"📝 Всего объявлений: {stats['total_ads']}\n"
    text += f"👥 Уникальных пользователей: {stats['total_users']}\n\n"
    text += "<b>По категориям:</b>\n"
    for cat, count in stats['category_stats']:
        text += f"  {cat}: {count}\n"
    text += "\n<b>Последние 5 объявлений:</b>\n"
    for ad_id, title, price, username in stats['last_ads']:
        text += f"  • {title} — {price} руб. (от @{username})\n"
    await message.answer(text, parse_mode='HTML', reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "❌ Отмена")
async def handle_cancel_button(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == SearchState.waiting_for_query:
        await state.clear()
        await message.answer("🚪 Вы вышли из режима поиска.", reply_markup=get_main_keyboard())
    else:
        await message.answer("✅ Возврат в главное меню.", reply_markup=get_main_keyboard())

# --- Обработчик поиска в состоянии ---
@dp.message(SearchState.waiting_for_query)
async def process_search_query(message: types.Message, state: FSMContext):
    # Обработка команды exit через кнопку
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("🚪 Вы вышли из режима поиска.", reply_markup=get_main_keyboard())
        return

    query = message.text.strip()
    if not query:
        await message.answer("❌ Пустой запрос. Введите что-нибудь.")
        return

    ads = search_ads(query)
    if not ads:
        await message.answer(f"📭 По запросу «{query}» ничего не найдено.")
    else:
        await message.answer(f"🔍 Результаты поиска по запросу «{query}»:")
        for ad in ads:
            text = f"<b>{ad['title']}</b> [{ad['category']}]\n{ad['description']}\n💰 {ad['price']} руб.\n👤 @{ad['username']}"
            if ad.get('district'):
                text += f"\n📍 Район: {ad['district']}"
            if ad.get('age_group'):
                text += f"\n👶 Возраст: {ad['age_group']}"
            if ad.get('gender'):
                text += f"\n🚻 Пол: {ad['gender']}"
            if ad.get('condition'):
                text += f"\n📦 Состояние: {ad['condition']}"
            keyboard = get_favorite_keyboard(message.from_user.id, ad['id'])
            if ad['photo']:
                await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=keyboard)
            else:
                await message.answer(text, parse_mode='HTML', reply_markup=keyboard)
        await message.answer("Продолжайте поиск или нажмите '❌ Отмена' для выхода.")
    # Состояние не очищаем, остаёмся в режиме поиска

# --- Добавление объявления с AI-модерацией ---
@dp.message(Command('add'))
async def cmd_add(message: types.Message, state: FSMContext):
    logging.info(f"Вызвана команда {message.text} от {message.from_user.id}")
    await state.clear()
    await message.answer("Введите название товара:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(AddAd.title)

@dp.message(AddAd.title)
async def add_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Теперь введите описание:")
    await state.set_state(AddAd.description)
    logging.info(f"Title saved: {message.text}")

@dp.message(AddAd.description)
async def add_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите цену (только число):")
    await state.set_state(AddAd.price)
    logging.info(f"Description saved: {message.text}")

@dp.message(AddAd.price)
async def add_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите цену числом.")
        return
    await state.update_data(price=int(message.text))
    # Логируем данные после сохранения цены
    data = await state.get_data()
    logging.info(f"Data after price: {data}")
    builder = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        builder.button(text=cat, callback_data=f"cat_{cat}")
    builder.adjust(1)
    await message.answer("Выберите категорию:", reply_markup=builder.as_markup())
    await state.set_state(AddAd.category)
    logging.info(f"Price saved: {message.text}")

@dp.callback_query(AddAd.category)
async def choose_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("cat_", "")
    await state.update_data(category=category)
    await callback.message.edit_reply_markup(reply_markup=None)

    # Показываем кнопки с возрастными группами
    builder = InlineKeyboardBuilder()
    age_groups = ["0–3 мес", "3–12 мес", "1–3 года", "3–7 лет", "7–12 лет"]
    for age_group in age_groups:
        builder.button(text=age_group, callback_data=f"age_{age_group}")
    builder.adjust(1)
    await callback.message.answer("Выберите возрастную группу:", reply_markup=builder.as_markup())
    await state.set_state(AddAd.age_group)
    await callback.answer()

@dp.callback_query(AddAd.district)
async def choose_district(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора района."""
    try:
        # Извлекаем индекс из callback_data
        index_str = callback.data.replace("dist_", "")
        index = int(index_str)
        
        # Получаем район по индексу из списка YAKUTSK_DISTRICTS
        if 0 <= index < len(YAKUTSK_DISTRICTS):
            district = YAKUTSK_DISTRICTS[index]
        else:
            district = "📍 Другой район"
            
        await state.update_data(district=district)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Отправьте фото товара (или /skip):")
        await state.set_state(AddAd.photo)
        await callback.answer()
    except (ValueError, IndexError):
        # Если произошла ошибка при обработке индекса
        await callback.answer("❌ Ошибка при выборе района. Попробуйте снова.")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Произошла ошибка. Пожалуйста, начните добавление объявления заново.")
        await state.clear()

@dp.message(AddAd.photo)
async def add_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    logging.info(f"Data in add_photo: {data}")
    
    # Проверяем наличие обязательных ключей
    if 'title' not in data or 'description' not in data or 'price' not in data:
        await message.answer("❌ Ошибка: данные объявления потеряны. Пожалуйста, начните добавление заново с /add")
        await state.clear()
        return
    
    photo_id = message.photo[-1].file_id if message.photo else None
    full_text = f"{data['title']}\n{data['description']}\nЦена: {data['price']}"
    is_clean = await moderate_with_deepseek(full_text)
    if is_clean:
        add_ad_to_db(
            title=data['title'],
            description=data['description'],
            price=data['price'],
            category=data['category'],
            age_group=data.get('age_group'),
            gender=data.get('gender'),
            condition=data.get('condition'),
            district=data.get('district', '📍 Другой район'),
            photo_id=photo_id,
            user_id=message.from_user.id,
            username=message.from_user.username or "NoUsername"
        )
        await message.answer("✅ Объявление прошло модерацию и опубликовано!", reply_markup=get_main_keyboard())
        
        # Отправляем уведомления подписчикам
        await notify_subscribers(
            category=data['category'],
            title=data['title'],
            description=data['description'],
            price=data['price'],
            username=message.from_user.username or "NoUsername",
            author_user_id=message.from_user.id,
            photo_id=photo_id
        )
        
        # Отправляем в общий чат, если CHAT_ID задан
        if CHAT_ID:
            await send_to_public_chat(
                title=data['title'],
                description=data['description'],
                price=data['price'],
                username=message.from_user.username or "NoUsername",
                district=data.get('district', '📍 Другой район'),
                photo_id=photo_id
            )
    else:
        await message.answer("❌ Объявление не прошло модерацию (содержит недопустимый контент).", reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(AddAd.photo, Command('skip'))
async def skip_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    full_text = f"{data['title']}\n{data['description']}\nЦена: {data['price']}"
    is_clean = await moderate_with_deepseek(full_text)
    if is_clean:
        add_ad_to_db(
            title=data['title'],
            description=data['description'],
            price=data['price'],
            category=data['category'],
            age_group=data.get('age_group'),
            gender=data.get('gender'),
            condition=data.get('condition'),
            district=data.get('district', '📍 Другой район'),
            photo_id=None,
            user_id=message.from_user.id,
            username=message.from_user.username or "NoUsername"
        )
        await message.answer("✅ Объявление прошло модерацию и опубликовано!", reply_markup=get_main_keyboard())
        
        # Отправляем уведомления подписчикам
        await notify_subscribers(
            category=data['category'],
            title=data['title'],
            description=data['description'],
            price=data['price'],
            username=message.from_user.username or "NoUsername",
            author_user_id=message.from_user.id,
            photo_id=None
        )
        
        # Отправляем в общий чат, если CHAT_ID задан
        if CHAT_ID:
            await send_to_public_chat(
                title=data['title'],
                description=data['description'],
                price=data['price'],
                username=message.from_user.username or "NoUsername",
                district=data.get('district', '📍 Другой район'),
                photo_id=None
            )
    else:
        await message.answer("❌ Объявление не прошло модерацию (содержит недопустимый контент).", reply_markup=get_main_keyboard())
    await state.clear()

# --- Команда /by_district (объявления по району) ---
@dp.message(Command('by_district'))
async def cmd_by_district(message: types.Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    for district in YAKUTSK_DISTRICTS:
        builder.button(text=district, callback_data=f"district_{district}")
    builder.adjust(1)
    await message.answer("Выберите район для просмотра:", reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data and c.data.startswith("district_"))
async def show_district(callback: types.CallbackQuery):
    district = callback.data.replace("district_", "")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT title, description, price, category, photo_id, username FROM ads WHERE district = ? ORDER BY id DESC", (district,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await callback.message.answer(f"В районе «{district}» пока нет объявлений.")
        await callback.answer()
        return

    for row in rows:
        text = f"<b>{row[0]}</b> [{row[3]}]\n{row[1]}\n💰 {row[2]} руб.\n👤 @{row[5]}\n📍 Район: {district}"
        if row[4]:
            await callback.message.answer_photo(photo=row[4], caption=text, parse_mode='HTML')
        else:
            await callback.message.answer(text, parse_mode='HTML')
    await callback.answer()
@dp.callback_query(lambda c: c.data and c.data.startswith("bydist_"))
async def show_district_ads(callback: types.CallbackQuery):
    """Показывает объявления выбранного района."""
    district = callback.data.replace("bydist_", "")
    ads = get_ads_by_district(district)
    
    if not ads:
        await callback.message.answer(f"📭 В районе «{district}» пока нет объявлений.")
        await callback.answer()
        return
    
    await callback.message.answer(f"📍 Объявления в районе: {district}")
    
    for ad in ads:
        # Добавляем информацию о районе в текст объявления
        text = f"<b>{ad['title']}</b> [{ad['category']}]\n📍 {ad['district']}\n{ad['description']}\n💰 {ad['price']} руб.\n👤 @{ad['username']}"
        keyboard = get_favorite_keyboard(callback.from_user.id, ad['id'])
        if ad['photo']:
            await callback.message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await callback.message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    
    await callback.answer()

# --- Команда /list (все объявления) ---
@dp.message(Command('list'))
async def cmd_list(message: types.Message, state: FSMContext):
    logging.info(f"Command /list from user {message.from_user.id}")
    await state.clear()
    ads = get_all_ads()
    if not ads:
        await message.answer("📭 Пока нет объявлений.", reply_markup=get_main_keyboard())
        return
    for ad in ads:
        text = format_ad_text(ad)
        keyboard = get_favorite_keyboard(message.from_user.id, ad['id'])
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    await message.answer("🔍 Что ищем дальше?", reply_markup=get_main_keyboard())

# --- Команда /categories ---
@dp.message(Command('categories'))
async def cmd_categories(message: types.Message, state: FSMContext):
    logging.info(f"Command /categories from user {message.from_user.id}")
    await state.clear()
    builder = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        builder.row(InlineKeyboardButton(text=cat, callback_data=f"show_{cat}"))
    await message.answer("Выберите категорию для просмотра объявлений:", reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data and c.data.startswith("show_"))
async def show_category_ads(callback: types.CallbackQuery):
    await callback.answer()
    category = callback.data.replace("show_", "")
    logging.info(f"Просмотр категории: {category}")
    
    # ВСЕГДА отправляем кнопки подписки, независимо от того, есть ли объявления в категории
    is_subscribed_status = is_subscribed(callback.from_user.id, category)
    builder = InlineKeyboardBuilder()
    if is_subscribed_status:
        builder.button(text="🔕 Отписаться", callback_data=f"sub_remove_{category}")
    else:
        builder.button(text="🔔 Подписаться", callback_data=f"sub_add_{category}")
    
    await callback.message.answer(
        f"Категория: {category}",
        reply_markup=builder.as_markup()
    )
    
    ads = get_ads_by_category(category)
    
    if not ads:
        await callback.message.answer(f"В категории «{category}» пока нет объявлений.")
        return
    
    await callback.message.answer(f"📂 Объявления в категории «{category}»:")
    for ad in ads:
        text = format_ad_text(ad)
        keyboard = get_favorite_keyboard(callback.from_user.id, ad['id'])
        if ad['photo']:
            await callback.message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await callback.message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    await callback.answer()

# --- Команда /myads (личный кабинет) ---
@dp.message(Command('myads'))
async def cmd_myads(message: types.Message, state: FSMContext):
    logging.info(f"Command /myads from user {message.from_user.id}")
    await state.clear()
    user_ads = get_user_ads(message.from_user.id)
    if not user_ads:
        await message.answer("📭 У вас пока нет объявлений.", reply_markup=get_main_keyboard())
        return
    for ad in user_ads:
        text = f"<b>{ad['title']}</b> [{ad['category']}]\n{ad['description']}\n💰 {ad['price']} руб."
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{ad['id']}"),
                    InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_{ad['id']}")
                ]
            ]
        )
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=kb)
        else:
            await message.answer(text, parse_mode='HTML', reply_markup=kb)
    await message.answer("Вот ваши объявления", reply_markup=get_main_keyboard())

# --- Редактирование ---
# --- Редактирование: выбор поля (должны быть выше общего обработчика) ---
@dp.callback_query(EditAd.choosing_field, lambda c: c.data == 'edit_title')
async def edit_title_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите новое название товара:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditAd.editing_title)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == 'edit_description')
async def edit_description_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите новое описание:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditAd.editing_description)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == 'edit_price')
async def edit_price_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите новую цену (только число):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditAd.editing_price)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == 'edit_category')
async def edit_category_start(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        builder.button(text=cat, callback_data=f"editcat_{cat}")
    builder.button(text="❌ Отмена", callback_data="edit_cancel")
    builder.adjust(1)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Выберите новую категорию:", reply_markup=builder.as_markup())
    await state.set_state(EditAd.editing_category)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == 'edit_photo')
async def edit_photo_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Отправьте новое фото (или /skip, чтобы оставить старое):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditAd.editing_photo)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == 'edit_cancel')
async def edit_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ Редактирование отменено.", reply_markup=get_main_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("edit_") and c.data.replace("edit_", "").isdigit() and len(c.data.split('_')) == 2)
async def edit_ad_start(callback: types.CallbackQuery, state: FSMContext):
    ad_id = int(callback.data.replace("edit_", ""))
    ad_data = get_ad_by_id(ad_id)
    if not ad_data:
        await callback.answer("❌ Объявление не найдено.")
        return
    if ad_data['user_id'] != callback.from_user.id:
        await callback.answer("❌ Это не ваше объявление.")
        return
    await state.clear()
    await state.update_data(edit_ad_id=ad_id, edit_ad_data=ad_data)
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Название", callback_data="edit_title")
    builder.button(text="📄 Описание", callback_data="edit_description")
    builder.button(text="💰 Цена", callback_data="edit_price")
    builder.button(text="🏷️ Категория", callback_data="edit_category")
    builder.button(text="🖼️ Фото", callback_data="edit_photo")
    builder.button(text="❌ Отмена", callback_data="edit_cancel")
    builder.adjust(1)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Что вы хотите изменить?", reply_markup=builder.as_markup())
    await state.set_state(EditAd.choosing_field)
    await callback.answer()

@dp.message(EditAd.editing_title)
async def edit_title_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    success = update_ad_field(ad_id, 'title', message.text)
    if success:
        await message.answer("✅ Название обновлено!", reply_markup=get_main_keyboard())
    else:
        await message.answer("❌ Ошибка при обновлении.", reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(EditAd.editing_description)
async def edit_description_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    success = update_ad_field(ad_id, 'description', message.text)
    if success:
        await message.answer("✅ Описание обновлено!", reply_markup=get_main_keyboard())
    else:
        await message.answer("❌ Ошибка при обновлении.", reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(EditAd.editing_price)
async def edit_price_finish(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите цену числом.")
        return
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    success = update_ad_field(ad_id, 'price', int(message.text))
    if success:
        await message.answer("✅ Цена обновлена!", reply_markup=get_main_keyboard())
    else:
        await message.answer("❌ Ошибка при обновлении.", reply_markup=get_main_keyboard())
    await state.clear()

@dp.callback_query(EditAd.editing_category, lambda c: c.data and c.data.startswith("editcat_"))
async def edit_category_finish(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("editcat_", "")
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    success = update_ad_field(ad_id, 'category', category)
    if success:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ Категория обновлена!", reply_markup=get_main_keyboard())
    else:
        await callback.message.answer("❌ Ошибка при обновлении.", reply_markup=get_main_keyboard())
    await state.clear()
    await callback.answer()

@dp.message(EditAd.editing_photo)
async def edit_photo_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    photo_id = message.photo[-1].file_id if message.photo else None
    if photo_id:
        success = update_ad_photo(ad_id, photo_id)
        if success:
            await message.answer("✅ Фото обновлено!", reply_markup=get_main_keyboard())
        else:
            await message.answer("❌ Ошибка при обновлении.", reply_markup=get_main_keyboard())
    else:
        await message.answer("❌ Фото не распознано. Попробуйте ещё раз или отправьте /skip.")
        return
    await state.clear()

@dp.message(EditAd.editing_photo, Command('skip'))
async def edit_photo_skip(message: types.Message, state: FSMContext):
    await message.answer("✅ Фото оставлено без изменений.", reply_markup=get_main_keyboard())
    await state.clear()

# --- Редактирование ---
# --- Редактирование: выбор поля (должны быть выше общего обработчика) ---
@dp.callback_query(EditAd.choosing_field, lambda c: c.data == 'edit_title')
async def edit_title_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите новое название товара:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditAd.editing_title)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == 'edit_description')
async def edit_description_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите новое описание:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditAd.editing_description)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == 'edit_price')
async def edit_price_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите новую цену (только число):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditAd.editing_price)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == 'edit_category')
async def edit_category_start(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        builder.button(text=cat, callback_data=f"editcat_{cat}")
    builder.button(text="❌ Отмена", callback_data="edit_cancel")
    builder.adjust(1)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Выберите новую категорию:", reply_markup=builder.as_markup())
    await state.set_state(EditAd.editing_category)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == 'edit_photo')
async def edit_photo_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Отправьте новое фото (или /skip, чтобы оставить старое):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditAd.editing_photo)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == 'edit_cancel')
async def edit_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ Редактирование отменено.", reply_markup=get_main_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("edit_") and c.data.replace("edit_", "").isdigit() and len(c.data.split('_')) == 2)
async def edit_ad_start(callback: types.CallbackQuery, state: FSMContext):
    ad_id = int(callback.data.replace("edit_", ""))
    ad_data = get_ad_by_id(ad_id)
    if not ad_data:
        await callback.answer("❌ Объявление не найдено.")
        return
    if ad_data['user_id'] != callback.from_user.id:
        await callback.answer("❌ Это не ваше объявление.")
        return
    await state.clear()
    await state.update_data(edit_ad_id=ad_id, edit_ad_data=ad_data)
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Название", callback_data="edit_title")
    builder.button(text="📄 Описание", callback_data="edit_description")
    builder.button(text="💰 Цена", callback_data="edit_price")
    builder.button(text="🏷️ Категория", callback_data="edit_category")
    builder.button(text="🖼️ Фото", callback_data="edit_photo")
    builder.button(text="❌ Отмена", callback_data="edit_cancel")
    builder.adjust(1)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Что вы хотите изменить?", reply_markup=builder.as_markup())
    await state.set_state(EditAd.choosing_field)
    await callback.answer()

@dp.message(EditAd.editing_title)
async def edit_title_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    success = update_ad_field(ad_id, 'title', message.text)
    if success:
        await message.answer("✅ Название обновлено!", reply_markup=get_main_keyboard())
    else:
        await message.answer("❌ Ошибка при обновлении.", reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(EditAd.editing_description)
async def edit_description_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    success = update_ad_field(ad_id, 'description', message.text)
    if success:
        await message.answer("✅ Описание обновлено!", reply_markup=get_main_keyboard())
    else:
        await message.answer("❌ Ошибка при обновлении.", reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(EditAd.editing_price)
async def edit_price_finish(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите цену числом.")
        return
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    success = update_ad_field(ad_id, 'price', int(message.text))
    if success:
        await message.answer("✅ Цена обновлена!", reply_markup=get_main_keyboard())
    else:
        await message.answer("❌ Ошибка при обновлении.", reply_markup=get_main_keyboard())
    await state.clear()

@dp.callback_query(EditAd.editing_category, lambda c: c.data and c.data.startswith("editcat_"))
async def edit_category_finish(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("editcat_", "")
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    success = update_ad_field(ad_id, 'category', category)
    if success:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ Категория обновлена!", reply_markup=get_main_keyboard())
    else:
        await callback.message.answer("❌ Ошибка при обновлении.", reply_markup=get_main_keyboard())
    await state.clear()
    await callback.answer()

@dp.message(EditAd.editing_photo)
async def edit_photo_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    photo_id = message.photo[-1].file_id if message.photo else None
    if photo_id:
        success = update_ad_photo(ad_id, photo_id)
        if success:
            await message.answer("✅ Фото обновлено!", reply_markup=get_main_keyboard())
        else:
            await message.answer("❌ Ошибка при обновлении.", reply_markup=get_main_keyboard())
    else:
        await message.answer("❌ Фото не распознано. Попробуйте ещё раз или отправьте /skip.")
        return
    await state.clear()

@dp.message(EditAd.editing_photo, Command('skip'))
async def edit_photo_skip(message: types.Message, state: FSMContext):
    await message.answer("✅ Фото оставлено без изменений.", reply_markup=get_main_keyboard())
    await state.clear()

# --- Удаление ---
@dp.callback_query(lambda c: c.data and c.data.startswith("del_"))
async def process_delete(callback: types.CallbackQuery, state: FSMContext):
    ad_id = int(callback.data.replace("del_", ""))
    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_del_{ad_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_del")
            ]
        ]
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Вы уверены, что хотите удалить это объявление?", reply_markup=confirm_kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("confirm_del_"))
async def confirm_delete(callback: types.CallbackQuery, state: FSMContext):
    ad_id = int(callback.data.replace("confirm_del_", ""))
    success = delete_ad_by_id(ad_id)
    if success:
        await callback.message.edit_text("✅ Объявление удалено.")
    else:
        await callback.message.edit_text("❌ Не удалось удалить объявление (возможно, оно уже удалено).")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cancel_del")
async def cancel_delete(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Удаление отменено.")
    await callback.answer()

# --- Команда /favorites ---
@dp.message(Command('favorites'))
async def cmd_favorites(message: types.Message, state: FSMContext):
    logging.info(f"Command /favorites from user {message.from_user.id}")
    await state.clear()
    favorites = get_user_favorites(message.from_user.id)
    if not favorites:
        await message.answer("⭐ У вас пока нет избранных объявлений.", reply_markup=get_main_keyboard())
        return
    await message.answer("⭐ Ваши избранные объявления:")
    for ad in favorites:
        text = format_ad_text(ad)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Удалить из избранного", callback_data=f"fav_remove_{ad['id']}")]]
        )
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    await message.answer("Вот ваши избранные объявления", reply_markup=get_main_keyboard())

# --- Команда /mysubs ---
@dp.message(Command('mysubs'))
async def cmd_mysubs(message: types.Message, state: FSMContext):
    logging.info(f"Command /mysubs from user {message.from_user.id}")
    await state.clear()
    subscriptions = get_user_subscriptions(message.from_user.id)
    if not subscriptions:
        await message.answer("🔔 Вы пока не подписаны ни на одну категорию.", reply_markup=get_main_keyboard())
        return
    
    text = "🔔 <b>Ваши подписки:</b>\n\n"
    for category in subscriptions:
        text += f"• {category}\n"
    
    # Создаём inline-кнопки для отписки
    builder = InlineKeyboardBuilder()
    for category in subscriptions:
        builder.button(text=f"❌ Отписаться от {category}", callback_data=f"sub_remove_{category}")
    builder.adjust(1)
    
    await message.answer(text, parse_mode='HTML', reply_markup=builder.as_markup())

# --- Обработчики избранного ---
@dp.callback_query(lambda c: c.data and c.data.startswith("fav_add_"))
async def add_to_favorites(callback: types.CallbackQuery):
    ad_id = int(callback.data.replace("fav_add_", ""))
    user_id = callback.from_user.id
    
    success = add_favorite(user_id, ad_id)
    if success:
        # Обновляем клавиатуру
        new_keyboard = get_favorite_keyboard(user_id, ad_id)
        try:
            if callback.message.photo:
                await callback.message.edit_reply_markup(reply_markup=new_keyboard)
            else:
                await callback.message.edit_reply_markup(reply_markup=new_keyboard)
            await callback.answer("✅ Добавлено в избранное!")
        except Exception as e:
            await callback.answer("✅ Добавлено в избранное!")
    else:
        await callback.answer("⚠️ Уже в избранном")

@dp.callback_query(lambda c: c.data and c.data.startswith("fav_remove_"))
async def remove_from_favorites(callback: types.CallbackQuery):
    ad_id = int(callback.data.replace("fav_remove_", ""))
    user_id = callback.from_user.id
    
    success = remove_favorite(user_id, ad_id)
    if success:
        # Если это сообщение из раздела избранного, удаляем его
        if "❌ Удалить из избранного" in callback.message.reply_markup.inline_keyboard[0][0].text:
            await callback.message.delete()
            await callback.answer("❌ Удалено из избранного")
        else:
            # Иначе обновляем клавиатуру
            new_keyboard = get_favorite_keyboard(user_id, ad_id)
            try:
                if callback.message.photo:
                    await callback.message.edit_reply_markup(reply_markup=new_keyboard)
                else:
                    await callback.message.edit_reply_markup(reply_markup=new_keyboard)
                await callback.answer("❌ Удалено из избранного")
            except Exception as e:
                await callback.answer("❌ Удалено из избранного")
    else:
        await callback.answer("⚠️ Не было в избранном")

# --- Обработчики подписок ---
@dp.callback_query(lambda c: c.data and c.data.startswith("sub_add_"))
async def add_subscription_handler(callback: types.CallbackQuery):
    category = callback.data.replace("sub_add_", "")
    user_id = callback.from_user.id
    
    success = add_subscription(user_id, category)
    if success:
        # Обновляем кнопку на "Отписаться"
        new_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔕 Отписаться", callback_data=f"sub_remove_{category}")]
        ])
        await callback.message.edit_reply_markup(reply_markup=new_kb)
        await callback.answer("✅ Вы подписались на категорию")
    else:
        await callback.answer("⚠️ Уже подписаны")

@dp.callback_query(lambda c: c.data and c.data.startswith("sub_remove_"))
async def remove_subscription_handler(callback: types.CallbackQuery):
    category = callback.data.replace("sub_remove_", "")
    user_id = callback.from_user.id
    
    success = remove_subscription(user_id, category)
    if success:
        # Обновляем кнопку на "Подписаться"
        new_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Подписаться", callback_data=f"sub_add_{category}")]
        ])
        await callback.message.edit_reply_markup(reply_markup=new_kb)
        await callback.answer("✅ Вы отписались от категории")
    else:
        await callback.answer("⚠️ Вы не были подписаны на эту категорию")

# --- Обработчики жалоб ---
@dp.callback_query(lambda c: c.data and c.data.startswith("complaint_") and not c.data.startswith("complaint_reason_"))
async def handle_complaint_button(callback: types.CallbackQuery):
    """Обработчик кнопки '⚠️ Пожаловаться'."""
    # Убираем префикс "complaint_" и получаем ID объявления
    ad_id_str = callback.data.replace("complaint_", "")
    try:
        ad_id = int(ad_id_str)
    except ValueError:
        await callback.answer("❌ Ошибка в данных жалобы.")
        return
    
    # Создаём клавиатуру с выбором причины
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Спам", callback_data=f"reason_{ad_id}_spam")
    builder.button(text="💰 Мошенничество", callback_data=f"reason_{ad_id}_fraud")
    builder.button(text="🤬 Оскорбления", callback_data=f"reason_{ad_id}_abuse")
    builder.button(text="📦 Другое", callback_data=f"reason_{ad_id}_other")
    builder.adjust(1)
    
    await callback.message.answer(
        "Выберите причину жалобы:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("reason_"))
async def handle_complaint_reason(callback: types.CallbackQuery):
    """Обработчик выбора причины жалобы."""
    # Разбираем callback_data: reason_<ad_id>_<reason>
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("❌ Ошибка в данных жалобы.")
        return
    
    ad_id = int(parts[1])
    reason_type = parts[2]
    
    # Маппинг причин на читаемые названия
    reason_map = {
        'spam': '🚫 Спам',
        'fraud': '💰 Мошенничество',
        'abuse': '🤬 Оскорбления',
        'other': '📦 Другое'
    }
    
    reason_text = reason_map.get(reason_type, '📦 Другое')
    
    # Добавляем жалобу в базу (асинхронно)
    complaint_id = await add_complaint(ad_id, callback.from_user.id, reason_text)
    
    if complaint_id:
        # Уведомляем пользователя
        await callback.message.edit_text("✅ Жалоба отправлена администратору. Спасибо за помощь!")
    else:
        await callback.message.edit_text("❌ Не удалось отправить жалобу. Попробуйте позже.")
    
    await callback.answer()

async def notify_admin_about_complaint(complaint_id):
    """Отправляет уведомление администратору о новой жалобе."""
    complaint = get_complaint_by_id(complaint_id)
    if not complaint:
        logging.error(f"Жалоба #{complaint_id} не найдена")
        return
    
    # Формируем текст уведомления
    text = (
        f"⚠️ *Новая жалоба*\n\n"
        f"🆔 Жалоба #{complaint['id']}\n"
        f"📌 Объявление #{complaint['ad_id']}\n"
        f"👤 Автор объявления: @{complaint['ad_username']} (id: {complaint['user_id']})\n"
        f"📝 Причина: {complaint['reason']}\n"
        f"🕐 Время: {complaint['created_at']}\n\n"
        f"📌 *Объявление:*\n"
        f"<b>{complaint['ad_title']}</b>\n"
        f"{complaint['ad_description']}\n"
        f"💰 {complaint['ad_price']} руб.\n"
        f"🏷️ Категория: {complaint['ad_category']}"
    )
    
    # Создаём inline-клавиатуру для админа
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Пометить решённой", callback_data=f"resolve_complaint_{complaint_id}"),
                InlineKeyboardButton(text="❌ Удалить объявление", callback_data=f"delete_ad_from_complaint_{complaint['ad_id']}_{complaint_id}")
            ],
            [
                InlineKeyboardButton(text="⏳ Оставить", callback_data=f"ignore_complaint_{complaint_id}")
            ]
        ]
    )
    
    try:
        # Отправляем уведомление админу
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
        logging.info(f"Уведомление о жалобе #{complaint_id} отправлено администратору")
    except Exception as e:
        logging.error(f"Ошибка отправки уведомления админу: {e}")

@dp.callback_query(lambda c: c.data and c.data.startswith("resolve_complaint_"))
async def handle_resolve_complaint(callback: types.CallbackQuery):
    """Обработчик кнопки '✅ Пометить решённой'."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Эта кнопка только для администратора.")
        return
    
    complaint_id = int(callback.data.replace("resolve_complaint_", ""))
    
    success = resolve_complaint(complaint_id)
    if success:
        await callback.message.edit_text(
            f"✅ Жалоба #{complaint_id} помечена как решённая.",
            reply_markup=None
        )
    else:
        await callback.message.edit_text(
            f"❌ Не удалось пометить жалобу как решённую.",
            reply_markup=None
        )
    
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("delete_ad_from_complaint_"))
async def handle_delete_ad_from_complaint(callback: types.CallbackQuery):
    """Обработчик кнопки '❌ Удалить объявление'."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Эта кнопка только для администратора.")
        return
    
    # Разбираем callback_data: delete_ad_from_complaint_<ad_id>_<complaint_id>
    parts = callback.data.split("_")
    if len(parts) < 6:
        await callback.answer("❌ Ошибка в данных.")
        return
    
    ad_id = int(parts[4])
    complaint_id = int(parts[5])
    
    # Получаем данные жалобы для уведомления автора
    complaint = get_complaint_by_id(complaint_id)
    if not complaint:
        await callback.answer("❌ Жалоба не найдена.")
        return
    
    # Получаем данные объявления для уведомления автора
    ad_data = get_ad_by_id(ad_id)
    if not ad_data:
        await callback.answer("❌ Объявление не найдено.")
        return
    
    # Удаляем объявление (каскадно удалятся и все жалобы на него)
    success = delete_ad_by_id(ad_id)
    if success:
        # Редактируем сообщение админу
        await callback.message.edit_text(
            f"❌ Объявление #{ad_id} удалено. Жалоба автоматически закрыта.",
            reply_markup=None
        )
        
        # Отправляем уведомление автору объявления
        try:
            await bot.send_message(
                chat_id=ad_data['user_id'],
                text=(
                    f"❌ Ваше объявление '{complaint['ad_title']}' удалено по жалобе пользователя.\n"
                    f"Причина: {complaint['reason']}.\n"
                    f"Если вы считаете это ошибкой, свяжитесь с поддержкой."
                )
            )
        except Exception as e:
            logging.error(f"Ошибка отправки уведомления автору объявления: {e}")
    else:
        await callback.message.edit_text(
            f"❌ Не удалось удалить объявление.",
            reply_markup=None
        )
    
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("delete_ad_complaint_"))
async def handle_delete_ad_complaint(callback: types.CallbackQuery):
    """Обработчик кнопки '❌ Удалить объявление' (альтернативный формат)."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Эта кнопка только для администратора.")
        return
    
    # Разбираем callback_data: delete_ad_complaint_<ad_id>_<complaint_id>
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer("❌ Ошибка в данных.")
        return
    
    ad_id = int(parts[3])
    complaint_id = int(parts[4])
    
    # Получаем данные жалобы для уведомления автора
    complaint = get_complaint_by_id(complaint_id)
    if not complaint:
        await callback.answer("❌ Жалоба не найдена.")
        return
    
    # Получаем данные объявления для уведомления автора
    ad_data = get_ad_by_id(ad_id)
    if not ad_data:
        await callback.answer("❌ Объявление не найдено.")
        return
    
    # Удаляем объявление (каскадно удалятся и все жалобы на него)
    success = delete_ad_by_id(ad_id)
    if success:
        # Редактируем сообщение админу
        await callback.message.edit_text(
            f"❌ Объявление #{ad_id} удалено. Жалоба автоматически закрыта.",
            reply_markup=None
        )
        
        # Отправляем уведомление автору объявления
        try:
            await bot.send_message(
                chat_id=ad_data['user_id'],
                text=(
                    f"❌ Ваше объявление '{complaint['ad_title']}' удалено по жалобе пользователя.\n"
                    f"Причина: {complaint['reason']}.\n"
                    f"Если вы считаете это ошибкой, свяжитесь с поддержкой."
                )
            )
        except Exception as e:
            logging.error(f"Ошибка отправки уведомления автору объявления: {e}")
    else:
        await callback.message.edit_text(
            f"❌ Не удалось удалить объявление.",
            reply_markup=None
        )
    
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("ignore_complaint_"))
async def handle_ignore_complaint(callback: types.CallbackQuery):
    """Обработчик кнопки '⏳ Оставить'."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Эта кнопка только для администратора.")
        return

    complaint_id = int(callback.data.replace("ignore_complaint_", ""))
    
    # Просто удаляем клавиатуру
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("✅ Клавиатура удалена.")

# --- Команда /complaints для админа ---
@dp.message(Command('complaints'))
async def cmd_complaints(message: types.Message, state: FSMContext):
    """Показывает список нерассмотренных жалоб для админа.""" 
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Эта команда только для администратора.", reply_markup=get_main_keyboard())
        return
    
    await state.clear()
    complaints = get_new_complaints(limit=10)
    
    if not complaints:
        await message.answer("📭 Нет нерассмотренных жалоб.", reply_markup=get_main_keyboard())
        return
    
    text = "⚠️ *Нерассмотренные жалобы:*\n\n"
    for i, complaint in enumerate(complaints, 1):
        text += (
            f"{i}. Жалоба #{complaint['id']}\n"
            f"   Объявление: {complaint['ad_title'][:30]}...\n"
            f"   Причина: {complaint['reason']}\n"
            f"   Время: {complaint['created_at'][:16]}\n\n"
        )
    
    # Создаём inline-кнопки для быстрого перехода
    builder = InlineKeyboardBuilder()
    for complaint in complaints[:5]:  # Ограничиваем 5 кнопками
        builder.button(
            text=f"Жалоба #{complaint['id']}",
            callback_data=f"show_complaint_{complaint['id']}"
        )
    builder.adjust(1)
    
    await message.answer(text, parse_mode='HTML', reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data and c.data.startswith("show_complaint_"))
async def handle_show_complaint(callback: types.CallbackQuery):
    """Показывает детали конкретной жалобы."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Эта кнопка только для администратора.")
        return
    
    complaint_id = int(callback.data.replace("show_complaint_", ""))
    complaint = get_complaint_by_id(complaint_id)
    
    if not complaint:
        await callback.answer("❌ Жалоба не найдена.")
        return
    
    text = (
        f"⚠️ *Детали жалобы #{complaint_id}*\n\n"
        f"🆔 Объявление #{complaint['ad_id']}\n"
        f"👤 Пользователь: @{complaint['ad_username']} (id: {complaint['user_id']})\n"
        f"📝 Причина: {complaint['reason']}\n"
        f"📅 Время: {complaint['created_at']}\n"
        f"📊 Статус: {complaint['status']}\n\n"
        f"📌 *Объявление:*\n"
        f"{complaint['ad_title']}\n"
        f"{complaint['ad_description']}\n"
        f"💰 {complaint['ad_price']} руб.\n"
        f"Категория: {complaint['ad_category']}"
    )
    
    # Создаём клавиатуру для управления жалобой
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Пометить решённой", callback_data=f"resolve_complaint_{complaint_id}"),
                InlineKeyboardButton(text="❌ Удалить объявление", callback_data=f"delete_ad_from_complaint_{complaint['ad_id']}_{complaint_id}")
            ],
            [
                InlineKeyboardButton(text="⏳ Оставить", callback_data=f"ignore_complaint_{complaint_id}")
            ]
        ]
    )
    
    await callback.message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    await callback.answer()

# --- Функция отправки уведомлений подписчикам ---
async def notify_subscribers(category, title, description, price, username, author_user_id=None, photo_id=None):
    """Отправляет уведомления всем подписчикам категории (кроме автора)."""
    subscribers = get_subscribers_for_category(category)
    if not subscribers:
        return
    
    # Исключаем автора из списка получателей
    if author_user_id is not None:
        subscribers = [user_id for user_id in subscribers if user_id != author_user_id]
    
    if not subscribers:
        return
    
    notification_text = (
        f"🔔 Новое объявление в категории {category}:\n\n"
        f"<b>{title}</b>\n"
        f"{description}\n"
        f"💰 {price} руб.\n"
        f"Автор: @{username}"
    )
    
    for user_id in subscribers:
        try:
            if photo_id:
                await bot.send_photo(
                    chat_id=user_id,
                    photo=photo_id,
                    caption=notification_text,
                    parse_mode='HTML'
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=notification_text,
                    parse_mode='HTML'
                )
        except Exception as e:
            logging.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

# --- Функция отправки в общий чат ---
async def send_to_public_chat(title, description, price, username, district, photo_id=None):
    """Отправляет сообщение о новом объявлении в общий чат."""
    if not CHAT_ID:
        return
    
    text = (
        f"📢 Новое объявление:\n\n"
        f"<b>{title}</b>\n"
        f"{description}\n"
        f"💰 {price} руб.\n"
        f"👤 @{username}\n"
        f"📍 {district}"
    )
    
    # Получаем username бота
    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username
    except Exception as e:
        logging.error(f"Ошибка получения username бота: {e}")
        bot_username = "your_bot_username"
    
    # Создаём кнопку-ссылку на бота
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Перейти в бот", url=f"https://t.me/{bot_username}")]
        ]
    )
    
    try:
        if photo_id:
            await bot.send_photo(
                chat_id=CHAT_ID,
                photo=photo_id,
                caption=text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        else:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        logging.info(f"Сообщение о новом объявлении отправлено в чат {CHAT_ID}")
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения в общий чат: {e}")

# --- Запуск бота ---
async def main():
    proxy_url = os.getenv('PROXY_URL')  # например, socks5://127.0.0.1:1080
    if proxy_url:
        connector = ProxyConnector.from_url(proxy_url)
        bot_with_proxy = Bot(token=API_TOKEN, connector=connector)
        logging.info(f"Using proxy: {proxy_url}")
    else:
        bot_with_proxy = Bot(token=API_TOKEN)
    
    await bot_with_proxy.delete_webhook()
    logging.info("Webhook удалён, запускаем polling...")
    await dp.start_polling(bot_with_proxy)

if __name__ == '__main__':
    asyncio.run(main())
