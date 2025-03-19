#!/usr/bin/env python
"""
Тестовый скрипт для проверки распознавания пользовательского формата ввода продуктов.
"""

import re
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_custom_format(input_text):
    """
    Проверяет, соответствует ли ввод пользователя формату "Название X Y Z W",
    где X, Y, Z, W - числа (ккал, белки, жиры, углеводы).
    
    Args:
        input_text (str): Текст, введенный пользователем
        
    Returns:
        tuple: (food_name, kcal, protein, fat, carbs) или None, если формат не распознан
    """
    # Паттерн для распознавания формата "Название X Y Z W"
    # Ищем строку, за которой следуют 4 числа (целые или с плавающей точкой)
    pattern = r'^(.+?)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)$'
    match = re.match(pattern, input_text.strip())
    
    if match:
        try:
            food_name = match.group(1).strip()
            kcal = float(match.group(2))
            protein = float(match.group(3))
            fat = float(match.group(4))
            carbs = float(match.group(5))
            
            # Проверяем корректность значений
            if (kcal < 0 or kcal > 900 or 
                protein < 0 or protein > 100 or 
                fat < 0 or fat > 100 or 
                carbs < 0 or carbs > 100 or
                protein + fat + carbs > 110):
                logger.warning(f"Некорректные значения КБЖУ: {kcal}, {protein}, {fat}, {carbs}")
                return None
                
            logger.info(f"Распознан пользовательский формат: {food_name} - {kcal} ккал, {protein}г белка, {fat}г жира, {carbs}г углеводов")
            return (food_name, kcal, protein, fat, carbs)
        except ValueError:
            logger.warning(f"Ошибка при преобразовании чисел в пользовательском формате: {input_text}")
            return None
    
    logger.info(f"Не распознан пользовательский формат: {input_text}")
    return None

def test_format(input_text):
    """
    Тестирует распознавание пользовательского формата на заданном тексте.
    
    Args:
        input_text (str): Текст для проверки формата
    """
    print(f"\nТестирование: '{input_text}'")
    result = parse_custom_format(input_text)
    
    if result:
        food_name, kcal, protein, fat, carbs = result
        print(f"✅ Формат распознан:")
        print(f"  Название: {food_name}")
        print(f"  КБЖУ: {kcal:.1f} ккал, {protein:.1f}г белка, {fat:.1f}г жира, {carbs:.1f}г углеводов")
    else:
        print(f"❌ Формат НЕ распознан")

def main():
    """Основная функция для запуска тестов."""
    test_cases = [
        "Творог 5% 121 18 5 3.3",
        "Тильзитер сыр 310 23 24 0",
        "Куриная грудка запеченная 165 30 3.6 0",
        "Яблоко красное 52 0.3 0.2 14",
        "Кока-кола 42 0 0 10.4",
        "Картофель отварной",
        "Филе лосося 142 20 7 0",
        "Филе лосося 142 20 7 0 дополнительный текст",
        "Яблоко 50",
        "123 456 789 012",
        "Кофе с молоком 1000 50 50 50",  # Некорректные значения
        "Торт 600 10 40 60"  # Сумма БЖУ > 100
    ]
    
    print("=== ТЕСТИРОВАНИЕ РАСПОЗНАВАНИЯ ПОЛЬЗОВАТЕЛЬСКОГО ФОРМАТА ===")
    
    for test_case in test_cases:
        test_format(test_case)
    
    # Интерактивный режим
    print("\n=== ИНТЕРАКТИВНЫЙ РЕЖИМ ===")
    print("Введите текст для проверки (или 'q' для выхода):")
    
    while True:
        try:
            user_input = input("> ")
            if user_input.lower() == 'q':
                break
            test_format(user_input)
        except KeyboardInterrupt:
            print("\nПрерывание работы...")
            break
        except Exception as e:
            print(f"Ошибка: {e}")

if __name__ == "__main__":
    main() 