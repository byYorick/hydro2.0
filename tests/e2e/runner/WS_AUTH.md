# WebSocket Authorization - Авторизация WebSocket

## ✅ Статус: Реализовано

`WSClient` полностью реализует авторизацию WebSocket согласно требованиям.

## Требования (DoD)

✅ **Endpoint авторизации WS: POST /broadcasting/auth**  
✅ **Передача токена через headers (Authorization: Bearer)**  
✅ **Токен передаётся при connect**  
✅ **Проверяется успешная авторизация канала**  
✅ **WS получает события CommandStatusUpdated, AlertCreated, ZoneEventCreated**

## Реализация

### 1. Endpoint авторизации

**POST /broadcasting/auth**

Поддерживает:
- Токен через заголовок `Authorization: Bearer <token>` (Sanctum PAT)
- Сессионная авторизация (web guard) как fallback

**Параметры запроса:**
- `socket_id`: ID WebSocket соединения
- `channel_name`: Имя канала для авторизации (например, `private-commands.1`)

**Ответ:**
```json
{
  "auth": "local:abc123..."
}
```

### 2. Передача токена при connect

При подключении к WebSocket токен автоматически передается в заголовках:

```python
# В методе connect()
if self.auth_client:
    token = await self.auth_client.get_token()
    headers["Authorization"] = f"Bearer {token}"
```

### 3. Авторизация приватных каналов

При подписке на приватные каналы (начинаются с `private-`):

```python
async def subscribe(self, channel: str):
    if channel.startswith("private-"):
        # Получаем токен через AuthClient
        token = await self.auth_client.get_token()
        
        # Вызываем /broadcasting/auth
        resp = await client.post(
            f"{api_url}/broadcasting/auth",
            headers={"Authorization": f"Bearer {token}"},
            data={"socket_id": self.socket_id, "channel_name": channel}
        )
        
        # Проверяем успешную авторизацию
        if resp.status_code == 401 or resp.status_code == 403:
            raise RuntimeError(f"Failed to authorize channel: {error_msg}")
        
        # Используем auth из ответа
        data["auth"] = resp.json()["auth"]
```

### 4. Проверка успешной авторизации

Проверяется:
- ✅ Статус ответа от `/broadcasting/auth` (не 401/403)
- ✅ Наличие поля `auth` в ответе
- ✅ Получение подтверждения подписки (`pusher_internal:subscription_succeeded`)

## События

WS получает следующие события:

### CommandStatusUpdated
- **Канал:** `private-commands.{zone_id}`
- **Пример:** `private-commands.1`
- **Использование:** E10_command_happy, E13_command_duplicate_response

### AlertCreated
- **Каналы:** 
  - `private-hydro.zones.{zone_id}` 
  - `private-hydro.alerts` (глобальный)
- **Пример:** `private-hydro.zones.1`
- **Использование:** E20_error_to_alert_realtime

### ZoneEventCreated / ZoneUpdated
- **Канал:** `private-hydro.zones.{zone_id}`
- **Пример:** `private-hydro.zones.1`
- **Использование:** E20_error_to_alert_realtime, E31_reconnect_replay_gap

## Интеграция с AuthClient

`WSClient` интегрирован с `AuthClient`:

```python
auth = AuthClient(api_url="http://localhost:8081")
ws = WSClient(
    ws_url="ws://localhost:6002/app/local",
    auth_client=auth,  # Автоматическое управление токенами
    api_url="http://localhost:8081"
)
```

Токен получается автоматически через `AuthClient` при:
- Подключении к WebSocket
- Подписке на приватные каналы

## Использование

### В сценариях

```yaml
steps:
  - name: Subscribe to command channel
    ws.subscribe:
      channel: private-commands.${test_zone_id}
  
  - name: Subscribe to zone channel
    ws.subscribe:
      channel: private-hydro.zones.${test_zone_id}
  
  - name: Wait for command status update
    ws.wait_event:
      event: ".App\\Events\\CommandStatusUpdated"
      timeout: 15.0
```

**Никаких токенов в сценариях не требуется!**

### Программно

```python
from runner.ws_client import WSClient
from runner.auth_client import AuthClient

auth = AuthClient(api_url="http://localhost:8081")
ws = WSClient(
    ws_url="ws://localhost:6002/app/local",
    auth_client=auth,
    api_url="http://localhost:8081"
)

await ws.connect()
await ws.subscribe("private-commands.1")
event = await ws.wait_event(".App\\Events\\CommandStatusUpdated", timeout=10.0)
```

## Проверка авторизации

### Успешная авторизация

```
✓ Channel 'private-commands.1' authorized successfully
✓ Subscribed to channel: private-commands.1 (confirmation received)
```

### Ошибка авторизации

```
RuntimeError: Failed to authorize channel 'private-commands.1': Unauthenticated 
(status 401). Check if token is valid and user has permissions.
```

## Каналы

### Командные каналы
- `private-commands.{zone_id}` - события команд для зоны
- `private-commands.global` - глобальные события команд

### Каналы зон
- `private-hydro.zones.{zone_id}` - все события зоны (команды, алерты, обновления)

### Каналы алертов
- `private-hydro.alerts` - глобальные события алертов

## См. также

- [AUTH_CLIENT.md](AUTH_CLIENT.md) - Документация AuthClient
- [API_CLIENT_AUTH.md](API_CLIENT_AUTH.md) - Авторизация API
