"""
Скрипт для миграции данных из старой базы данных в новую.
Переносит данные из единой базы данных user_data.db в отдельные 
базы данных для пользователей, продуктов и журнала питания.
"""

import os
import sqlite3
import logging
import sys
import shutil
from pathlib import Path
from datetime import datetime

# Добавляем текущую директорию в путь для импорта модулей
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем модули базы данных
from database.connection_pool import (
    get_users_connection, get_products_connection, get_food_log_connection, transaction
)
from database.db_utils import ensure_db_dir

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("migration.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("db_migration")

# Путь к старой базе данных
OLD_DB_PATH = "user_data.db"

def backup_old_database():
    """Создает резервную копию старой базы данных."""
    if not os.path.exists(OLD_DB_PATH):
        logger.warning(f"Старая база данных {OLD_DB_PATH} не найдена, миграция невозможна.")
        return False
        
    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"user_data_{timestamp}.db")
    
    try:
        shutil.copy2(OLD_DB_PATH, backup_path)
        logger.info(f"Создана резервная копия базы данных: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии: {e}")
        return False

def migrate_users():
    """Переносит данные пользователей из старой базы данных в новую."""
    logger.info("Начало миграции данных пользователей...")
    
    try:
        # Подключаемся к старой базе данных
        old_conn = sqlite3.connect(OLD_DB_PATH)
        old_cursor = old_conn.cursor()
        
        # Проверяем, есть ли таблица users в старой БД
        old_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not old_cursor.fetchone():
            logger.warning("Таблица users не найдена в старой базе данных.")
            old_conn.close()
            return False
            
        # Получаем данные пользователей из старой БД
        old_cursor.execute("SELECT * FROM users")
        users_data = old_cursor.fetchall()
        
        if not users_data:
            logger.info("Нет данных пользователей для миграции.")
            old_conn.close()
            return True
            
        # Получаем имена столбцов
        old_cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in old_cursor.fetchall()]
        
        logger.info(f"Найдено {len(users_data)} пользователей для миграции.")
        
        # Переносим данные в новую БД
        with get_users_connection() as new_conn:
            with transaction(new_conn) as tx:
                new_cursor = tx.cursor()
                
                # Получаем структуру новой таблицы
                new_cursor.execute("PRAGMA table_info(users)")
                new_columns = [col[1] for col in new_cursor.fetchall()]
                
                # Определяем общие столбцы
                common_columns = set(columns).intersection(set(new_columns))
                
                for user in users_data:
                    # Создаем словарь с данными пользователя
                    user_dict = {columns[i]: user[i] for i in range(len(columns))}
                    
                    # Готовим данные для вставки (только общие столбцы)
                    insert_columns = ', '.join(common_columns)
                    placeholders = ', '.join(['?' for _ in common_columns])
                    values = [user_dict[col] for col in common_columns]
                    
                    # Вставляем данные пользователя
                    new_cursor.execute(
                        f"INSERT OR REPLACE INTO users ({insert_columns}) VALUES ({placeholders})",
                        values
                    )
                
        old_conn.close()
        logger.info("Миграция данных пользователей завершена успешно.")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при миграции данных пользователей: {e}")
        return False

