"""
Упрощенный тест для модуля пула соединений с базой данных.
"""

import unittest
import sqlite3
import os
from database.connection_pool import (
    DatabaseConnectionPool, get_db_connection, transaction
)

class TestDatabaseConnectionPoolSimple(unittest.TestCase):
    """Упрощенные тесты для класса DatabaseConnectionPool."""
    
    def test_pool_creation(self):
        """Тест создания пула соединений."""
        # Создаем пул соединений в памяти
        pool = DatabaseConnectionPool(":memory:", max_connections=5)
        self.assertIsInstance(pool, DatabaseConnectionPool)
        self.assertEqual(pool.max_connections, 5)
        self.assertEqual(pool.db_path, ":memory:")
        
        # Получаем соединение из пула
        conn = pool.get_connection()
        self.assertIsInstance(conn, sqlite3.Connection)
        
        # Возвращаем соединение в пул
        pool.return_connection(conn)
        
        # Закрываем все соединения
        pool.close_all()
    
    def test_context_manager(self):
        """Тест контекстного менеджера."""
        # Используем базу данных в памяти
        with get_db_connection(":memory:") as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            cursor.execute("INSERT INTO test (name) VALUES (?)", ("test",))
            
            # Проверяем, что данные сохранились
            cursor.execute("SELECT name FROM test WHERE name = 'test'")
            result = cursor.fetchone()
            self.assertIsNotNone(result)
            self.assertEqual(result[0], "test")
    
    def test_transaction(self):
        """Тест транзакций."""
        # Используем базу данных в памяти
        with get_db_connection(":memory:") as conn:
            # Создаем таблицу
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test_transaction (id INTEGER PRIMARY KEY, name TEXT)")
            
            # Тестируем успешную транзакцию
            with transaction(conn) as tx:
                cursor = tx.cursor()
                cursor.execute("INSERT INTO test_transaction (name) VALUES (?)", ("success",))
            
            # Проверяем, что данные сохранились
            cursor.execute("SELECT name FROM test_transaction WHERE name = 'success'")
            result = cursor.fetchone()
            self.assertIsNotNone(result)
            self.assertEqual(result[0], "success")
            
            # Тестируем откат транзакции при ошибке
            try:
                with transaction(conn) as tx:
                    cursor = tx.cursor()
                    cursor.execute("INSERT INTO test_transaction (name) VALUES (?)", ("failure",))
                    # Вызываем ошибку
                    raise Exception("Test exception")
            except Exception:
                pass
            
            # Проверяем, что данные не сохранились
            cursor.execute("SELECT name FROM test_transaction WHERE name = 'failure'")
            result = cursor.fetchone()
            self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main() 