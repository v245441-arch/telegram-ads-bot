import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен берем из переменной окружения (на Railway зададим отдельно)
API_TOKEN = os.getenv('BOT_TOKEN', 'ТВОЙ_ТОКЕН_ЗДЕСЬ')  # второй вариант для локального теста

# Настройки вебхука
WEBHOOK_PATH = '/webhook'
WEBHOOK_SECRET = 'my-secret-key'  # можно придумать любую строку
BASE_WEBHOOK_URL = os.getenv('BASE_WEBHOOK_URL', '')  # будет задан на Railway

# Создаем объекты бота и диспетчера
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Список объявлений (пока в памяти)
ads = []

# Состояния FSM
class AddAd(StatesGroup):
    title = State()
    description = State()
    price = State()
    photo = State()

# Команда /start
@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот-доска объявлений.\n"
        "Команды:\n"
        "/add — добавить объявление\n"
        "/list — показать все объявления"
    )

# Команда /add
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
    await message.answer("Отправьте фото товара (или отправьте /skip, чтобы пропустить):")
    await state.set_state(AddAd.photo)

@dp.message(AddAd.photo)
async def add_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
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

# Команда /list
@dp.message(Command('list'))
async def cmd_list(message: types.Message):
    if not ads:
        await message.answer("📭 Пока нет ни одного объявления.")
        return
    for ad in ads:
        text = f"<b>{ad['title']}</b>\n{ad['description']}\n💰 Цена: {ad['price']} руб.\n👤 Автор: @{ad['username']}"
        if ad['photo']:
            await message.answer_photo(photo=ad['photo'], caption=text, parse_mode='HTML')
        else:
            await message.answer(text, parse_mode='HTML')

# Функция, которая выполнится при запуске бота (установка вебхука)
async def on_startup(bot: Bot, base_url: str):
    await bot.set_webhook(f"{base_url}{WEBHOOK_PATH}", secret_token=WEBHOOK_SECRET)
    logging.info(f"Webhook set to {base_url}{WEBHOOK_PATH}")

# Функция, которая выполнится при остановке (удаление вебхука)
async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logging.info("Webhook deleted")

# Главная функция запуска
async def main():
    # Настраиваем aiohttp приложение
    app = web.Application()
    
    # Создаем обработчик вебхука для aiogram
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    
    # Регистрируем обработчик вебхука
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    # Регистрируем функции запуска/остановки
    app.on_startup.append(lambda _: asyncio.create_task(on_startup(bot, BASE_WEBHOOK_URL)))
    app.on_shutdown.append(lambda _: asyncio.create_task(on_shutdown(bot)))
    
    # Подключаем диспетчер к приложению
    setup_application(app, dp, bot=bot)
    
    # Получаем порт из окружения (Railway задает PORT автоматически)
    port = int(os.getenv('PORT', '8080'))
    
    # Запускаем веб-сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()
    
    logging.info(f"Bot started on port {port}")
    
    # Держим приложение запущенным
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
