"""
Скрипт для очистки и стандартизации базы данных продуктов.
Выполняет следующие операции:
1. Удаление дубликатов продуктов
2. Стандартизация названий продуктов
3. Исправление некорректных значений пищевой ценности
4. Проверка и исправление связей со штрихкодами
"""

import os
import sys
import logging
import re
import sqlite3
import time
from pathlib import Path

# Добавление директории проекта в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection_pool import get_products_connection, transaction

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("product_cleanup.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("product_cleanup")

def backup_database():
    """Создает резервную копию базы данных продуктов перед очисткой."""
    db_dir = "data"
    db_file = "products.db"
    db_path = os.path.join(db_dir, db_file)
    
    if not os.path.exists(db_path):
        logger.error(f"База данных {db_path} не найдена")
        return False
    
    backup_dir = os.path.join(db_dir, "backups")
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"products_{timestamp}.db")
    
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        logger.info(f"Создана резервная копия базы данных: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии: {e}")
        return False

def standardize_product_name(name):
    """
    Стандартизирует название продукта:
    - Приводит к нижнему регистру
    - Удаляет лишние пробелы
    - Удаляет специальные символы
    - Стандартизирует обозначения
    - Обрабатывает специфические названия брендов
    - Выполняет транслитерацию для известных продуктов
    """
    if not name:
        return name
        
    # Приводим к нижнему регистру
    result = name.lower()
    
    # Специальная обработка для известных брендов и продуктов
    brand_mappings = {
        "рафаэло": "raffaello",
        "рафаело": "raffaello",
        "рафаэлло": "raffaello",
        "рафаелло": "raffaello",
        "феррейро": "ferrero rocher",
        "ферреро": "ferrero rocher",
        "нутелла": "nutella",
        "нутела": "nutella",
        "милка": "milka",
        "милька": "milka",
        "твикс": "twix",
        "марс": "mars",
        "сникерс": "snickers",
        "киткат": "kitkat",
        "кит-кат": "kitkat",
        "кит кат": "kitkat",
        "кока кола": "coca-cola",
        "кока-кола": "coca-cola",
        "пепси": "pepsi",
        "фанта": "fanta",
        "спрайт": "sprite"
    }
    
    # Заменяем известные бренды
    for ru_brand, en_brand in brand_mappings.items():
        if ru_brand in result:
            # Заменяем только полное слово, а не часть слова
            pattern = r'\b' + re.escape(ru_brand) + r'\b'
            result = re.sub(pattern, en_brand, result)
    
    # Заменяем часто встречающиеся синонимы на стандартные названия
    food_mappings = {
        "куриная грудка": "куриная грудка",
        "грудка курицы": "куриная грудка",
        "филе куриное": "куриная грудка",
        "куриное филе": "куриная грудка",
        "говядина": "говядина",
        "говяжий": "говядина",
        "свинина": "свинина",
        "свиной": "свинина",
        "творог 0%": "творог обезжиренный",
        "творог 0": "творог обезжиренный",
        "творог нежирный": "творог обезжиренный",
        "творог обезжир": "творог обезжиренный",
        "яблоко зеленое": "яблоко",
        "яблоко красное": "яблоко",
        "яблоко желтое": "яблоко",
        "сыр моцарелла": "моцарелла",
        "сыр фета": "фета",
        "сыр твердый": "сыр",
        "хлеб белый": "хлеб пшеничный",
        "хлеб черный": "хлеб ржаной",
        "батон": "хлеб пшеничный",
        "кофе черный": "кофе",
        "кофе с молоком": "кофе с молоком",
        "чай черный": "чай",
        "чай зеленый": "зеленый чай"
    }
    
    for old, new in food_mappings.items():
        if old in result:
            result = result.replace(old, new)
    
    # Удаляем уточнения в скобках
    result = re.sub(r'\([^)]*\)', '', result)
    
    # Удаляем единицы измерения
    result = re.sub(r'\d+\s*(?:г|мл|л|кг|шт)', '', result)
    
    # Удаляем процентное содержание жира
    result = re.sub(r'\d+(?:[.,]\d+)?%', '', result)
    
    # Удаляем лишние пробелы
    result = ' '.join(result.split())
    
    # Удаляем точки и запятые в конце
    result = result.rstrip('.,;')
    
    # Первая буква заглавная, остальные маленькие
    if result:
        result = result[0].upper() + result[1:]
    
    return result

