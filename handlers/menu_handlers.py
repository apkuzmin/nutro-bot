from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import get_user_data, get_daily_intake, get_day_end_time, get_user_timezone
from database.food_log_db import update_daily_intake_for_user
from handlers.utils import get_main_menu, schedule_daily_summary_for_user
from handlers.log_handlers import show_food_log
import logging
import html

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        user_id = update.message.from_user.id
        reply_func = update.message.reply_text
    elif update.callback_query:
        user_id = update.callback_query.from_user.id
        reply_func = update.callback_query.edit_message_text
        await update.callback_query.answer()
    else:
        return ConversationHandler.END

    user_data = get_user_data(user_id)

    if user_data:
        # Обновляем данные о потреблении перед их получением
        update_daily_intake_for_user(user_id)
        
        # Планируем отправку итогов дня
        await schedule_daily_summary_for_user(user_id, context)
        
        daily_calories, protein, fat, carbs = user_data
        intake = get_daily_intake(user_id)
        intake_calories, intake_protein, intake_fat, intake_carbs = intake
        
        daily_calories = daily_calories or 0
        protein = protein or 0
        fat = fat or 0
        carbs = carbs or 0
        intake_calories = intake_calories or 0
        intake_protein = intake_protein or 0
        intake_fat = intake_fat or 0
        intake_carbs = intake_carbs or 0
        
        percentage = (intake_calories / daily_calories) * 100 if daily_calories > 0 else 0
        
        html_message = (
            f"<b>Ваш текущий прогресс:</b>\n"
            f"<b>Калории:</b> {intake_calories:.0f} / {daily_calories:.0f} ккал ({percentage:.1f}%)\n"
            f"<b>Белки:</b> {intake_protein:.1f} / {protein:.1f}г\n"
            f"<b>Жиры:</b> {intake_fat:.1f} / {fat:.1f}г\n"
            f"<b>Углеводы:</b> {intake_carbs:.1f} / {carbs:.1f}г"
        )
        
        await reply_func(
            html_message,
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
    else:
        # Добавляем приветственное сообщение перед анкетой
        welcome_message = (
            "Привет!👋 Добро пожаловать в Nutro — умного помощника по питанию с нейросетью.\n\n"
            "Заполни короткую анкету, и я подберу для тебя оптимальный план. Это займет меньше минуты! 🚀"
        )
        
        # Отправляем приветственное сообщение
        await reply_func(welcome_message)
        
        # Затем отправляем первый вопрос анкеты
        keyboard = [
            [InlineKeyboardButton("Парень", callback_data="Парень"), InlineKeyboardButton("Девушка", callback_data="Девушка")]
        ]
        await reply_func(
            "Выберите ваш пол:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        from config import GENDER
        return GENDER
    return ConversationHandler.END

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    # Получаем данные о языке и подписке пользователя
    user_id = query.from_user.id
    language = "🇷🇺 Русский"  # По умолчанию русский, в будущем можно добавить выбор языка
    subscription_status = "Неактивно"  # По умолчанию неактивно
    day_end_time = get_day_end_time(user_id)  # Получаем время завершения дня
    timezone = get_user_timezone(user_id)  # Получаем часовой пояс пользователя
    
    # Создаем клавиатуру для настроек
    keyboard = [
        [InlineKeyboardButton("📝 Обновить анкету", callback_data="update_profile"), 
         InlineKeyboardButton("🎯 Установить свою норму", callback_data="set_custom_macros")],
        [InlineKeyboardButton(f"⏰ Завершения дня: {day_end_time}", callback_data="set_day_end_time"),
         InlineKeyboardButton(f"🌐 Часовой пояс: UTC{'+' if timezone >= 0 else ''}{timezone}", callback_data="change_timezone")],
        [InlineKeyboardButton("Сменить язык", callback_data="change_language")],
        [InlineKeyboardButton("Удалить данные", callback_data="delete_data")],
        [InlineKeyboardButton("⬅ Назад", callback_data="home")]
    ]
    
    # Формируем сообщение с настройками
    message = (
        f"<b>⚙️ Настройки</b>\n"
        f"Ваш язык: {language}\n"
        f"Подписка: {subscription_status}\n"
        f"Время завершения дня: {day_end_time}\n"
        f"Часовой пояс: UTC{'+' if timezone >= 0 else ''}{timezone}\n"
    )
    
    await query.edit_message_text(
        message, 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Подписка пока не реализована.", reply_markup=get_main_menu())
    return ConversationHandler.END

async def home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.callback_query:
            # Сразу отвечаем на callback-запрос, чтобы избежать залагивания кнопок
            try:
                await update.callback_query.answer()
            except Exception as e:
                logger.error(f"Ошибка при ответе на callback-запрос в home: {e}")
        
        return await start(update, context)
    except Exception as e:
        logger.error(f"Необработанная ошибка в home: {e}")
        if update.callback_query:
            try:
                await update.callback_query.answer("Произошла ошибка. Пожалуйста, попробуйте еще раз.")
                await update.callback_query.edit_message_text(
                    "Произошла ошибка при возврате в главное меню. Пожалуйста, попробуйте еще раз.",
                    reply_markup=get_main_menu()
                )
            except:
                pass
        return ConversationHandler.END