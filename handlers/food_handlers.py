import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import FOOD_NAME, FOOD_WEIGHT, ADMIN_ADD, ADMIN_KCAL, ADMIN_PROTEIN, ADMIN_FAT, ADMIN_CARBS, ADMIN_ID, EDIT_FOOD_WEIGHT, DEEPSEEK_API_KEY, DEEPSEEK_API_URL
from database import get_product_data, save_product_data, search_products, delete_food_log, log_food, get_user_data, get_daily_intake, get_product_by_barcode, save_barcode_product
from openai import OpenAI
import re
import json
import logging
import time
from functools import lru_cache
import asyncio

logger = logging.getLogger(__name__)

# Отключаем логирование SSL ключей, чтобы избежать ошибки доступа
os.environ["SSLKEYLOGFILE"] = ""

# Создаем функцию для получения клиента OpenAI с повторными попытками
@lru_cache(maxsize=1)
def get_openai_client():
    """Создает и возвращает клиент OpenAI с настройками из config.py.
    Использует кэширование для повторного использования клиента."""
    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_API_URL,
        timeout=30.0,  # Увеличиваем таймаут до 30 секунд
        max_retries=3  # Добавляем автоматические повторные попытки
    )

# Получаем клиент OpenAI
client = get_openai_client()

# Функция для выполнения запроса к API с повторными попытками
async def call_ai_api(food_name, max_retries=3, retry_delay=2):
    """Выполняет запрос к API с повторными попытками в случае ошибок сети."""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "Ты — эксперт по питанию. Предоставь точные данные о пищевой ценности продукта на 100 г СТРОГО в формате: [калории] [белки] [жиры] [углеводы]. Например: 165 31 3.6 0. НЕ ИСПОЛЬЗУЙ единицы измерения, НЕ ИСПОЛЬЗУЙ форматирование текста, НЕ ДОБАВЛЯЙ дополнительную информацию. ТОЛЬКО четыре числа через пробел."},
                    {"role": "user", "content": f"Какая пищевая ценность у '{food_name}' на 100 г? Ответь ТОЛЬКО четырьмя числами через пробел: калории, белки, жиры, углеводы."}
                ],
                stream=False
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Попытка {attempt+1}/{max_retries} вызова API не удалась: {e}")
            if attempt < max_retries - 1:
                # Экспоненциальная задержка между попытками
                wait_time = retry_delay * (2 ** attempt)
                logger.info(f"Повторная попытка через {wait_time} секунд...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Все попытки вызова API не удались: {e}")
                raise

