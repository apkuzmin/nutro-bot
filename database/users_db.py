"""
Модуль для работы с базой данных пользователей.
Предоставляет функции для работы с данными пользователей и их дневным потреблением.
"""

import time
import logging
from datetime import date, datetime, timedelta
from .db_utils import get_users_db  # Оставляем для обратной совместимости
from .connection_pool import get_users_connection, transaction, get_food_log_connection

logger = logging.getLogger(__name__)

def get_user_data(user_id):
    """
    Получить данные пользователя.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        tuple: (daily_calories, protein, fat, carbs) или None, если пользователь не найден
    """
    with get_users_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT daily_calories, protein, fat, carbs FROM users WHERE user_id = ?", 
            (user_id,)
        )
        result = cursor.fetchone()
        
        return result

def get_user_profile(user_id):
    """
    Получить полный профиль пользователя.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        dict: Данные профиля пользователя или None, если пользователь не найден
    """
    with get_users_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT gender, age, weight, height, activity, goal, 
                     daily_calories, protein, fat, carbs, language, day_end_time, timezone 
              FROM users 
              WHERE user_id = ?""", 
            (user_id,)
        )
        result = cursor.fetchone()
        
        if result:
            return {
                "gender": result[0],
                "age": result[1],
                "weight": result[2],
                "height": result[3],
                "activity": result[4],
                "goal": result[5],
                "daily_calories": result[6],
                "protein": result[7],
                "fat": result[8],
                "carbs": result[9],
                "language": result[10],
                "day_end_time": result[11],
                "timezone": result[12]
            }
        return None

def save_user_data(user_id, daily_calories, protein, fat, carbs):
    """
    Сохранить данные пользователя.
    
    Args:
        user_id (int): ID пользователя
        daily_calories (float): Дневная норма калорий
        protein (float): Дневная норма белков
        fat (float): Дневная норма жиров
        carbs (float): Дневная норма углеводов
    """
    with get_users_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            current_time = time.strftime('%Y-%m-%d %H:%M:%S')
            
            # Проверяем, существует ли уже пользователь
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            if result:
                # Обновляем существующего пользователя
                cursor.execute(
                    """UPDATE users 
                       SET daily_calories = ?, protein = ?, fat = ?, carbs = ?, updated_at = ?
                       WHERE user_id = ?""",
                    (daily_calories, protein, fat, carbs, current_time, user_id)
                )
                logger.info(f"Обновлены данные пользователя: {user_id}")
            else:
                # Добавляем нового пользователя
                cursor.execute(
                    """INSERT INTO users 
                       (user_id, daily_calories, protein, fat, carbs, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, daily_calories, protein, fat, carbs, current_time, current_time)
                )
                logger.info(f"Добавлен новый пользователь: {user_id}")

def save_user_profile(user_id, gender, age, weight, height, activity, goal, daily_calories, protein, fat, carbs, language='ru', timezone=3):
    """
    Сохранить полный профиль пользователя.
    
    Args:
        user_id (int): ID пользователя
        gender (str): Пол пользователя
        age (int): Возраст пользователя
        weight (float): Вес пользователя
        height (float): Рост пользователя
        activity (str): Уровень активности пользователя
        goal (str): Цель пользователя
        daily_calories (float): Дневная норма калорий
        protein (float): Дневная норма белков
        fat (float): Дневная норма жиров
        carbs (float): Дневная норма углеводов
        language (str): Язык пользователя
        timezone (int): Часовой пояс пользователя
    """
    with get_users_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            current_time = time.strftime('%Y-%m-%d %H:%M:%S')
            
            # Проверяем, существует ли уже пользователь
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            if result:
                # Обновляем существующего пользователя
                cursor.execute(
                    """UPDATE users 
                       SET gender = ?, age = ?, weight = ?, height = ?, activity = ?, goal = ?,
                           daily_calories = ?, protein = ?, fat = ?, carbs = ?, language = ?, timezone = ?, updated_at = ?
                       WHERE user_id = ?""",
                    (gender, age, weight, height, activity, goal, daily_calories, protein, fat, carbs, language, timezone, current_time, user_id)
                )
                logger.info(f"Обновлен профиль пользователя: {user_id}")
            else:
                # Добавляем нового пользователя
                cursor.execute(
                    """INSERT INTO users 
                       (user_id, gender, age, weight, height, activity, goal, daily_calories, protein, fat, carbs, language, timezone, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, gender, age, weight, height, activity, goal, daily_calories, protein, fat, carbs, language, timezone, current_time, current_time)
                )
                logger.info(f"Добавлен новый профиль пользователя: {user_id}")

def save_custom_macros(user_id, calories, protein, fat, carbs):
    """
    Сохранить пользовательские макронутриенты.
    
    Args:
        user_id (int): ID пользователя
        calories (float): Дневная норма калорий
        protein (float): Дневная норма белков
        fat (float): Дневная норма жиров
        carbs (float): Дневная норма углеводов
    """
    save_user_data(user_id, calories, protein, fat, carbs)

def get_current_day(user_id):
    """
    Получить текущий день для пользователя с учетом его настроек времени окончания дня.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        str: Текущий день в формате YYYY-MM-DD
    """
    with get_users_connection() as conn:
        cursor = conn.cursor()
        
        # Получаем часовой пояс пользователя
        cursor.execute("SELECT timezone FROM users WHERE user_id = ?", (user_id,))
        timezone_result = cursor.fetchone()
        
        if timezone_result:
            timezone = timezone_result[0]
        else:
            timezone = 3  # По умолчанию используем московское время (UTC+3)
        
        # Получаем время окончания дня
        cursor.execute("SELECT day_end_time FROM users WHERE user_id = ?", (user_id,))
        day_end_time_result = cursor.fetchone()
        
        if day_end_time_result and day_end_time_result[0]:
            day_end_time = day_end_time_result[0]
        else:
            day_end_time = "00:00"  # По умолчанию день заканчивается в полночь
        
        # Получаем текущее время с учетом часового пояса
        now = datetime.utcnow() + timedelta(hours=timezone)
        
        # Парсим время окончания дня
        end_hour, end_minute = map(int, day_end_time.split(':'))
        
        # Если текущее время меньше времени окончания дня, то текущий день - вчерашний
        if now.hour < end_hour or (now.hour == end_hour and now.minute < end_minute):
            current_day = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            current_day = now.strftime('%Y-%m-%d')
        
        return current_day

def get_daily_intake(user_id):
    """
    Получить дневное потребление пользователя.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        tuple: (calories, protein, fat, carbs) или (0, 0, 0, 0), если данных нет
    """
    with get_food_log_connection() as conn:
        cursor = conn.cursor()
        
        # Получаем текущий день
        current_day = get_current_day(user_id)
        
        # Получаем дневное потребление
        cursor.execute(
            """SELECT calories, protein, fat, carbs 
               FROM daily_intake 
               WHERE user_id = ? AND date = ?""", 
            (user_id, current_day)
        )
        result = cursor.fetchone()
        
        if result:
            return result
        return (0, 0, 0, 0)

def update_daily_intake(user_id, calories, protein, fat, carbs, day_date=None):
    """
    Обновить дневное потребление пользователя.
    
    Args:
        user_id (int): ID пользователя
        calories (float): Калории
        protein (float): Белки
        fat (float): Жиры
        carbs (float): Углеводы
        day_date (str): Дата в формате YYYY-MM-DD или None для текущего дня
    """
    with get_food_log_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            # Если дата не указана, используем текущий день
            if day_date is None:
                day_date = get_current_day(user_id)
            
            # Обновляем или добавляем запись
            cursor.execute(
                """INSERT OR REPLACE INTO daily_intake (user_id, date, calories, protein, fat, carbs)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, day_date, calories, protein, fat, carbs)
            )
            
            logger.info(f"Обновлено дневное потребление пользователя {user_id} на {day_date}")

