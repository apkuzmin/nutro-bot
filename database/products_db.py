"""
Модуль для работы с базой данных продуктов.
Предоставляет функции для добавления, поиска и получения информации о продуктах.
"""

import time
import logging
from functools import lru_cache
from .db_utils import get_products_db  # Оставляем для обратной совместимости
from .connection_pool import get_products_connection, transaction

logger = logging.getLogger(__name__)

@lru_cache(maxsize=100)
def get_product_data(food_name):
    """
    Получить данные о продукте по его названию.
    
    Args:
        food_name (str): Название продукта
        
    Returns:
        tuple: (kcal, protein, fat, carbs) или None, если продукт не найден
    """
    with get_products_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT kcal, protein, fat, carbs FROM products WHERE name = ?", (food_name,))
        result = cursor.fetchone()
        return result

def save_product_data(food_name, kcal, protein, fat, carbs):
    """
    Сохранить данные о продукте.
    
    Args:
        food_name (str): Название продукта
        kcal (float): Калории на 100г
        protein (float): Белки на 100г
        fat (float): Жиры на 100г
        carbs (float): Углеводы на 100г
    """
    with get_products_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            current_time = time.strftime('%Y-%m-%d %H:%M:%S')
            
            # Проверяем, существует ли уже продукт
            cursor.execute("SELECT id FROM products WHERE name = ?", (food_name,))
            result = cursor.fetchone()
            
            if result:
                # Обновляем существующий продукт
                product_id = result[0]
                cursor.execute(
                    "UPDATE products SET kcal = ?, protein = ?, fat = ?, carbs = ?, updated_at = ? WHERE id = ?",
                    (kcal, protein, fat, carbs, current_time, product_id)
                )
                logger.info(f"Обновлен продукт: {food_name}")
            else:
                # Добавляем новый продукт
                cursor.execute(
                    "INSERT INTO products (name, kcal, protein, fat, carbs, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (food_name, kcal, protein, fat, carbs, current_time, current_time)
                )
                logger.info(f"Добавлен новый продукт: {food_name}")
            
            # Очищаем кэш для этого продукта
            get_product_data.cache_clear()

def search_products(query, limit=10):
    """
    Поиск продуктов по части названия.
    
    Args:
        query (str): Часть названия продукта для поиска
        limit (int): Максимальное количество результатов
        
    Returns:
        list: Список названий продуктов, соответствующих запросу
    """
    with get_products_connection() as conn:
        cursor = conn.cursor()
        
        # Используем LIKE для поиска по части названия
        cursor.execute(
            "SELECT name FROM products WHERE name LIKE ? ORDER BY name LIMIT ?",
            (f"%{query}%", limit)
        )
        
        results = cursor.fetchall()
        return [row[0] for row in results]

def get_product_by_barcode(barcode):
    """
    Получить данные о продукте по штрихкоду.
    
    Args:
        barcode (str): Штрихкод продукта
        
    Returns:
        tuple: (name, kcal, protein, fat, carbs) или None, если продукт не найден
    """
    with get_products_connection() as conn:
        cursor = conn.cursor()
        
        # Сначала ищем штрихкод в таблице barcodes
        cursor.execute(
            """
            SELECT p.name, p.kcal, p.protein, p.fat, p.carbs
            FROM barcodes b
            JOIN products p ON b.product_id = p.id
            WHERE b.barcode = ?
            """,
            (barcode,)
        )
        
        result = cursor.fetchone()
        
        if result:
            logger.info(f"Найден продукт по штрихкоду {barcode}: {result[0]}")
        else:
            logger.info(f"Продукт по штрихкоду {barcode} не найден")
            
        return result

def save_barcode_product(barcode, food_name):
    """
    Связать штрихкод с продуктом.
    
    Args:
        barcode (str): Штрихкод продукта
        food_name (str): Название продукта
        
    Returns:
        bool: True, если операция выполнена успешно, иначе False
    """
    with get_products_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            # Проверяем, существует ли продукт
            cursor.execute("SELECT id FROM products WHERE name = ?", (food_name,))
            product_result = cursor.fetchone()
            
            if not product_result:
                logger.error(f"Не удалось связать штрихкод {barcode} с продуктом {food_name}: продукт не найден")
                return False
                
            product_id = product_result[0]
            
            # Проверяем, существует ли уже такой штрихкод
            cursor.execute("SELECT product_id FROM barcodes WHERE barcode = ?", (barcode,))
            barcode_result = cursor.fetchone()
            
            current_time = time.strftime('%Y-%m-%d %H:%M:%S')
            
            if barcode_result:
                # Обновляем существующий штрихкод
                cursor.execute(
                    "UPDATE barcodes SET product_id = ? WHERE barcode = ?",
                    (product_id, barcode)
                )
                logger.info(f"Обновлен штрихкод {barcode} для продукта {food_name}")
            else:
                # Добавляем новый штрихкод
                cursor.execute(
                    "INSERT INTO barcodes (barcode, product_id, created_at) VALUES (?, ?, ?)",
                    (barcode, product_id, current_time)
                )
                logger.info(f"Добавлен новый штрихкод {barcode} для продукта {food_name}")
                
            return True 