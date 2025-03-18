#!/usr/bin/env python
"""
Тестовый скрипт для проверки работы с альтернативными названиями продуктов.
"""

import sqlite3
import os
import sys
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Добавление директории проекта в sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импорт функций для работы с базой данных
from database.products_db import get_product_data, save_product_data, search_products, add_product_alias, get_product_by_alias
from database.connection_pool import get_products_connection, transaction

def show_all_products():
    """Показать все продукты в базе данных."""
    with get_products_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, kcal, protein, fat, carbs FROM products ORDER BY name")
        products = cursor.fetchall()
        
        print("\n=== СПИСОК ПРОДУКТОВ ===")
        for product in products:
            product_id, name, kcal, protein, fat, carbs = product
            print(f"ID: {product_id} | {name} — {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У)")
        print(f"Всего продуктов: {len(products)}")

def show_all_aliases():
    """Показать все альтернативные названия продуктов."""
    with get_products_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.id, a.alias_name, p.name, p.id
            FROM product_aliases a
            JOIN products p ON a.product_id = p.id
            ORDER BY a.alias_name
        """)
        aliases = cursor.fetchall()
        
        print("\n=== АЛЬТЕРНАТИВНЫЕ НАЗВАНИЯ ===")
        for alias in aliases:
            alias_id, alias_name, product_name, product_id = alias
            print(f"ID: {alias_id} | '{alias_name}' → '{product_name}' (ID: {product_id})")
        print(f"Всего альтернативных названий: {len(aliases)}")

def test_add_alias():
    """Тест добавления альтернативного названия."""
    product_name = "Raffaello"
    alias_name = input("Введите альтернативное название для продукта 'Raffaello': ")
    
    # Проверяем, есть ли продукт в базе
    product_data = get_product_data(product_name)
    if not product_data:
        print(f"Продукт '{product_name}' не найден в базе. Сначала добавьте продукт.")
        return
    
    # Добавляем альтернативное название
    result = add_product_alias(product_name, alias_name)
    if result:
        print(f"✅ Успешно добавлено альтернативное название '{alias_name}' для продукта '{product_name}'")
    else:
        print(f"❌ Не удалось добавить альтернативное название '{alias_name}' для продукта '{product_name}'")

def test_search_by_alias():
    """Тест поиска продукта по альтернативному названию."""
    alias_name = input("Введите название продукта для поиска: ")
    
    print(f"\nПоиск продукта '{alias_name}'...")
    
    # Сначала проверяем прямой поиск в таблице продуктов
    with get_products_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, kcal, protein, fat, carbs FROM products WHERE name = ?", (alias_name,))
        direct_result = cursor.fetchone()
        
        if direct_result:
            product_id, name, kcal, protein, fat, carbs = direct_result
            print(f"✅ Найдено в основной таблице products напрямую:")
            print(f"   ID: {product_id} | {name} — {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У)")
        else:
            print(f"❌ Не найдено в основной таблице products напрямую")
    
    # Проверяем в таблице альтернативных названий
    with get_products_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.id, a.alias_name, p.id, p.name, p.kcal, p.protein, p.fat, p.carbs
            FROM product_aliases a
            JOIN products p ON a.product_id = p.id
            WHERE a.alias_name = ?
        """, (alias_name,))
        alias_result = cursor.fetchone()
        
        if alias_result:
            alias_id, alias_name, product_id, name, kcal, protein, fat, carbs = alias_result
            print(f"✅ Найдено через альтернативное название в таблице product_aliases:")
            print(f"   Alias ID: {alias_id} | '{alias_name}' → '{name}' (ID: {product_id})")
            print(f"   Данные: {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У)")
        else:
            print(f"❌ Не найдено в таблице альтернативных названий product_aliases")
    
    # Теперь проверяем через функцию get_product_data
    product_data = get_product_data(alias_name)
    if product_data:
        kcal, protein, fat, carbs = product_data
        print(f"\n✅ Результат функции get_product_data():")
        print(f"   {alias_name} — {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У)")
    else:
        print(f"\n❌ Функция get_product_data() не нашла продукт '{alias_name}'")
        
    # Проверяем через функцию get_product_by_alias
    product = get_product_by_alias(alias_name)
    if product:
        product_id, name, kcal, protein, fat, carbs = product
        print(f"\n✅ Результат функции get_product_by_alias():")
        print(f"   '{alias_name}' → '{name}' (ID: {product_id})")
        print(f"   Данные: {kcal:.0f} ккал ({protein:.1f}Б / {fat:.1f}Ж / {carbs:.1f}У)")
    else:
        print(f"\n❌ Функция get_product_by_alias() не нашла альтернативное название '{alias_name}'")

def main():
    """Основная функция."""
    while True:
        print("\n=== МЕНЮ ТЕСТИРОВАНИЯ ===")
        print("1. Показать все продукты")
        print("2. Показать все альтернативные названия")
        print("3. Добавить альтернативное название")
        print("4. Найти продукт по названию или альтернативному названию")
        print("0. Выход")
        
        choice = input("\nВыберите действие: ")
        
        try:
            if choice == "1":
                show_all_products()
            elif choice == "2":
                show_all_aliases()
            elif choice == "3":
                test_add_alias()
            elif choice == "4":
                test_search_by_alias()
            elif choice == "0":
                print("Выход из программы...")
                break
            else:
                print("Неверный выбор. Пожалуйста, выберите действие из списка.")
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            print(f"Произошла ошибка: {e}")

if __name__ == "__main__":
    main() 