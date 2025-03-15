import os
from dotenv import load_dotenv

# Загрузка переменных из .env файла
load_dotenv()

# Основные настройки
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "719920992"))

# DeepSeek API настройки
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL")

ACTIVITY_COEFFS = {
    "Сидячий": 1.2,
    "Легкая активность": 1.375,
    "Умеренная активность": 1.55,
    "Высокая активность": 1.725,
    "Очень высокая активность": 1.9
}

MACRO_RATIOS = {
    "Поддержание веса": (0.3, 0.3, 0.4),
    "Снижение веса": (0.4, 0.3, 0.3),
    "Набор массы": (0.25, 0.25, 0.5)
}

# Состояния для диалога с пользователем
# Важно: каждое состояние должно иметь уникальный номер
GENDER = 0
AGE = 1
WEIGHT = 2
HEIGHT = 3
ACTIVITY = 4
GOAL = 5
TIMEZONE = 6
FOOD_NAME = 7
FOOD_WEIGHT = 8
ADMIN_ADD = 9
ADMIN_KCAL = 10
ADMIN_PROTEIN = 11
ADMIN_FAT = 12
ADMIN_CARBS = 13
EDIT_FOOD_WEIGHT = 14

# Состояния для настроек
CUSTOM_MACROS = 15
DAY_END_TIME = 16