import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен и URL из переменных окружения (обязательно!)
API_TOKEN = os.getenv('BOT_TOKEN')
BASE_WEBHOOK_URL = os.getenv('BASE_WEBHOOK_URL')
WEBHOOK_PATH = '/webhook'

if not API_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")
if not BASE_WEBHOOK_URL:
    raise ValueError("BASE_WEBHOOK_URL не задан!")

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

# --- Вебхук часть ---
async def on_startup(bot: Bot, base_url: str):
    webhook_url = f"{base_url}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    logging.info(f"✅ Вебхук установлен: {webhook_url}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logging.info("🔴 Вебхук удалён")

async def main():
    app = web.Application()

    # Простой GET-обработчик для проверки доступности сервера
    async def handle_get(request):
        return web.Response(text="Бот работает!")
    app.router.add_get('/', handle_get)
    app.router.add_get('/webhook', handle_get)  # тоже для теста

    # Регистрация обработчика вебхуков aiogram
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)

    # Подключаем диспетчер к приложению (важно!)
    setup_application(app, dp, bot=bot)

    # Запуск и остановка
    app.on_startup.append(lambda _: asyncio.create_task(on_startup(bot, BASE_WEBHOOK_URL)))
    app.on_shutdown.append(lambda _: asyncio.create_task(on_shutdown(bot)))

    # Получаем порт из переменной окружения (Railway задаёт PORT)
    port = int(os.getenv('PORT', '8080'))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()

    logging.info(f"🚀 Сервер запущен на порту {port}")
    logging.info(f"🔗 Эндпоинт вебхука: {BASE_WEBHOOK_URL}{WEBHOOK_PATH}")

    # Ожидаем бесконечно
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
