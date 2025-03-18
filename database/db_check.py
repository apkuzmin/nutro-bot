"""
Инструмент для проверки состояния баз данных и исправления распространенных проблем.
"""

import os
import sqlite3
import logging
import sys
from contextlib import contextmanager

# Добавляем текущую директорию в путь для импорта модулей
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем модули базы данных
from database.connection_pool import DatabaseConnectionPool
from database.db_utils import ensure_db_dir

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("db_check.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("db_checker")

# Пути к базам данных
DB_DIR = "data"
DB_FILES = ["users.db", "products.db", "food_log.db"]

def check_db_exists():
    """
    Проверяет существование всех необходимых файлов баз данных.
    
    Returns:
        dict: Словарь с результатами проверки {db_name: exists}
    """
    ensure_db_dir()
    results = {}
    
    for db_file in DB_FILES:
        db_path = os.path.join(DB_DIR, db_file)
        exists = os.path.exists(db_path)
        results[db_file] = exists
        
        if exists:
            size = os.path.getsize(db_path)
            logger.info(f"База данных {db_file} существует, размер: {size/1024:.2f} KB")
        else:
            logger.warning(f"База данных {db_file} не найдена")
    
    return results

def check_journal_files():
    """
    Проверяет наличие файлов журнала SQLite (-wal, -shm) и их состояние.
    
    Returns:
        dict: Словарь с результатами проверки {db_name: {wal: exists, shm: exists}}
    """
    results = {}
    
    for db_file in DB_FILES:
        db_path = os.path.join(DB_DIR, db_file)
        wal_path = f"{db_path}-wal"
        shm_path = f"{db_path}-shm"
        
        wal_exists = os.path.exists(wal_path)
        shm_exists = os.path.exists(shm_path)
        
        if wal_exists:
            wal_size = os.path.getsize(wal_path)
            logger.info(f"WAL файл для {db_file} существует, размер: {wal_size/1024:.2f} KB")
        
        if shm_exists:
            shm_size = os.path.getsize(shm_path)
            logger.info(f"SHM файл для {db_file} существует, размер: {shm_size/1024:.2f} KB")
        
        results[db_file] = {"wal": wal_exists, "shm": shm_exists}
    
    return results

@contextmanager
def direct_connection(db_path):
    """
    Создает прямое соединение с базой данных, минуя пул соединений.
    
    Args:
        db_path (str): Путь к файлу базы данных
        
    Yields:
        sqlite3.Connection: Соединение с базой данных
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        # Включаем поддержку внешних ключей
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
    finally:
        if conn:
            conn.close()

def check_tables(db_file):
    """
    Проверяет структуру таблиц в базе данных.
    
    Args:
        db_file (str): Имя файла базы данных
        
    Returns:
        dict: Словарь с информацией о таблицах
    """
    db_path = os.path.join(DB_DIR, db_file)
    if not os.path.exists(db_path):
        logger.warning(f"База данных {db_file} не найдена, невозможно проверить таблицы")
        return {}
    
    tables_info = {}
    
    with direct_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Получаем список таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            
            # Получаем структуру таблицы
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            # Получаем количество записей
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            
            # Проверяем индексы
            cursor.execute(f"PRAGMA index_list({table_name})")
            indices = cursor.fetchall()
            
            tables_info[table_name] = {
                "columns": [{"name": col[1], "type": col[2], "notnull": col[3], "pk": col[5]} for col in columns],
                "rows": count,
                "indices": [idx[1] for idx in indices]
            }
            
            logger.info(f"Таблица {table_name} в {db_file}: {count} записей, {len(columns)} столбцов, {len(indices)} индексов")
    
    return tables_info

def check_integrity(db_file):
    """
    Проверяет целостность базы данных.
    
    Args:
        db_file (str): Имя файла базы данных
        
    Returns:
        bool: True, если база данных целостна, иначе False
    """
    db_path = os.path.join(DB_DIR, db_file)
    if not os.path.exists(db_path):
        logger.warning(f"База данных {db_file} не найдена, невозможно проверить целостность")
        return False
    
    with direct_connection(db_path) as conn:
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            
            if result and result[0] == "ok":
                logger.info(f"Проверка целостности {db_file} успешна")
                return True
            else:
                logger.error(f"Проверка целостности {db_file} не удалась: {result}")
                return False
        except sqlite3.Error as e:
            logger.error(f"Ошибка при проверке целостности {db_file}: {e}")
            return False

def fix_journal_files():
    """
    Исправляет проблемы с файлами журнала SQLite путем чистого завершения всех соединений.
    
    Returns:
        bool: True, если все исправления успешны, иначе False
    """
    success = True
    
    # Закрываем все пулы соединений
    for db_file in DB_FILES:
        try:
            pool = DatabaseConnectionPool.get_pool(db_file)
            pool.close_all()
            logger.info(f"Все соединения с {db_file} закрыты")
        except Exception as e:
            logger.error(f"Ошибка при закрытии соединений с {db_file}: {e}")
            success = False
    
    # Открываем и чисто закрываем соединения для каждой базы данных
    for db_file in DB_FILES:
        db_path = os.path.join(DB_DIR, db_file)
        if not os.path.exists(db_path):
            continue
        
        try:
            # Открываем соединение и меняем режим журнала на DELETE
            with direct_connection(db_path) as conn:
                conn.execute("PRAGMA journal_mode = DELETE")
                conn.execute("PRAGMA journal_mode = WAL")  # Возвращаем в WAL режим
                logger.info(f"Режим журнала для {db_file} сброшен успешно")
        except sqlite3.Error as e:
            logger.error(f"Ошибка при сбросе режима журнала для {db_file}: {e}")
            success = False
    
    return success

def vacuum_database(db_file):
    """
    Выполняет VACUUM для оптимизации базы данных.
    
    Args:
        db_file (str): Имя файла базы данных
        
    Returns:
        bool: True, если операция успешна, иначе False
    """
    db_path = os.path.join(DB_DIR, db_file)
    if not os.path.exists(db_path):
        logger.warning(f"База данных {db_file} не найдена, невозможно выполнить VACUUM")
        return False
    
    try:
        # Закрываем все соединения в пуле
        pool = DatabaseConnectionPool.get_pool(db_file)
        pool.close_all()
        
        # Открываем прямое соединение
        with direct_connection(db_path) as conn:
            conn.execute("PRAGMA journal_mode = DELETE")  # Временно меняем режим журнала
            conn.execute("VACUUM")  # Выполняем VACUUM
            conn.execute("PRAGMA journal_mode = WAL")  # Возвращаем WAL режим
            logger.info(f"VACUUM для {db_file} выполнен успешно")
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка при выполнении VACUUM для {db_file}: {e}")
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при выполнении VACUUM для {db_file}: {e}")
        return False

def fix_all_databases():
    """
    Выполняет комплексное исправление всех баз данных.
    
    Returns:
        bool: True, если все операции успешны, иначе False
    """
    logger.info("Начало комплексного исправления баз данных...")
    
    # Проверяем существование баз данных
    db_exists = check_db_exists()
    all_exists = all(db_exists.values())
    
    if not all_exists:
        logger.error("Не все базы данных существуют, исправление невозможно")
        return False
    
    # Исправляем файлы журнала
    journal_fixed = fix_journal_files()
    
    # Проверяем целостность и выполняем VACUUM для каждой базы данных
    integrity_ok = True
    vacuum_ok = True
    
    for db_file in DB_FILES:
        if check_integrity(db_file):
            # Выполняем VACUUM только если проверка целостности успешна
            if not vacuum_database(db_file):
                vacuum_ok = False
        else:
            integrity_ok = False
    
    if journal_fixed and integrity_ok and vacuum_ok:
        logger.info("Комплексное исправление баз данных завершено успешно")
        return True
    else:
        logger.warning("Комплексное исправление баз данных завершено с предупреждениями")
        return False

def run_health_check():
    """
    Запускает полную проверку состояния баз данных.
    
    Returns:
        dict: Словарь с результатами проверки
    """
    logger.info("Начало проверки состояния баз данных...")
    
    results = {
        "db_exists": check_db_exists(),
        "journal_files": check_journal_files(),
        "tables": {},
        "integrity": {}
    }
    
    for db_file in DB_FILES:
        if results["db_exists"].get(db_file, False):
            results["tables"][db_file] = check_tables(db_file)
            results["integrity"][db_file] = check_integrity(db_file)
    
    logger.info("Проверка состояния баз данных завершена")
    return results

if __name__ == "__main__":
    try:
        action = None
        if len(sys.argv) > 1:
            action = sys.argv[1].lower()
        
        if action == "check":
            results = run_health_check()
            print("Результаты проверки:")
            print(f"Существование БД: {all(results['db_exists'].values())}")
            
            for db_file in DB_FILES:
                if results["db_exists"].get(db_file, False):
                    print(f"\nБаза данных: {db_file}")
                    print(f"  Целостность: {results['integrity'].get(db_file, False)}")
                    
                    tables = results["tables"].get(db_file, {})
                    print(f"  Таблицы ({len(tables)}):")
                    for table_name, table_info in tables.items():
                        print(f"    {table_name}: {table_info['rows']} записей")
        elif action == "fix":
            print("Запуск исправления баз данных...")
            if fix_all_databases():
                print("Исправление завершено успешно!")
            else:
                print("Исправление завершено с предупреждениями. Проверьте db_check.log")
        else:
            print("Использование:")
            print("  python db_check.py check - Проверить состояние баз данных")
            print("  python db_check.py fix - Исправить проблемы с базами данных")
    except KeyboardInterrupt:
        print("\nОперация прервана пользователем.")
    except Exception as e:
        print(f"Непредвиденная ошибка: {e}")
        logger.error(f"Непредвиденная ошибка: {e}") 