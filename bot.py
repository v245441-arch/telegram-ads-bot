import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
import openai

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# --- Переменные окружения (обязательно задать на Railway) ---
API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY не задан!")

ADMIN_ID = os.getenv('ADMIN_ID')
if not ADMIN_ID:
    raise ValueError("ADMIN_ID не задан! Укажите ID администратора.")
ADMIN_ID = int(ADMIN_ID)

# --- Настройка DeepSeek (совместим с OpenAI) ---
openai.api_key = DEEPSEEK_API_KEY
openai.base_url = "https://api.deepseek.com/v1/"

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- Список категорий ---
CATEGORIES = [
    "🏠 Недвижимость",
    "🚗 Транспорт",
    "📱 Электроника",
    "👗 Одежда",
    "🔧 Услуги",
    "📦 Другое"
]

# --- Работа с базой данных SQLite ---
DB_PATH = "ads.db"

def init_db():
    """Создаёт таблицу объявлений и избранного, если их нет."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                price INTEGER NOT NULL,
                category TEXT NOT NULL,
                photo_id TEXT,
                user_id INTEGER NOT NULL,
                username TEXT
            )
        """)
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
        conn.commit()

def add_ad_to_db(title, description, price, category, photo_id, user_id, username):
    """Добавляет новое объявление в базу."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ads (title, description, price, category, photo_id, user_id, username)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title, description, price, category, photo_id, user_id, username))
        conn.commit()
        return cursor.lastrowid

def get_all_ads():
    """Возвращает список всех объявлений."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, description, price, category, photo_id, username FROM ads ORDER BY id DESC")
        rows = cursor.fetchall()
        ads = []
        for row in rows:
            ads.append({
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'price': row[3],
                'category': row[4],
                'photo': row[5],
                'username': row[6]
            })
        return ads

def get_ads_by_category(category):
    """Возвращает объявления указанной категории."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, description, price, category, photo_id, username FROM ads WHERE category = ? ORDER BY id DESC", (category,))
        rows = cursor.fetchall()
        ads = []
        for row in rows:
            ads.append({
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'price': row[3],
                'category': row[4],
                'photo': row[5],
                'username': row[6]
            })
        return ads

def search_ads(keyword):
    """Ищет объявления по ключевому слову в названии и описании."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        pattern = f"%{keyword}%"
        cursor.execute("""
            SELECT id, title, description, price, category, photo_id, username 
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
                'photo': row[5],
                'username': row[6]
            })
        return ads

def get_user_ads(user_id):
    """Возвращает объявления конкретного пользователя."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, description, price, category, photo_id FROM ads WHERE user_id = ? ORDER BY id DESC", (user_id,))
        rows = cursor.fetchall()
        ads = []
        for row in rows:
            ads.append({
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'price': row[3],
                'category': row[4],
                'photo': row[5]
            })
        return ads