async def add_food(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    try:
        logger.debug("Add food triggered")
        from handlers.utils import get_main_menu
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="home")]]
        await query.edit_message_text(
            "🔍 <b>Введите продукт, который хотите добавить.</b>\nНапример: Запеченная куриная грудка",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return FOOD_NAME
    except Exception as e:
        logger.error(f"Error in add_food: {e}")
        await query.edit_message_text("Произошла ошибка. Попробуй снова.", reply_markup=get_main_menu())
        return ConversationHandler.END

async def food_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    food = update.message.text.lower()
    context.user_data["food"] = food
    logger.debug(f"Food name entered: {food}")

    result = get_product_data(food)
    if result:
        kcal, protein, fat, carbs = result
        context.user_data["food_data"] = (kcal, protein, fat, carbs)
        from handlers.utils import get_main_menu
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="home")]]
        message = f"✅ {food.capitalize()} — {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У) на 100г\nУкажи вес в граммах:"
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return FOOD_WEIGHT
    else:
        similar = search_products(food)
        logger.debug(f"Similar products found: {similar}")
        if similar:
            keyboard = [[InlineKeyboardButton(item, callback_data=f"select_{item}")] for item in similar]
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="home")])
            keyboard.insert(-1, [InlineKeyboardButton("🧮 Рассчитать мой вариант", callback_data="calculate_custom")])
            await update.message.reply_text(
                f"🔍По запросу '{food}' найдено несколько вариантов.\nВыберите подходящий или рассчитайте с помощью нейросети.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return FOOD_NAME
        else:
            await update.message.reply_text("✅ Не нашлось в базе, но нейросеть уже считает. Секунду!")
            try:
                response = await call_ai_api(food)
                logger.debug(f"DeepSeek response: {response}")

                # Попробуем извлечь данные в числовом формате: "158 5.5 1.1 30.1"
                numeric_pattern = r"(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)"
                numeric_match = re.search(numeric_pattern, response)

                if numeric_match:
                    kcal = float(numeric_match.group(1))
                    protein = float(numeric_match.group(2))
                    fat = float(numeric_match.group(3))
                    carbs = float(numeric_match.group(4))
                else:
                    # Удаляем markdown-форматирование (** для жирного текста)
                    clean_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', response)
                    
                    # Альтернативный формат с единицами измерения - улучшенный паттерн
                    text_pattern = r"(\d+[.,]?\d*)\s*(?:кк?ал|ккалорий|калорий)[.,]?.*?(\d+[.,]?\d*)\s*(?:г|гр)?\s*(?:белк[ао]|протеин)[ао]?[в]?.*?(\d+[.,]?\d*)\s*(?:г|гр)?\s*жир[ао]?[в]?.*?(\d+[.,]?\d*)\s*(?:г|гр)?\s*(?:углевод|угле)[ао]?[в]?"
                    text_match = re.search(text_pattern, clean_text, re.IGNORECASE | re.DOTALL)
                    
                    if text_match:
                        # Заменяем запятые на точки для корректного преобразования в float
                        kcal = float(text_match.group(1).replace(',', '.'))
                        protein = float(text_match.group(2).replace(',', '.'))
                        fat = float(text_match.group(3).replace(',', '.'))
                        carbs = float(text_match.group(4).replace(',', '.'))
                    else:
                        # Еще более общий паттерн для поиска чисел рядом с ключевыми словами
                        kcal_pattern = r"(\d+[.,]?\d*)\s*(?:кк?ал|ккалорий|калорий)"
                        protein_pattern = r"(\d+[.,]?\d*)\s*(?:г|гр)?\s*(?:белк[ао]|протеин)"
                        fat_pattern = r"(\d+[.,]?\d*)\s*(?:г|гр)?\s*жир"
                        carbs_pattern = r"(\d+[.,]?\d*)\s*(?:г|гр)?\s*(?:углевод|угле)"
                        
                        kcal_match = re.search(kcal_pattern, clean_text, re.IGNORECASE)
                        protein_match = re.search(protein_pattern, clean_text, re.IGNORECASE)
                        fat_match = re.search(fat_pattern, clean_text, re.IGNORECASE)
                        carbs_match = re.search(carbs_pattern, clean_text, re.IGNORECASE)
                        
                        if kcal_match and protein_match and fat_match and carbs_match:
                            kcal = float(kcal_match.group(1).replace(',', '.'))
                            protein = float(protein_match.group(1).replace(',', '.'))
                            fat = float(fat_match.group(1).replace(',', '.'))
                            carbs = float(carbs_match.group(1).replace(',', '.'))
                        else:
                            raise ValueError("Не удалось распознать данные от DeepSeek")

                save_product_data(food, kcal, protein, fat, carbs)
                context.user_data["food_data"] = (kcal, protein, fat, carbs)
                from handlers.utils import get_main_menu
                keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="home")]]
                message = f"✅ {food.capitalize()} — {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У) на 100г\nУкажи вес в граммах:"
                await update.message.reply_text(
                    message,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return FOOD_WEIGHT
            except Exception as e:
                logger.error(f"Ошибка DeepSeek API: {e}")
                user_id = update.message.from_user.id
                keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="home")]]
                if user_id == ADMIN_ID:
                    keyboard.insert(0, [InlineKeyboardButton("Добавить новый продукт (админ)", callback_data="admin_add")])
                await update.message.reply_text(
                    f"Продукт '{food}' не найден. Ошибка API: {e}\n"
                    "Ты можешь добавить его вручную, если ты админ.",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return FOOD_NAME

async def food_name_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    logger.debug(f"Food name buttons triggered with callback_data: {query.data}")

    if query.data.startswith("select_"):
        food = query.data.replace("select_", "")
        context.user_data["food"] = food
        product_data = get_product_data(food)
        logger.debug(f"Selected food: {food}, product_data: {product_data}")
        if product_data is None:
            from handlers.utils import get_main_menu
            await query.edit_message_text(
                f"Ошибка: продукт '{food}' не найден в базе данных.",
                reply_markup=get_main_menu()
            )
            return ConversationHandler.END
        kcal, protein, fat, carbs = product_data
        context.user_data["food_data"] = (kcal, protein, fat, carbs)
        from handlers.utils import get_main_menu
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="home")]]
        message = f"✅ {food.capitalize()} — {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У) на 100г\nУкажи вес в граммах:"
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return FOOD_WEIGHT
    elif query.data == "admin_add":
        user_id = query.from_user.id
        logger.debug(f"Admin add triggered: User ID = {user_id}, ADMIN_ID = {ADMIN_ID}")
        if user_id != ADMIN_ID:
            from handlers.utils import get_main_menu
            await query.edit_message_text("Только администратор может добавлять продукты.", reply_markup=get_main_menu())
            return ConversationHandler.END
        food = context.user_data.get("food", "неизвестный продукт")
        logger.debug(f"Admin adding product: {food}")
        await query.edit_message_text(f"Добавляем '{food}'. Укажи калории на 100 г:")
        return ADMIN_KCAL
    elif query.data == "calculate_custom":
        food = context.user_data.get("food", "неизвестный продукт")
        logger.debug(f"Calculating custom product with neural network: {food}")
        await query.edit_message_text(f"✅ Рассчитываю данные для '{food}'. Секунду...")
        
        try:
            logger.debug(f"Sending request to DeepSeek API for food: {food}")
            response = await call_ai_api(food)
            logger.debug(f"DeepSeek response: {response}")

            # Попробуем извлечь данные в числовом формате: "158 5.5 1.1 30.1"
            numeric_pattern = r"(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)"
            numeric_match = re.search(numeric_pattern, response)

            if numeric_match:
                kcal = float(numeric_match.group(1))
                protein = float(numeric_match.group(2))
                fat = float(numeric_match.group(3))
                carbs = float(numeric_match.group(4))
            else:
                # Удаляем markdown-форматирование (** для жирного текста)
                clean_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', response)
                
                # Альтернативный формат с единицами измерения - улучшенный паттерн
                text_pattern = r"(\d+[.,]?\d*)\s*(?:кк?ал|ккалорий|калорий)[.,]?.*?(\d+[.,]?\d*)\s*(?:г|гр)?\s*(?:белк[ао]|протеин)[ао]?[в]?.*?(\d+[.,]?\d*)\s*(?:г|гр)?\s*жир[ао]?[в]?.*?(\d+[.,]?\d*)\s*(?:г|гр)?\s*(?:углевод|угле)[ао]?[в]?"
                text_match = re.search(text_pattern, clean_text, re.IGNORECASE | re.DOTALL)
                
                if text_match:
                    # Заменяем запятые на точки для корректного преобразования в float
                    kcal = float(text_match.group(1).replace(',', '.'))
                    protein = float(text_match.group(2).replace(',', '.'))
                    fat = float(text_match.group(3).replace(',', '.'))
                    carbs = float(text_match.group(4).replace(',', '.'))
                else:
                    # Еще более общий паттерн для поиска чисел рядом с ключевыми словами
                    kcal_pattern = r"(\d+[.,]?\d*)\s*(?:кк?ал|ккалорий|калорий)"
                    protein_pattern = r"(\d+[.,]?\d*)\s*(?:г|гр)?\s*(?:белк[ао]|протеин)"
                    fat_pattern = r"(\d+[.,]?\d*)\s*(?:г|гр)?\s*жир"
                    carbs_pattern = r"(\d+[.,]?\d*)\s*(?:г|гр)?\s*(?:углевод|угле)"
                    
                    kcal_match = re.search(kcal_pattern, clean_text, re.IGNORECASE)
                    protein_match = re.search(protein_pattern, clean_text, re.IGNORECASE)
                    fat_match = re.search(fat_pattern, clean_text, re.IGNORECASE)
                    carbs_match = re.search(carbs_pattern, clean_text, re.IGNORECASE)
                    
                    if kcal_match and protein_match and fat_match and carbs_match:
                        kcal = float(kcal_match.group(1).replace(',', '.'))
                        protein = float(protein_match.group(1).replace(',', '.'))
                        fat = float(fat_match.group(1).replace(',', '.'))
                        carbs = float(carbs_match.group(1).replace(',', '.'))
                    else:
                        raise ValueError("Не удалось распознать данные от DeepSeek")

            save_product_data(food, kcal, protein, fat, carbs)
            context.user_data["food_data"] = (kcal, protein, fat, carbs)
            from handlers.utils import get_main_menu
            keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="home")]]
            message = f"✅ {food.capitalize()} — {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У) на 100г\nУкажи вес в граммах:"
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return FOOD_WEIGHT
        except Exception as e:
            logger.error(f"Ошибка DeepSeek API: {e}")
            from handlers.utils import get_main_menu
            error_message = f"Ошибка при расчете данных для '{food}': {str(e)}"
            logger.error(error_message)
            
            # Проверка на ошибки API ключа или соединения
            if "authentication" in str(e).lower() or "api key" in str(e).lower():
                error_message = f"Ошибка авторизации в нейросети. Пожалуйста, сообщите администратору."
            elif "timeout" in str(e).lower() or "connection" in str(e).lower():
                error_message = f"Ошибка соединения с нейросетью. Пожалуйста, попробуйте позже."
            
            await query.edit_message_text(
                error_message,
                reply_markup=get_main_menu()
            )
            return ConversationHandler.END
    elif query.data == "food_log":
        from handlers.log_handlers import show_food_log
        await show_food_log(update, context)
        return ConversationHandler.END
    elif query.data.startswith("edit_weight_"):
        log_id = int(query.data.replace("edit_weight_", ""))
        context.user_data["edit_log_id"] = log_id
        await query.edit_message_text("Укажи новый вес в граммах:")
        return EDIT_FOOD_WEIGHT
    elif query.data.startswith("edit_"):
        log_id = int(query.data.replace("edit_", ""))
        context.user_data["edit_log_id"] = log_id
        await query.edit_message_text("Укажи новый вес в граммах:")
        return EDIT_FOOD_WEIGHT
    elif query.data.startswith("delete_"):
        log_id = int(query.data.replace("delete_", ""))
        user_id = query.from_user.id
        delete_food_log(log_id)
        from handlers.log_handlers import show_food_log
        await query.edit_message_text("Продукт удалён. Обновляю историю...")
        await show_food_log(update, context)
        return ConversationHandler.END
    elif query.data == "home":
        from handlers.menu_handlers import start
        return await start(update, context)
    return FOOD_NAME