def migrate_products():
    """Переносит данные продуктов из старой базы данных в новую."""
    logger.info("Начало миграции данных продуктов...")
    
    try:
        # Подключаемся к старой базе данных
        old_conn = sqlite3.connect(OLD_DB_PATH)
        old_cursor = old_conn.cursor()
        
        # Проверяем, есть ли таблица products в старой БД
        old_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
        if not old_cursor.fetchone():
            logger.warning("Таблица products не найдена в старой базе данных.")
            old_conn.close()
            return False
            
        # Получаем данные продуктов из старой БД
        old_cursor.execute("SELECT * FROM products")
        products_data = old_cursor.fetchall()
        
        if not products_data:
            logger.info("Нет данных продуктов для миграции.")
            old_conn.close()
            return True
            
        # Получаем имена столбцов
        old_cursor.execute("PRAGMA table_info(products)")
        columns = [col[1] for col in old_cursor.fetchall()]
        
        logger.info(f"Найдено {len(products_data)} продуктов для миграции.")
        
        # Переносим данные в новую БД
        with get_products_connection() as new_conn:
            with transaction(new_conn) as tx:
                new_cursor = tx.cursor()
                
                # Получаем структуру новой таблицы
                new_cursor.execute("PRAGMA table_info(products)")
                new_columns = [col[1] for col in new_cursor.fetchall()]
                
                # В новой структуре name не является PRIMARY KEY, а есть отдельный id
                # Поэтому нам нужна специальная обработка
                
                for product in products_data:
                    # Создаем словарь с данными продукта
                    product_dict = {columns[i]: product[i] for i in range(len(columns))}
                    
                    # Проверяем, есть ли name в новых столбцах
                    if 'name' in new_columns:
                        new_cursor.execute(
                            "INSERT OR REPLACE INTO products (name, kcal, protein, fat, carbs) VALUES (?, ?, ?, ?, ?)",
                            (product_dict.get('name', ''), 
                             product_dict.get('kcal', 0), 
                             product_dict.get('protein', 0), 
                             product_dict.get('fat', 0), 
                             product_dict.get('carbs', 0))
                        )
                
        # Проверяем таблицу barcode_products
        old_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='barcode_products'")
        if old_cursor.fetchone():
            # Получаем данные штрихкодов из старой БД
            old_cursor.execute("SELECT * FROM barcode_products")
            barcodes_data = old_cursor.fetchall()
            
            if barcodes_data:
                logger.info(f"Найдено {len(barcodes_data)} штрихкодов для миграции.")
                
                # Переносим данные в новую БД
                with get_products_connection() as new_conn:
                    with transaction(new_conn) as tx:
                        new_cursor = tx.cursor()
                        
                        for barcode in barcodes_data:
                            barcode_value = barcode[0]
                            food_name = barcode[1]
                            
                            # Находим ID продукта в новой БД
                            new_cursor.execute("SELECT id FROM products WHERE name = ?", (food_name,))
                            result = new_cursor.fetchone()
                            
                            if result:
                                product_id = result[0]
                                new_cursor.execute(
                                    "INSERT OR REPLACE INTO barcodes (barcode, product_id) VALUES (?, ?)",
                                    (barcode_value, product_id)
                                )
                            else:
                                logger.warning(f"Не удалось найти продукт {food_name} для штрихкода {barcode_value}")
        
        old_conn.close()
        logger.info("Миграция данных продуктов завершена успешно.")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при миграции данных продуктов: {e}")
        return False

