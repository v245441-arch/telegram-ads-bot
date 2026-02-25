import asyncio
import logging
import os
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

ads = []

class AddAd(StatesGroup):
    title = State()
    description = State()
    price = State()
    photo = State()

@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Я бот-доска объявлений.\n/add — добавить\n/list — показать все")

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
    ad = {
        'title': data['title'],
        'description': data['description'],
        'price': data['price'],
        'photo': photo_id,
        'user_id': message.from_user.id,
        'username': message.from_user.username
    }
    ads.append(ad)
    await message.answer("✅ Объявление добавлено!")
    await state.clear()

@dp.message(AddAd.photo, Command('skip'))
async def skip_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ad = {
        'title': data['title'],
        'description': data['description'],
        'price': data['price'],
        'photo': None,
        'user_id': message.from_user.id,
        'username': message.from_user.username
    }
    ads.append(ad)
    await message.answer("✅ Объявление добавлено без фото.")
    await state.clear()

@dp.message(Command('list'))
async def cmd_list(message: types.Message):
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
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
