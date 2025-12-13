"""
WebSocket клиент для работы с Laravel Reverb.

Автоматически передает токен при подключении и при подписке на приватные каналы.
Проверяет успешную авторизацию каналов через /broadcasting/auth endpoint.
"""

import asyncio
import json
import logging
import os
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


class WSClient:
    """Клиент для работы с WebSocket (Laravel Reverb)."""
    
    def __init__(
        self,
        ws_url: str = "ws://localhost:6001",
        api_token: Optional[str] = None,
        auth_client: Optional[Any] = None,
        api_url: Optional[str] = None
    ):
        """
        Инициализация WebSocket клиента.
        
        Args:
            ws_url: URL WebSocket сервера
            api_token: Токен аутентификации (используется только если auth_client не указан)
            auth_client: Экземпляр AuthClient для автоматического управления токенами
            api_url: URL API для /broadcasting/auth (по умолчанию из LARAVEL_URL)
        """
        self.ws_url = ws_url
        self.api_token = api_token  # Устаревший способ
        self.auth_client = auth_client
        self.api_url = api_url or os.getenv("LARAVEL_URL", "http://localhost:8081").rstrip("/")
        self.socket_id: Optional[str] = None
        self.ws: Optional[WebSocketClientProtocol] = None
        self.connected = False
        self._message_queue: List[Dict[str, Any]] = []
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._subscribed_channels: List[str] = []
        self._receive_task: Optional[asyncio.Task] = None
    
    async def connect(self):
        """
        Подключиться к WebSocket серверу.
        
        Автоматически передает токен в заголовках Authorization для аутентификации.
        """
        if self.connected:
            return
        
        # Получаем токен через AuthClient если доступен, иначе используем api_token
        token = None
        headers = {}
        
        if self.auth_client:
            try:
                token = await self.auth_client.get_token()
                headers["Authorization"] = f"Bearer {token}"
                logger.debug(f"WS Client: Using token from AuthClient (length: {len(token)})")
            except Exception as e:
                logger.warning(f"Failed to get token from AuthClient: {e}, falling back to api_token")
                if self.api_token:
                    headers["Authorization"] = f"Bearer {self.api_token}"
        elif self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
            logger.debug(f"WS Client: Using provided api_token (length: {len(self.api_token)})")
        else:
            logger.warning("WS Client: No api_token or auth_client provided, connection may fail")
        
        try:
            # Формируем правильный URL для Laravel Reverb
            # Формат: ws://host:port/app/{app_id}?protocol=7&client=python&version=1.0
            if "/app/" not in self.ws_url:
                # Если URL не содержит /app/, добавляем его
                base_url = self.ws_url.rstrip("/")
                # Проверяем, что не заканчивается на /app/local (учитывая возможные query параметры)
                parsed_url = self.ws_url.split("?")[0]  # Убираем query параметры для проверки
                if not parsed_url.rstrip("/").endswith("/app/local"):
                    self.ws_url = f"{base_url}/app/local?protocol=7&client=python&version=1.0&flash=false"
            
            # websockets<15 использует extra_headers, websockets>=15 использует additional_headers
            try:
                self.ws = await websockets.connect(
                    self.ws_url,
                    additional_headers=headers
                )
            except TypeError:
                self.ws = await websockets.connect(
                    self.ws_url,
                    extra_headers=headers
                )
            self.connected = True
            logger.info(f"Connected to WebSocket at {self.ws_url}")

            # Ожидаем connection_established, чтобы получить socket_id
            try:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                data = json.loads(msg)
                if data.get("event") == "pusher:connection_established":
                    payload = json.loads(data.get("data", "{}"))
                    self.socket_id = payload.get("socket_id")
                    logger.info(f"WebSocket socket_id acquired: {self.socket_id}")
                else:
                    # кладем обратно в очередь как обычное сообщение
                    self._message_queue.append({"data": data, "timestamp": datetime.now().isoformat()})
            except Exception as e:
                logger.warning(f"Failed to read connection_established: {e}")
            
            # Запускаем задачу для приема сообщений
            self._receive_task = asyncio.create_task(self._receive_messages())
            
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            raise
    
    async def disconnect(self):
        """Отключиться от WebSocket сервера."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self.ws:
            await self.ws.close()
            self.connected = False
            logger.info("Disconnected from WebSocket")
    
    async def _receive_messages(self):
        """Принимать сообщения от WebSocket сервера."""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    self._message_queue.append({
                        "data": data,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    # Вызываем обработчики событий
                    event_type = data.get("event", data.get("type"))
                    if event_type and event_type in self._event_handlers:
                        for handler in self._event_handlers[event_type]:
                            try:
                                await handler(data)
                            except Exception as e:
                                logger.error(f"Error in event handler: {e}")
                    
                    # Логируем все события для отладки
                    event_name = data.get("event", data.get("type"))
                    if event_name and ("Command" in event_name or "command" in event_name.lower()):
                        logger.info(f"Received WebSocket message with command event: {event_name}, full data: {json.dumps(data, indent=2)}")
                    else:
                        logger.debug(f"Received WebSocket message: {data}")
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse WebSocket message: {message}")
        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection closed")
            self.connected = False
        except Exception as e:
            logger.error(f"Error receiving WebSocket messages: {e}")
            self.connected = False
    
    async def subscribe(self, channel: str):
        """
        Подписаться на канал.
        
        Для приватных каналов автоматически вызывает /broadcasting/auth для авторизации.
        Проверяет успешную авторизацию перед подпиской.
        
        Args:
            channel: Имя канала (например, "private-commands.1" или "private-events.global")
            
        Raises:
            RuntimeError: Если WebSocket не подключен, нет токена, или авторизация не удалась
        """
        if not self.connected or not self.ws:
            raise RuntimeError("WebSocket not connected")

        data: Dict[str, Any] = {"channel": channel}

        # Private channels требуют auth подписи через /broadcasting/auth
        if channel.startswith("private-"):
            # Получаем токен через AuthClient если доступен
            token = None
            if self.auth_client:
                try:
                    token = await self.auth_client.get_token()
                except Exception as e:
                    logger.error(f"Failed to get token from AuthClient: {e}")
                    raise RuntimeError(f"Cannot subscribe to private channel: failed to get token") from e
            elif self.api_token:
                token = self.api_token
            else:
                raise RuntimeError("api_token or auth_client is required to subscribe to private channels")
            
            if not self.socket_id:
                raise RuntimeError("socket_id is not available (connection_established missing)")

            # Вызываем /broadcasting/auth для авторизации канала
            auth_url = f"{self.api_url}/broadcasting/auth"

            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    auth_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    data={"socket_id": self.socket_id, "channel_name": channel},
                )
            
            # Проверяем успешную авторизацию
            if resp.status_code == 401 or resp.status_code == 403:
                error_msg = resp.json().get("message", "Unauthenticated")
                raise RuntimeError(
                    f"Failed to authorize channel '{channel}': {error_msg} "
                    f"(status {resp.status_code}). Check if token is valid and user has permissions."
                )
            
            resp.raise_for_status()
            auth_payload = resp.json()
            
            # Проверяем наличие поля 'auth' в ответе
            if "auth" not in auth_payload:
                raise RuntimeError(
                    f"broadcasting/auth response missing 'auth' field: {auth_payload}. "
                    f"Channel authorization failed."
                )
            
            data["auth"] = auth_payload["auth"]
            logger.debug(f"Channel '{channel}' authorized successfully")

        # Формат подписки для Laravel Reverb/Pusher
        subscribe_message = {"event": "pusher:subscribe", "data": data}
        
        await self.ws.send(json.dumps(subscribe_message))
        
        # Ожидаем подтверждение подписки (pusher_internal:subscription_succeeded)
        # Это подтверждает успешную подписку на канал
        confirmation_received = False
        try:
            confirmation = await asyncio.wait_for(
                self._wait_subscription_confirmation(channel),
                timeout=5.0
            )
            if confirmation:
                confirmation_received = True
                logger.info(f"✓ Subscribed to channel: {channel} (confirmation received)")
            else:
                logger.warning(f"Subscribed to channel: {channel} (no confirmation received)")
        except asyncio.TimeoutError:
            logger.warning(f"Subscribed to channel: {channel} (confirmation timeout)")
        except Exception as e:
            logger.warning(f"Error waiting for subscription confirmation: {e}")
        
        self._subscribed_channels.append(channel)
        if not confirmation_received:
            logger.info(f"Subscribed to channel: {channel}")
    
    async def wait_event(
        self,
        event_type: str,
        timeout: float = 10.0,
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
        filter: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Ожидать событие определенного типа.
        
        Args:
            event_type: Тип события для ожидания
            timeout: Таймаут ожидания в секундах
            condition: Дополнительное условие для фильтрации событий
            filter: Словарь для фильтрации по полям (например, {"status": "ACCEPTED"})
            
        Returns:
            Данные события или None при таймауте
        """
        import time
        start_time = time.time()
        
        # Нормализуем имя события (может быть полным классом или коротким именем)
        event_type_normalized = event_type
        if "." in event_type:
            # Если полное имя класса, извлекаем короткое имя
            event_type_normalized = event_type.split("\\")[-1]
        
        while True:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning(f"Timeout waiting for event: {event_type}")
                # Логируем последние сообщения для отладки
                recent_messages = self._message_queue[-10:]
                logger.debug(f"Recent messages: {[msg.get('data', {}).get('event') for msg in recent_messages]}")
                return None
            
            # Проверяем очередь сообщений
            for msg in self._message_queue:
                data = msg["data"]
                msg_event = data.get("event", data.get("type"))
                
                # Логируем все события для отладки
                if msg_event and (event_type.lower() in msg_event.lower() or msg_event.lower() in event_type.lower()):
                    logger.debug(f"Found potential event match: {msg_event} vs {event_type}, data: {data}")
                
                # Проверяем полное имя или короткое имя
                msg_event_normalized = msg_event
                if msg_event and ("\\" in msg_event or "." in msg_event):
                    # Извлекаем короткое имя из полного класса
                    parts = msg_event.replace("\\", ".").split(".")
                    msg_event_normalized = parts[-1] if parts else msg_event
                
                if msg_event == event_type or msg_event_normalized == event_type_normalized:
                    # Проверяем фильтр, если указан
                    if filter:
                        event_data_raw = data.get("data", {})
                        # Если data - строка JSON, парсим её
                        if isinstance(event_data_raw, str):
                            try:
                                event_data = json.loads(event_data_raw)
                            except (json.JSONDecodeError, TypeError):
                                event_data = {}
                        else:
                            event_data = event_data_raw if isinstance(event_data_raw, dict) else {}
                        
                        match = True
                        for key, value in filter.items():
                            if isinstance(value, list):
                                # Если значение - список, проверяем, что поле в списке
                                if event_data.get(key) not in value:
                                    match = False
                                    break
                            else:
                                if event_data.get(key) != value:
                                    match = False
                                    break
                        if not match:
                            continue
                    
                    if condition is None or condition(data):
                        return data
            
            await asyncio.sleep(0.1)
    
    def get_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Получить последние сообщения.
        
        Args:
            limit: Максимальное количество сообщений
            
        Returns:
            Список последних сообщений
        """
        return self._message_queue[-limit:]
    
    def clear_messages(self):
        """Очистить очередь сообщений."""
        self._message_queue.clear()
    
    async def _wait_subscription_confirmation(self, channel: str) -> bool:
        """
        Ожидать подтверждение подписки на канал.
        
        Args:
            channel: Имя канала
            
        Returns:
            True если получено подтверждение, False иначе
        """
        # Проверяем последние сообщения для подтверждения подписки
        for msg in list(self._message_queue):
            data = msg.get("data", {})
            event = data.get("event", "")
            event_channel = data.get("channel", "")
            
            # pusher_internal:subscription_succeeded означает успешную подписку
            if event == "pusher_internal:subscription_succeeded" and event_channel == channel:
                logger.debug(f"Received subscription confirmation for channel: {channel}")
                return True
        
        # Если в очереди нет, ждем новое сообщение
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < 5.0:
            # Проверяем новые сообщения
            for msg in list(self._message_queue):
                data = msg.get("data", {})
                event = data.get("event", "")
                event_channel = data.get("channel", "")
                
                if event == "pusher_internal:subscription_succeeded" and event_channel == channel:
                    logger.debug(f"Received subscription confirmation for channel: {channel}")
                    return True
            
            await asyncio.sleep(0.1)
        
        return False

