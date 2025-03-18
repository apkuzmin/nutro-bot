from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import delete_user_data, get_user_data, save_custom_macros, get_day_end_time, set_day_end_time, get_user_timezone, set_user_timezone
from handlers.menu_handlers import start
from handlers.user_data_handlers import update
from handlers.utils import schedule_daily_summary_for_user
from config import CUSTOM_MACROS
import re
from datetime import datetime

# Состояния для диалога установки пользовательских макронутриентов
CALORIES, PROTEIN, FAT, CARBS = range(100, 104)
# Состояние для подтверждения удаления данных
DELETE_CONFIRM = 104
# Состояние для установки времени завершения дня
DAY_END_TIME = 105
# Состояние для смены часового пояса
TIMEZONE_SETTINGS = 106

async def set_custom_macros(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик для установки пользовательских значений КБЖУ"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = get_user_data(user_id)
    
    if user_data:
        daily_calories, protein, fat, carbs = user_data
        message = (
            "Вы можете установить свои значения калорий и макронутриентов.\n\n"
            f"Текущие значения:\n"
            f"Калории: {daily_calories:.0f} ккал\n"
            f"Белки: {protein:.1f} г\n"
            f"Жиры: {fat:.1f} г\n"
            f"Углеводы: {carbs:.1f} г\n\n"
            "Введите новое значение калорий (ккал):"
        )
    else:
        message = "Введите желаемое количество калорий (ккал):"
    
    await query.edit_message_text(message)
    return CALORIES

async def process_calories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода калорий"""
    try:
        calories = float(update.message.text)
        if 500 <= calories <= 10000:
            context.user_data["custom_calories"] = calories
            await update.message.reply_text(f"Калории установлены: {calories:.0f} ккал\n\nТеперь введите количество белка (г):")
            return PROTEIN
        else:
            await update.message.reply_text("Пожалуйста, введите значение от 500 до 10000 ккал.")
            return CALORIES
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число.")
        return CALORIES

async def process_protein(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода белка"""
    try:
        protein = float(update.message.text)
        if 10 <= protein <= 500:
            context.user_data["custom_protein"] = protein
            await update.message.reply_text(f"Белки установлены: {protein:.1f} г\n\nТеперь введите количество жиров (г):")
            return FAT
        else:
            await update.message.reply_text("Пожалуйста, введите значение от 10 до 500 г.")
            return PROTEIN
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число.")
        return PROTEIN

async def process_fat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода жиров"""
    try:
        fat = float(update.message.text)
        if 10 <= fat <= 500:
            context.user_data["custom_fat"] = fat
            await update.message.reply_text(f"Жиры установлены: {fat:.1f} г\n\nТеперь введите количество углеводов (г):")
            return CARBS
        else:
            await update.message.reply_text("Пожалуйста, введите значение от 10 до 500 г.")
            return FAT
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число.")
        return FAT

async def process_carbs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода углеводов и сохранение всех данных"""
    try:
        carbs = float(update.message.text)
        if 10 <= carbs <= 1000:
            context.user_data["custom_carbs"] = carbs
            
            # Получаем все значения из контекста
            calories = context.user_data.get("custom_calories")
            protein = context.user_data.get("custom_protein")
            fat = context.user_data.get("custom_fat")
            
            user_id = update.message.from_user.id
            
            # Сохраняем пользовательские значения в базу данных
            save_custom_macros(user_id, calories, protein, fat, carbs)
            
            # Формируем сообщение с результатами
            message = (
                "✅ Ваши значения КБЖУ успешно сохранены:\n\n"
                f"Калории: {calories:.0f} ккал\n"
                f"Белки: {protein:.1f} г\n"
                f"Жиры: {fat:.1f} г\n"
                f"Углеводы: {carbs:.1f} г"
            )
            
            # Создаем клавиатуру для возврата в главное меню
            keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="home")]]
            
            await update.message.reply_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Очищаем временные данные
            for key in ["custom_calories", "custom_protein", "custom_fat", "custom_carbs"]:
                if key in context.user_data:
                    del context.user_data[key]
                    
            return ConversationHandler.END
        else:
            await update.message.reply_text("Пожалуйста, введите значение от 10 до 1000 г.")
            return CARBS
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число.")
        return CARBS

async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик для смены языка"""
    query = update.callback_query
    await query.answer()
    
    # В текущей версии поддерживается только русский язык
    keyboard = [
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("⬅ Назад", callback_data="settings")]
    ]
    
    await query.edit_message_text(
        "Выберите язык интерфейса:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

async def delete_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик для удаления данных пользователя"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [
            InlineKeyboardButton("Да, удалить", callback_data="confirm_delete"),
            InlineKeyboardButton("Нет, отмена", callback_data="settings")
        ]
    ]
    
    await query.edit_message_text(
        "⚠️ Вы уверены, что хотите удалить все свои данные?\n\n"
        "Это действие нельзя отменить. Будут удалены все ваши записи о питании и настройки.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    # Возвращаем состояние подтверждения удаления
    return DELETE_CONFIRM

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение удаления данных пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Удаляем данные пользователя из базы данных
    delete_user_data(user_id)
    
    keyboard = [[InlineKeyboardButton("⬅ На главную", callback_data="home")]]
    
    await query.edit_message_text(
        "✅ Все ваши данные успешно удалены.\n\n"
        "Вы можете заново заполнить анкету, чтобы начать пользоваться ботом.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

async def lang_ru(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора русского языка"""
    query = update.callback_query
    await query.answer()
    
    # Здесь можно добавить логику сохранения выбранного языка в базу данных
    
    await query.edit_message_text(
        "✅ Язык интерфейса установлен: 🇷🇺 Русский",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Назад", callback_data="settings")]])
    )
    return ConversationHandler.END

