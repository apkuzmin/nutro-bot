import sqlite3
from datetime import date, datetime
import uuid
from functools import lru_cache
import logging
import threading
from contextlib import contextmanager

# Настройка логирования
logger = logging.getLogger(__name__)

# Создаем локальное хранилище для соединений с базой данных (по одному на поток)
_local = threading.local()

# Путь к файлу базы данных
DB_PATH = "user_data.db"

@contextmanager
def get_connection():
    """Контекстный менеджер для получения соединения с базой данных.
    Использует пул соединений (по одному на поток)."""
    if not hasattr(_local, 'conn'):
        _local.conn = sqlite3.connect(DB_PATH)
        # Включаем поддержку внешних ключей
        _local.conn.execute("PRAGMA foreign_keys = ON")
        # Включаем автоматическую фиксацию изменений
        _local.conn.isolation_level = None
    
    try:
        yield _local.conn
    except Exception as e:
        logger.error(f"Ошибка при работе с БД: {e}")
        raise
    
# Для обратной совместимости
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

def init_db():
    """Инициализация таблиц базы данных с индексами и триггерами."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                daily_calories REAL,
                protein REAL,
                fat REAL,
                carbs REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                name TEXT PRIMARY KEY,
                kcal REAL,
                protein REAL,
                fat REAL,
                carbs REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_intake (
                user_id INTEGER,
                date TEXT,
                calories REAL DEFAULT 0,
                protein REAL DEFAULT 0,
                fat REAL DEFAULT 0,
                carbs REAL DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS food_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                food_name TEXT,
                weight REAL,
                date TEXT,
                time TEXT,
                edit_code TEXT UNIQUE,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (food_name) REFERENCES products(name)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS barcode_products (
                barcode TEXT PRIMARY KEY,
                food_name TEXT,
                FOREIGN KEY (food_name) REFERENCES products(name)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_food_log_user_date ON food_log(user_id, date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_intake_user_date ON daily_intake(user_id, date)")
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_daily_intake_after_insert
            AFTER INSERT ON food_log
            FOR EACH ROW
            BEGIN
                INSERT OR REPLACE INTO daily_intake (user_id, date, calories, protein, fat, carbs)
                SELECT 
                    NEW.user_id,
                    NEW.date,
                    COALESCE(SUM(p.kcal * fl.weight / 100), 0),
                    COALESCE(SUM(p.protein * fl.weight / 100), 0),
                    COALESCE(SUM(p.fat * fl.weight / 100), 0),
                    COALESCE(SUM(p.carbs * fl.weight / 100), 0)
                FROM food_log fl
                JOIN products p ON fl.food_name = p.name
                WHERE fl.user_id = NEW.user_id AND fl.date = NEW.date;
            END;
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_daily_intake_after_update
            AFTER UPDATE ON food_log
            FOR EACH ROW
            BEGIN
                INSERT OR REPLACE INTO daily_intake (user_id, date, calories, protein, fat, carbs)
                SELECT 
                    NEW.user_id,
                    NEW.date,
                    COALESCE(SUM(p.kcal * fl.weight / 100), 0),
                    COALESCE(SUM(p.protein * fl.weight / 100), 0),
                    COALESCE(SUM(p.fat * fl.weight / 100), 0),
                    COALESCE(SUM(p.carbs * fl.weight / 100), 0)
                FROM food_log fl
                JOIN products p ON fl.food_name = p.name
                WHERE fl.user_id = NEW.user_id AND fl.date = NEW.date;
            END;
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_daily_intake_after_delete
            AFTER DELETE ON food_log
            FOR EACH ROW
            BEGIN
                INSERT OR REPLACE INTO daily_intake (user_id, date, calories, protein, fat, carbs)
                SELECT 
                    OLD.user_id,
                    OLD.date,
                    COALESCE(SUM(p.kcal * fl.weight / 100), 0),
                    COALESCE(SUM(p.protein * fl.weight / 100), 0),
                    COALESCE(SUM(p.fat * fl.weight / 100), 0),
                    COALESCE(SUM(p.carbs * fl.weight / 100), 0)
                FROM food_log fl
                JOIN products p ON fl.food_name = p.name
                WHERE fl.user_id = OLD.user_id AND fl.date = OLD.date;
            END;
        """)
        conn.commit()

