"""
API клиент для выполнения HTTP запросов к Laravel API.
"""

import httpx
import logging
from typing import Dict, Any, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class APIClient:
    """Клиент для работы с REST API."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_token: Optional[str] = None,
        timeout: float = 30.0
    ):
        """
        Инициализация API клиента.
        
        Args:
            base_url: Базовый URL API
            api_token: Токен аутентификации (Bearer token)
            timeout: Таймаут запросов в секундах
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._get_headers()
        )
        self._last_response: Optional[httpx.Response] = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Получить заголовки для запросов."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers
    
    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Выполнить GET запрос.
        
        Args:
            path: Путь относительно base_url
            params: Query параметры
            
        Returns:
            JSON ответ как словарь
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        logger.debug(f"GET {url} with params: {params}")
        
        response = await self.client.get(url, params=params)
        self._last_response = response
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
        
        Args:
            path: Путь относительно base_url
            data: Form data
            json: JSON данные
            
        Returns:
            JSON ответ как словарь
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        logger.debug(f"POST {url} with json: {json}")
        
        response = await self.client.post(url, json=json, data=data)
        self._last_response = response
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
        
        Args:
            path: Путь относительно base_url
            data: Form data
            json: JSON данные
            
        Returns:
            JSON ответ как словарь
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        logger.debug(f"PUT {url} with json: {json}")
        
        response = await self.client.put(url, json=json, data=data)
        self._last_response = response
        response.raise_for_status()
        
        return response.json()
    
    async def delete(self, path: str) -> Dict[str, Any]:
        """
        Выполнить DELETE запрос.
        
        Args:
            path: Путь относительно base_url
            
        Returns:
            JSON ответ как словарь
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        logger.debug(f"DELETE {url}")
        
        response = await self.client.delete(url)
        self._last_response = response
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
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        method = method.upper()
        logger.debug(f"{method} {url} with json: {json}")
        response = await self.client.request(method, url, params=params, json=json, data=data)
        self._last_response = response
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

