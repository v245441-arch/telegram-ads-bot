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
import openai

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота из переменных окружения
API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")

# Ключ DeepSeek API
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY не задан!")

# Настройка клиента DeepSeek (совместим с OpenAI)
openai.api_key = DEEPSEEK_API_KEY
# ВАЖНО: base_url должен оканчиваться на слеш, чтобы корректно формировался /v1/chat/completions
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
    """Создаёт таблицу объявлений, если её нет."""
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
        return cursor.lastrowid

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
        logging.info(f"Полный ответ AI: {full_answer}")  # отладка
        logging.info(f"Текст объявления: {text}")       # отладка
        return first_word == "ok"
    except Exception as e:
        logging.error(f"Ошибка DeepSeek API: {e}")
        return False

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

# --- Добавление объявления с AI-модерацией ---
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
        await message.answer("✅ Объявление прошло модерацию и опубликовано!")
    else:
        await message.answer("❌ Объявление не прошло модерацию (содержит недопустимый контент).")
    
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
        await message.answer("✅ Объявление прошло модерацию и опубликовано!")
    else:
        await message.answer("❌ Объявление не прошло модерацию (содержит недопустимый контент).")
    
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
    user_ads = get_user_ads(message.from_user.id)
    if not user_ads:
        await message.answer("📭 У вас пока нет объявлений.")
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
    await callback.message.answer("Введите новое название товара:")
    await state.set_state(EditAd.editing_title)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == "edit_description")
async def edit_description_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите новое описание:")
    await state.set_state(EditAd.editing_description)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == "edit_price")
async def edit_price_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите новую цену (только число):")
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
    await callback.message.answer("Отправьте новое фото (или /skip, чтобы оставить старое):")
    await state.set_state(EditAd.editing_photo)
    await callback.answer()

@dp.callback_query(EditAd.choosing_field, lambda c: c.data == "edit_cancel")
async def edit_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ Редактирование отменено.")
    await callback.answer()

@dp.message(EditAd.editing_title)
async def edit_title_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    success = update_ad_field(ad_id, 'title', message.text)
    if success:
        await message.answer("✅ Название обновлено!")
    else:
        await message.answer("❌ Ошибка при обновлении.")
    await state.clear()

@dp.message(EditAd.editing_description)
async def edit_description_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    success = update_ad_field(ad_id, 'description', message.text)
    if success:
        await message.answer("✅ Описание обновлено!")
    else:
        await message.answer("❌ Ошибка при обновлении.")
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
        await message.answer("✅ Цена обновлена!")
    else:
        await message.answer("❌ Ошибка при обновлении.")
    await state.clear()

@dp.callback_query(EditAd.editing_category, lambda c: c.data and c.data.startswith("editcat_"))
async def edit_category_finish(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("editcat_", "")
    data = await state.get_data()
    ad_id = data['edit_ad_id']
    success = update_ad_field(ad_id, 'category', category)
    if success:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ Категория обновлена!")
    else:
        await callback.message.answer("❌ Ошибка при обновлении.")
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
            await message.answer("✅ Фото обновлено!")
        else:
            await message.answer("❌ Ошибка при обновлении.")
    else:
        await message.answer("❌ Фото не распознано. Попробуйте ещё раз или отправьте /skip.")
        return
    await state.clear()

@dp.message(EditAd.editing_photo, Command('skip'))
async def edit_photo_skip(message: types.Message, state: FSMContext):
    await message.answer("✅ Фото оставлено без изменений.")
    await state.clear()

# --- Удаление ---
@dp.callback_query(lambda c: c.data and c.data.startswith("del_"))
async def process_delete(callback: types.CallbackQuery):
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