def is_valid_nutrition_value(kcal, protein, fat, carbs):
    """Проверяет корректность значений пищевой ценности."""
    # Проверяем, что значения являются числами
    try:
        kcal = float(kcal)
        protein = float(protein)
        fat = float(fat)
        carbs = float(carbs)
    except (TypeError, ValueError):
        return False
    
    # Проверяем диапазоны значений
    if kcal < 0 or kcal > 900:  # Максимальная калорийность ~900 ккал/100г для масел
        return False
    if protein < 0 or protein > 100:
        return False
    if fat < 0 or fat > 100:
        return False
    if carbs < 0 or carbs > 100:
        return False
    
    # Проверяем, что сумма БЖУ не превышает 100г (с небольшим запасом)
    if protein + fat + carbs > 110:
        return False
    
    # Проверяем соответствие калорийности и БЖУ (с погрешностью 20%)
    calculated_kcal = protein * 4 + fat * 9 + carbs * 4
    difference = abs(calculated_kcal - kcal)
    
    # Если разница больше 20% и больше 20 ккал
    if difference > max(20, kcal * 0.2):
        return False
    
    return True

def remove_duplicate_products():
    """Удаляет дубликаты продуктов на основе схожести названий."""
    with get_products_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            # Получаем все продукты
            cursor.execute("SELECT id, name, kcal, protein, fat, carbs FROM products ORDER BY name")
            products = cursor.fetchall()
            
            # Создаем словарь для отслеживания уникальных продуктов
            unique_products = {}
            duplicates = []
            
            for product_id, name, kcal, protein, fat, carbs in products:
                # Стандартизируем название
                std_name = standardize_product_name(name)
                
                # Если имя уже существует, добавляем в список дубликатов
                if std_name in unique_products:
                    duplicates.append((product_id, name, std_name, unique_products[std_name][0]))
                else:
                    unique_products[std_name] = (product_id, name, kcal, protein, fat, carbs)
            
            logger.info(f"Найдено {len(duplicates)} дубликатов из {len(products)} продуктов")
            
            # Обновляем ссылки штрихкодов на продукты
            for dup_id, dup_name, std_name, original_id in duplicates:
                # Обновляем ссылки штрихкодов
                cursor.execute(
                    "UPDATE barcodes SET product_id = ? WHERE product_id = ?",
                    (original_id, dup_id)
                )
                
                # Удаляем дубликат
                cursor.execute("DELETE FROM products WHERE id = ?", (dup_id,))
                logger.info(f"Удален дубликат: {dup_name} (ID: {dup_id}) -> {std_name} (ID: {original_id})")

def update_product_names():
    """Обновляет названия продуктов в соответствии со стандартизированными правилами."""
    with get_products_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            # Получаем все продукты
            cursor.execute("SELECT id, name FROM products")
            products = cursor.fetchall()
            
            updated_count = 0
            
            for product_id, name in products:
                # Стандартизируем название
                std_name = standardize_product_name(name)
                
                # Если название изменилось, обновляем
                if std_name != name:
                    cursor.execute(
                        "UPDATE products SET name = ?, updated_at = ? WHERE id = ?",
                        (std_name, time.strftime('%Y-%m-%d %H:%M:%S'), product_id)
                    )
                    updated_count += 1
                    logger.info(f"Обновлено название: {name} -> {std_name}")
            
            logger.info(f"Обновлено {updated_count} названий продуктов из {len(products)}")