async def set_day_end_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик для установки времени завершения дня"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    current_time = get_day_end_time(user_id)
    
    await query.edit_message_text(
        f"Текущее время завершения дня: {current_time}\n\n"
        "Введите новое время в формате ЧЧ:ММ (например, 23:59).\n"
        "В это время будут подводиться итоги дня и начинаться новый день учета питания.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Назад", callback_data="settings")]])
    )
    return DAY_END_TIME

async def process_day_end_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода времени завершения дня"""
    user_id = update.message.from_user.id
    time_text = update.message.text.strip()
    
    # Проверяем формат времени (ЧЧ:ММ)
    time_pattern = re.compile(r'^([01]?[0-9]|2[0-3]):([0-5][0-9])$')
    match = time_pattern.match(time_text)
    
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        
        # Форматируем время в виде "ЧЧ:ММ"
        formatted_time = f"{hour:02d}:{minute:02d}"
        
        # Сохраняем время завершения дня
        set_day_end_time(user_id, formatted_time)
        
        # Планируем отправку итогов дня
        await schedule_daily_summary_for_user(user_id, context)
        
        # Получаем данные о языке и подписке пользователя
        language = "🇷🇺 Русский"  # По умолчанию русский
        subscription_status = "Неактивно"  # По умолчанию неактивно
        timezone = get_user_timezone(user_id)  # Получаем часовой пояс пользователя
        
        # Создаем клавиатуру для настроек
        keyboard = [
            [InlineKeyboardButton("📝 Обновить анкету", callback_data="update_profile"), 
             InlineKeyboardButton("🎯 Установить норму", callback_data="set_custom_macros")],
            [InlineKeyboardButton(f"⏰ Завершения дня: {formatted_time}", callback_data="set_day_end_time"),
             InlineKeyboardButton(f"🌐 Часовой пояс: UTC{'+' if timezone >= 0 else ''}{timezone}", callback_data="change_timezone")],
            [InlineKeyboardButton("Сменить язык", callback_data="change_language")],
            [InlineKeyboardButton("Удалить данные", callback_data="delete_data")],
            [InlineKeyboardButton("⬅ Назад", callback_data="home")]
        ]
        
        # Формируем сообщение с настройками
        settings_message = (
            f"⚙️ Настройки\n"
            f"Ваш язык: {language}\n"
            f"Подписка: {subscription_status}\n"
            f"Время завершения дня: {formatted_time}\n"
            f"Часовой пояс: UTC{'+' if timezone >= 0 else ''}{timezone}"
        )
        
        # Отправляем сообщение о успешном изменении времени
        await update.message.reply_text(
            f"✅ Время завершения дня установлено: {formatted_time}",
            reply_markup=None
        )
        
        # Отправляем обновленные настройки
        await update.message.reply_text(
            settings_message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, введите время в формате ЧЧ:ММ (например, 23:59).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Назад", callback_data="settings")]])
        )
        return DAY_END_TIME

async def change_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик для смены часового пояса"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    current_timezone = get_user_timezone(user_id)
    
    # Текущее время по UTC
    now_utc = datetime.utcnow()
    current_hour_utc = now_utc.hour
    current_minute = now_utc.minute
    
    # Словарь для группировки часовых поясов по времени
    time_to_tz = {}
    
    # Группируем часовые пояса по времени
    for tz_offset in range(-12, 15):
        # Вычисляем время в этом часовом поясе
        tz_hour = (current_hour_utc + tz_offset) % 24
        time_str = f"{tz_hour:02d}:{current_minute:02d}"
        
        # Добавляем часовой пояс к соответствующему времени
        if time_str in time_to_tz:
            time_to_tz[time_str].append(tz_offset)
        else:
            time_to_tz[time_str] = [tz_offset]
    
    # Создаем клавиатуру
    keyboard = []
    row = []
    
    # Сортируем времена для логичного порядка
    sorted_times = sorted(time_to_tz.keys(), key=lambda x: int(x.split(':')[0]))
    
    # Добавляем кнопки для каждого уникального времени
    for time_str in sorted_times:
        # Берем первый часовой пояс из списка для этого времени
        tz_offset = time_to_tz[time_str][0]
        
        # Добавляем кнопку в текущий ряд (только время без UTC)
        row.append(InlineKeyboardButton(time_str, callback_data=f"tz_{tz_offset}"))
        
        # Если в ряду уже 3 кнопки, добавляем ряд в клавиатуру
        if len(row) == 3:
            keyboard.append(row)
            row = []
    
    # Добавляем оставшиеся кнопки, если есть
    if row:
        keyboard.append(row)
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="settings")])
    
    await query.edit_message_text(
        f"Текущий часовой пояс: UTC{'+' if current_timezone >= 0 else ''}{current_timezone}\n\n"
        "Выберите текущее время для установки часового пояса:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TIMEZONE_SETTINGS

async def process_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора часового пояса в настройках"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем часовой пояс из callback_data
    timezone = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    # Устанавливаем часовой пояс пользователя
    set_user_timezone(user_id, timezone)
    
    # Возвращаемся в настройки
    from handlers.menu_handlers import settings
    return await settings(update, context) 