"""
Auth Client - управление аутентификацией для E2E тестов.

Обеспечивает:
- Получение токена через API или Artisan команду
- Хранение токена один на прогон
- Автоматическое обновление при 401
- Учет TTL токена
"""

import httpx
import logging
import os
import subprocess
import asyncio
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AuthClient:
    """
    Клиент для управления аутентификацией E2E тестов.
    
    Правила:
    - Токен хранится один на прогон (singleton pattern)
    - TTL учитывается (по умолчанию 24 часа)
    - При 401 → автоматический re-auth
    - Никакого хардкода токенов в сценариях
    """
    
    # Класс-переменная для хранения токена на весь прогон
    _instance: Optional['AuthClient'] = None
    _token: Optional[str] = None
    _token_expires_at: Optional[datetime] = None
    _token_ttl_seconds: int = 24 * 60 * 60  # 24 часа по умолчанию
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern - один экземпляр на прогон."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        api_url: Optional[str] = None,
        email: str = "e2e@test.local",
        role: str = "agronomist",  # По умолчанию agronomist для работы с ревизиями и циклами
        token_ttl_seconds: Optional[int] = None
    ):
        """
        Инициализация Auth Client.
        
        Args:
            api_url: URL API (по умолчанию из LARAVEL_URL)
            email: Email пользователя для E2E тестов
            role: Роль пользователя (admin, operator, viewer)
            token_ttl_seconds: TTL токена в секундах (по умолчанию 24 часа)
        """
        # Если уже инициализирован, не переинициализируем
        if hasattr(self, '_initialized'):
            return
        
        self.api_url = (api_url or os.getenv("LARAVEL_URL", "http://localhost:8081")).rstrip('/')
        self.email = email
        self.role = role
        if token_ttl_seconds:
            self.__class__._token_ttl_seconds = token_ttl_seconds
        
        self._initialized = True
        logger.debug(f"AuthClient initialized: api_url={self.api_url}, email={self.email}, role={self.role}")
    
    async def get_token(self, force_refresh: bool = False) -> str:
        """
        Получить токен аутентификации.
        
        Args:
            force_refresh: Принудительно обновить токен даже если он еще валиден
            
        Returns:
            Токен аутентификации
        """
        # Проверяем, нужно ли обновить токен
        if force_refresh or self._should_refresh_token():
            logger.info("Obtaining new authentication token...")
            token = await self._fetch_token()
            if token:
                self.__class__._token = token
                self.__class__._token_expires_at = datetime.now() + timedelta(
                    seconds=self.__class__._token_ttl_seconds
                )
                logger.info(f"✓ Token obtained (expires at {self.__class__._token_expires_at})")
                return token
            else:
                raise RuntimeError("Failed to obtain authentication token")
        
        # Используем существующий токен
        if self.__class__._token:
            logger.debug("Using existing token")
            return self.__class__._token
        
        # Если токена нет, получаем новый
        logger.info("No token available, obtaining new one...")
        return await self.get_token(force_refresh=True)
    
    async def refresh_token_if_needed(self) -> Optional[str]:
        """
        Обновить токен, если он истек или скоро истечет.
        
        Returns:
            Новый токен или None, если обновление не требуется
        """
        if self._should_refresh_token():
            logger.info("Token expired or expiring soon, refreshing...")
            return await self.get_token(force_refresh=True)
        return None
    
    def get_auth_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        """
        Получить заголовки авторизации.
        
        Args:
            token: Токен (если не указан, используется текущий)
            
        Returns:
            Словарь с заголовками Authorization
        """
        if token is None:
            # Синхронный доступ к токену - используется только если токен уже получен
            token = self.__class__._token
        
        if not token:
            logger.warning("No token available, returning empty headers")
            return {}
        
        return {
            "Authorization": f"Bearer {token}"
        }
    
    def _should_refresh_token(self) -> bool:
        """Проверить, нужно ли обновить токен."""
        # Если токена нет
        if not self.__class__._token:
            return True
        
        # Если срок действия не установлен (старый формат)
        if not self.__class__._token_expires_at:
            return True
        
        # Если токен истек или истечет в ближайшие 5 минут
        now = datetime.now()
        refresh_threshold = now + timedelta(minutes=5)
        
        if self.__class__._token_expires_at <= refresh_threshold:
            return True
        
        return False
    
    async def _fetch_token(self) -> Optional[str]:
        """
        Получить токен через API endpoint или Artisan команду.
        
        Пробует в следующем порядке:
        1. API endpoint POST /api/e2e/auth/token
        2. Artisan команда e2e:auth-bootstrap
        
        Returns:
            Токен или None в случае ошибки
        """
        # Попытка 1: API endpoint
        token = await self._fetch_token_via_api()
        if token:
            return token
        
        # Попытка 2: Artisan команда
        token = await self._fetch_token_via_artisan()
        if token:
            return token
        
        logger.error("Failed to obtain token via both API and Artisan command")
        return None
    
    async def _fetch_token_via_api(self) -> Optional[str]:
        """Получить токен через API endpoint."""
        try:
            url = f"{self.api_url}/api/e2e/auth/token"
            payload = {
                "email": self.email,
                "role": self.role
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") == "ok" and "data" in data:
                    token = data["data"].get("token")
                    if token:
                        logger.debug("✓ Token obtained via API endpoint")
                        return token
                    else:
                        logger.warning("API response missing token")
                else:
                    logger.warning(f"API returned error: {data}")
        
        except httpx.HTTPStatusError as e:
            # 429 Rate Limit - это нормально при частых запросах, пробуем Artisan
            if e.response.status_code == 429:
                logger.info(f"API endpoint rate limited (429), will try Artisan fallback")
            else:
                logger.warning(f"API endpoint returned {e.response.status_code}: {e}")
        except httpx.RequestError as e:
            logger.warning(f"Failed to connect to API endpoint: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error fetching token via API: {e}")
        
        return None
    
    async def _fetch_token_via_artisan(self) -> Optional[str]:
        """Получить токен через Artisan команду."""
        try:
            # Пробуем разные варианты запуска команды
            commands = [
                # В Docker контейнере (если есть docker-compose)
                # Пробуем разные пути к docker-compose файлу
                [
                    "docker-compose", "-f", "tests/e2e/docker-compose.e2e.yml",
                    "exec", "-T", "laravel",
                    "php", "artisan", "e2e:auth-bootstrap",
                    "--email", self.email,
                    "--role", self.role
                ],
                [
                    "docker-compose", "-f", "../../tests/e2e/docker-compose.e2e.yml",
                    "exec", "-T", "laravel",
                    "php", "artisan", "e2e:auth-bootstrap",
                    "--email", self.email,
                    "--role", self.role
                ],
                # Локально (если Laravel установлен локально)
                [
                    "php", "artisan", "e2e:auth-bootstrap",
                    "--email", self.email,
                    "--role", self.role
                ]
            ]
            
            for cmd in commands:
                try:
                    # Запускаем команду асинхронно
                    # Пробуем из текущей директории и из корня проекта
                    cwd_options = [
                        os.getcwd(),
                        os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')),
                        os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
                    ]
                    
                    process = None
                    for cwd in cwd_options:
                        try:
                            process = await asyncio.to_thread(
                                subprocess.run,
                                cmd,
                                capture_output=True,
                                text=True,
                                timeout=10.0,
                                cwd=cwd
                            )
                            if process.returncode == 0:
                                break
                        except (FileNotFoundError, subprocess.TimeoutExpired):
                            continue
                    
                    if not process:
                        continue
                    
                    if process.returncode == 0 and process.stdout:
                        token = process.stdout.strip().split('\n')[-1].strip()
                        if token and len(token) > 20:  # Токен должен быть достаточно длинным
                            logger.debug("✓ Token obtained via Artisan command")
                            return token
                    
                    logger.debug(f"Artisan command failed with return code {process.returncode}")
                
                except FileNotFoundError:
                    # Команда не найдена, пробуем следующую
                    continue
                except subprocess.TimeoutExpired:
                    logger.warning(f"Artisan command timed out: {' '.join(cmd)}")
                    continue
                except Exception as e:
                    logger.debug(f"Error running artisan command: {e}")
                    continue
            
            logger.warning("All Artisan command attempts failed")
        
        except Exception as e:
            logger.warning(f"Unexpected error fetching token via Artisan: {e}")
        
        return None
    
    async def handle_401_error(self) -> str:
        """
        Обработать ошибку 401 - обновить токен.
        
        Returns:
            Новый токен
        """
        logger.warning("Received 401 Unauthorized, refreshing token...")
        return await self.get_token(force_refresh=True)
    
    @classmethod
    def reset(cls):
        """Сбросить токен (для тестирования или нового прогона)."""
        cls._token = None
        cls._token_expires_at = None
        logger.debug("AuthClient token reset")
    
    @classmethod
    def get_current_token(cls) -> Optional[str]:
        """Получить текущий токен (синхронно, для отладки)."""
        return cls._token

