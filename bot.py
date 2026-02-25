import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- Работа с базой данных ---
DB_PATH = "ads.db"

def init_db():
    """Создаёт таблицу объявлений, если её нет."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                price INTEGER NOT NULL,
                photo_id TEXT,
                user_id INTEGER NOT NULL,
                username TEXT
            )
        """)
        conn.commit()

def add_ad_to_db(title, description, price, photo_id, user_id, username):
    """Добавляет новое объявление в базу."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ads (title, description, price, photo_id, user_id, username)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, description, price, photo_id, user_id, username))
        conn.commit()

def get_all_ads():
    """Возвращает список всех объявлений."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, description, price, photo_id, username FROM ads ORDER BY id DESC")
        rows = cursor.fetchall()
        ads = []
        for row in rows:
            ads.append({
                'title': row[0],
                'description': row[1],
                'price': row[2],
                'photo': row[3],
                'username': row[4]
            })
        return ads

# Инициализируем БД при запуске
init_db()

# --- Состояния FSM (те же) ---
class AddAd(StatesGroup):
    title = State()
    description = State()
    price = State()
    photo = State()

# --- Команды ---
@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот-доска объявлений.\n"
        "/add — добавить объявление\n"
        "/list — показать все объявления"
    )

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
    await message.answer("Отправьте фото товара (или /skip):")
    await state.set_state(AddAd.photo)

@dp.message(AddAd.photo)
async def add_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = message.photo[-1].file_id if message.photo else None
    # Сохраняем в базу
    add_ad_to_db(
        title=data['title'],
        description=data['description'],
        price=data['price'],
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
        photo_id=None,
        user_id=message.from_user.id,
        username=message.from_user.username or "NoUsername"
    )
    await message.answer("✅ Объявление добавлено без фото.")
    await state.clear()

@dp.message(Command('list'))
async def cmd_list(message: types.Message):
    ads = get_all_ads()
    if not ads:
        await message.answer("📭 Пока нет объявлений.")
        return
    for ad in ads:
        text = f"<b>{ad['title']}</b>\n{ad['description']}\n💰 {ad['price']} руб.\n👤 @{ad['username']}"
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML')
        else:
            await message.answer(text, parse_mode='HTML')

async def main():
    # Удаляем вебхук перед запуском polling
    await bot.delete_webhook()
    logging.info("Webhook удалён, запускаем polling...")
    await dp.start_polling(bot)

if __name__ == '__main__':
 asyncio.run(main())
