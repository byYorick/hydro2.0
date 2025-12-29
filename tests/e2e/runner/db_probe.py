"""
Проверки базы данных через SQL запросы.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Callable, Tuple
import sqlite3
import os
from pathlib import Path
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DBProbe:
    """Проверки базы данных."""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Инициализация DB probe.
        
        Args:
            db_path: Путь к SQLite базе данных или DSN (например postgresql://...)
        """
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None
        self.pg_conn = None  # psycopg connection (sync)
        self._backend: Optional[str] = None  # "sqlite" | "postgres"
    
    def _get_db_path(self) -> Optional[str]:
        """Получить путь к базе данных. Только PostgreSQL поддерживается."""
        if self.db_path:
            # Если явно указан путь, проверяем, это DSN или файл
            if self.db_path.startswith(("postgres://", "postgresql://")):
                return self.db_path
            # Если это не DSN, считаем что это PostgreSQL DSN нужно сформировать
            # Но лучше использовать переменные окружения
        
        # Приоритет 1: DATABASE_URL (если установлен)
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            return database_url
        
        # Приоритет 2: PostgreSQL переменные окружения
        db_host = os.getenv("DB_HOST", "localhost")
        # Выравниваем дефолт с docker-compose.e2e.yml (5433->5432 inside container)
        db_port = os.getenv("DB_PORT", "5433")
        db_name = os.getenv("DB_DATABASE", "hydro_e2e")
        db_user = os.getenv("DB_USERNAME", "hydro")
        db_pass = os.getenv("DB_PASSWORD", "hydro_e2e")
        
        # Всегда используем PostgreSQL, если есть переменные окружения
        if db_host and db_name:
            dsn = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
            return dsn
        
        # Если переменные не установлены, возвращаем None
        return None
    
    def connect(self):
        """Подключиться к базе данных."""
        db_path = self._get_db_path()
        if not db_path:
            raise RuntimeError("Database path not found. Set DB_DATABASE or db_path parameter.")

        # Только PostgreSQL поддерживается
        if not isinstance(db_path, str) or not db_path.startswith(("postgres://", "postgresql://")):
            raise RuntimeError(
                f"Only PostgreSQL is supported. Got: {db_path}. "
                "Set DATABASE_URL or DB_HOST/DB_PORT/DB_DATABASE environment variables."
            )
        
        try:
            import psycopg
        except Exception as e:
            raise RuntimeError("psycopg is required for Postgres DBProbe. Install tests/e2e requirements.") from e

        self.pg_conn = psycopg.connect(db_path)
        self.pg_conn.autocommit = True
        self._backend = "postgres"
        logger.info(f"Connected to Postgres database: {db_path.split('@')[1] if '@' in db_path else 'via DSN'}")
    
    def disconnect(self):
        """Отключиться от базы данных."""
        if self.connection:
            self.connection.close()
            self.connection = None
        if self.pg_conn:
            try:
                self.pg_conn.close()
            except Exception:
                pass
            self.pg_conn = None
        self._backend = None

    def _convert_named_params(self, query: str, params: Dict[str, Any], backend: str) -> Tuple[str, List[Any]]:
        """
        Convert ':name' params into backend placeholders and return ordered args.
        - sqlite: uses '?'
        - postgres (psycopg): uses '%s'
        """
        if not params:
            return query, []

        # Keep deterministic ordering based on first appearance in query.
        order: List[str] = []
        def repl(m: re.Match) -> str:
            name = m.group(1)
            if name not in params:
                # leave untouched; will fail later at execute
                return m.group(0)
            if name not in order:
                order.append(name)
            return "?" if backend == "sqlite" else "%s"

        converted = re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", repl, query)
        args = [params[k] for k in order]
        return converted, args
    
    async def wait(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
        expected_rows: Optional[int] = None,
        condition: Optional[Callable[[List[Dict[str, Any]]], bool]] = None
    ) -> List[Dict[str, Any]]:
        """
        Ожидать выполнения SQL запроса с условием.
        
        Args:
            query: SQL запрос (может содержать плейсхолдеры :param)
            params: Параметры для запроса
            timeout: Таймаут ожидания в секундах
            expected_rows: Ожидаемое количество строк
            condition: Функция-условие для проверки результата
            
        Returns:
            Список строк результата
        """
        if not self.connection and not self.pg_conn:
            self.connect()
        
        import time
        start_time = time.time()
        params = params or {}
        
        logger.info(f"db.wait: Starting wait for query: {query} with params: {params}, timeout: {timeout}s")
        
        while True:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning(f"db.wait: Timeout after {elapsed:.2f}s for query: {query} with params: {params}")
                raise TimeoutError(f"Timeout waiting for DB condition: {query}")

            result: List[Dict[str, Any]] = []

            if self._backend == "postgres":
                q, args = self._convert_named_params(query, params, backend="postgres")
                logger.debug(f"db.wait: Executing query: {q} with args: {args}")
                cur = self.pg_conn.cursor()
                cur.execute(q, args)
                rows = cur.fetchall()
                cols = [d.name for d in cur.description] if cur.description else []
                result = [dict(zip(cols, row)) for row in rows]
            else:
                cursor = self.connection.cursor()
                sqlite_query, sqlite_params = self._convert_named_params(query, params, backend="sqlite")
                logger.debug(f"db.wait: Executing query: {sqlite_query} with params: {sqlite_params}")
                cursor.execute(sqlite_query, sqlite_params)
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
            
            logger.debug(f"db.wait: Query returned {len(result)} rows: {result}")
            
            # Проверяем условия
            if expected_rows is not None:
                if len(result) == expected_rows:
                    logger.info(f"db.wait: Condition met - got {len(result)} rows (expected {expected_rows})")
                    return result
                else:
                    logger.debug(f"db.wait: Waiting - got {len(result)} rows, expected {expected_rows} (elapsed: {elapsed:.2f}s)")
            elif condition is not None:
                if condition(result):
                    logger.info(f"db.wait: Condition met - custom condition returned True")
                    return result
                else:
                    logger.debug(f"db.wait: Waiting - custom condition returned False (elapsed: {elapsed:.2f}s)")
            elif len(result) > 0:
                logger.info(f"db.wait: Condition met - got {len(result)} rows")
                return result
            else:
                logger.debug(f"db.wait: Waiting - no rows returned yet (elapsed: {elapsed:.2f}s)")
            
            await asyncio.sleep(0.1)
    
    def query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Выполнить SQL запрос.
        
        Args:
            query: SQL запрос
            params: Параметры для запроса
            
        Returns:
            Список строк результата
        """
        if not self.connection and not self.pg_conn:
            self.connect()

        params = params or {}

        if self._backend == "postgres":
            q, args = self._convert_named_params(query, params, backend="postgres")
            cur = self.pg_conn.cursor()
            cur.execute(q, args)
            rows = cur.fetchall()
            cols = [d.name for d in cur.description] if cur.description else []
            return [dict(zip(cols, row)) for row in rows]

        cursor = self.connection.cursor()
        sqlite_query, sqlite_params = self._convert_named_params(query, params, backend="sqlite")
        cursor.execute(sqlite_query, sqlite_params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def execute(self, query: str, params: Optional[Dict[str, Any]] = None):
        """
        Выполнить SQL запрос без возврата результата (INSERT, UPDATE, DELETE).
        
        Args:
            query: SQL запрос
            params: Параметры для запроса
        """
        if not self.connection and not self.pg_conn:
            self.connect()

        params = params or {}

        if self._backend == "postgres":
            q, args = self._convert_named_params(query, params, backend="postgres")
            cur = self.pg_conn.cursor()
            cur.execute(q, args)
            return

        cursor = self.connection.cursor()
        sqlite_query, sqlite_params = self._convert_named_params(query, params, backend="sqlite")
        cursor.execute(sqlite_query, sqlite_params)
        self.connection.commit()

    def table_exists(self, table_name: str) -> bool:
        """
        Проверить существование таблицы.

        Args:
            table_name: Имя таблицы

        Returns:
            True если таблица существует
        """
        if self._backend == "postgres":
            query = """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = :table_name
                )
            """
            result = self.query(query, {"table_name": table_name})
            return result[0]["exists"] if result else False

        elif self._backend == "sqlite":
            query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
            result = self.query(query, {"table_name": table_name})
            return len(result) > 0

        return False

    def column_exists(self, table_name: str, column_name: str) -> bool:
        """
        Проверить существование колонки в таблице.

        Args:
            table_name: Имя таблицы
            column_name: Имя колонки

        Returns:
            True если колонка существует
        """
        if self._backend == "postgres":
            query = """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    AND table_name = :table_name
                    AND column_name = :column_name
                )
            """
            result = self.query(query, {"table_name": table_name, "column_name": column_name})
            return result[0]["exists"] if result else False

        elif self._backend == "sqlite":
            query = f"PRAGMA table_info({table_name})"
            result = self.query(query)
            return any(row["name"] == column_name for row in result)

        return False
