# Авторизация в E2E тестах

## Обзор

E2E тесты используют единую систему авторизации для API и WebSocket:
- **Единый источник истины**: Sanctum Personal Access Tokens (PAT)
- **Автоматическое управление**: `AuthClient` получает, кеширует и обновляет токены
- **Прозрачная интеграция**: Сценарии не знают о токенах (token-agnostic)

## Архитектура

### Компоненты

1. **AuthClient** (`tests/e2e/runner/auth_client.py`)
   - Получает токен через API endpoint или Artisan команду
   - Кеширует токен на время выполнения теста
   - Автоматически обновляет токен при истечении
   - Обрабатывает ошибки 401

2. **APIClient** (`tests/e2e/runner/api_client.py`)
   - Автоматически добавляет `Authorization: Bearer <token>` к каждому запросу
   - При 401 обновляет токен через `AuthClient` и повторяет запрос
   - Выбрасывает `AuthenticationError` если повторный запрос тоже 401

3. **WSClient** (`tests/e2e/runner/ws_client.py`)
   - Использует токен из `AuthClient` при подключении
   - Автоматически вызывает `/broadcasting/auth` для приватных каналов
   - Проверяет успешную авторизацию канала

4. **E2ERunner** (`tests/e2e/runner/e2e_runner.py`)
   - Инициализирует `AuthClient` в начале прогона
   - Передает `AuthClient` в `APIClient` и `WSClient`
   - Обрабатывает `AuthenticationError` как ошибку теста

## Получение токена

### Метод 1: API Endpoint (предпочтительно)

```
POST /api/e2e/auth/token
Content-Type: application/json

{
  "email": "e2e@test.local",
  "role": "admin"
}

Response:
{
  "status": "ok",
  "data": {
    "token": "...",
    "user": {...}
  }
}
```

**Доступен только в:** `testing`, `e2e`, `local` окружениях.

### Метод 2: Artisan Command

```bash
php artisan e2e:auth-bootstrap [--email=email] [--role=role]
```

Выводит токен в stdout.

### Автоматический выбор

`AuthClient` автоматически выбирает метод:
1. Сначала пытается API endpoint
2. Если не удалось → использует Artisan команду

## Использование в сценариях

### API запросы

Токен добавляется автоматически, сценарий ничего не знает о токенах:

```yaml
steps:
  - name: Get zones
    api.get:
      path: /api/zones
      save: zones
```

### WebSocket подключение и подписка

```yaml
steps:
  - name: Connect to WebSocket
    ws.connect:
      # Токен используется автоматически

  - name: Subscribe to private channel
    ws.subscribe:
      channel: private-hydro.zones.${zone_id}
      # Автоматически вызывает /broadcasting/auth с токеном
```

## Обработка ошибок

### API: 401 → автоматический re-auth

При получении 401:
1. `APIClient` вызывает `auth_client.handle_401_error()`
2. `AuthClient` получает новый токен
3. `APIClient` повторяет запрос с новым токеном
4. Если снова 401 → выбрасывается `AuthenticationError` → тест падает

### WebSocket: ошибка авторизации канала

При подписке на приватный канал без токена:
- `RuntimeError` с понятным сообщением
- Тест падает с описанием проблемы

## E2E сценарии авторизации

### E2E_AUTH_01_valid_token

Проверяет работу валидного токена:
- Получение токена через AuthClient
- Вызов защищённого API endpoint
- Подключение к WebSocket
- Подписка на приватный канал
- Получение WebSocket события

**DoD**: все шаги проходят успешно.

### E2E_AUTH_02_expired_token

Проверяет автоматическое обновление токена:
- Устанавливается невалидный токен
- API возвращает 401
- `APIClient` автоматически обновляет токен
- Повторный запрос проходит успешно

**DoD**: re-auth происходит автоматически, тест проходит.

### E2E_AUTH_03_ws_forbidden

Проверяет защиту приватных каналов:
- Создается `WSClient` без токена
- Попытка подписки на приватный канал
- Ожидается `RuntimeError` с понятным сообщением

**DoD**: тест падает с понятной ошибкой.

## Запреты

### ❌ Нельзя отключать middleware ради тестов

Все middleware должны работать в тестах так же, как в продакшене.

### ❌ Нельзя использовать APP_DEBUG как auth-bypass

`APP_DEBUG` не влияет на авторизацию.

### ❌ Нельзя хардкодить токены

Все токены получаются динамически через `AuthClient`.

### ❌ Нельзя иметь разные auth-механизмы для API и WS

Оба используют один источник истины: Sanctum PAT токены.

## Проверка системы

При внесении изменений в auth-логику обязательно:

1. **Проверить единообразие**:
   - API и WS используют одни и те же токены
   - Оба используют `AuthClient`
   - Оба обрабатывают 401 одинаково

2. **Проверить отсутствие bypass'ов**:
   - Нет отключенных middleware для тестов
   - Нет `APP_DEBUG` проверок в auth-логике
   - Нет environment-based bypass'ов

3. **Запустить E2E_AUTH_* сценарии**:
   - E2E_AUTH_01 должен быть зелёным
   - E2E_AUTH_02 должен быть зелёным
   - E2E_AUTH_03 должен быть зелёным (падает как ожидается)

## Troubleshooting

### Ошибка: "Failed to obtain token"

**Причина**: Не удалось получить токен ни через API, ни через Artisan.

**Решение**:
1. Проверьте что Laravel запущен
2. Проверьте что `APP_ENV=e2e` или `APP_ENV=testing`
3. Проверьте доступность `/api/e2e/auth/token`

### Ошибка: "Authentication failed after token refresh"

**Причина**: После обновления токена запрос всё ещё возвращает 401.

**Решение**:
1. Проверьте права пользователя
2. Проверьте что токен действительно обновлен
3. Проверьте что middleware не блокируют запрос

### Ошибка: "Failed to authorize channel"

**Причина**: Не удалось авторизовать подписку на приватный канал.

**Решение**:
1. Проверьте что токен валиден
2. Проверьте что пользователь имеет доступ к зоне
3. Проверьте что `/broadcasting/auth` возвращает `auth` поле

## См. также

- [AUTH_SYSTEM.md](../../doc_ai/08_SECURITY_AND_OPS/AUTH_SYSTEM.md) - Архитектура авторизации
- [AUTH_CLIENT.md](../../tests/e2e/runner/AUTH_CLIENT.md) - Документация AuthClient
- [API_CLIENT_AUTH.md](../../tests/e2e/runner/API_CLIENT_AUTH.md) - Авторизация в APIClient
- [WS_AUTH.md](../../tests/e2e/runner/WS_AUTH.md) - Авторизация в WSClient
