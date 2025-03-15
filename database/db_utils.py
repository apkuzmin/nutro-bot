"""
Утилитарные функции для работы с базами данных.
Предоставляет функции для инициализации и подключения к базам данных.
"""

import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

# Директория для хранения файлов баз данных
DB_DIR = "data"

def ensure_db_dir():
    """Убедиться, что директория для баз данных существует."""
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)

def get_products_db():
    """Получить соединение с базой данных продуктов."""
    ensure_db_dir()
    return sqlite3.connect(os.path.join(DB_DIR, "products.db"))

def get_users_db():
    """Получить соединение с базой данных пользователей."""
    ensure_db_dir()
    return sqlite3.connect(os.path.join(DB_DIR, "users.db"))

def get_food_log_db():
    """Получить соединение с базой данных логов питания."""
    ensure_db_dir()
    return sqlite3.connect(os.path.join(DB_DIR, "food_log.db"))

def init_all_db():
    """Инициализировать все базы данных."""
    init_products_db()
    init_users_db()
    init_food_log_db()

def init_products_db():
    """Инициализировать базу данных продуктов."""
    conn = get_products_db()
    cursor = conn.cursor()
    
    # Создаем таблицу продуктов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        kcal REAL,
        protein REAL,
        fat REAL,
        carbs REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Создаем таблицу штрихкодов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS barcodes (
        barcode TEXT PRIMARY KEY,
        product_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_id) REFERENCES products (id)
    )
    ''')
    
    # Создаем индексы для ускорения поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_barcodes_product_id ON barcodes(product_id)')
    
    conn.commit()
    conn.close()

def init_users_db():
    """Инициализировать базу данных пользователей."""
    conn = get_users_db()
    cursor = conn.cursor()
    
    # Создаем таблицу пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        gender TEXT,
        age INTEGER,
        weight REAL,
        height REAL,
        activity TEXT,
        goal TEXT,
        daily_calories REAL,
        protein REAL,
        fat REAL,
        carbs REAL,
        language TEXT DEFAULT 'ru',
        day_end_time TEXT DEFAULT '00:00',
        timezone INTEGER DEFAULT 3,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Проверяем, существует ли колонка timezone, и добавляем ее, если нет
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'timezone' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN timezone INTEGER DEFAULT 3")
    
    # Создаем таблицу дневного потребления
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS daily_intake (
        user_id INTEGER,
        date TEXT,
        calories REAL DEFAULT 0,
        protein REAL DEFAULT 0,
        fat REAL DEFAULT 0,
        carbs REAL DEFAULT 0,
        PRIMARY KEY (user_id, date),
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')
    
    # Создаем индексы для ускорения поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_intake_user_date ON daily_intake(user_id, date)')
    
    conn.commit()
    conn.close()

def init_food_log_db():
    """Инициализировать базу данных журнала питания."""
    conn = get_food_log_db()
    cursor = conn.cursor()
    
    # Создаем таблицу журнала питания
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS food_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        food_name TEXT,
        weight REAL,
        date TEXT,
        time TEXT,
        edit_code TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Создаем индексы для ускорения поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_food_log_user_date ON food_log(user_id, date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_food_log_edit_code ON food_log(edit_code)')
    
    conn.commit()
    conn.close() 