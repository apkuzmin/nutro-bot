import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import GENDER, AGE, WEIGHT, HEIGHT, ACTIVITY, GOAL, TIMEZONE, ACTIVITY_COEFFS, MACRO_RATIOS
from calculations import calculate_bmr, calculate_tdee, adjust_calories, calculate_macros
from database import save_user_data, save_user_profile, set_user_timezone
from handlers.menu_handlers import start
from datetime import datetime

logger = logging.getLogger(__name__)

async def gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    logger.debug(f"Выбран пол: {query.data}")
    context.user_data["gender"] = query.data
    logger.debug(f"Пол сохранен в context.user_data: {context.user_data['gender']}")
    
    try:
        await query.edit_message_text("Введите ваш возраст:")
        logger.debug("Сообщение с запросом возраста отправлено успешно")
        return AGE
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения с запросом возраста: {e}")
        # Попробуем отправить новое сообщение вместо редактирования
        try:
            await query.message.reply_text("Введите ваш возраст:")
            logger.debug("Новое сообщение с запросом возраста отправлено успешно")
            return AGE
        except Exception as e2:
            logger.error(f"Ошибка при отправке нового сообщения: {e2}")
            return GENDER

async def age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        age = int(update.message.text)
        if 10 <= age <= 120:
            context.user_data["age"] = age
            await update.message.reply_text("Введите ваш вес (кг):")
            return WEIGHT
        else:
            await update.message.reply_text("Укажи возраст от 10 до 120 лет.")
            return AGE
    except ValueError:
        await update.message.reply_text("Введи число. Сколько тебе лет?")
        return AGE

async def weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        weight = float(update.message.text)
        if 20 <= weight <= 300:
            context.user_data["weight"] = weight
            await update.message.reply_text("Введите ваш рост (см):")
            return HEIGHT
        else:
            await update.message.reply_text("Укажи вес от 20 до 300 кг.")
            return WEIGHT
    except ValueError:
        await update.message.reply_text("Введи число. Какой у тебя вес?")
        return WEIGHT

