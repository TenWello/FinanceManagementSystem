import sqlite3, os
db = os.getenv("DB_PATH", "finance.db")
print(f"DB: {db}")
conn = sqlite3.connect(db)
conn.executescript("""
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL,
    color TEXT DEFAULT '#6366f1'
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL DEFAULT 'boshqa',
    note TEXT DEFAULT '',
    date TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    added_by_id INTEGER DEFAULT 0,
    added_by_name TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS allowed_users (
    user_id INTEGER PRIMARY KEY,
    username TEXT DEFAULT '',
    full_name TEXT DEFAULT '',
    role TEXT DEFAULT 'user',
    web_password_hash TEXT DEFAULT '',
    added_at TEXT DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO categories (name,type,color) VALUES
    ('sotuv','income','#10b981'),
    ('xizmat','income','#06b6d4'),
    ('investitsiya','income','#8b5cf6'),
    ('boshqa kirim','income','#64748b'),
    ('maosh','expense','#f59e0b'),
    ('ijara','expense','#ef4444'),
    ('transport','expense','#f97316'),
    ('kommunal','expense','#ec4899'),
    ('oziq-ovqat','expense','#84cc16'),
    ('reklama','expense','#a78bfa'),
    ('logistika','expense','#38bdf8'),
    ('boshqa','both','#94a3b8');
""")
conn.commit()
count = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
conn.close()
print(f"Kategoriyalar: {count}")