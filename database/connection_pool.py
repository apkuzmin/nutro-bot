"""
Модуль для управления пулом соединений с базами данных.
Обеспечивает эффективное повторное использование соединений и управление транзакциями.
"""

import sqlite3
import os
import threading
import logging
import queue
import time
from contextlib import contextmanager

# Настройка логирования
logger = logging.getLogger(__name__)

# Директория для хранения файлов баз данных
DB_DIR = "data"

# Убедиться, что директория для баз данных существует
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

class DatabaseConnectionPool:
    """
    Класс для управления пулом соединений с базой данных SQLite.
    Обеспечивает эффективное повторное использование соединений и управление транзакциями.
    """
    
    _pools = {}  # Словарь пулов соединений для разных баз данных
    _lock = threading.RLock()  # Блокировка для потокобезопасности
    
    @classmethod
    def get_pool(cls, db_name):
        """
        Получить или создать пул соединений для указанной базы данных.
        
        Args:
            db_name (str): Имя файла базы данных
            
        Returns:
            DatabaseConnectionPool: Экземпляр пула соединений
        """
        with cls._lock:
            if db_name not in cls._pools:
                cls._pools[db_name] = DatabaseConnectionPool(db_name)
            return cls._pools[db_name]
    
    def __init__(self, db_name, max_connections=10, timeout=5.0):
        """
        Инициализировать пул соединений.
        
        Args:
            db_name (str): Имя файла базы данных
            max_connections (int): Максимальное количество соединений в пуле
            timeout (float): Таймаут ожидания доступного соединения в секундах
        """
        # Проверяем, является ли это базой данных в памяти
        self.is_memory_db = db_name == ":memory:"
        
        # Для баз данных в памяти не используем путь к файлу
        if self.is_memory_db:
            self.db_path = db_name
        else:
            self.db_path = os.path.join(DB_DIR, db_name)
            
        self.max_connections = max_connections
        self.timeout = timeout
        self.pool = queue.Queue(maxsize=max_connections)
        self.active_connections = 0
        self.lock = threading.RLock()
        
        # Инициализация пула начальными соединениями
        self._initialize_pool(2)  # Начинаем с 2 соединений
    
    def _initialize_pool(self, initial_size):
        """
        Инициализировать пул начальными соединениями.
        
        Args:
            initial_size (int): Начальное количество соединений
        """
        for _ in range(min(initial_size, self.max_connections)):
            conn = self._create_connection()
            if conn:
                self.pool.put(conn)
    
    def _create_connection(self):
        """
        Создать новое соединение с базой данных.
        
        Returns:
            sqlite3.Connection: Новое соединение с базой данных
        """
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # Включаем поддержку внешних ключей
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Оптимизация производительности (только для файловых баз данных)
            if not self.is_memory_db:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA cache_size = 10000")
                conn.execute("PRAGMA temp_store = MEMORY")
            return conn
        except Exception as e:
            logger.error(f"Ошибка при создании соединения с БД {self.db_path}: {e}")
            return None
    
    def get_connection(self):
        """
        Получить соединение из пула или создать новое, если пул не заполнен.
        
        Returns:
            sqlite3.Connection: Соединение с базой данных
        
        Raises:
            TimeoutError: Если не удалось получить соединение в течение таймаута
        """
        start_time = time.time()
        
        while True:
            # Проверяем, не превышен ли таймаут
            if time.time() - start_time > self.timeout:
                raise TimeoutError(f"Таймаут при получении соединения с БД {self.db_path}")
            
            try:
                # Пытаемся получить соединение из пула
                conn = self.pool.get(block=False)
                logger.debug(f"Получено соединение из пула для {self.db_path}")
                return conn
            except queue.Empty:
                # Пул пуст, проверяем, можем ли мы создать новое соединение
                with self.lock:
                    if self.active_connections < self.max_connections:
                        self.active_connections += 1
                        conn = self._create_connection()
                        if conn:
                            logger.debug(f"Создано новое соединение для {self.db_path}")
                            return conn
                        else:
                            self.active_connections -= 1
                
                # Если не удалось создать новое соединение, ждем немного и пробуем снова
                time.sleep(0.1)
    
    def return_connection(self, conn):
        """
        Вернуть соединение в пул.
        
        Args:
            conn (sqlite3.Connection): Соединение для возврата в пул
        """
        try:
            # Проверяем, что соединение все еще работает
            conn.execute("SELECT 1")
            # Возвращаем соединение в пул
            self.pool.put(conn, block=False)
            logger.debug(f"Соединение возвращено в пул для {self.db_path}")
        except (sqlite3.Error, queue.Full) as e:
            # Если соединение повреждено или пул полон, закрываем его
            logger.warning(f"Не удалось вернуть соединение в пул для {self.db_path}: {e}")
            try:
                conn.close()
            except Exception:
                pass
            with self.lock:
                self.active_connections -= 1
    
    def close_all(self):
        """
        Закрыть все соединения в пуле.
        """
        with self.lock:
            while not self.pool.empty():
                try:
                    conn = self.pool.get(block=False)
                    conn.close()
                except Exception as e:
                    logger.warning(f"Ошибка при закрытии соединения: {e}")
            self.active_connections = 0
            logger.info(f"Все соединения закрыты для {self.db_path}")

@contextmanager
def get_db_connection(db_name):
    """
    Контекстный менеджер для получения соединения из пула.
    Автоматически возвращает соединение в пул после использования.
    
    Args:
        db_name (str): Имя файла базы данных
        
    Yields:
        sqlite3.Connection: Соединение с базой данных
    """
    pool = DatabaseConnectionPool.get_pool(db_name)
    conn = None
    try:
        conn = pool.get_connection()
        yield conn
    finally:
        if conn:
            pool.return_connection(conn)

@contextmanager
def transaction(conn):
    """
    Контекстный менеджер для управления транзакциями.
    Автоматически выполняет commit или rollback.
    
    Args:
        conn (sqlite3.Connection): Соединение с базой данных
        
    Yields:
        sqlite3.Connection: То же соединение с базой данных
    """
    try:
        conn.execute("BEGIN TRANSACTION")
        yield conn
        conn.execute("COMMIT")
    except Exception as e:
        logger.error(f"Ошибка в транзакции: {e}")
        conn.execute("ROLLBACK")
        raise

# Функции-хелперы для получения соединений с конкретными базами данных
@contextmanager
def get_products_connection():
    """Получить соединение с базой данных продуктов."""
    with get_db_connection("products.db") as conn:
        yield conn

@contextmanager
def get_users_connection():
    """Получить соединение с базой данных пользователей."""
    with get_db_connection("users.db") as conn:
        yield conn

@contextmanager
def get_food_log_connection():
    """Получить соединение с базой данных логов питания."""
    with get_db_connection("food_log.db") as conn:
        yield conn 