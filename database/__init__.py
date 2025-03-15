"""
Модуль для работы с базами данных приложения.
Предоставляет функции для работы с пользователями, продуктами и журналом питания.
"""

from .db_utils import init_all_db
from .users_db import (
    get_user_data, save_user_data, save_custom_macros, delete_user_data,
    get_daily_intake, get_day_end_time, set_day_end_time, get_current_day,
    get_user_timezone, set_user_timezone, save_user_profile
)
from .products_db import (
    get_product_data, save_product_data, search_products,
    get_product_by_barcode, save_barcode_product
)
from .food_log_db import (
    log_food, get_food_log, update_food_log, delete_food_log
)

# Инициализация всех баз данных при импорте модуля
init_all_db() 