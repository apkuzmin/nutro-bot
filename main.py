import logging
import os
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler, ContextTypes
from handlers.menu_handlers import start, settings, subscription, home
from handlers.user_data_handlers import update, gender, age, weight, height, activity, goal, timezone
from handlers.food_handlers import add_food, food_name, food_name_buttons, food_weight, admin_kcal, admin_protein, admin_fat, admin_carbs, handle_webapp_data
from handlers.log_handlers import show_food_log, edit_menu, edit_food_weight
from handlers.utils import cancel, get_main_menu, send_daily_summary, send_daily_summary_now, schedule_daily_summary_for_user
from handlers.settings_handlers import set_custom_macros, process_calories, process_protein, process_fat, process_carbs, change_language, delete_data, confirm_delete, lang_ru, CALORIES, PROTEIN, FAT, CARBS, DELETE_CONFIRM, set_day_end_time_handler, process_day_end_time, DAY_END_TIME, change_timezone, process_timezone, TIMEZONE_SETTINGS
from config import TOKEN, GENDER, AGE, WEIGHT, HEIGHT, ACTIVITY, GOAL, TIMEZONE, FOOD_NAME, FOOD_WEIGHT, ADMIN_ADD, ADMIN_KCAL, ADMIN_PROTEIN, ADMIN_FAT, ADMIN_CARBS, EDIT_FOOD_WEIGHT, CUSTOM_MACROS
from database import init_all_db
from datetime import time
import httpx
from database.db_utils import get_users_db

# Определяем уровень логирования на основе переменной окружения
# В продакшн-среде установите NUTRO_ENV=production
ENV = os.getenv("NUTRO_ENV", "production")
LOG_LEVEL = logging.INFO

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=LOG_LEVEL
)
logger = logging.getLogger(__name__)

# Настройка уровня логирования для httpx и httpcore
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger.info(f"Запуск приложения в режиме: {ENV}")

async def set_bot_commands(app):
    """Установка команд бота через BotFather."""
    commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("summary", "Показать итоги дня"),
        BotCommand("log", "Показать историю питания"),
    ]
    await app.bot.set_my_commands(commands)

async def schedule_all_daily_summaries(app):
    """Планирует отправку итогов дня для всех пользователей."""
    # Получаем соединение с базой данных пользователей
    conn = get_users_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT user_id FROM users")
    user_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    for user_id in user_ids:
        await schedule_daily_summary_for_user(user_id, app)

def main():
    init_all_db()
    
    # Настройка HTTP-клиента с увеличенными таймаутами
    # В python-telegram-bot 20.x используется метод get_updates_http_version и get_updates_connection_pool_size
    # вместо request_kwargs
    app = (
        Application.builder()
        .token(TOKEN)
        .get_updates_http_version("1.1")  # Используем HTTP 1.1 для long polling
        .get_updates_connection_pool_size(10)  # Размер пула соединений
        .get_updates_read_timeout(30.0)  # Таймаут чтения для getUpdates
        .get_updates_connect_timeout(30.0)  # Таймаут соединения для getUpdates
        .build()
    )

    # Группа 2: Специфические обработчики
    app.add_handler(MessageHandler(filters.Regex(r'^/edit_[A-Z0-9]{8}$'), edit_menu), group=2)
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data), group=2)
    app.add_handler(CommandHandler("summary", send_daily_summary_now), group=2)
    app.add_handler(CommandHandler("log", show_food_log), group=2)

    # ConversationHandler для управления диалогами
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("update", update),
            CallbackQueryHandler(update, pattern="update"),
            CallbackQueryHandler(add_food, pattern="add_food"),
            CallbackQueryHandler(show_food_log, pattern="food_log"),
            CallbackQueryHandler(food_name_buttons, pattern="edit_.*"),
            CallbackQueryHandler(food_name_buttons, pattern="^delete_(?!data$).*$"),
            CallbackQueryHandler(settings, pattern="settings"),
            CallbackQueryHandler(subscription, pattern="subscription"),
            CallbackQueryHandler(home, pattern="home"),
            CallbackQueryHandler(food_name_buttons, pattern="back_to_add_food"),
            CallbackQueryHandler(food_name_buttons, pattern="edit_weight_.*"),
            CallbackQueryHandler(update, pattern="update_profile"),
            CallbackQueryHandler(set_custom_macros, pattern="set_custom_macros"),
            CallbackQueryHandler(change_language, pattern="change_language"),
            CallbackQueryHandler(delete_data, pattern="delete_data"),
            CallbackQueryHandler(confirm_delete, pattern="confirm_delete"),
            CallbackQueryHandler(lang_ru, pattern="lang_ru"),
            CallbackQueryHandler(set_day_end_time_handler, pattern="set_day_end_time"),
            CallbackQueryHandler(show_food_log, pattern="^log_date_.*$"),
            CallbackQueryHandler(gender, pattern="^(Парень|Девушка)$"),
            CallbackQueryHandler(change_timezone, pattern="change_timezone"),
        ],
        states={
            GENDER: [CallbackQueryHandler(gender, pattern="^(Парень|Девушка)$")],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, height)],
            ACTIVITY: [CallbackQueryHandler(activity)],
            GOAL: [CallbackQueryHandler(goal)],
            TIMEZONE: [CallbackQueryHandler(timezone)],
            TIMEZONE_SETTINGS: [
                CallbackQueryHandler(process_timezone, pattern="^tz_-?[0-9]+$"),
                CallbackQueryHandler(settings, pattern="settings"),
            ],
            FOOD_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, food_name),
                CallbackQueryHandler(food_name_buttons, pattern="select_.*|admin_add|calculate_custom|home|back_to_add_food|edit_weight_.*"),
            ],
            FOOD_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, food_weight)],
            EDIT_FOOD_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_food_weight)],
            ADMIN_KCAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_kcal)],
            ADMIN_PROTEIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_protein)],
            ADMIN_FAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_fat)],
            ADMIN_CARBS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_carbs)],
            CALORIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_calories)],
            PROTEIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_protein)],
            FAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_fat)],
            CARBS: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_carbs)],
            DELETE_CONFIRM: [
                CallbackQueryHandler(confirm_delete, pattern="confirm_delete"),
                CallbackQueryHandler(settings, pattern="settings"),
            ],
            DAY_END_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_day_end_time),
                CallbackQueryHandler(settings, pattern="settings"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CallbackQueryHandler(home, pattern="home"),
        ],
        per_chat=True,
        name="main_conversation"
    )

    app.add_handler(conv_handler, group=3)
    app.post_init = set_bot_commands
    
    # Планирование отправки итогов дня для всех пользователей при запуске бота
    app.job_queue.run_once(lambda context: schedule_all_daily_summaries(app), 10)  # Через 10 секунд после запуска

    # Добавляем отдельный обработчик для команды обновления анкеты
    app.add_handler(CommandHandler("update", update), group=2)
    
    # Добавляем обработчик для текстовых сообщений в состоянии AGE
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, 
                                  lambda update, context: age(update, context) if context.user_data.get('filling_profile') else None), 
                   group=4)

    print("Бот запущен")
    logger.info("Бот запущен и готов к работе")
    app.run_polling()

if __name__ == "__main__":
    main()