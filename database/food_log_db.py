"""
Модуль для работы с базой данных журнала питания.
Предоставляет функции для добавления, получения и редактирования записей о приеме пищи.
"""

import logging
import uuid
from datetime import date, datetime
from .connection_pool import get_food_log_connection, transaction
from .products_db import get_product_data
from .users_db import update_daily_intake, get_current_day
import sqlite3

logger = logging.getLogger(__name__)

def generate_edit_code():
    """
    Генерировать уникальный код для редактирования записи.
    
    Returns:
        str: Уникальный код
    """
    return str(uuid.uuid4())[:8].upper()

def log_food(user_id, food_name, weight):
    """
    Добавить запись о приеме пищи.
    
    Args:
        user_id (int): ID пользователя
        food_name (str): Название продукта
        weight (float): Вес продукта в граммах
        
    Returns:
        str: Код для редактирования записи или None в случае ошибки
    """
    try:
        # Получаем данные о продукте
        product_data = get_product_data(food_name)
        if not product_data:
            logger.warning(f"Не удалось найти продукт: {food_name}")
            return None
        
        kcal, protein, fat, carbs = product_data
        
        # Рассчитываем пищевую ценность для указанного веса
        weight_factor = weight / 100.0
        kcal_total = kcal * weight_factor
        protein_total = protein * weight_factor
        fat_total = fat * weight_factor
        carbs_total = carbs * weight_factor
        
        now = datetime.now()
        # Получаем текущий день с учетом времени окончания дня
        date_str = get_current_day(user_id)
        time_str = now.strftime('%H:%M:%S')
        edit_code = generate_edit_code()
        
        with get_food_log_connection() as conn:
            with transaction(conn) as tx:
                cursor = tx.cursor()
                
                # Добавляем запись о приеме пищи
                cursor.execute(
                    """INSERT INTO food_log 
                       (user_id, food_name, weight, kcal, protein, fat, carbs, date, time, edit_code, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, food_name, weight, kcal_total, protein_total, fat_total, carbs_total, 
                     date_str, time_str, edit_code, now.strftime('%Y-%m-%d %H:%M:%S'))
                )
                
                # Обновляем дневное потребление в той же транзакции
                cursor.execute(
                    """SELECT COALESCE(SUM(kcal), 0), COALESCE(SUM(protein), 0), 
                              COALESCE(SUM(fat), 0), COALESCE(SUM(carbs), 0)
                       FROM food_log
                       WHERE user_id = ? AND date = ?""",
                    (user_id, date_str)
                )
                
                result = cursor.fetchone()
                if result:
                    calories, protein, fat, carbs = result
                    cursor.execute(
                        """INSERT OR REPLACE INTO daily_intake 
                           (user_id, date, calories, protein, fat, carbs)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (user_id, date_str, calories, protein, fat, carbs)
                    )
                
                logger.info(f"Добавлена запись о приеме пищи: {food_name} ({weight}г) для пользователя {user_id}")
                return edit_code
                
    except sqlite3.Error as e:
        logger.error(f"Ошибка SQLite при добавлении записи о приеме пищи: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при добавлении записи о приеме пищи: {e}")
        return None

