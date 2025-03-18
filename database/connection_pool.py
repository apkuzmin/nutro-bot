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
            # Для Windows используем более консервативные настройки
            if os.name == 'nt':
                conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
                conn.execute("PRAGMA busy_timeout = 30000")  # 30 секунд таймаут для занятых операций
            else:
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
        except sqlite3.Error as e:
            logger.error(f"Ошибка SQLite при создании соединения с БД {self.db_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при создании соединения с БД {self.db_path}: {e}")
            return None
    
    def get_connection(self):
        """
        Получить соединение из пула или создать новое, если пул не заполнен.
        
        Returns:
            sqlite3.Connection: Соединение с базой данных
        
        Raises:
            TimeoutError: Если не удалось получить соединение в течение таймаута
            sqlite3.Error: Если не удалось создать новое соединение
        """
        start_time = time.time()
        retry_count = 0
        max_retries = 3
        base_delay = 0.1
        
        while True:
            # Проверяем, не превышен ли таймаут
            if time.time() - start_time > self.timeout:
                raise TimeoutError(f"Таймаут при получении соединения с БД {self.db_path}")
            
            try:
                # Пытаемся получить соединение из пула
                conn = self.pool.get(block=False)
                # Проверяем, что соединение все еще работает
                conn.execute("SELECT 1")
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
                            if retry_count < max_retries:
                                retry_count += 1
                                delay = base_delay * (2 ** (retry_count - 1))
                                logger.warning(f"Не удалось создать соединение, попытка {retry_count}/{max_retries} через {delay:.1f}с")
                                time.sleep(delay)
                                continue
                            raise sqlite3.Error(f"Не удалось создать соединение с БД {self.db_path} после {max_retries} попыток")
                
                # Если не удалось создать новое соединение, ждем немного и пробуем снова
                time.sleep(base_delay)
    
    def return_connection(self, conn):
        """
        Вернуть соединение в пул.
        
        Args:
            conn (sqlite3.Connection): Соединение для возврата в пул
        """
        if conn is None:
            logger.warning(f"Попытка вернуть None соединение в пул для {self.db_path}")
            return
            
        try:
            # Проверяем, что соединение все еще работает
            conn.execute("SELECT 1")
            # Возвращаем соединение в пул
            self.pool.put(conn, block=False)
            logger.debug(f"Соединение возвращено в пул для {self.db_path}")
        except sqlite3.Error as e:
            # Если соединение повреждено, закрываем его
            logger.warning(f"Соединение повреждено для {self.db_path}: {e}")
            try:
                conn.close()
            except Exception:
                pass
            with self.lock:
                self.active_connections -= 1
        except queue.Full:
            # Если пул полон, закрываем соединение
            logger.warning(f"Пул соединений полон для {self.db_path}")
            try:
                conn.close()
            except Exception:
                pass
            with self.lock:
                self.active_connections -= 1
        except Exception as e:
            # Обрабатываем любые другие неожиданные ошибки
            logger.error(f"Неожиданная ошибка при возврате соединения в пул для {self.db_path}: {e}")
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
                except sqlite3.Error as e:
                    logger.warning(f"Ошибка SQLite при закрытии соединения: {e}")
                except Exception as e:
                    logger.warning(f"Неожиданная ошибка при закрытии соединения: {e}")
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
    except sqlite3.Error as e:
        logger.error(f"Ошибка SQLite при работе с БД {db_name}: {e}")
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка при работе с БД {db_name}: {e}")
        raise
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
    retry_count = 0
    max_retries = 3
    base_delay = 0.5  # Начальная задержка в секундах
    
    while True:
        try:
            # Устанавливаем таймаут для занятых операций
            conn.execute("PRAGMA busy_timeout = 30000")  # 30 секунд
            
            # Начинаем транзакцию
            conn.execute("BEGIN TRANSACTION")
            
            try:
                yield conn
                conn.execute("COMMIT")
                return
            except Exception as e:
                conn.execute("ROLLBACK")
                raise
                
        except sqlite3.Error as e:
            error_msg = str(e).lower()
            if retry_count < max_retries and ("database is locked" in error_msg or "busy" in error_msg):
                retry_count += 1
                delay = base_delay * (2 ** (retry_count - 1))  # Экспоненциальная задержка
                logger.warning(f"База данных заблокирована, попытка {retry_count}/{max_retries} через {delay:.1f}с")
                time.sleep(delay)
                continue
            logger.error(f"Ошибка SQLite в транзакции: {e}")
            raise
        except Exception as e:
            logger.error(f"Неожиданная ошибка в транзакции: {e}")
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