# AuthClient - Автоматическое управление аутентификацией

## Описание

`AuthClient` обеспечивает автоматическое управление токенами аутентификации для E2E тестов.

## Основные возможности

✅ **Токен хранится один на прогон** - Singleton pattern  
✅ **TTL учитывается** - автоматическое обновление при истечении  
✅ **Автоматический re-auth при 401** - прозрачное обновление токена  
✅ **Никакого хардкода токенов** - токены получаются автоматически

## Использование

### Автоматическое (рекомендуется)

`AuthClient` автоматически используется в `E2ERunner`:

```python
from runner.e2e_runner import E2ERunner

runner = E2ERunner({
    "api_url": "http://localhost:8081",
    "auth_email": "e2e@test.local",  # опционально
    "auth_role": "admin"  # опционально
})

await runner.setup()
# Токен автоматически получен через AuthClient
await runner.api.get("/api/zones")
```

### Прямое использование

```python
from runner.auth_client import AuthClient

auth = AuthClient(
    api_url="http://localhost:8081",
    email="e2e@test.local",
    role="admin"
)

# Получить токен
token = await auth.get_token()

# Получить заголовки авторизации
headers = auth.get_auth_headers(token)

# Обновить токен при необходимости
new_token = await auth.refresh_token_if_needed()
```

## Методы

### `get_token(force_refresh: bool = False) -> str`

Получить токен аутентификации. Если токен уже получен и еще валиден, возвращает существующий.

**Параметры:**
- `force_refresh`: Принудительно обновить токен даже если он еще валиден

**Возвращает:** Токен аутентификации

### `refresh_token_if_needed() -> Optional[str]`

Обновить токен, если он истек или скоро истечет (в течение 5 минут).

**Возвращает:** Новый токен или `None`, если обновление не требуется

### `get_auth_headers(token: Optional[str] = None) -> Dict[str, str]`

Получить заголовки авторизации для HTTP запросов.

**Параметры:**
- `token`: Токен (если не указан, используется текущий сохраненный)

**Возвращает:** Словарь с заголовком `Authorization: Bearer <token>`

### `handle_401_error() -> str`

Обработать ошибку 401 - обновить токен.

**Возвращает:** Новый токен

## Получение токена

`AuthClient` пробует получить токен в следующем порядке:

1. **API endpoint** `POST /api/e2e/auth/token`
   - Быстрый способ
   - Требует доступный Laravel API

2. **Artisan команда** `php artisan e2e:auth-bootstrap`
   - Fallback вариант
   - Работает через Docker или локально

## Интеграция с APIClient

`APIClient` автоматически использует `AuthClient`, если он передан при инициализации:

```python
from runner.api_client import APIClient
from runner.auth_client import AuthClient

auth = AuthClient(api_url="http://localhost:8081")
api = APIClient(
    base_url="http://localhost:8081",
    auth_client=auth  # Автоматическое управление токенами
)

# При 401 токен автоматически обновится
await api.get("/api/zones")
```

## TTL токена

По умолчанию TTL токена = 24 часа. Токен автоматически обновляется:
- При истечении
- За 5 минут до истечения
- При получении 401 ошибки

## Singleton Pattern

`AuthClient` использует singleton pattern - один экземпляр на весь прогон тестов. Это гарантирует, что токен не дублируется и используется единообразно.

```python
auth1 = AuthClient()
auth2 = AuthClient()
# auth1 и auth2 - один и тот же экземпляр
```

Для сброса токена (например, перед новым прогоном):

```python
AuthClient.reset()
```

## Примеры

### Базовое использование

```python
import asyncio
from runner.auth_client import AuthClient

async def main():
    auth = AuthClient()
    token = await auth.get_token()
    print(f"Token: {token[:20]}...")

asyncio.run(main())
```

### Использование с APIClient

```python
import asyncio
from runner.api_client import APIClient
from runner.auth_client import AuthClient

async def main():
    auth = AuthClient(api_url="http://localhost:8081")
    api = APIClient(
        base_url="http://localhost:8081",
        auth_client=auth
    )
    
    # Токен автоматически получается и обновляется
    zones = await api.get("/api/zones")
    print(f"Zones: {zones}")

asyncio.run(main())
```

### Ручная обработка 401

```python
import asyncio
from runner.auth_client import AuthClient
import httpx

async def main():
    auth = AuthClient()
    token = await auth.get_token()
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8081/api/zones",
            headers=auth.get_auth_headers(token)
        )
        
        if response.status_code == 401:
            # Автоматическое обновление
            new_token = await auth.handle_401_error()
            response = await client.get(
                "http://localhost:8081/api/zones",
                headers=auth.get_auth_headers(new_token)
            )

asyncio.run(main())
```

## Конфигурация

### Переменные окружения

- `LARAVEL_URL` - URL Laravel API (по умолчанию: `http://localhost:8081`)
- `LARAVEL_API_TOKEN` - Если установлен, используется вместо `AuthClient` (для обратной совместимости)

### Параметры конструктора

- `api_url`: URL API
- `email`: Email пользователя (по умолчанию: `e2e@test.local`)
- `role`: Роль пользователя (по умолчанию: `admin`)
- `token_ttl_seconds`: TTL токена в секундах (по умолчанию: 24 часа)

## Запреты

❌ **Никакого хардкода токенов в сценариях** - все токены получаются автоматически  
❌ **Не использовать прямой доступ к `_token`** - используйте методы API  
❌ **Не создавать несколько экземпляров** - используйте singleton

## См. также

- [E2E_GUIDE.md](../../docs/testing/E2E_GUIDE.md) - Руководство по E2E тестам
- [E2E_AUTH_BOOTSTRAP.md](../../../backend/E2E_AUTH_BOOTSTRAP.md) - E2E Auth Bootstrap

