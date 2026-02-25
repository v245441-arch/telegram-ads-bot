import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")

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

# --- Работа с базой данных ---
DB_PATH = "ads.db"

def init_db():
    """Создаёт таблицу объявлений с полем category."""
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

def get_all_ads():
    """Возвращает список всех объявлений."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, description, price, category, photo_id, username FROM ads ORDER BY id DESC")
        rows = cursor.fetchall()
        ads = []
        for row in rows:
            ads.append({
                'title': row[0],
                'description': row[1],
                'price': row[2],
                'category': row[3],
                'photo': row[4],
                'username': row[5]
            })
        return ads

def get_ads_by_category(category):
    """Возвращает объявления только указанной категории."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, description, price, category, photo_id, username FROM ads WHERE category = ? ORDER BY id DESC", (category,))
        rows = cursor.fetchall()
        ads = []
        for row in rows:
            ads.append({
                'title': row[0],
                'description': row[1],
                'price': row[2],
                'category': row[3],
                'photo': row[4],
                'username': row[5]
            })
        return ads

# Инициализируем БД при запуске
init_db()

# --- Состояния FSM ---
class AddAd(StatesGroup):
    title = State()
    description = State()
    price = State()
    category = State()   # новое состояние для выбора категории
    photo = State()

# --- Команда /start ---
@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот-доска объявлений.\n"
        "/add — добавить объявление\n"
        "/list — показать все объявления\n"
        "/categories — показать объявления по категориям"
    )

# --- Команда /add ---
@dp.message(Command('add'))
async def cmd_add(message: types.Message, state: FSMContext):
    await message.answer("Введите название товара:")
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

    # Показываем inline-кнопки с категориями
    builder = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        builder.button(text=cat, callback_data=f"cat_{cat}")
    builder.adjust(1)  # по одной кнопке в ряд
    await message.answer("Выберите категорию:", reply_markup=builder.as_markup())
    await state.set_state(AddAd.category)

# --- Обработчик выбора категории (callback) ---
@dp.callback_query(AddAd.category)
async def choose_category(callback: types.CallbackQuery, state: FSMContext):
    # Из callback_data получаем название категории (оно после "cat_")
    category = callback.data.replace("cat_", "")
    await state.update_data(category=category)
    await callback.message.edit_reply_markup(reply_markup=None)  # убираем кнопки
    await callback.message.answer("Отправьте фото товара (или /skip):")
    await state.set_state(AddAd.photo)
    await callback.answer()

# --- Обработчик фото ---
@dp.message(AddAd.photo)
async def add_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = message.photo[-1].file_id if message.photo else None
    add_ad_to_db(
        title=data['title'],
        description=data['description'],
        price=data['price'],
        category=data['category'],
        photo_id=photo_id,
        user_id=message.from_user.id,
        username=message.from_user.username or "NoUsername"
    )
    await message.answer("✅ Объявление добавлено!")
    await state.clear()

@dp.message(AddAd.photo, Command('skip'))
async def skip_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    add_ad_to_db(
        title=data['title'],
        description=data['description'],
        price=data['price'],
        category=data['category'],
        photo_id=None,
        user_id=message.from_user.id,
        username=message.from_user.username or "NoUsername"
    )
    await message.answer("✅ Объявление добавлено без фото.")
    await state.clear()

# --- Команда /list (все объявления) ---
@dp.message(Command('list'))
async def cmd_list(message: types.Message):
    ads = get_all_ads()
    if not ads:
        await message.answer("📭 Пока нет объявлений.")
        return
    for ad in ads:
        text = f"<b>{ad['title']}</b> [{ad['category']}]\n{ad['description']}\n💰 {ad['price']} руб.\n👤 @{ad['username']}"
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML')
        else:
            await message.answer(text, parse_mode='HTML')

# --- Команда /categories ---
@dp.message(Command('categories'))
async def cmd_categories(message: types.Message):
    builder = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        builder.button(text=cat, callback_data=f"show_{cat}")
    builder.adjust(1)
    await message.answer("Выберите категорию для просмотра:", reply_markup=builder.as_markup())

# --- Обработчик показа объявлений по категории ---
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
        if ad['photo']:
            await callback.message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML')
        else:
            await callback.message.answer(text, parse_mode='HTML')
    await callback.answer()

# --- Запуск бота ---
async def main():
    await bot.delete_webhook()
    logging.info("Webhook удалён, запускаем polling...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