def fix_nutrition_values():
    """Исправляет некорректные значения пищевой ценности продуктов."""
    with get_products_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            # Получаем все продукты
            cursor.execute("SELECT id, name, kcal, protein, fat, carbs FROM products")
            products = cursor.fetchall()
            
            invalid_count = 0
            
            for product_id, name, kcal, protein, fat, carbs in products:
                # Проверяем корректность значений
                if not is_valid_nutrition_value(kcal, protein, fat, carbs):
                    invalid_count += 1
                    logger.warning(f"Некорректные значения пищевой ценности для {name}: {kcal}, {protein}, {fat}, {carbs}")
                    
                    # Пытаемся исправить очевидные ошибки
                    fixed = False
                    
                    # Проверяем, не перепутаны ли значения
                    if protein > 100 and kcal < 100:
                        # Вероятно, значения перепутаны
                        temp = kcal
                        kcal = protein
                        protein = temp
                        fixed = True
                    
                    # Если белки + жиры + углеводы > 100, пропорционально уменьшаем
                    if protein + fat + carbs > 100:
                        factor = 100 / (protein + fat + carbs)
                        protein *= factor
                        fat *= factor
                        carbs *= factor
                        fixed = True
                    
                    # Если калорийность не соответствует БЖУ, пересчитываем
                    calculated_kcal = protein * 4 + fat * 9 + carbs * 4
                    if abs(calculated_kcal - kcal) > max(20, kcal * 0.2):
                        kcal = calculated_kcal
                        fixed = True
                    
                    if fixed:
                        cursor.execute(
                            "UPDATE products SET kcal = ?, protein = ?, fat = ?, carbs = ?, updated_at = ? WHERE id = ?",
                            (kcal, protein, fat, carbs, time.strftime('%Y-%m-%d %H:%M:%S'), product_id)
                        )
                        logger.info(f"Исправлены значения пищевой ценности для {name}: {kcal}, {protein}, {fat}, {carbs}")
            
            logger.info(f"Найдено {invalid_count} продуктов с некорректными значениями пищевой ценности")

def fix_barcode_relationships():
    """Проверяет и исправляет связи штрихкодов с продуктами."""
    with get_products_connection() as conn:
        with transaction(conn) as tx:
            cursor = tx.cursor()
            
            # Находим штрихкоды, которые ссылаются на несуществующие продукты
            cursor.execute(
                """
                SELECT b.barcode, b.product_id 
                FROM barcodes b
                LEFT JOIN products p ON b.product_id = p.id
                WHERE p.id IS NULL
                """
            )
            orphan_barcodes = cursor.fetchall()
            
            for barcode, product_id in orphan_barcodes:
                logger.warning(f"Штрихкод {barcode} ссылается на несуществующий продукт с ID {product_id}")
                cursor.execute("DELETE FROM barcodes WHERE barcode = ?", (barcode,))
                logger.info(f"Удален штрихкод {barcode}")
            
            logger.info(f"Удалено {len(orphan_barcodes)} штрихкодов, ссылающихся на несуществующие продукты")

def run_cleanup():
    """Запускает полную процедуру очистки базы данных продуктов."""
    logger.info("Начало очистки базы данных продуктов")
    
    if not backup_database():
        logger.error("Не удалось создать резервную копию базы данных. Очистка отменена.")
        return False
    
    try:
        # Последовательно выполняем все операции очистки
        fix_barcode_relationships()
        remove_duplicate_products()
        update_product_names()
        fix_nutrition_values()
        fix_barcode_relationships()  # Повторно проверяем после всех изменений
        
        logger.info("Очистка базы данных продуктов завершена успешно")
        return True
    except Exception as e:
        logger.error(f"Ошибка при очистке базы данных продуктов: {e}")
        return False

if __name__ == "__main__":
    try:
        import argparse
        
        parser = argparse.ArgumentParser(description="Очистка и стандартизация базы данных продуктов")
        parser.add_argument('--force', action='store_true', help='Запустить без запроса подтверждения')
        args = parser.parse_args()
        
        if args.force or input("Запустить очистку базы данных продуктов? (y/n): ").lower() == 'y':
            success = run_cleanup()
            if success:
                print("Очистка базы данных продуктов завершена успешно")
            else:
                print("Очистка базы данных продуктов завершилась с ошибками")
        else:
            print("Очистка базы данных продуктов отменена пользователем")
    except KeyboardInterrupt:
        print("\nОчистка базы данных продуктов прервана пользователем")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка: {e}")
        print(f"Произошла ошибка: {e}") 