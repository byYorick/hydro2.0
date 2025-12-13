"""
API клиент для выполнения HTTP запросов к Laravel API.

Автоматически добавляет Authorization заголовок ко всем запросам.
При 401 автоматически обновляет токен и повторяет запрос.
Если после обновления токена снова 401 → тест FAIL.
"""

import httpx
import logging
from typing import Dict, Any, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Исключение при ошибке аутентификации после обновления токена."""
    pass


class APIClient:
    """Клиент для работы с REST API."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_token: Optional[str] = None,
        timeout: float = 30.0,
        auth_client: Optional[Any] = None
    ):
        """
        Инициализация API клиента.
        
        Args:
            base_url: Базовый URL API
            api_token: Токен аутентификации (Bearer token) - используется только если auth_client не указан
            timeout: Таймаут запросов в секундах
            auth_client: Экземпляр AuthClient для автоматического управления токенами
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token  # Устаревший способ, используется только если auth_client не указан
        self.auth_client = auth_client
        self.timeout = timeout
        # Создаем клиент БЕЗ заголовков, чтобы добавлять их динамически
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout
        )
        self._last_response: Optional[httpx.Response] = None
    
    async def _get_headers(self) -> Dict[str, str]:
        """Получить заголовки для запросов."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Используем AuthClient если доступен (приоритет)
        if self.auth_client:
            try:
                token = await self.auth_client.get_token()
                headers.update(self.auth_client.get_auth_headers(token))
                logger.debug(f"API Client: Using token from AuthClient (length: {len(token)})")
            except Exception as e:
                logger.warning(f"Failed to get token from AuthClient: {e}, falling back to api_token")
                if self.api_token:
                    headers["Authorization"] = f"Bearer {self.api_token}"
        elif self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
            logger.debug(f"API Client: Using Authorization header with token (length: {len(self.api_token)})")
        else:
            logger.warning("API Client: No api_token or auth_client provided, requests may fail with 401 Unauthorized")
        
        return headers
    
    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Выполнить GET запрос.
        
        Автоматически добавляет Authorization заголовок.
        При 401 обновляет токен и повторяет запрос.
        Если после обновления снова 401 → выбрасывает AuthenticationError.
        
        Args:
            path: Путь относительно base_url
            params: Query параметры
            
        Returns:
            JSON ответ как словарь
            
        Raises:
            AuthenticationError: Если после обновления токена снова получен 401
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        headers = await self._get_headers()
        logger.debug(f"[API_CLIENT] GET {url}")
        
        response = await self.client.get(url, params=params, headers=headers)
        self._last_response = response
        
        # Обработка 401 - автоматический re-auth с повторным запросом
        if response.status_code == 401:
            if self.auth_client:
                logger.warning(f"GET {url} returned 401, refreshing token and retrying...")
                await self.auth_client.handle_401_error()
                headers = await self._get_headers()
                response = await self.client.get(url, params=params, headers=headers)
                self._last_response = response
                
                # Если после обновления токена снова 401 → FAIL теста
                if response.status_code == 401:
                    raise AuthenticationError(
                        f"Authentication failed after token refresh. "
                        f"GET {url} returned 401 even with refreshed token. "
                        f"Check if user has proper permissions or token is valid."
                    )
            else:
                # Нет auth_client, не можем обновить токен
                response.raise_for_status()
        
        response.raise_for_status()
        
        return response.json()
    
    async def post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Выполнить POST запрос.
        
        Автоматически добавляет Authorization заголовок.
        При 401 обновляет токен и повторяет запрос.
        Если после обновления снова 401 → выбрасывает AuthenticationError.
        
        Args:
            path: Путь относительно base_url
            data: Form data
            json: JSON данные
            
        Returns:
            JSON ответ как словарь
            
        Raises:
            AuthenticationError: Если после обновления токена снова получен 401
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        headers = await self._get_headers()
        logger.debug(f"[API_CLIENT] POST {url}")
        
        response = await self.client.post(url, json=json, data=data, headers=headers)
        self._last_response = response
        
        # Обработка 401 - автоматический re-auth с повторным запросом
        if response.status_code == 401:
            if self.auth_client:
                logger.warning(f"POST {url} returned 401, refreshing token and retrying...")
                await self.auth_client.handle_401_error()
                headers = await self._get_headers()
                response = await self.client.post(url, json=json, data=data, headers=headers)
                self._last_response = response
                
                # Если после обновления токена снова 401 → FAIL теста
                if response.status_code == 401:
                    raise AuthenticationError(
                        f"Authentication failed after token refresh. "
                        f"POST {url} returned 401 even with refreshed token. "
                        f"Check if user has proper permissions or token is valid."
                    )
            else:
                # Нет auth_client, не можем обновить токен
                response.raise_for_status()
        
        response.raise_for_status()
        
        return response.json()
    
    async def put(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Выполнить PUT запрос.
        
        Автоматически добавляет Authorization заголовок.
        При 401 обновляет токен и повторяет запрос.
        Если после обновления снова 401 → выбрасывает AuthenticationError.
        
        Args:
            path: Путь относительно base_url
            data: Form data
            json: JSON данные
            
        Returns:
            JSON ответ как словарь
            
        Raises:
            AuthenticationError: Если после обновления токена снова получен 401
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        headers = await self._get_headers()
        logger.debug(f"[API_CLIENT] PUT {url}")
        
        response = await self.client.put(url, json=json, data=data, headers=headers)
        self._last_response = response
        
        # Обработка 401 - автоматический re-auth с повторным запросом
        if response.status_code == 401:
            if self.auth_client:
                logger.warning(f"PUT {url} returned 401, refreshing token and retrying...")
                await self.auth_client.handle_401_error()
                headers = await self._get_headers()
                response = await self.client.put(url, json=json, data=data, headers=headers)
                self._last_response = response
                
                # Если после обновления токена снова 401 → FAIL теста
                if response.status_code == 401:
                    raise AuthenticationError(
                        f"Authentication failed after token refresh. "
                        f"PUT {url} returned 401 even with refreshed token. "
                        f"Check if user has proper permissions or token is valid."
                    )
            else:
                # Нет auth_client, не можем обновить токен
                response.raise_for_status()
        
        response.raise_for_status()
        
        return response.json()
    
    async def delete(self, path: str) -> Dict[str, Any]:
        """
        Выполнить DELETE запрос.
        
        Автоматически добавляет Authorization заголовок.
        При 401 обновляет токен и повторяет запрос.
        Если после обновления снова 401 → выбрасывает AuthenticationError.
        
        Args:
            path: Путь относительно base_url
            
        Returns:
            JSON ответ как словарь
            
        Raises:
            AuthenticationError: Если после обновления токена снова получен 401
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        headers = await self._get_headers()
        logger.debug(f"[API_CLIENT] DELETE {url}")
        
        response = await self.client.delete(url, headers=headers)
        self._last_response = response
        
        # Обработка 401 - автоматический re-auth с повторным запросом
        if response.status_code == 401:
            if self.auth_client:
                logger.warning(f"DELETE {url} returned 401, refreshing token and retrying...")
                await self.auth_client.handle_401_error()
                headers = await self._get_headers()
                response = await self.client.delete(url, headers=headers)
                self._last_response = response
                
                # Если после обновления токена снова 401 → FAIL теста
                if response.status_code == 401:
                    raise AuthenticationError(
                        f"Authentication failed after token refresh. "
                        f"DELETE {url} returned 401 even with refreshed token. "
                        f"Check if user has proper permissions or token is valid."
                    )
            else:
                # Нет auth_client, не можем обновить токен
                response.raise_for_status()
        
        response.raise_for_status()
        
        return response.json() if response.content else {}

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Выполнить произвольный HTTP запрос.
        Полезно для PATCH и нестандартных методов.
        
        Автоматически добавляет Authorization заголовок.
        При 401 обновляет токен и повторяет запрос.
        Если после обновления снова 401 → выбрасывает AuthenticationError.
        
        Args:
            method: HTTP метод (GET, POST, PUT, DELETE, PATCH, etc.)
            path: Путь относительно base_url
            params: Query параметры
            json: JSON данные
            data: Form data
            
        Returns:
            JSON ответ как словарь
            
        Raises:
            AuthenticationError: Если после обновления токена снова получен 401
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        method = method.upper()
        headers = await self._get_headers()
        logger.debug(f"[API_CLIENT] {method} {url}")
        
        response = await self.client.request(method, url, params=params, json=json, data=data, headers=headers)
        self._last_response = response
        
        # Обработка 401 - автоматический re-auth с повторным запросом
        if response.status_code == 401:
            if self.auth_client:
                logger.warning(f"{method} {url} returned 401, refreshing token and retrying...")
                await self.auth_client.handle_401_error()
                headers = await self._get_headers()
                response = await self.client.request(method, url, params=params, json=json, data=data, headers=headers)
                self._last_response = response
                
                # Если после обновления токена снова 401 → FAIL теста
                if response.status_code == 401:
                    raise AuthenticationError(
                        f"Authentication failed after token refresh. "
                        f"{method} {url} returned 401 even with refreshed token. "
                        f"Check if user has proper permissions or token is valid."
                    )
            else:
                # Нет auth_client, не можем обновить токен
                response.raise_for_status()
        
        response.raise_for_status()
        return response.json() if response.content else {}

    async def patch(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Выполнить PATCH запрос."""
        return await self.request("PATCH", path, json=json, data=data)
    
    def get_last_response(self) -> Optional[httpx.Response]:
        """Получить последний HTTP ответ."""
        return self._last_response
    
    async def close(self):
        """Закрыть HTTP клиент."""
        await self.client.aclose()