def migrate_food_log():
    """Переносит данные журнала питания из старой базы данных в новую."""
    logger.info("Начало миграции данных журнала питания...")
    
    try:
        # Подключаемся к старой базе данных
        old_conn = sqlite3.connect(OLD_DB_PATH)
        old_cursor = old_conn.cursor()
        
        # Проверяем, есть ли таблица food_log в старой БД
        old_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='food_log'")
        if not old_cursor.fetchone():
            logger.warning("Таблица food_log не найдена в старой базе данных.")
            old_conn.close()
            return False
            
        # Получаем данные журнала питания из старой БД
        old_cursor.execute("SELECT * FROM food_log")
        food_log_data = old_cursor.fetchall()
        
        if not food_log_data:
            logger.info("Нет данных журнала питания для миграции.")
            old_conn.close()
            return True
            
        # Получаем имена столбцов
        old_cursor.execute("PRAGMA table_info(food_log)")
        columns = [col[1] for col in old_cursor.fetchall()]
        
        logger.info(f"Найдено {len(food_log_data)} записей журнала питания для миграции.")
        
        # Переносим данные в новую БД
        with get_food_log_connection() as new_conn:
            with transaction(new_conn) as tx:
                new_cursor = tx.cursor()
                
                for log in food_log_data:
                    # Создаем словарь с данными записи
                    log_dict = {columns[i]: log[i] for i in range(len(columns))}
                    
                    # Получаем пищевую ценность продукта из таблицы products
                    user_id = log_dict.get('user_id')
                    food_name = log_dict.get('food_name')
                    weight = log_dict.get('weight')
                    date_str = log_dict.get('date')
                    time_str = log_dict.get('time')
                    edit_code = log_dict.get('edit_code')
                    
                    # Находим пищевую ценность продукта
                    old_cursor.execute(
                        "SELECT kcal, protein, fat, carbs FROM products WHERE name = ?",
                        (food_name,)
                    )
                    product = old_cursor.fetchone()
                    
                    if product:
                        kcal, protein, fat, carbs = product
                        
                        # Рассчитываем пищевую ценность для указанного веса
                        weight_factor = weight / 100.0
                        kcal_total = kcal * weight_factor
                        protein_total = protein * weight_factor
                        fat_total = fat * weight_factor
                        carbs_total = carbs * weight_factor
                        
                        # Добавляем запись в новую БД
                        new_cursor.execute(
                            """INSERT OR REPLACE INTO food_log 
                               (user_id, food_name, weight, kcal, protein, fat, carbs, date, time, edit_code)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (user_id, food_name, weight, kcal_total, protein_total, fat_total, carbs_total, 
                             date_str, time_str, edit_code)
                        )
                    else:
                        logger.warning(f"Не удалось найти продукт {food_name} для записи в журнале питания")
                
        # Проверяем таблицу daily_intake
        old_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_intake'")
        if old_cursor.fetchone():
            # Получаем данные daily_intake из старой БД
            old_cursor.execute("SELECT * FROM daily_intake")
            daily_intake_data = old_cursor.fetchall()
            
            if daily_intake_data:
                logger.info(f"Найдено {len(daily_intake_data)} записей daily_intake для миграции.")
                
                # Переносим данные в новую БД
                with get_food_log_connection() as new_conn:
                    with transaction(new_conn) as tx:
                        new_cursor = tx.cursor()
                        
                        old_cursor.execute("PRAGMA table_info(daily_intake)")
                        di_columns = [col[1] for col in old_cursor.fetchall()]
                        
                        for intake in daily_intake_data:
                            # Создаем словарь с данными записи
                            intake_dict = {di_columns[i]: intake[i] for i in range(len(di_columns))}
                            
                            new_cursor.execute(
                                "INSERT OR REPLACE INTO daily_intake (user_id, date, calories, protein, fat, carbs) VALUES (?, ?, ?, ?, ?, ?)",
                                (intake_dict.get('user_id'), 
                                 intake_dict.get('date'), 
                                 intake_dict.get('calories', 0), 
                                 intake_dict.get('protein', 0), 
                                 intake_dict.get('fat', 0), 
                                 intake_dict.get('carbs', 0))
                            )
        
        old_conn.close()
        logger.info("Миграция данных журнала питания завершена успешно.")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при миграции данных журнала питания: {e}")
        return False

def run_migration():
    """Запускает полный процесс миграции."""
    logger.info("Начало процесса миграции базы данных...")
    
    # Создаем резервную копию старой базы данных
    if not backup_old_database():
        logger.error("Не удалось создать резервную копию. Миграция отменена.")
        return False
    
    # Проверяем существование директории для новых баз данных
    ensure_db_dir()
    
    # Выполняем миграцию данных
    users_success = migrate_users()
    products_success = migrate_products()
    food_log_success = migrate_food_log()
    
    if users_success and products_success and food_log_success:
        logger.info("Миграция базы данных завершена успешно.")
        
        # Переименовываем старую базу данных для предотвращения её использования
        try:
            os.rename(OLD_DB_PATH, f"{OLD_DB_PATH}.old")
            logger.info(f"Старая база данных переименована в {OLD_DB_PATH}.old")
        except Exception as e:
            logger.warning(f"Не удалось переименовать старую базу данных: {e}")
        
        return True
    else:
        logger.error("Миграция базы данных завершилась с ошибками.")
        return False

if __name__ == "__main__":
    try:
        # Запрашиваем подтверждение пользователя
        answer = input("Вы хотите начать миграцию базы данных? (y/n): ")
        if answer.lower() == 'y':
            success = run_migration()
            if success:
                print("Миграция завершена успешно!")
            else:
                print("Миграция завершилась с ошибками. Проверьте migration.log для подробностей.")
        else:
            print("Миграция отменена пользователем.")
    except KeyboardInterrupt:
        print("\nМиграция прервана пользователем.")
    except Exception as e:
        print(f"Непредвиденная ошибка: {e}")
        logger.error(f"Непредвиденная ошибка: {e}") 