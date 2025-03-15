"""
Модуль для работы с базой данных пользователей.
Предоставляет функции для работы с данными пользователей и их дневным потреблением.
"""

import time
import logging
from datetime import date, datetime, timedelta
from .db_utils import get_users_db

logger = logging.getLogger(__name__)

def get_user_data(user_id):
    """
    Получить данные пользователя.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        tuple: (daily_calories, protein, fat, carbs) или None, если пользователь не найден
    """
    conn = get_users_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT daily_calories, protein, fat, carbs FROM users WHERE user_id = ?", 
        (user_id,)
    )
    result = cursor.fetchone()
    
    conn.close()
    return result

def get_user_profile(user_id):
    """
    Получить полный профиль пользователя.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        dict: Данные профиля пользователя или None, если пользователь не найден
    """
    conn = get_users_db()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT gender, age, weight, height, activity, goal, 
                 daily_calories, protein, fat, carbs, language, day_end_time 
          FROM users WHERE user_id = ?""", 
        (user_id,)
    )
    result = cursor.fetchone()
    
    conn.close()
    
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
            "day_end_time": result[11]
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
    conn = get_users_db()
    cursor = conn.cursor()
    
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # Проверяем, существует ли уже пользователь
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    existing_user = cursor.fetchone()
    
    if existing_user:
        # Обновляем существующего пользователя
        cursor.execute("""
            UPDATE users 
            SET daily_calories = ?, protein = ?, fat = ?, carbs = ?, updated_at = ?
            WHERE user_id = ?
        """, (daily_calories, protein, fat, carbs, current_time, user_id))
    else:
        # Добавляем нового пользователя
        cursor.execute("""
            INSERT INTO users (user_id, daily_calories, protein, fat, carbs, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, daily_calories, protein, fat, carbs, current_time, current_time))
    
    conn.commit()
    conn.close()

def save_user_profile(user_id, gender, age, weight, height, activity, goal, daily_calories, protein, fat, carbs, language='ru', timezone=3):
    """
    Сохранить полный профиль пользователя.
    
    Args:
        user_id (int): ID пользователя
        gender (str): Пол пользователя
        age (int): Возраст пользователя
        weight (float): Вес пользователя в кг
        height (float): Рост пользователя в см
        activity (str): Уровень активности пользователя
        goal (str): Цель пользователя
        daily_calories (float): Дневная норма калорий
        protein (float): Дневная норма белков в граммах
        fat (float): Дневная норма жиров в граммах
        carbs (float): Дневная норма углеводов в граммах
        language (str, optional): Язык пользователя. По умолчанию 'ru'.
        timezone (int, optional): Часовой пояс пользователя (смещение от UTC в часах). По умолчанию 3 (Москва).
    """
    conn = get_users_db()
    cursor = conn.cursor()
    
    cursor.execute(
        """INSERT OR REPLACE INTO users 
           (user_id, gender, age, weight, height, activity, goal, 
            daily_calories, protein, fat, carbs, language, timezone)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, gender, age, weight, height, activity, goal, 
         daily_calories, protein, fat, carbs, language, timezone)
    )
    
    conn.commit()
    conn.close()
    
    logger.debug(f"Сохранен профиль пользователя {user_id}: {daily_calories:.0f} ккал, "
                f"{protein:.1f}г белка, {fat:.1f}г жиров, {carbs:.1f}г углеводов, "
                f"часовой пояс: UTC+{timezone}")
    
    return True

def save_custom_macros(user_id, calories, protein, fat, carbs):
    """
    Сохранить пользовательские значения макронутриентов.
    
    Args:
        user_id (int): ID пользователя
        calories (float): Калории
        protein (float): Белки
        fat (float): Жиры
        carbs (float): Углеводы
    """
    save_user_data(user_id, calories, protein, fat, carbs)

def get_current_day(user_id):
    """
    Получить текущий день для пользователя с учетом времени завершения дня.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        str: Текущий день в формате ISO (YYYY-MM-DD)
    """
    # Получаем время завершения дня пользователя
    day_end_time = get_day_end_time(user_id)
    
    # Разбиваем время на часы и минуты
    try:
        hours, minutes = map(int, day_end_time.split(':'))
    except (ValueError, AttributeError):
        # В случае ошибки используем значение по умолчанию
        hours, minutes = 0, 0
    
    # Получаем текущее время
    now = datetime.now()
    
    # Создаем объект datetime для времени завершения дня сегодня
    day_end_today = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    
    # Если текущее время меньше времени завершения дня,
    # то текущий день - это вчерашний день
    if now < day_end_today:
        current_day = (now - timedelta(days=1)).date()
    else:
        current_day = now.date()
    
    return current_day.isoformat()

def get_daily_intake(user_id):
    """
    Получить дневное потребление пользователя.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        tuple: (calories, protein, fat, carbs) - потребление за текущий день
    """
    # Получаем текущий день с учетом времени завершения дня
    current_day = get_current_day(user_id)
    
    conn = get_users_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT calories, protein, fat, carbs FROM daily_intake 
        WHERE user_id = ? AND date = ?
    """, (user_id, current_day))
    result = cursor.fetchone()
    
    conn.close()
    return tuple(0 if x is None else x for x in result) if result else (0, 0, 0, 0)

