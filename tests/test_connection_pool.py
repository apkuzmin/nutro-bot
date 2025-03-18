"""
Тесты для модуля пула соединений с базой данных.
"""

import unittest
import threading
import time
import os
import sqlite3
from database.connection_pool import (
    DatabaseConnectionPool, get_db_connection, transaction,
    get_products_connection, get_users_connection, get_food_log_connection
)

class TestDatabaseConnectionPool(unittest.TestCase):
    """Тесты для класса DatabaseConnectionPool."""
    
    @classmethod
    def setUpClass(cls):
        """Подготовка к тестам на уровне класса."""
        # Создаем временную директорию для тестовых баз данных
        cls.test_db_dir = "test_data"
        if not os.path.exists(cls.test_db_dir):
            os.makedirs(cls.test_db_dir)
        
        # Сохраняем оригинальное значение DB_DIR
        import database.connection_pool as cp
        cls.original_db_dir = cp.DB_DIR
        cp.DB_DIR = cls.test_db_dir
        
        # Создаем тестовую базу данных
        cls.test_db = "test.db"
        cls.pool = DatabaseConnectionPool(cls.test_db, max_connections=5)
    
    @classmethod
    def tearDownClass(cls):
        """Очистка после тестов на уровне класса."""
        # Закрываем все соединения
        cls.pool.close_all()
        
        # Восстанавливаем оригинальное значение DB_DIR
        import database.connection_pool as cp
        cp.DB_DIR = cls.original_db_dir
        
        # В Windows файлы SQLite могут оставаться заблокированными,
        # поэтому мы не удаляем директорию, а просто очищаем ее содержимое
        for filename in os.listdir(cls.test_db_dir):
            try:
                file_path = os.path.join(cls.test_db_dir, filename)
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Не удалось удалить файл {file_path}: {e}")
    
    def setUp(self):
        """Подготовка к каждому тесту."""
        # Создаем тестовые таблицы
        with get_db_connection(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, name TEXT)")
            cursor.execute("CREATE TABLE IF NOT EXISTS test_transaction (id INTEGER PRIMARY KEY, name TEXT)")
            # Очищаем таблицы перед каждым тестом
            cursor.execute("DELETE FROM test")
            cursor.execute("DELETE FROM test_transaction")
    
    def test_get_connection(self):
        """Тест получения соединения из пула."""
        conn = self.pool.get_connection()
        self.assertIsInstance(conn, sqlite3.Connection)
        self.pool.return_connection(conn)
    
    def test_connection_reuse(self):
        """Тест повторного использования соединений."""
        conn1 = self.pool.get_connection()
        self.pool.return_connection(conn1)
        conn2 = self.pool.get_connection()
        
        # Проверяем, что это то же самое соединение
        self.assertEqual(id(conn1), id(conn2))
        
        self.pool.return_connection(conn2)
    
    def test_max_connections(self):
        """Тест максимального количества соединений."""
        # Получаем максимальное количество соединений
        connections = []
        for _ in range(self.pool.max_connections):
            connections.append(self.pool.get_connection())
        
        # Проверяем, что следующее соединение будет ждать
        def get_connection_with_timeout():
            try:
                conn = self.pool.get_connection()
                self.pool.return_connection(conn)
                return True
            except TimeoutError:
                return False
        
        thread = threading.Thread(target=get_connection_with_timeout)
        thread.daemon = True
        thread.start()
        thread.join(1)  # Ждем 1 секунду
        
        # Возвращаем одно соединение в пул
        self.pool.return_connection(connections.pop())
        
        # Теперь должно быть доступно одно соединение
        conn = self.pool.get_connection()
        self.assertIsInstance(conn, sqlite3.Connection)
        self.pool.return_connection(conn)
        
        # Возвращаем остальные соединения
        for conn in connections:
            self.pool.return_connection(conn)
    
    def test_context_manager(self):
        """Тест контекстного менеджера."""
        with get_db_connection(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO test (name) VALUES (?)", ("test",))
        
        # Проверяем, что данные сохранились
        with get_db_connection(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM test WHERE name = 'test'")
            result = cursor.fetchone()
            self.assertIsNotNone(result)
            self.assertEqual(result[0], "test")
    
    def test_transaction(self):
        """Тест транзакций."""
        # Тестируем успешную транзакцию
        with get_db_connection(self.test_db) as conn:
            with transaction(conn) as tx:
                cursor = tx.cursor()
                cursor.execute("INSERT INTO test_transaction (name) VALUES (?)", ("success",))
        
        # Проверяем, что данные сохранились
        with get_db_connection(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM test_transaction WHERE name = 'success'")
            result = cursor.fetchone()
            self.assertIsNotNone(result)
            self.assertEqual(result[0], "success")
        
        # Тестируем откат транзакции при ошибке
        try:
            with get_db_connection(self.test_db) as conn:
                with transaction(conn) as tx:
                    cursor = tx.cursor()
                    cursor.execute("INSERT INTO test_transaction (name) VALUES (?)", ("failure",))
                    # Вызываем ошибку
                    raise Exception("Test exception")
        except Exception:
            pass
        
        # Проверяем, что данные не сохранились
        with get_db_connection(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM test_transaction WHERE name = 'failure'")
            result = cursor.fetchone()
            self.assertIsNone(result)
    
    def test_specific_connections(self):
        """Тест специфичных соединений для разных баз данных."""
        # Тестируем соединение с базой данных продуктов
        with get_products_connection() as conn:
            self.assertIsInstance(conn, sqlite3.Connection)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS products_test (id INTEGER PRIMARY KEY)")
        
        # Тестируем соединение с базой данных пользователей
        with get_users_connection() as conn:
            self.assertIsInstance(conn, sqlite3.Connection)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS users_test (id INTEGER PRIMARY KEY)")
        
        # Тестируем соединение с базой данных логов питания
        with get_food_log_connection() as conn:
            self.assertIsInstance(conn, sqlite3.Connection)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS food_log_test (id INTEGER PRIMARY KEY)")

if __name__ == "__main__":
    unittest.main() 