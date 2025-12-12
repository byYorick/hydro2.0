"""
WebSocket клиент для работы с Laravel Reverb.
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
        api_token: Optional[str] = None
    ):
        """
        Инициализация WebSocket клиента.
        
        Args:
            ws_url: URL WebSocket сервера
            api_token: Токен аутентификации
        """
        self.ws_url = ws_url
        self.api_token = api_token
        self.socket_id: Optional[str] = None
        self.ws: Optional[WebSocketClientProtocol] = None
        self.connected = False
        self._message_queue: List[Dict[str, Any]] = []
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._subscribed_channels: List[str] = []
        self._receive_task: Optional[asyncio.Task] = None
    
    async def connect(self):
        """Подключиться к WebSocket серверу."""
        if self.connected:
            return
        
        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        
        try:
            # Формируем правильный URL для Laravel Reverb
            # Формат: ws://host:port/app/{app_id}?protocol=7&client=python&version=1.0
            if "/app/" not in self.ws_url:
                # Если URL не содержит /app/, добавляем его
                base_url = self.ws_url.rstrip("/")
                if not base_url.endswith("/app/local"):
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
        
        Args:
            channel: Имя канала (например, "private-commands.1" или "private-events.global")
        """
        if not self.connected or not self.ws:
            raise RuntimeError("WebSocket not connected")

        data: Dict[str, Any] = {"channel": channel}

        # Private channels требуют auth подписи через /broadcasting/auth
        if channel.startswith("private-"):
            if not self.api_token:
                raise RuntimeError("api_token is required to subscribe to private channels")
            if not self.socket_id:
                raise RuntimeError("socket_id is not available (connection_established missing)")

            laravel_url = os.getenv("LARAVEL_URL", "http://localhost:8081").rstrip("/")
            auth_url = f"{laravel_url}/broadcasting/auth"

            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    auth_url,
                    headers={
                        "Authorization": f"Bearer {self.api_token}",
                        "Accept": "application/json",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    data={"socket_id": self.socket_id, "channel_name": channel},
                )
            resp.raise_for_status()
            auth_payload = resp.json()
            if "auth" not in auth_payload:
                raise RuntimeError(f"broadcasting/auth missing 'auth' field: {auth_payload}")
            data["auth"] = auth_payload["auth"]

        # Формат подписки для Laravel Reverb/Pusher
        subscribe_message = {"event": "pusher:subscribe", "data": data}
        
        await self.ws.send(json.dumps(subscribe_message))
        self._subscribed_channels.append(channel)
        logger.info(f"Subscribed to channel: {channel}")
    
    async def wait_event(
        self,
        event_type: str,
        timeout: float = 10.0,
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Ожидать событие определенного типа.
        
        Args:
            event_type: Тип события для ожидания
            timeout: Таймаут ожидания в секундах
            condition: Дополнительное условие для фильтрации событий
            
        Returns:
            Данные события или None при таймауте
        """
        import time
        start_time = time.time()
        
        while True:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning(f"Timeout waiting for event: {event_type}")
                return None
            
            # Проверяем очередь сообщений
            for msg in self._message_queue:
                data = msg["data"]
                msg_event = data.get("event", data.get("type"))
                
                if msg_event == event_type:
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

