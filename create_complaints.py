import sqlite3

DB_PATH = "ads.db"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Создаём таблицу complaints
cursor.execute('''
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'new',
        FOREIGN KEY (ad_id) REFERENCES ads(id) ON DELETE CASCADE
    )
''')

# Индексы для быстрого поиска
cursor.execute('CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_complaints_ad_id ON complaints(ad_id)')

conn.commit()
conn.close()
print("✅ Таблица complaints успешно создана (или уже существовала).")
