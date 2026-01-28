# API Client - Автоматическая инъекция авторизации

## ✅ Статус: Реализовано

`APIClient` полностью реализует автоматическую инъекцию авторизации согласно требованиям.

## Требования (DoD)

✅ **Все запросы автоматически добавляют `Authorization: Bearer <token>`**  
✅ **При 401: refresh token и повторить запрос**  
✅ **Если снова 401 → FAIL теста**  
✅ **Сценарии не знают о токенах вообще**

## Реализация

### 1. Автоматическое добавление заголовка Authorization

Все HTTP методы (`get`, `post`, `put`, `delete`, `request`, `patch`) автоматически вызывают `_get_headers()`, который:

```python
async def _get_headers(self) -> Dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Используем AuthClient для получения токена
    if self.auth_client:
        token = await self.auth_client.get_token()
        headers.update(self.auth_client.get_auth_headers(token))
    
    return headers
```

**Результат:** Все запросы автоматически получают заголовок `Authorization: Bearer <token>`.

### 2. Обработка 401 с retry

При получении 401:

```python
if response.status_code == 401:
    if self.auth_client:
        logger.warning(f"Request returned 401, refreshing token and retrying...")
        await self.auth_client.handle_401_error()  # Обновить токен
        headers = await self._get_headers()  # Получить новый токен
        response = await self.client.request(...)  # Повторить запрос
```

**Результат:** Токен автоматически обновляется, запрос повторяется с новым токеном.

### 3. FAIL теста при повторной 401

Если после обновления токена снова получен 401:

```python
if response.status_code == 401:
    raise AuthenticationError(
        f"Authentication failed after token refresh. "
        f"{method} {url} returned 401 even with refreshed token. "
        f"Check if user has proper permissions or token is valid."
    )
```

**Результат:** Тест падает с понятным сообщением об ошибке.

### 4. Сценарии не знают о токенах

Проверено: в YAML сценариях нет упоминаний токенов. Все сценарии используют только:

```yaml
steps:
  - name: Get zones
    api.get:
      path: /api/zones
      save: zones
```

Токены полностью скрыты от сценариев.

## Примеры использования

### В сценариях

```yaml
steps:
  - name: Get zones
    api.get:
      path: /api/zones
      save: zones
  
  - name: Create zone
    api.post:
      path: /api/zones
      json:
        name: "Test Zone"
      save: zone
```

**Никаких токенов не требуется!**

### Программно

```python
from runner.api_client import APIClient
from runner.auth_client import AuthClient

auth = AuthClient(api_url="http://localhost:8081")
api = APIClient(
    base_url="http://localhost:8081",
    auth_client=auth
)

# Токен добавляется автоматически
zones = await api.get("/api/zones")

# При 401 автоматически обновляется и повторяется
# Если снова 401 → выбрасывается AuthenticationError
```

## Обработка ошибок

### AuthenticationError

Исключение выбрасывается когда:
- После обновления токена запрос снова вернул 401
- Это означает проблему с правами доступа или валидностью токена

**Обработка в E2ERunner:**
- `AuthenticationError` пробрасывается как обычное исключение
- Тест падает с понятным сообщением

## Логирование

Все операции логируются:

```
[API_CLIENT] GET /api/zones
GET /api/zones returned 401, refreshing token and retrying...
✓ Token obtained via AuthClient
[API_CLIENT] GET /api/zones
```

Если после refresh снова 401:
```
AuthenticationError: Authentication failed after token refresh. 
GET /api/zones returned 401 even with refreshed token. 
Check if user has proper permissions or token is valid.
```

## Поддерживаемые методы

Все HTTP методы поддерживают автоматическую авторизацию:
- ✅ `get(path, params)`
- ✅ `post(path, json, data)`
- ✅ `put(path, json, data)`
- ✅ `delete(path)`
- ✅ `patch(path, json, data)`
- ✅ `request(method, path, ...)`

## Проверка реализации

```bash
# Проверка синтаксиса
python3 -m py_compile runner/api_client.py

# Проверка что сценарии не содержат токенов
grep -r "token\|Token\|TOKEN" scenarios/*.yaml
# Результат: нет упоминаний (кроме комментариев в README)
```

## См. также

- [AUTH_CLIENT.md](AUTH_CLIENT.md) - Документация AuthClient
- [AUTHCLIENT_INTEGRATION.md](../AUTHCLIENT_INTEGRATION.md) - Интеграция в E2E тесты

