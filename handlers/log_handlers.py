from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import get_food_log, update_food_log, delete_food_log, get_product_data, get_daily_intake, get_current_day
from config import EDIT_FOOD_WEIGHT
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

async def show_food_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if update.callback_query:
            query = update.callback_query
            user_id = query.from_user.id
            reply_func = query.edit_message_text
            
            # Сразу отвечаем на callback-запрос, чтобы избежать залагивания кнопок
            try:
                await query.answer()
            except Exception as e:
                logger.error(f"Ошибка при ответе на callback-запрос: {e}")
            
            # Проверяем, содержит ли callback_data дату
            if query.data.startswith("log_date_"):
                log_date = query.data.split("_")[2]
                logger.debug(f"Showing food log for date: {log_date}")
            else:
                log_date = None
        elif update.message:
            user_id = update.message.from_user.id
            reply_func = update.message.reply_text
            log_date = None
        else:
            return

        # Если дата не указана, используем текущий день
        if log_date is None:
            log_date = get_current_day(user_id)
        
        # Преобразуем строку даты в объект datetime для форматирования и навигации
        try:
            date_obj = datetime.fromisoformat(log_date)
            formatted_date = date_obj.strftime("%d %B")  # Например, "10 Марта"
            prev_date = (date_obj - timedelta(days=1)).isoformat()[:10]
            next_date = (date_obj + timedelta(days=1)).isoformat()[:10]
        except ValueError as e:
            logger.error(f"Ошибка при обработке даты {log_date}: {e}")
            # В случае ошибки используем текущий день
            current_day = get_current_day(user_id)
            date_obj = datetime.fromisoformat(current_day)
            formatted_date = date_obj.strftime("%d %B")
            prev_date = (date_obj - timedelta(days=1)).isoformat()[:10]
            next_date = (date_obj + timedelta(days=1)).isoformat()[:10]

        logger.debug(f"Showing food log for user: {user_id}, date: {log_date}")
        food_log = get_food_log(user_id, log_date)
        logger.debug(f"Food log entries: {len(food_log)}")
        
        if not food_log:
            html_message = f"<b>🍽 История питания за {formatted_date}:</b>\n\nПока ничего не добавлено."
        else:
            html_message = f"<b>🍽 История питания за {formatted_date}:</b>\n\n"
            edited_log_id = context.user_data.get("edit_log_id")
            old_weight = context.user_data.get("old_weight")
            
            for log in food_log:
                log_id = log["id"]
                food_name = log["food_name"]
                weight = log["weight"]
                kcal = log["kcal"]
                protein = log["protein"]
                fat = log["fat"]
                carbs = log["carbs"]
                timestamp = log["timestamp"]
                edit_code = log["edit_code"]
                
                if "T" in timestamp:
                    time_str = timestamp.split('T')[1][:5]
                else:
                    time_str = "00:00"
                
                if edited_log_id == log_id and old_weight is not None and "just_edited" in context.user_data:
                    html_message += (
                        f"🕛 {time_str} — {food_name}, {weight:.0f}г (было {old_weight:.0f}г)\n"
                        f"⚡️ {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У)\n"
                        f"/edit_{edit_code}\n\n"
                    )
                else:
                    html_message += (
                        f"🕛 {time_str} — {food_name}, {weight:.0f}г\n"
                        f"⚡️ {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У)\n"
                        f"/edit_{edit_code}\n\n"
                    )
            
            if "just_edited" in context.user_data:
                del context.user_data["just_edited"]

        # Создаем кнопки для навигации между днями
        prev_date_obj = datetime.fromisoformat(prev_date)
        next_date_obj = datetime.fromisoformat(next_date)
        
        prev_formatted = prev_date_obj.strftime("%d %B")
        next_formatted = next_date_obj.strftime("%d %B")
        
        keyboard = [
            [
                InlineKeyboardButton(f"◀️ {prev_formatted}", callback_data=f"log_date_{prev_date}"),
                InlineKeyboardButton(f"{next_formatted} ▶️", callback_data=f"log_date_{next_date}")
            ],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="home")]
        ]
        
        try:
            await reply_func(
                html_message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
            # Если не удалось отредактировать сообщение, пробуем отправить новое
            if update.callback_query:
                try:
                    await update.callback_query.message.reply_text(
                        html_message,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode="HTML"
                    )
                except Exception as e2:
                    logger.error(f"Ошибка при отправке нового сообщения: {e2}")
    except Exception as e:
        logger.error(f"Необработанная ошибка в show_food_log: {e}")
        if update.callback_query:
            try:
                await update.callback_query.answer("Произошла ошибка. Пожалуйста, попробуйте еще раз.")
            except:
                pass

async def edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    logger.debug(f"Edit menu triggered for user {user_id} with command: {update.message.text}")
    try:
        edit_code = update.message.text.split('_')[1]
        logger.debug(f"Extracted edit_code: {edit_code}")
    except IndexError:
        logger.debug("Failed to extract edit_code: IndexError")
        from handlers.utils import get_main_menu
        await update.message.reply_text("Неверная команда. Используй команду из истории.", reply_markup=get_main_menu())
        return ConversationHandler.END

    food_log = get_food_log(user_id)
    logger.debug(f"Food log for user {user_id}: {food_log}")
    log_entry = next((entry for entry in food_log if entry["edit_code"] == edit_code), None)
    if not log_entry:
        logger.debug(f"No log entry found for edit_code: {edit_code}")
        from handlers.utils import get_main_menu
        await update.message.reply_text("Запись не найдена.", reply_markup=get_main_menu())
        return ConversationHandler.END

    log_id = log_entry["id"]
    food_name = log_entry["food_name"]
    weight = log_entry["weight"]
    kcal = log_entry["kcal"]
    protein = log_entry["protein"]
    fat = log_entry["fat"]
    carbs = log_entry["carbs"]
    timestamp = log_entry["timestamp"]
    
    logger.debug(f"Found log entry: {food_name}, log_id: {log_id}")
    context.user_data["edit_log_id"] = log_id
    context.user_data["old_weight"] = weight
    
    # Извлекаем время из timestamp
    if "T" in timestamp:
        time_str = timestamp.split('T')[1][:5]
    else:
        # Если формат timestamp изменился, используем значение по умолчанию
        time_str = "00:00"
        
    html_message = (
        f"<b>Редактирование:</b>\n"
        f"{food_name} {weight:.0f}г — {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У)\n"
        f"Время: {time_str}"
    )
    keyboard = [
        [InlineKeyboardButton("Редактировать вес", callback_data=f"edit_weight_{log_id}"),
         InlineKeyboardButton("Удалить", callback_data=f"delete_{log_id}")],
        [InlineKeyboardButton("⬅ Назад", callback_data="food_log")]
    ]
    await update.message.reply_text(
        html_message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def edit_food_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        new_weight = float(update.message.text)
        log_id = context.user_data["edit_log_id"]
        user_id = update.message.from_user.id

        food_log = get_food_log(user_id)
        log_entry = next((entry for entry in food_log if entry["id"] == log_id), None)
        if not log_entry:
            from handlers.utils import get_main_menu
            await update.message.reply_text("Запись не найдена.", reply_markup=get_main_menu())
            return ConversationHandler.END

        old_weight = log_entry["weight"]
        update_food_log(log_id, new_weight)

        context.user_data["old_weight"] = old_weight
        context.user_data["just_edited"] = True

        await show_food_log(update, context)

        if "old_weight" in context.user_data:
            del context.user_data["old_weight"]
        if "edit_log_id" in context.user_data:
            del context.user_data["edit_log_id"]

        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Введи число. Сколько г?")
        return EDIT_FOOD_WEIGHT