def delete_user_data(user_id):
    """
    Удалить все данные пользователя.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        bool: True, если данные удалены успешно, иначе False
    """
    # Удаляем данные из базы пользователей
    with get_users_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            # Удаляем данные пользователя
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            
            logger.info(f"Удалены данные пользователя из таблицы users: {user_id}")
    
    # Удаляем данные из базы логов питания
    with get_food_log_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            # Удаляем данные из таблицы daily_intake
            cursor.execute("DELETE FROM daily_intake WHERE user_id = ?", (user_id,))
            # Удаляем данные из таблицы food_log
            cursor.execute("DELETE FROM food_log WHERE user_id = ?", (user_id,))
            
            logger.info(f"Удалены данные пользователя из таблиц daily_intake и food_log: {user_id}")
    
    return True

def get_day_end_time(user_id):
    """
    Получить время окончания дня для пользователя.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        str: Время окончания дня в формате HH:MM или "00:00" по умолчанию
    """
    with get_users_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT day_end_time FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            return result[0]
        return "00:00"  # По умолчанию день заканчивается в полночь

def set_day_end_time(user_id, day_end_time):
    """
    Установить время окончания дня для пользователя.
    
    Args:
        user_id (int): ID пользователя
        day_end_time (str): Время окончания дня в формате HH:MM
        
    Returns:
        bool: True, если время установлено успешно, иначе False
    """
    with get_users_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            # Проверяем, существует ли пользователь
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            current_time = time.strftime('%Y-%m-%d %H:%M:%S')
            
            if result:
                # Обновляем время окончания дня
                cursor.execute(
                    "UPDATE users SET day_end_time = ?, updated_at = ? WHERE user_id = ?",
                    (day_end_time, current_time, user_id)
                )
                logger.info(f"Обновлено время окончания дня для пользователя {user_id}: {day_end_time}")
                return True
            else:
                # Пользователь не существует
                logger.warning(f"Не удалось установить время окончания дня для пользователя {user_id}: пользователь не найден")
                return False

def get_user_timezone(user_id):
    """
    Получить часовой пояс пользователя.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        int: Часовой пояс пользователя (смещение от UTC в часах) или 3 по умолчанию (московское время)
    """
    with get_users_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT timezone FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result:
            return result[0]
        return 3  # По умолчанию используем московское время (UTC+3)

def set_user_timezone(user_id, timezone):
    """
    Установить часовой пояс пользователя.
    
    Args:
        user_id (int): ID пользователя
        timezone (int): Часовой пояс (смещение от UTC в часах)
        
    Returns:
        bool: True, если часовой пояс установлен успешно, иначе False
    """
    with get_users_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            # Проверяем, существует ли пользователь
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            current_time = time.strftime('%Y-%m-%d %H:%M:%S')
            
            if result:
                # Обновляем часовой пояс
                cursor.execute(
                    "UPDATE users SET timezone = ?, updated_at = ? WHERE user_id = ?",
                    (timezone, current_time, user_id)
                )
                logger.info(f"Обновлен часовой пояс для пользователя {user_id}: {timezone}")
                return True
            else:
                # Пользователь не существует
                logger.warning(f"Не удалось установить часовой пояс для пользователя {user_id}: пользователь не найден")
                return False 