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
    """Создаёт таблицу объявлений."""
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
    """Добавляет новое объявление в базу (по умолчанию approved = 0)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ads (title, description, price, category, photo_id, user_id, username, approved)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (title, description, price, category, photo_id, user_id, username))
        conn.commit()
        return cursor.lastrowid

def get_all_ads():
    """Возвращает список всех объявлений (без ID, но с категорией)."""
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
    """Возвращает объявления указанной категории."""
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

def get_ads_by_user(user_id):
    """Возвращает объявления конкретного пользователя (включая ID для удаления)."""
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

def delete_ad_by_id(ad_id):
    """Удаляет объявление по его ID."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ads WHERE id = ?", (ad_id,))
        conn.commit()
        return cursor.rowcount > 0  # вернёт True, если удалена хотя бы одна запись

# Инициализируем БД при запуске
init_db()

# --- Состояния FSM ---
class AddAd(StatesGroup):
    title = State()
    description = State()
    price = State()
    category = State()
    photo = State()

# --- Команда /start ---
@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот-доска объявлений.\n"
        "/add — добавить объявление\n"
        "/list — показать все объявления\n"
        "/categories — показать объявления по категориям\n"
        "/myads — мои объявления"
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
    ad_id = add_ad_to_db(
        title=data['title'],
        description=data['description'],
        price=data['price'],
        category=data['category'],
        photo_id=photo_id,
        user_id=message.from_user.id,
        username=message.from_user.username or "NoUsername"
    )
    await message.answer("✅ Объявление добавлено! (ID: {})".format(ad_id))
    await state.clear()

@dp.message(AddAd.photo, Command('skip'))
async def skip_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ad_id = add_ad_to_db(
        title=data['title'],
        description=data['description'],
        price=data['price'],
        category=data['category'],
        photo_id=None,
        user_id=message.from_user.id,
        username=message.from_user.username or "NoUsername"
    )
    await message.answer("✅ Объявление добавлено без фото! (ID: {})".format(ad_id))
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

# --- Команда /myads (личный кабинет) ---
@dp.message(Command('myads'))
async def cmd_myads(message: types.Message):
    user_ads = get_ads_by_user(message.from_user.id)
    if not user_ads:
        await message.answer("📭 У вас пока нет объявлений.")
        return

    for ad in user_ads:
        text = f"<b>{ad['title']}</b> [{ad['category']}]\n{ad['description']}\n💰 {ad['price']} руб."
        # Кнопка удаления
        delete_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_{ad['id']}")]
            ]
        )
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML', reply_markup=delete_kb)
        else:
            await message.answer(text, parse_mode='HTML', reply_markup=delete_kb)

# --- Обработчик удаления ---
@dp.callback_query(lambda c: c.data and c.data.startswith("del_"))
async def process_delete(callback: types.CallbackQuery):
    ad_id = int(callback.data.replace("del_", ""))

    # Подтверждение удаления
    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_del_{ad_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_del")
            ]
        ]
    )
    await callback.message.edit_reply_markup(reply_markup=None)  # убираем старую клавиатуру
    await callback.message.answer("Вы уверены, что хотите удалить это объявление?", reply_markup=confirm_kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("confirm_del_"))
async def confirm_delete(callback: types.CallbackQuery):
    ad_id = int(callback.data.replace("confirm_del_", ""))
    success = delete_ad_by_id(ad_id)
    if success:
        await callback.message.edit_text("✅ Объявление удалено.")
    else:
        await callback.message.edit_text("❌ Не удалось удалить объявление (возможно, оно уже удалено).")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cancel_del")
async def cancel_delete(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Удаление отменено.")
    await callback.answer()

# --- Запуск бота ---
async def main():
    await bot.delete_webhook()
    logging.info("Webhook удалён, запускаем polling...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
