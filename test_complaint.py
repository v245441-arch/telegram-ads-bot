import sqlite3
import asyncio
import os
from aiogram import Bot

# Токен бота (будет взят из переменной окружения, если не указан)
API_TOKEN = os.getenv('BOT_TOKEN', 'ВАШ_ТОКЕН_БОТА')
# Твой Telegram ID (уже подставлен)
ADMIN_ID = 362901319

# Подключение к БД
DB_PATH = "ads.db"

def add_complaint_manual(ad_id, user_id, reason):
    """Вручную добавляет жалобу в БД и возвращает её id."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO complaints (ad_id, user_id, reason)
        VALUES (?, ?, ?)
    ''', (ad_id, user_id, reason))
    complaint_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return complaint_id

def get_ad_details(ad_id):
    """Получает данные объявления для уведомления."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT title, description, price, category, username FROM ads WHERE id = ?', (ad_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'title': row[0],
            'description': row[1],
            'price': row[2],
            'category': row[3],
            'username': row[4]
        }
    return None

async def send_notification(ad_id, complaint_id, reason, user_id):
    """Отправляет тестовое уведомление админу."""
    bot = Bot(token=API_TOKEN)
    ad = get_ad_details(ad_id)
    if not ad:
        print("❌ Объявление не найдено.")
        return
    text = (f"⚠️ *Новая жалоба*\n\n"
            f"🆔 Объявление #{ad_id}\n"
            f"👤 Пожаловался: {user_id}\n"
            f"📝 Причина: {reason}\n\n"
            f"📌 *Объявление:*\n"
            f"{ad['title']}\n"
            f"{ad['description']}\n"
            f"💰 {ad['price']} руб.\n"
            f"Категория: {ad['category']}\n"
            f"Автор: @{ad['username']}")
    await bot.send_message(ADMIN_ID, text, parse_mode='Markdown')
    await bot.session.close()
    print("✅ Уведомление отправлено админу.")

async def main():
    # Укажите ID объявления, на которое хотите пожаловаться (замените на реальный)
    ad_id = 1
    reason = "спам"
    # ID пользователя, от имени которого подаётся жалоба (можно использовать свой)
    user_id = ADMIN_ID  # или любой другой, например 12345

    # Добавляем жалобу
    complaint_id = add_complaint_manual(ad_id, user_id, reason)
    print(f"✅ Жалоба добавлена, ID={complaint_id}")

    # Отправляем уведомление админу
    await send_notification(ad_id, complaint_id, reason, user_id)

if __name__ == '__main__':
    asyncio.run(main())
