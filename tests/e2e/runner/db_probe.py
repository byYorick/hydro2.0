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
        """Получить путь к базе данных."""
        if self.db_path:
            return self.db_path
        
        # Пытаемся найти базу данных через переменные окружения или стандартные пути
        possible_paths = [
            os.getenv("DB_DATABASE"),
            os.getenv("DATABASE_URL"),
            "database/database.sqlite",
            "backend/laravel/database/database.sqlite",
        ]
        
        for path in possible_paths:
            if path and Path(path).exists():
                return path
        
        return None
    
    def connect(self):
        """Подключиться к базе данных."""
        db_path = self._get_db_path()
        if not db_path:
            raise RuntimeError("Database path not found. Set DB_DATABASE or db_path parameter.")

        # DSN?
        if isinstance(db_path, str) and db_path.startswith(("postgres://", "postgresql://")):
            try:
                import psycopg
            except Exception as e:
                raise RuntimeError("psycopg is required for Postgres DBProbe. Install tests/e2e requirements.") from e

            self.pg_conn = psycopg.connect(db_path)
            self.pg_conn.autocommit = True
            self._backend = "postgres"
            logger.info("Connected to Postgres database via DSN")
            return

        # SQLite file
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
        self._backend = "sqlite"
        logger.info(f"Connected to SQLite database: {db_path}")
    
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
        
        while True:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                raise TimeoutError(f"Timeout waiting for DB condition: {query}")

            result: List[Dict[str, Any]] = []

            if self._backend == "postgres":
                q, args = self._convert_named_params(query, params, backend="postgres")
                cur = self.pg_conn.cursor()
                cur.execute(q, args)
                rows = cur.fetchall()
                cols = [d.name for d in cur.description] if cur.description else []
                result = [dict(zip(cols, row)) for row in rows]
            else:
                cursor = self.connection.cursor()
                sqlite_query, sqlite_params = self._convert_named_params(query, params, backend="sqlite")
                cursor.execute(sqlite_query, sqlite_params)
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
            
            # Проверяем условия
            if expected_rows is not None and len(result) != expected_rows:
                await asyncio.sleep(0.5)
                continue
            
            if condition is None or condition(result):
                logger.debug(f"DB wait condition met: {query}")
                return result
            
            await asyncio.sleep(0.5)
    
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