async def height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        height = float(update.message.text)
        if 100 <= height <= 250:
            context.user_data["height"] = height
            keyboard = [
                [InlineKeyboardButton("🪑 Сидячий", callback_data="Сидячий")],
                [InlineKeyboardButton("🚶‍♂️ Легкая активность", callback_data="Легкая активность")],
                [InlineKeyboardButton("🏃 Умеренная активность", callback_data="Умеренная активность")],
                [InlineKeyboardButton("🏋️ Высокая активность", callback_data="Высокая активность")],
                [InlineKeyboardButton("🔥 Очень высокая активность", callback_data="Очень высокая активность")]
            ]
            await update.message.reply_text(
                "Какой у вас уровень активности?\n"
                "🪑 **Сидячий** — минимальная активность, офисная работа, мало движения.\n"
                "🚶‍♂️ **Легкая активность** — редкие прогулки, 1–2 тренировки в неделю.\n"
                "🏃 **Умеренная активность** — тренировки 3–5 раз в неделю, подвижная работа.\n"
                "🏋️ **Высокая активность** — тяжелые тренировки 6–7 раз в неделю или физический труд.\n"
                "🔥 **Очень высокая активность** — спорт на профуровне, интенсивные нагрузки каждый день.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return ACTIVITY
        else:
            await update.message.reply_text("Укажи рост от 100 до 250 см.")
            return HEIGHT
    except ValueError:
        await update.message.reply_text("Введи число. Какой у тебя рост?")
        return HEIGHT

async def activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data in ACTIVITY_COEFFS:
        context.user_data["activity"] = query.data
        keyboard = [
            [InlineKeyboardButton("⚖️ Поддержание веса", callback_data="Поддержание веса")],
            [InlineKeyboardButton("🔥 Снижение веса (дефицит калорий)", callback_data="Снижение веса")],
            [InlineKeyboardButton("🍽 Набор массы (профицит калорий)", callback_data="Набор массы")]
        ]
        await query.edit_message_text(
            "Выберите вашу цель:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return GOAL
    return ACTIVITY

async def goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    logger.debug(f"Выбрана цель: {query.data}")
    
    if query.data in MACRO_RATIOS:
        context.user_data["goal"] = query.data
        logger.debug(f"Цель сохранена в context.user_data: {context.user_data['goal']}")
        
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
            row.append(InlineKeyboardButton(time_str, callback_data=str(tz_offset)))
            
            # Если в ряду уже 3 кнопки, добавляем ряд в клавиатуру
            if len(row) == 3:
                keyboard.append(row)
                row = []
        
        # Добавляем оставшиеся кнопки, если есть
        if row:
            keyboard.append(row)
        
        try:
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "Выберите текущее время для установки часового пояса:",
                reply_markup=reply_markup
            )
            logger.debug("Сообщение с выбором часового пояса отправлено успешно")
            logger.debug("Переход к состоянию TIMEZONE")
            return TIMEZONE
        except Exception as e:
            logger.error(f"Ошибка при отправке клавиатуры с часовыми поясами: {e}")
            # Пробуем отправить новое сообщение, если не удалось отредактировать
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="Выберите текущее время для установки часового пояса:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                logger.debug("Упрощенное сообщение с выбором часового пояса отправлено успешно")
                return TIMEZONE
            except Exception as e2:
                logger.error(f"Не удалось отправить сообщение с часовыми поясами: {e2}")
                return ConversationHandler.END
    
    logger.debug(f"Неверная цель: {query.data}, остаемся в состоянии GOAL")
    return GOAL

async def timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    try:
        # Получаем выбранный часовой пояс
        timezone = int(query.data)
        context.user_data["timezone"] = timezone
        
        user_id = query.from_user.id
        
        # Рассчитываем нормы питания
        bmr = calculate_bmr(context.user_data["gender"], context.user_data["weight"],
                            context.user_data["height"], context.user_data["age"])
        tdee = calculate_tdee(bmr, context.user_data["activity"])
        daily_calories = adjust_calories(tdee, context.user_data["goal"])
        protein, fat, carbs = calculate_macros(daily_calories, context.user_data["goal"])
        
        # Сохраняем полный профиль пользователя
        save_user_profile(
            user_id, 
            context.user_data["gender"], 
            context.user_data["age"], 
            context.user_data["weight"], 
            context.user_data["height"], 
            context.user_data["activity"], 
            context.user_data["goal"], 
            daily_calories, 
            protein, 
            fat, 
            carbs,
            timezone=timezone
        )
        
        # Для обратной совместимости также вызываем save_user_data
        save_user_data(user_id, daily_calories, protein, fat, carbs)
        
        # Устанавливаем часовой пояс пользователя
        set_user_timezone(user_id, timezone)
        
        # Сбрасываем флаг заполнения анкеты
        context.user_data['filling_profile'] = False
        
        # Обновленный формат сообщения
        html_message = (
            f"<b>Анкета заполнена! Ваша дневная норма:</b>\n\n"
            f"<b>Калории:</b> {daily_calories:.0f} ккал/день\n"
            f"<b>Белки:</b> {protein:.1f} г/день\n"
            f"<b>Жиры:</b> {fat:.1f} г/день\n"
            f"<b>Углеводы:</b> {carbs:.1f} г/день\n"
        )
        from handlers.utils import get_main_menu
        await query.edit_message_text(
            html_message,
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
        return ConversationHandler.END
    except ValueError as e:
        # В случае ошибки возвращаемся к выбору часового пояса
        logger.error(f"Ошибка при обработке часового пояса: {e}")
        await query.edit_message_text(
            "Произошла ошибка. Пожалуйста, выберите часовой пояс снова:",
            reply_markup=query.message.reply_markup
        )
        return TIMEZONE

async def update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    welcome_message = (
        "Привет!👋 Добро пожаловать в Nutro — умного помощника по питанию с нейросетью.\n\n"
        "Заполни короткую анкету, и я подберу для тебя оптимальный план. Это займет меньше минуты! 🚀"
    )
    
    # Устанавливаем флаг, что пользователь начал заполнять анкету
    context.user_data['filling_profile'] = True
    
    keyboard = [
        [InlineKeyboardButton("Парень", callback_data="Парень"), InlineKeyboardButton("Девушка", callback_data="Девушка")]
    ]
    if update.message:
        # Сначала отправляем приветственное сообщение
        await update.message.reply_text(welcome_message)
        # Затем отправляем первый вопрос анкеты
        await update.message.reply_text(
            "Выберите ваш пол:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif update.callback_query:
        query = update.callback_query
        try:
            await query.answer()
            # Для callback_query редактируем текущее сообщение
            await query.edit_message_text(
                "Выберите ваш пол:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка при обработке callback-запроса: {e}")
            # Если не удалось ответить на callback-запрос, отправляем новое сообщение
            await query.message.reply_text(
                "Выберите ваш пол:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    return GENDER