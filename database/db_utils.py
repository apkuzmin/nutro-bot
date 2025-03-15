"""
Утилитарные функции для работы с базами данных.
Предоставляет функции для инициализации и подключения к базам данных.
"""

import sqlite3
import os
import logging
from database.connection_pool import get_products_connection, get_users_connection, get_food_log_connection, transaction

logger = logging.getLogger(__name__)

# Директория для хранения файлов баз данных
DB_DIR = "data"

def ensure_db_dir():
    """Убедиться, что директория для баз данных существует."""
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)

def get_products_db():
    """
    Получить соединение с базой данных продуктов.
    
    Устаревшая функция, оставлена для обратной совместимости.
    Рекомендуется использовать контекстный менеджер get_products_connection().
    
    Returns:
        sqlite3.Connection: Соединение с базой данных продуктов
    """
    logger.warning("Использование устаревшей функции get_products_db(). Рекомендуется использовать контекстный менеджер get_products_connection().")
    ensure_db_dir()
    return sqlite3.connect(os.path.join(DB_DIR, "products.db"))

def get_users_db():
    """
    Получить соединение с базой данных пользователей.
    
    Устаревшая функция, оставлена для обратной совместимости.
    Рекомендуется использовать контекстный менеджер get_users_connection().
    
    Returns:
        sqlite3.Connection: Соединение с базой данных пользователей
    """
    logger.warning("Использование устаревшей функции get_users_db(). Рекомендуется использовать контекстный менеджер get_users_connection().")
    ensure_db_dir()
    return sqlite3.connect(os.path.join(DB_DIR, "users.db"))

def get_food_log_db():
    """
    Получить соединение с базой данных логов питания.
    
    Устаревшая функция, оставлена для обратной совместимости.
    Рекомендуется использовать контекстный менеджер get_food_log_connection().
    
    Returns:
        sqlite3.Connection: Соединение с базой данных логов питания
    """
    logger.warning("Использование устаревшей функции get_food_log_db(). Рекомендуется использовать контекстный менеджер get_food_log_connection().")
    ensure_db_dir()
    return sqlite3.connect(os.path.join(DB_DIR, "food_log.db"))

def init_all_db():
    """Инициализировать все базы данных."""
    init_products_db()
    init_users_db()
    init_food_log_db()

def init_products_db():
    """Инициализировать базу данных продуктов."""
    ensure_db_dir()
    with get_products_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
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

def init_users_db():
    """Инициализировать базу данных пользователей."""
    ensure_db_dir()
    with get_users_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
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
            
            # Создаем индексы
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_timezone ON users(timezone)')

def init_food_log_db():
    """Инициализировать базу данных логов питания."""
    ensure_db_dir()
    with get_food_log_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            # Создаем таблицу логов питания
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS food_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                food_name TEXT,
                weight REAL,
                kcal REAL,
                protein REAL,
                fat REAL,
                carbs REAL,
                date TEXT,
                time TEXT,
                edit_code TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Создаем таблицу дневного потребления
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_intake (
                user_id INTEGER,
                date TEXT,
                calories REAL DEFAULT 0,
                protein REAL DEFAULT 0,
                fat REAL DEFAULT 0,
                carbs REAL DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
            ''')
            
            # Создаем индексы
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_food_log_user_date ON food_log(user_id, date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_food_log_edit_code ON food_log(edit_code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_intake_user_date ON daily_intake(user_id, date)')
            
            # Создаем триггер для автоматического обновления daily_intake при добавлении записи в food_log
            cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS update_daily_intake_after_insert
            AFTER INSERT ON food_log
            FOR EACH ROW
            BEGIN
                INSERT OR REPLACE INTO daily_intake (user_id, date, calories, protein, fat, carbs)
                VALUES (
                    NEW.user_id,
                    NEW.date,
                    COALESCE((SELECT calories FROM daily_intake WHERE user_id = NEW.user_id AND date = NEW.date), 0) + NEW.kcal,
                    COALESCE((SELECT protein FROM daily_intake WHERE user_id = NEW.user_id AND date = NEW.date), 0) + NEW.protein,
                    COALESCE((SELECT fat FROM daily_intake WHERE user_id = NEW.user_id AND date = NEW.date), 0) + NEW.fat,
                    COALESCE((SELECT carbs FROM daily_intake WHERE user_id = NEW.user_id AND date = NEW.date), 0) + NEW.carbs
                );
            END;
            ''')
            
            # Создаем триггер для автоматического обновления daily_intake при удалении записи из food_log
            cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS update_daily_intake_after_delete
            AFTER DELETE ON food_log
            FOR EACH ROW
            BEGIN
                UPDATE daily_intake
                SET 
                    calories = calories - OLD.kcal,
                    protein = protein - OLD.protein,
                    fat = fat - OLD.fat,
                    carbs = carbs - OLD.carbs
                WHERE user_id = OLD.user_id AND date = OLD.date;
            END;
            ''')
            
            # Создаем триггер для автоматического обновления daily_intake при обновлении записи в food_log
            cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS update_daily_intake_after_update
            AFTER UPDATE ON food_log
            FOR EACH ROW
            BEGIN
                UPDATE daily_intake
                SET 
                    calories = calories - OLD.kcal + NEW.kcal,
                    protein = protein - OLD.protein + NEW.protein,
                    fat = fat - OLD.fat + NEW.fat,
                    carbs = carbs - OLD.carbs + NEW.carbs
                WHERE user_id = OLD.user_id AND date = OLD.date;
                
                -- Если дата изменилась, обновляем также запись для новой даты
                INSERT OR REPLACE INTO daily_intake (user_id, date, calories, protein, fat, carbs)
                SELECT
                    NEW.user_id,
                    NEW.date,
                    COALESCE((SELECT calories FROM daily_intake WHERE user_id = NEW.user_id AND date = NEW.date), 0) + NEW.kcal,
                    COALESCE((SELECT protein FROM daily_intake WHERE user_id = NEW.user_id AND date = NEW.date), 0) + NEW.protein,
                    COALESCE((SELECT fat FROM daily_intake WHERE user_id = NEW.user_id AND date = NEW.date), 0) + NEW.fat,
                    COALESCE((SELECT carbs FROM daily_intake WHERE user_id = NEW.user_id AND date = NEW.date), 0) + NEW.carbs
                WHERE OLD.date != NEW.date;
            END;
            ''') 