def get_ad_by_id(ad_id):
    """Возвращает данные объявления по ID (для редактирования)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, description, price, category, photo_id, user_id FROM ads WHERE id = ?", (ad_id,))
        row = cursor.fetchone()
        if row:
            return {
                'title': row[0],
                'description': row[1],
                'price': row[2],
                'category': row[3],
                'photo': row[4],
                'user_id': row[5]
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
            SELECT a.id, a.title, a.description, a.price, a.category, a.photo_id, a.username
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
                'photo': row[5],
                'username': row[6]
            })
        return ads

def is_favorite(user_id, ad_id):
    """Проверяет, находится ли объявление в избранном у пользователя."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM favorites WHERE user_id = ? AND ad_id = ?", (user_id, ad_id))
        return cursor.fetchone() is not None

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
def get_main_keyboard():
    """Главное меню с кнопками команд."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Список объявлений")],
            [KeyboardButton(text="➕ Добавить объявление")],
            [KeyboardButton(text="📁 Категории"), KeyboardButton(text="👤 Мои объявления")],
            [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="⭐ Избранное")],
            [KeyboardButton(text="📊 Статистика")]
        ],
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
    """Создаёт inline-клавиатуру с кнопкой избранного."""
    is_fav = is_favorite(user_id, ad_id)
    if is_fav:
        button = InlineKeyboardButton(text="✅ В избранном", callback_data=f"fav_remove_{ad_id}")
    else:
        button = InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_add_{ad_id}")
    return InlineKeyboardMarkup(inline_keyboard=[[button]])

# --- Состояния FSM для добавления ---
class AddAd(StatesGroup):
    title = State()
    description = State()
    price = State()
    category = State()
    photo = State()

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

# --- Команда /start ---
@dp.message(Command('start'))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать в доску объявлений!\n"
        "Используйте кнопки ниже для навигации.",
        reply_markup=get_main_keyboard()
    )
    if message.from_user.id == ADMIN_ID:
        await message.answer("🔧 Вы администратор. Статистика доступна.")

# --- Команда /stats (только для админа) ---
@dp.message(Command('stats'))
async def cmd_stats(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Эта команда только для администратора.", reply_markup=get_main_keyboard())
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
        await message.answer("🚪 Вы вышли из режима поиска.", reply_markup=get_main_keyboard())
    else:
        await message.answer("❓ Вы не в режиме поиска.", reply_markup=get_main_keyboard())

# --- Обработчики кнопок главного меню ---
@dp.message(lambda message: message.text == "📋 Список объявлений")
async def handle_list_button(message: types.Message, state: FSMContext):
    await state.clear()
    ads = get_all_ads()
    if not ads:
        await message.answer("📭 Пока нет объявлений.", reply_markup=get_main_keyboard())
        return
    for ad in ads:
        text = f"<b>{ad['title']}</b> [{ad['category']}]\n{ad['description']}\n💰 {ad['price']} руб.\n👤 @{ad['username']}"
        keyboard = get_favorite_keyboard(message.from_user.id, ad['id'])
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    await message.answer("🔍 Что ищем дальше?", reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "➕ Добавить объявление")
async def handle_add_button(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Введите название товара:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(AddAd.title)

@dp.message(lambda message: message.text == "📁 Категории")
async def handle_categories_button(message: types.Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        builder.button(text=cat, callback_data=f"show_{cat}")
    builder.adjust(1)
    await message.answer(
        "Выберите категорию для просмотра:",
        reply_markup=builder.as_markup()
    )

@dp.message(lambda message: message.text == "👤 Мои объявления")
async def handle_myads_button(message: types.Message, state: FSMContext):
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
        await message.answer("⭐ У вас пока нет избранных объявлений.", reply_markup=get_main_keyboard())
        return
    await message.answer("⭐ Ваши избранные объявления:")
    for ad in favorites:
        text = f"<b>{ad['title']}</b> [{ad['category']}]\n{ad['description']}\n💰 {ad['price']} руб.\n👤 @{ad['username']}"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Удалить из избранного", callback_data=f"fav_remove_{ad['id']}")]]
        )
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    await message.answer("Вот ваши избранные объявления", reply_markup=get_main_keyboard())

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
    await state.clear()
    await message.answer("Введите название товара:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(AddAd.title)

@dp.message(AddAd.title)
async def add_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Теперь введите описание:")
    await state.set_state(AddAd.description)

@dp.message(AddAd.description)
async def add_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите цену (только число):")
    await state.set_state(AddAd.price)

@dp.message(AddAd.price)
async def add_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите цену числом.")
        return
    await state.update_data(price=int(message.text))
    builder = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        builder.button(text=cat, callback_data=f"cat_{cat}")
    builder.adjust(1)
    await message.answer("Выберите категорию:", reply_markup=builder.as_markup())
    await state.set_state(AddAd.category)

@dp.callback_query(AddAd.category)
async def choose_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("cat_", "")
    await state.update_data(category=category)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Отправьте фото товара (или /skip):")
    await state.set_state(AddAd.photo)
    await callback.answer()

@dp.message(AddAd.photo)
async def add_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = message.photo[-1].file_id if message.photo else None
    full_text = f"{data['title']}\n{data['description']}\nЦена: {data['price']}"
    is_clean = await moderate_with_deepseek(full_text)
    if is_clean:
        add_ad_to_db(
            title=data['title'],
            description=data['description'],
            price=data['price'],
            category=data['category'],
            photo_id=photo_id,
            user_id=message.from_user.id,
            username=message.from_user.username or "NoUsername"
        )
        await message.answer("✅ Объявление прошло модерацию и опубликовано!", reply_markup=get_main_keyboard())
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
            photo_id=None,
            user_id=message.from_user.id,
            username=message.from_user.username or "NoUsername"
        )
        await message.answer("✅ Объявление прошло модерацию и опубликовано!", reply_markup=get_main_keyboard())
    else:
        await message.answer("❌ Объявление не прошло модерацию (содержит недопустимый контент).", reply_markup=get_main_keyboard())
    await state.clear()

# --- Команда /list (все объявления) ---
@dp.message(Command('list'))
async def cmd_list(message: types.Message, state: FSMContext):
    await state.clear()
    ads = get_all_ads()
    if not ads:
        await message.answer("📭 Пока нет объявлений.", reply_markup=get_main_keyboard())
        return
    for ad in ads:
        text = f"<b>{ad['title']}</b> [{ad['category']}]\n{ad['description']}\n💰 {ad['price']} руб.\n👤 @{ad['username']}"
        keyboard = get_favorite_keyboard(message.from_user.id, ad['id'])
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    await message.answer("🔍 Что ищем дальше?", reply_markup=get_main_keyboard())

# --- Команда /categories ---
@dp.message(Command('categories'))
async def cmd_categories(message: types.Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        builder.button(text=cat, callback_data=f"show_{cat}")
    builder.adjust(1)
    await message.answer("Выберите категорию для просмотра:", reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data and c.data.startswith("show_"))
async def show_category(callback: types.CallbackQuery):
    category = callback.data.replace("show_", "")
    ads = get_ads_by_category(category)
    if not ads:
        await callback.message.answer(f"В категории «{category}» пока нет объявлений.")
        await callback.answer()
        return
    for ad in ads:
        text = f"<b>{ad['title']}</b>\n{ad['description']}\n💰 {ad['price']} руб.\n👤 @{ad['username']}"
        keyboard = get_favorite_keyboard(callback.from_user.id, ad['id'])
        if ad['photo']:
            await callback.message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await callback.message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    await callback.answer()

# --- Команда /myads (личный кабинет) ---
@dp.message(Command('myads'))
async def cmd_myads(message: types.Message, state: FSMContext):
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
@dp.callback_query(lambda c: c.data and c.data.startswith("edit_"))
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

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == "edit_title")
async def edit_title_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите новое название товара:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditAd.editing_title)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == "edit_description")
async def edit_description_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите новое описание:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditAd.editing_description)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == "edit_price")
async def edit_price_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите новую цену (только число):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditAd.editing_price)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == "edit_category")
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

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == "edit_photo")
async def edit_photo_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Отправьте новое фото (или /skip, чтобы оставить старое):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditAd.editing_photo)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == "edit_cancel")
async def edit_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ Редактирование отменено.", reply_markup=get_main_keyboard())
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
        await callback.message.edit_text("✅ Объявление удалено.", reply_markup=get_main_keyboard())
    else:
        await callback.message.edit_text("❌ Не удалось удалить объявление (возможно, оно уже удалено).", reply_markup=get_main_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cancel_del")
async def cancel_delete(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Удаление отменено.", reply_markup=get_main_keyboard())
    await callback.answer()

# --- Команда /favorites ---
@dp.message(Command('favorites'))
async def cmd_favorites(message: types.Message, state: FSMContext):
    await state.clear()
    favorites = get_user_favorites(message.from_user.id)
    if not favorites:
        await message.answer("⭐ У вас пока нет избранных объявлений.", reply_markup=get_main_keyboard())
        return
    await message.answer("⭐ Ваши избранные объявления:")
    for ad in favorites:
        text = f"<b>{ad['title']}</b> [{ad['category']}]\n{ad['description']}\n💰 {ad['price']} руб.\n👤 @{ad['username']}"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Удалить из избранного", callback_data=f"fav_remove_{ad['id']}")]]
        )
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    await message.answer("Вот ваши избранные объявления", reply_markup=get_main_keyboard())

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

# --- Запуск бота ---
async def main():
    await bot.delete_webhook()
    logging.info("Webhook удалён, запускаем polling...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