def get_user_data(user_id):
    """Получение данных пользователя из базы данных."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT daily_calories, protein, fat, carbs FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()

def save_user_data(user_id, daily_calories, protein, fat, carbs):
    """Сохранение данных пользователя в базу данных."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, daily_calories, protein, fat, carbs) VALUES (?, ?, ?, ?, ?)",
            (user_id, daily_calories, protein, fat, carbs)
        )

@lru_cache(maxsize=100)
def get_product_data(food_name):
    """Получение данных о продукте из базы данных с кэшированием."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT kcal, protein, fat, carbs FROM products WHERE name = ?", (food_name,))
        return cursor.fetchone()

def save_product_data(food_name, kcal, protein, fat, carbs):
    """Сохранение данных о продукте в базу данных."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO products (name, kcal, protein, fat, carbs) VALUES (?, ?, ?, ?, ?)",
            (food_name, kcal, protein, fat, carbs)
        )
        # Очищаем кэш для этого продукта
        get_product_data.cache_clear()

def search_products(query):
    """Поиск продуктов по запросу."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM products WHERE name LIKE ? LIMIT 10", (f"%{query}%",))
        return [row[0] for row in cursor.fetchall()]

def get_daily_intake(user_id):
    today = date.today().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT calories, protein, fat, carbs FROM daily_intake 
            WHERE user_id = ? AND date = ?
        """, (user_id, today))
        result = cursor.fetchone()
        return tuple(0 if x is None else x for x in result) if result else (0, 0, 0, 0)

def generate_edit_code():
    return str(uuid.uuid4())[:8].upper()

def log_food(user_id, food_name, weight):
    now = datetime.now()
    date_str = now.date().isoformat()
    time_str = now.time().isoformat()
    edit_code = generate_edit_code()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO food_log (user_id, food_name, weight, date, time, edit_code)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, food_name, weight, date_str, time_str, edit_code))
    return edit_code

def get_food_log(user_id):
    today = date.today().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT fl.id, fl.food_name, fl.weight, 
                (p.kcal * fl.weight / 100), (p.protein * fl.weight / 100), 
                (p.fat * fl.weight / 100), (p.carbs * fl.weight / 100), 
                fl.date || 'T' || fl.time AS timestamp, fl.edit_code 
            FROM food_log fl
            JOIN products p ON fl.food_name = p.name
            WHERE fl.user_id = ? AND fl.date = ?
            ORDER BY fl.date, fl.time ASC
        """, (user_id, today))
        return cursor.fetchall()

def update_food_log(log_id, weight):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE food_log 
            SET weight = ?
            WHERE id = ?
        """, (weight, log_id))

def delete_food_log(log_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM food_log WHERE id = ?", (log_id,))

def get_product_by_barcode(barcode):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.name, p.kcal, p.protein, p.fat, p.carbs
            FROM barcode_products bp
            JOIN products p ON bp.food_name = p.name
            WHERE bp.barcode = ?
        """, (barcode,))
        result = cursor.fetchone()
        if result:
            return {"name": result[0], "kcal": result[1], "protein": result[2], "fat": result[3], "carbs": result[4]}
        return None

def save_barcode_product(barcode, food_name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO barcode_products (barcode, food_name)
            VALUES (?, ?)
        """, (barcode, food_name))

def save_custom_macros(user_id, calories, protein, fat, carbs):
    """Сохраняет пользовательские значения макронутриентов."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO users (user_id, daily_calories, protein, fat, carbs)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, calories, protein, fat, carbs))

def delete_user_data(user_id):
    """Удаляет все данные пользователя из базы данных."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Удаляем данные из таблицы users
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        
        # Удаляем данные из таблицы daily_intake
        cursor.execute("DELETE FROM daily_intake WHERE user_id = ?", (user_id,))
        
        # Удаляем данные из таблицы food_log
        cursor.execute("DELETE FROM food_log WHERE user_id = ?", (user_id,))

def init_all_db():
    """Инициализация всех баз данных."""
    logger = logging.getLogger("database.db_utils")
    logger.debug("Инициализация всех баз данных...")
    
    # Инициализация базы данных продуктов
    init_db()
    logger.debug("База данных продуктов инициализирована")
    
    # Инициализация базы данных пользователей
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT 'ru',
                day_end_time TEXT DEFAULT '23:59'
            )
        """)
    logger.debug("База данных пользователей инициализирована")
    
    # Инициализация базы данных журнала питания
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_summaries (
                user_id INTEGER PRIMARY KEY,
                job_id TEXT
            )
        """)
    logger.debug("База данных журнала питания инициализирована")
    
    logger.debug("Все базы данных инициализированы успешно")