async def food_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    try:
        weight = float(text)
        food = context.user_data["food"]
        kcal, protein, fat, carbs = context.user_data["food_data"]
        total_kcal = kcal * weight / 100
        total_protein = protein * weight / 100
        total_fat = fat * weight / 100
        total_carbs = carbs * weight / 100

        user_id = update.message.from_user.id
        log_food(user_id, food, weight)

        intake_calories, intake_protein, intake_fat, intake_carbs = get_daily_intake(user_id)
        norm_calories, norm_protein, norm_fat, norm_carbs = get_user_data(user_id)
        percentage = (intake_calories / norm_calories) * 100 if norm_calories > 0 else 0

        html_message = (
            f"✅ Добавлено: {food} {weight:.0f}г — {total_kcal:.0f} ккал ({total_protein:.1f}Б / {total_fat:.1f}Ж / {total_carbs:.1f}У)\n\n"
            f"<b>Твой дневной итог:</b>\n"
            f"Калории: {intake_calories:.0f} / {norm_calories:.0f} ккал ({percentage:.1f}%)\n"
            f"Белки: {intake_protein:.1f} / {norm_protein:.1f}г\n"
            f"Жиры: {intake_fat:.1f} / {norm_fat:.1f}г\n"
            f"Углеводы: {intake_carbs:.1f} / {norm_carbs:.1f}г"
        )
        from handlers.utils import get_main_menu
        await update.message.reply_text(
            html_message,
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
        return ConversationHandler.END
    except ValueError:
        context.user_data["food"] = text.lower()
        logger.debug(f"Food name entered: {text}")
        return await food_name(update, context)

async def admin_kcal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        kcal = float(update.message.text)
        context.user_data["kcal"] = kcal
        await update.message.reply_text("Укажи белки на 100 г:")
        return ADMIN_PROTEIN
    except ValueError:
        await update.message.reply_text("Введи число. Сколько калорий на 100 г?")
        return ADMIN_KCAL

async def admin_protein(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        protein = float(update.message.text)
        context.user_data["protein"] = protein
        await update.message.reply_text("Укажи жиры на 100 г:")
        return ADMIN_FAT
    except ValueError:
        await update.message.reply_text("Введи число. Сколько белков на 100 г?")
        return ADMIN_PROTEIN

async def admin_fat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        fat = float(update.message.text)
        context.user_data["fat"] = fat
        await update.message.reply_text("Укажи углеводы на 100 г:")
        return ADMIN_CARBS
    except ValueError:
        await update.message.reply_text("Введи число. Сколько жиров на 100 г?")
        return ADMIN_FAT

async def admin_carbs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        carbs = float(update.message.text)
        food = context.user_data["food"]
        kcal = context.user_data["kcal"]
        protein = context.user_data["protein"]
        fat = context.user_data["fat"]

        save_product_data(food, kcal, protein, fat, carbs)

        message = f"✅ {food.capitalize()} — {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У) на 100г\nУкажи вес в граммах:"
        await update.message.reply_text(message)
        context.user_data["food_data"] = (kcal, protein, fat, carbs)
        return FOOD_WEIGHT
    except ValueError:
        await update.message.reply_text("Введи число. Сколько углеводов на 100 г?")
        return ADMIN_CARBS

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка данных от мини-приложения (штрихкода и информации о продукте)."""
    try:
        raw_data = update.message.web_app_data.data
        product_data = json.loads(raw_data)
        barcode = product_data["barcode"]
        food_name = product_data["name"]
        kcal = product_data["kcal"]
        protein = product_data["protein"]
        fat = product_data["fat"]
        carbs = product_data["carbs"]
        user_id = update.message.from_user.id

        existing_product = get_product_data(food_name)
        if not existing_product:
            save_product_data(food_name, kcal, protein, fat, carbs)
            save_barcode_product(barcode, food_name)
        else:
            save_barcode_product(barcode, food_name)

        weight = 100  # По умолчанию 100г
        log_food(user_id, food_name, weight)
        
        intake_calories, intake_protein, intake_fat, intake_carbs = get_daily_intake(user_id)
        norm_calories, norm_protein, norm_fat, norm_carbs = get_user_data(user_id)
        percentage = (intake_calories / norm_calories) * 100 if norm_calories > 0 else 0

        html_message = (
            f"✅ Добавлено по штрихкоду {barcode}: {food_name} {weight:.0f}г — {kcal:.0f} ккал "
            f"({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У) на 100г\n\n"
            f"<b>Твой дневной итог:</b>\n"
            f"Калории: {intake_calories:.0f} / {norm_calories:.0f} ккал ({percentage:.1f}%)\n"
            f"Белки: {intake_protein:.1f} / {norm_protein:.1f}г\n"
            f"Жиры: {intake_fat:.1f} / {norm_fat:.1f}г\n"
            f"Углеводы: {intake_carbs:.1f} / {norm_carbs:.1f}г"
        )
        from handlers.utils import get_main_menu
        await update.message.reply_text(html_message, reply_markup=get_main_menu(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error processing web app data: {e}")
        await update.message.reply_text(f"Ошибка обработки штрихкода: {e}")