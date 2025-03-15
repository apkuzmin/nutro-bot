async def show_food_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Получаем текущий день для пользователя
    current_day = get_current_day_for_user(user_id)
    
    # Обновляем данные о потреблении перед отображением
    await update_daily_intake_for_user(user_id, current_day)
    
    # Получаем записи о питании за текущий день
    food_entries = get_food_entries_for_day(user_id, current_day)
    
    if not food_entries:
        await update.message.reply_text("У вас пока нет записей о питании за сегодня.")
        return
    
    # Формируем новый формат истории питания
    message = "🍽 История питания за сегодня:\n\n"
    
    for entry in food_entries:
        # Форматируем время
        time_str = entry['time'].strftime("%H:%M")
        
        # Форматируем название и вес продукта
        food_name = entry['food_name']
        weight = int(entry['weight'])  # Округляем вес до целого числа
        
        # Форматируем КБЖУ с одним десятичным знаком
        calories = int(entry['calories'])  # Округляем калории до целого числа
        protein = round(entry['protein'], 1)
        fat = round(entry['fat'], 1)
        carbs = round(entry['carbs'], 1)
        
        # Формируем ID для команды редактирования
        edit_id = entry['id']
        
        # Добавляем запись в сообщение
        message += f"🕛 {time_str} — {food_name}, {weight}г\n"
        message += f"⚡️ {calories} ккал ({protein}Б / {fat}Ж / {carbs}У)\n"
        message += f"/edit_{edit_id}\n\n"
    
    await update.message.reply_text(message) 