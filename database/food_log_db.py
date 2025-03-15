"""
Модуль для работы с базой данных журнала питания.
Предоставляет функции для добавления, получения и редактирования записей о приеме пищи.
"""

import logging
import uuid
from datetime import date, datetime
from .db_utils import get_food_log_db
from .products_db import get_product_data
from .users_db import update_daily_intake, get_current_day

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
        str: Код для редактирования записи
    """
    now = datetime.now()
    # Получаем текущий день с учетом времени завершения дня
    date_str = get_current_day(user_id)
    time_str = now.time().isoformat()
    edit_code = generate_edit_code()
    
    conn = get_food_log_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO food_log (user_id, food_name, weight, date, time, edit_code, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, food_name, weight, date_str, time_str, edit_code, now.isoformat(), now.isoformat()))
    
    conn.commit()
    conn.close()
    
    # Обновляем дневное потребление
    update_daily_intake_for_user(user_id, date_str)
    
    logger.debug(f"Добавлена запись о приеме пищи: {food_name} ({weight}г) для пользователя {user_id} на дату {date_str}")
    return edit_code

def get_food_log(user_id, log_date=None):
    """
    Получить журнал питания пользователя.
    
    Args:
        user_id (int): ID пользователя
        log_date (str, optional): Дата в формате ISO (YYYY-MM-DD). 
                                 По умолчанию - текущий день с учетом времени завершения дня.
        
    Returns:
        list: Список записей о приеме пищи
    """
    if log_date is None:
        log_date = get_current_day(user_id)
    
    conn = get_food_log_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, food_name, weight, date, time, edit_code
        FROM food_log
        WHERE user_id = ? AND date = ?
        ORDER BY date, time ASC
    """, (user_id, log_date))
    
    logs = cursor.fetchall()
    conn.close()
    
    # Преобразуем результаты в список словарей с дополнительной информацией о питательной ценности
    result = []
    for log in logs:
        log_id, food_name, weight, log_date, log_time, edit_code = log
        
        # Получаем данные о продукте
        product_data = get_product_data(food_name)
        if product_data:
            kcal, protein, fat, carbs = product_data
            
            # Рассчитываем питательную ценность для указанного веса
            kcal_total = kcal * weight / 100
            protein_total = protein * weight / 100
            fat_total = fat * weight / 100
            carbs_total = carbs * weight / 100
            
            result.append({
                "id": log_id,
                "food_name": food_name,
                "weight": weight,
                "kcal": kcal_total,
                "protein": protein_total,
                "fat": fat_total,
                "carbs": carbs_total,
                "timestamp": f"{log_date}T{log_time}",
                "edit_code": edit_code
            })
    
    logger.debug(f"Получен журнал питания для пользователя {user_id} на дату {log_date}: {len(result)} записей")
    return result

def update_food_log(log_id, weight):
    """
    Обновить запись о приеме пищи.
    
    Args:
        log_id (int): ID записи
        weight (float): Новый вес продукта в граммах
        
    Returns:
        bool: True, если запись успешно обновлена
    """
    conn = get_food_log_db()
    cursor = conn.cursor()
    
    # Получаем user_id для последующего обновления дневного потребления
    cursor.execute("SELECT user_id FROM food_log WHERE id = ?", (log_id,))
    user_id_result = cursor.fetchone()
    
    if not user_id_result:
        logger.error(f"Не удалось найти запись с ID {log_id}")
        conn.close()
        return False
    
    user_id = user_id_result[0]
    now = datetime.now().isoformat()
    
    cursor.execute("""
        UPDATE food_log 
        SET weight = ?, updated_at = ?
        WHERE id = ?
    """, (weight, now, log_id))
    
    conn.commit()
    conn.close()
    
    # Обновляем дневное потребление
    update_daily_intake_for_user(user_id)
    
    logger.debug(f"Обновлена запись о приеме пищи (ID: {log_id}) с новым весом: {weight}г")
    return True

def delete_food_log(log_id):
    """
    Удалить запись о приеме пищи.
    
    Args:
        log_id (int): ID записи
        
    Returns:
        bool: True, если запись успешно удалена
    """
    conn = get_food_log_db()
    cursor = conn.cursor()
    
    # Получаем user_id для последующего обновления дневного потребления
    cursor.execute("SELECT user_id FROM food_log WHERE id = ?", (log_id,))
    user_id_result = cursor.fetchone()
    
    if not user_id_result:
        logger.error(f"Не удалось найти запись с ID {log_id}")
        conn.close()
        return False
    
    user_id = user_id_result[0]
    
    cursor.execute("DELETE FROM food_log WHERE id = ?", (log_id,))
    
    conn.commit()
    conn.close()
    
    # Обновляем дневное потребление
    update_daily_intake_for_user(user_id)
    
    logger.debug(f"Удалена запись о приеме пищи (ID: {log_id})")
    return True

def update_daily_intake_for_user(user_id, log_date=None):
    """
    Обновить дневное потребление пользователя на основе журнала питания.
    
    Args:
        user_id (int): ID пользователя
        log_date (str, optional): Дата в формате ISO (YYYY-MM-DD). 
                                 По умолчанию - текущий день с учетом времени завершения дня.
    """
    if log_date is None:
        log_date = get_current_day(user_id)
    
    # Получаем все записи о приеме пищи за указанную дату
    food_logs = get_food_log(user_id, log_date)
    
    # Суммируем питательную ценность
    total_kcal = sum(log["kcal"] for log in food_logs)
    total_protein = sum(log["protein"] for log in food_logs)
    total_fat = sum(log["fat"] for log in food_logs)
    total_carbs = sum(log["carbs"] for log in food_logs)
    
    # Обновляем дневное потребление
    update_daily_intake(user_id, total_kcal, total_protein, total_fat, total_carbs, log_date)
    
    logger.debug(f"Обновлено дневное потребление для пользователя {user_id} на дату {log_date}")

def get_food_log_by_edit_code(edit_code):
    """
    Получить запись о приеме пищи по коду редактирования.
    
    Args:
        edit_code (str): Код редактирования
        
    Returns:
        dict: Информация о записи или None, если запись не найдена
    """
    conn = get_food_log_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, user_id, food_name, weight, date, time
        FROM food_log
        WHERE edit_code = ?
    """, (edit_code,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        log_id, user_id, food_name, weight, log_date, log_time = result
        
        # Получаем данные о продукте
        product_data = get_product_data(food_name)
        if product_data:
            kcal, protein, fat, carbs = product_data
            
            return {
                "id": log_id,
                "user_id": user_id,
                "food_name": food_name,
                "weight": weight,
                "kcal_per_100g": kcal,
                "protein_per_100g": protein,
                "fat_per_100g": fat,
                "carbs_per_100g": carbs,
                "date": log_date,
                "time": log_time,
                "edit_code": edit_code
            }
    
    return None 