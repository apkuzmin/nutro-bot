"""
Модуль для работы с базой данных продуктов.
Предоставляет функции для добавления, поиска и получения информации о продуктах.
"""

import time
import logging
from functools import lru_cache
from .db_utils import get_products_db

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
    conn = get_products_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT kcal, protein, fat, carbs FROM products WHERE name = ?", (food_name,))
    result = cursor.fetchone()
    
    conn.close()
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
    conn = get_products_db()
    cursor = conn.cursor()
    
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # Проверяем, существует ли уже продукт
    cursor.execute("SELECT id FROM products WHERE name = ?", (food_name,))
    existing_product = cursor.fetchone()
    
    if existing_product:
        # Обновляем существующий продукт
        cursor.execute("""
            UPDATE products 
            SET kcal = ?, protein = ?, fat = ?, carbs = ?, updated_at = ?
            WHERE name = ?
        """, (kcal, protein, fat, carbs, current_time, food_name))
        logger.debug(f"Обновлен продукт: {food_name}")
    else:
        # Добавляем новый продукт
        cursor.execute("""
            INSERT INTO products (name, kcal, protein, fat, carbs, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (food_name, kcal, protein, fat, carbs, current_time, current_time))
        logger.debug(f"Добавлен новый продукт: {food_name}")
    
    conn.commit()
    conn.close()
    
    # Очищаем кэш для этого продукта
    get_product_data.cache_clear()

def search_products(query, limit=10):
    """
    Поиск продуктов по названию.
    
    Args:
        query (str): Строка поиска
        limit (int): Максимальное количество результатов
        
    Returns:
        list: Список названий продуктов, соответствующих запросу
    """
    conn = get_products_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT name FROM products WHERE name LIKE ? LIMIT ?", 
        (f"%{query}%", limit)
    )
    results = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    logger.debug(f"Поиск продуктов по запросу '{query}': найдено {len(results)} результатов")
    return results

def get_product_by_barcode(barcode):
    """
    Получить продукт по штрихкоду.
    
    Args:
        barcode (str): Штрихкод продукта
        
    Returns:
        dict: Информация о продукте или None, если продукт не найден
    """
    conn = get_products_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.name, p.kcal, p.protein, p.fat, p.carbs 
        FROM barcodes b
        JOIN products p ON b.product_id = p.id
        WHERE b.barcode = ?
    """, (barcode,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            "name": result[0],
            "kcal": result[1],
            "protein": result[2],
            "fat": result[3],
            "carbs": result[4]
        }
    return None

def save_barcode_product(barcode, food_name):
    """
    Сохранить связь между штрихкодом и продуктом.
    
    Args:
        barcode (str): Штрихкод продукта
        food_name (str): Название продукта
    """
    conn = get_products_db()
    cursor = conn.cursor()
    
    # Получаем ID продукта
    cursor.execute("SELECT id FROM products WHERE name = ?", (food_name,))
    product_id = cursor.fetchone()
    
    if product_id:
        product_id = product_id[0]
        cursor.execute(
            "INSERT OR REPLACE INTO barcodes (barcode, product_id) VALUES (?, ?)",
            (barcode, product_id)
        )
        conn.commit()
        logger.debug(f"Сохранен штрихкод {barcode} для продукта {food_name}")
    else:
        logger.error(f"Не удалось найти продукт '{food_name}' для сохранения штрихкода")
    
    conn.close() 