def update_daily_intake(user_id, calories, protein, fat, carbs, day_date=None):
    """
    Обновить дневное потребление пользователя.
    
    Args:
        user_id (int): ID пользователя
        calories (float): Калории
        protein (float): Белки
        fat (float): Жиры
        carbs (float): Углеводы
        day_date (str, optional): Дата в формате ISO (YYYY-MM-DD). 
                                 По умолчанию - текущий день с учетом времени завершения дня.
    """
    if day_date is None:
        day_date = get_current_day(user_id)
    
    conn = get_users_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR REPLACE INTO daily_intake (user_id, date, calories, protein, fat, carbs)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, day_date, calories, protein, fat, carbs))
    
    conn.commit()
    conn.close()
    logger.debug(f"Обновлено дневное потребление для пользователя {user_id} на дату {day_date}")

def delete_user_data(user_id):
    """
    Удалить все данные пользователя.
    
    Args:
        user_id (int): ID пользователя
    """
    conn = get_users_db()
    cursor = conn.cursor()
    
    # Удаляем данные из таблицы users
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    
    # Удаляем данные из таблицы daily_intake
    cursor.execute("DELETE FROM daily_intake WHERE user_id = ?", (user_id,))
    
    conn.commit()
    conn.close()
    logger.debug(f"Удалены данные пользователя: {user_id}")

def get_day_end_time(user_id):
    """
    Получить время завершения дня пользователя.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        str: Время завершения дня в формате "HH:MM" или "00:00" по умолчанию
    """
    conn = get_users_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT day_end_time FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result and result[0]:
        return result[0]
    return "00:00"  # Значение по умолчанию

def set_day_end_time(user_id, day_end_time):
    """
    Установить время завершения дня пользователя.
    
    Args:
        user_id (int): ID пользователя
        day_end_time (str): Время завершения дня в формате "HH:MM"
        
    Returns:
        bool: True, если время успешно установлено
    """
    conn = get_users_db()
    cursor = conn.cursor()
    
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # Проверяем, существует ли уже пользователь
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    existing_user = cursor.fetchone()
    
    if existing_user:
        # Обновляем существующего пользователя
        cursor.execute("""
            UPDATE users 
            SET day_end_time = ?, updated_at = ?
            WHERE user_id = ?
        """, (day_end_time, current_time, user_id))
        logger.debug(f"Обновлено время завершения дня для пользователя {user_id}: {day_end_time}")
    else:
        # Если пользователя нет, создаем запись только с временем завершения дня
        cursor.execute("""
            INSERT INTO users (user_id, day_end_time, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, day_end_time, current_time, current_time))
        logger.debug(f"Создан новый пользователь {user_id} с временем завершения дня: {day_end_time}")
    
    conn.commit()
    conn.close()
    return True

def get_user_timezone(user_id):
    """
    Получить часовой пояс пользователя.
    
    Args:
        user_id (int): ID пользователя
        
    Returns:
        int: Часовой пояс пользователя (смещение от UTC в часах) или 3 (Москва) по умолчанию
    """
    conn = get_users_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT timezone FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        return result[0]
    return 3  # По умолчанию возвращаем UTC+3 (Москва)

def set_user_timezone(user_id, timezone):
    """
    Установить часовой пояс пользователя.
    
    Args:
        user_id (int): ID пользователя
        timezone (int): Часовой пояс (смещение от UTC в часах)
        
    Returns:
        bool: True в случае успеха
    """
    conn = get_users_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE users SET timezone = ? WHERE user_id = ?",
        (timezone, user_id)
    )
    
    conn.commit()
    conn.close()
    
    logger.debug(f"Установлен часовой пояс UTC+{timezone} для пользователя {user_id}")
    return True 