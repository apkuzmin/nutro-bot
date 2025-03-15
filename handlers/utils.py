from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import get_daily_intake, get_user_data, get_food_log, get_current_day, get_day_end_time
from database.food_log_db import update_daily_intake_for_user
from datetime import date, datetime, time
import logging

logger = logging.getLogger(__name__)

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("🥗 Добавить еду", callback_data="add_food")],
        [InlineKeyboardButton("📜 История", callback_data="food_log"),
         InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
         InlineKeyboardButton("💳 Подписка", callback_data="subscription")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Сбрасываем флаг заполнения анкеты
    if 'filling_profile' in context.user_data:
        context.user_data['filling_profile'] = False
        
    await update.message.reply_text("Действие отменено.", reply_markup=get_main_menu())
    return ConversationHandler.END

async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправка итогов дня всем пользователям в соответствии с их настройками."""
    from database import conn
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT user_id FROM users")
    user_ids = [row[0] for row in cursor.fetchall()]
    
    # Текущее время
    now = datetime.now()
    current_hour = now.hour
    current_minute = now.minute
    
    logger.debug(f"Проверка отправки итогов дня. Текущее время: {current_hour:02d}:{current_minute:02d}")
    logger.debug(f"Найдено пользователей: {len(user_ids)}")

    for user_id in user_ids:
        try:
            # Получаем время завершения дня пользователя
            day_end_time = get_day_end_time(user_id)
            logger.debug(f"Пользователь {user_id}: время завершения дня = {day_end_time}")
            
            # Разбиваем время на часы и минуты
            try:
                end_hour, end_minute = map(int, day_end_time.split(':'))
            except (ValueError, AttributeError):
                # В случае ошибки используем значение по умолчанию
                end_hour, end_minute = 0, 0
                logger.debug(f"Ошибка при разборе времени завершения дня, используем значение по умолчанию: 00:00")
            
            # Проверяем, совпадает ли текущее время с временем завершения дня пользователя
            # Допускаем погрешность в 5 минут
            time_diff_minutes = abs((current_hour * 60 + current_minute) - (end_hour * 60 + end_minute))
            logger.debug(f"Разница во времени: {time_diff_minutes} минут")
            
            if time_diff_minutes > 5:
                # Если время не совпадает, пропускаем пользователя
                logger.debug(f"Пропускаем пользователя {user_id}: время не совпадает")
                continue
            
            logger.debug(f"Отправляем итоги дня пользователю {user_id}")
            
            # Получаем текущий день для пользователя (который заканчивается)
            current_day = get_current_day(user_id)
            
            # Обновляем данные о потреблении перед их получением
            update_daily_intake_for_user(user_id, current_day)
            
            norm = get_user_data(user_id)
            if not norm:
                logger.debug(f"Нет данных нормы для пользователя {user_id}")
                continue
            norm_calories, norm_protein, norm_fat, norm_carbs = norm

            intake = get_daily_intake(user_id)
            intake_calories, intake_protein, intake_fat, intake_carbs = intake

            percentage = (intake_calories / norm_calories) * 100 if norm_calories > 0 else 0

            html_message = (
                f"📅 {current_day}\n\n"
                f"<b>Итоги дня:</b>\n"
                f"<b>Калории:</b> {intake_calories:.0f} / {norm_calories:.0f} ккал ({percentage:.1f}%)\n"
                f"<b>Белки:</b> {intake_protein:.1f} / {norm_protein:.1f}г\n"
                f"<b>Жиры:</b> {intake_fat:.1f} / {norm_fat:.1f}г\n"
                f"<b>Углеводы:</b> {intake_carbs:.1f} / {norm_carbs:.1f}г\n\n"
                f"День завершён в {day_end_time}, ваш итог сохранён."
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=html_message,
                parse_mode="HTML"
            )
            logger.debug(f"Отправлены итоги дня пользователю {user_id} за дату {current_day}")
        except Exception as e:
            logger.error(f"Ошибка отправки итогов дня пользователю {user_id}: {e}")

async def send_daily_summary_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ручная отправка итогов дня пользователю."""
    user_id = update.message.from_user.id
    
    try:
        # Получаем текущий день для пользователя
        current_day = get_current_day(user_id)
        
        # Обновляем данные о потреблении перед их получением
        update_daily_intake_for_user(user_id, current_day)
        
        norm = get_user_data(user_id)
        if not norm:
            await update.message.reply_text("Нет данных о вашей норме. Пожалуйста, заполните анкету.")
            return
        
        norm_calories, norm_protein, norm_fat, norm_carbs = norm
        
        intake = get_daily_intake(user_id)
        intake_calories, intake_protein, intake_fat, intake_carbs = intake
        
        percentage = (intake_calories / norm_calories) * 100 if norm_calories > 0 else 0
        
        day_end_time = get_day_end_time(user_id)
        
        html_message = (
            f"📅 {current_day}\n\n"
            f"<b>Итоги дня:</b>\n"
            f"<b>Калории:</b> {intake_calories:.0f} / {norm_calories:.0f} ккал ({percentage:.1f}%)\n"
            f"<b>Белки:</b> {intake_protein:.1f} / {norm_protein:.1f}г\n"
            f"<b>Жиры:</b> {intake_fat:.1f} / {norm_fat:.1f}г\n"
            f"<b>Углеводы:</b> {intake_carbs:.1f} / {norm_carbs:.1f}г\n\n"
            f"День завершается в {day_end_time}."
        )
        
        await update.message.reply_text(
            html_message,
            parse_mode="HTML"
        )
        
        logger.debug(f"Отправлены итоги дня пользователю {user_id} за дату {current_day} (ручной запрос)")
    except Exception as e:
        logger.error(f"Ошибка отправки итогов дня пользователю {user_id}: {e}")
        await update.message.reply_text(f"Ошибка при получении итогов дня: {e}")

async def schedule_daily_summary_for_user(user_id, context):
    """
    Планирует отправку итогов дня для конкретного пользователя.
    
    Args:
        user_id (int): ID пользователя
        context (ContextTypes.DEFAULT_TYPE): Контекст бота
    """
    try:
        # Получаем время завершения дня пользователя
        day_end_time = get_day_end_time(user_id)
        logger.debug(f"Планирование отправки итогов дня для пользователя {user_id} в {day_end_time}")
        
        # Разбиваем время на часы и минуты
        try:
            end_hour, end_minute = map(int, day_end_time.split(':'))
        except (ValueError, AttributeError):
            # В случае ошибки используем значение по умолчанию
            end_hour, end_minute = 0, 0
            logger.debug(f"Ошибка при разборе времени завершения дня, используем значение по умолчанию: 00:00")
        
        # Создаем время для планирования
        summary_time = time(hour=end_hour, minute=end_minute)
        
        # Удаляем существующие задачи для этого пользователя
        for job in context.job_queue.get_jobs_by_name(f"summary_{user_id}"):
            job.schedule_removal()
        
        # Планируем новую задачу
        context.job_queue.run_daily(
            send_daily_summary_for_user,
            summary_time,
            days=(0, 1, 2, 3, 4, 5, 6),  # Каждый день недели
            chat_id=user_id,
            name=f"summary_{user_id}",
            data=user_id
        )
        
        logger.debug(f"Запланирована отправка итогов дня для пользователя {user_id} в {day_end_time}")
    except Exception as e:
        logger.error(f"Ошибка при планировании отправки итогов дня для пользователя {user_id}: {e}")

async def send_daily_summary_for_user(context):
    """Отправляет итоги дня пользователю."""
    job = context.job
    user_id = job.data
    
    try:
        # Получаем текущую дату для пользователя с учетом его часового пояса
        current_day = get_current_day(user_id)
        
        # Получаем данные о потреблении за день
        intake_calories, intake_protein, intake_fat, intake_carbs = get_daily_intake(user_id)
        
        # Получаем нормы пользователя
        norm_calories, norm_protein, norm_fat, norm_carbs = get_user_data(user_id)
        
        # Рассчитываем процент от нормы
        percentage = (intake_calories / norm_calories) * 100 if norm_calories > 0 else 0
        
        # Формируем сообщение
        html_message = f"<b>Итоги дня ({current_day}):</b>\n\n"
        html_message += f"Калории: {intake_calories:.0f} / {norm_calories:.0f} ккал ({percentage:.0f}%)\n"
        html_message += f"Белки: {intake_protein:.1f} / {norm_protein:.1f} г\n"
        html_message += f"Жиры: {intake_fat:.1f} / {norm_fat:.1f} г\n"
        html_message += f"Углеводы: {intake_carbs:.1f} / {norm_carbs:.1f} г\n"
        
        # Добавляем список продуктов
        food_log = get_food_log_for_date(user_id, current_day)
        if food_log:
            html_message += "\n<b>Съедено сегодня:</b>\n"
            for item in food_log:
                food_name = item[1]
                weight = item[2]
                calories = item[3]
                html_message += f"• {food_name} - {weight}г ({calories:.0f} ккал)\n"
        
        await context.bot.send_message(
            chat_id=user_id,
            text=html_message,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки итогов дня пользователю {user_id}: {e}")