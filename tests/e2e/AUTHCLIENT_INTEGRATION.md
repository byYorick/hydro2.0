# Интеграция AuthClient в E2E тесты

## ✅ Статус: Внедрено

`AuthClient` полностью интегрирован в E2E тесты и работает автоматически.

## Изменения

### 1. E2ERunner (`tests/e2e/runner/e2e_runner.py`)

**Автоматическое использование AuthClient:**
- По умолчанию `E2ERunner` использует `AuthClient` для получения токенов
- `LARAVEL_API_TOKEN` из переменных окружения **игнорируется** (чтобы использовать AuthClient)
- Явный токен принимается только через `config.get("api_token")` для обратной совместимости

**Код:**
```python
# Инициализация AuthClient (singleton)
self.auth_client = AuthClient(
    api_url=self.api_url,
    email=auth_email,
    role=auth_role
)

# api_token только из config, не из env
self.api_token = config.get("api_token")  # Только из config, не из env

# При setup токен получается автоматически
if not self.api_token:
    token = await self.auth_client.get_token()
```

### 2. APIClient (`tests/e2e/runner/api_client.py`)

**Автоматическое обновление токенов:**
- При получении 401 автоматически обновляется токен через `AuthClient`
- Все HTTP методы (GET, POST, PUT, DELETE, REQUEST) поддерживают автоматический re-auth

**Код:**
```python
# Обработка 401 - автоматический re-auth
if response.status_code == 401 and self.auth_client:
    logger.warning(f"Request returned 401, refreshing token...")
    new_token = await self.auth_client.handle_401_error()
    headers = await self._get_headers()
    response = await self.client.request(...)  # Повторный запрос
```

### 3. run_e2e.sh (`tools/testing/run_e2e.sh`)

**Упрощенная логика:**
- Скрипт больше не устанавливает `LARAVEL_API_TOKEN` автоматически
- AuthClient получает токен сам при запуске тестов
- `LARAVEL_API_TOKEN` принимается только если явно установлен пользователем (для обратной совместимости)

**Код:**
```bash
if [ -n "$LARAVEL_API_TOKEN" ]; then
    log_info "LARAVEL_API_TOKEN установлен, будет использован (для обратной совместимости)"
else
    log_info "Используется AuthClient для автоматического управления токенами"
fi
# Не устанавливаем LARAVEL_API_TOKEN, чтобы AuthClient работал автоматически
```

## Использование

### Стандартное использование (рекомендуется)

```bash
# Просто запустите тесты - токен получится автоматически
./tools/testing/run_e2e.sh all
```

### С кастомными параметрами

```python
from runner.e2e_runner import E2ERunner

runner = E2ERunner({
    "api_url": "http://localhost:8081",
    "auth_email": "custom@test.local",  # опционально
    "auth_role": "admin"  # опционально
})

await runner.setup()
# Токен автоматически получен через AuthClient
```

### Для обратной совместимости

Если нужно использовать явный токен (не рекомендуется):

```python
runner = E2ERunner({
    "api_url": "http://localhost:8081",
    "api_token": "explicit-token-here"  # Явный токен из config
})
```

## Преимущества

✅ **Никакого хардкода токенов** - токены получаются автоматически  
✅ **Автоматическое обновление** - при 401 токен обновляется автоматически  
✅ **TTL учитывается** - токен обновляется за 5 минут до истечения  
✅ **Один токен на прогон** - singleton pattern гарантирует единообразие  
✅ **Fallback механизм** - если API недоступен, используется Artisan команда  

## Миграция

Если у вас есть старые тесты или скрипты, использующие `LARAVEL_API_TOKEN`:

1. **Удалите** установку `LARAVEL_API_TOKEN` из скриптов
2. **Оставьте** переменную пустой или не устанавливайте её вообще
3. AuthClient автоматически получит токен при запуске

## Проверка работы

Запустите тест:

```bash
cd tests/e2e
python3 -m runner.e2e_runner scenarios/E01_bootstrap.yaml
```

Вы должны увидеть в логах:
```
E2E Runner: Using AuthClient for automatic token management
✓ Token obtained via AuthClient (length: 51)
```

## См. также

- [AUTH_CLIENT.md](runner/AUTH_CLIENT.md) - Документация AuthClient
- [E2E_AUTH_BOOTSTRAP.md](../../../backend/E2E_AUTH_BOOTSTRAP.md) - E2E Auth Bootstrap