def get_food_log(user_id, log_date=None):
    """
    Получить журнал питания пользователя.
    
    Args:
        user_id (int): ID пользователя
        log_date (str, optional): Дата в формате YYYY-MM-DD или None для текущего дня
        
    Returns:
        list: Список записей о приеме пищи
    """
    # Если дата не указана, используем текущий день
    if log_date is None:
        log_date = get_current_day(user_id)
    
    with get_food_log_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT id, food_name, weight, kcal, protein, fat, carbs, time, edit_code
               FROM food_log
               WHERE user_id = ? AND date = ?
               ORDER BY time ASC""",
            (user_id, log_date)
        )
        
        results = cursor.fetchall()
        
        # Преобразуем результаты в список словарей
        food_log = []
        for row in results:
            food_log.append({
                "id": row[0],
                "food_name": row[1],
                "weight": row[2],
                "kcal": row[3],
                "protein": row[4],
                "fat": row[5],
                "carbs": row[6],
                "time": row[7],
                "edit_code": row[8]
            })
        
        logger.debug(f"Получен журнал питания для пользователя {user_id} на дату {log_date}: {len(food_log)} записей")
        
        return food_log

def update_food_log(log_id, weight):
    """
    Обновить запись о приеме пищи.
    
    Args:
        log_id (int): ID записи
        weight (float): Новый вес продукта в граммах
        
    Returns:
        tuple: (bool, user_id, log_date) - успех операции, ID пользователя и дата записи
    """
    user_id = None
    log_date = None
    
    with get_food_log_connection() as conn:
        cursor = conn.cursor()
        
        # Получаем данные о записи
        cursor.execute(
            "SELECT user_id, food_name, date FROM food_log WHERE id = ?",
            (log_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            logger.warning(f"Не удалось найти запись с ID {log_id}")
            return False, None, None
        
        user_id, food_name, log_date = result
        
        # Получаем данные о продукте
        product_data = get_product_data(food_name)
        if not product_data:
            logger.warning(f"Не удалось найти продукт: {food_name}")
            return False, user_id, log_date
        
        kcal, protein, fat, carbs = product_data
        
        # Рассчитываем пищевую ценность для указанного веса
        weight_factor = weight / 100.0
        kcal_total = kcal * weight_factor
        protein_total = protein * weight_factor
        fat_total = fat * weight_factor
        carbs_total = carbs * weight_factor
        
        # Обновляем запись
        cursor.execute(
            """UPDATE food_log
               SET weight = ?, kcal = ?, protein = ?, fat = ?, carbs = ?
               WHERE id = ?""",
            (weight, kcal_total, protein_total, fat_total, carbs_total, log_id)
        )
        
        conn.commit()
        logger.info(f"Обновлена запись о приеме пищи: ID {log_id}, новый вес {weight}г")
        
        # Возвращаем True и данные для обновления дневного потребления
        return True, user_id, log_date

def delete_food_log(log_id):
    """
    Удалить запись о приеме пищи.
    
    Args:
        log_id (int): ID записи
        
    Returns:
        tuple: (bool, user_id, log_date) - успех операции, ID пользователя и дата записи
    """
    with get_food_log_connection() as conn:
        cursor = conn.cursor()
        
        # Получаем данные о записи
        cursor.execute(
            "SELECT user_id, date FROM food_log WHERE id = ?",
            (log_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            logger.warning(f"Не удалось найти запись с ID {log_id}")
            return False, None, None
        
        user_id, log_date = result
        
        # Удаляем запись
        cursor.execute("DELETE FROM food_log WHERE id = ?", (log_id,))
        conn.commit()
        
        logger.info(f"Удалена запись о приеме пищи: ID {log_id}")
        
        # Возвращаем данные для обновления дневного потребления
        return True, user_id, log_date

def update_daily_intake_for_user(user_id, log_date=None):
    """
    Обновить дневное потребление пользователя на основе журнала питания.
    
    Args:
        user_id (int): ID пользователя
        log_date (str, optional): Дата в формате YYYY-MM-DD или None для текущего дня
    """
    # Если дата не указана, используем текущий день
    if log_date is None:
        log_date = get_current_day(user_id)
    
    try:
        with get_food_log_connection() as conn:
            cursor = conn.cursor()
            
            # Получаем суммарное потребление за день
            cursor.execute(
                """SELECT COALESCE(SUM(kcal), 0), COALESCE(SUM(protein), 0), 
                          COALESCE(SUM(fat), 0), COALESCE(SUM(carbs), 0)
                   FROM food_log
                   WHERE user_id = ? AND date = ?""",
                (user_id, log_date)
            )
            
            result = cursor.fetchone()
            
            if result:
                calories, protein, fat, carbs = result
                # Обновляем дневное потребление
                cursor.execute(
                    """INSERT OR REPLACE INTO daily_intake 
                       (user_id, date, calories, protein, fat, carbs)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (user_id, log_date, calories, protein, fat, carbs)
                )
                conn.commit()
                logger.debug(f"Обновлено дневное потребление для пользователя {user_id} на дату {log_date}: "
                           f"{calories:.1f} ккал, {protein:.1f}Б, {fat:.1f}Ж, {carbs:.1f}У")
    except sqlite3.Error as e:
        logger.error(f"Ошибка SQLite при обновлении дневного потребления: {e}")
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка при обновлении дневного потребления: {e}")
        if conn:
            conn.rollback()
        raise

def get_food_log_by_edit_code(edit_code):
    """
    Получить запись о приеме пищи по коду редактирования.
    
    Args:
        edit_code (str): Код редактирования
        
    Returns:
        dict: Данные о записи или None, если запись не найдена
    """
    with get_food_log_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT id, user_id, food_name, weight, kcal, protein, fat, carbs, date, time
               FROM food_log
               WHERE edit_code = ?""",
            (edit_code,)
        )
        
        result = cursor.fetchone()
        
        if result:
            return {
                "id": result[0],
                "user_id": result[1],
                "food_name": result[2],
                "weight": result[3],
                "kcal": result[4],
                "protein": result[5],
                "fat": result[6],
                "carbs": result[7],
                "date": result[8],
                "time": result[9]
            }
        
        logger.warning(f"Не удалось найти запись с кодом редактирования {edit_code}")
        return None 