# E2E Auth Bootstrap - Автоматическая подготовка токена для E2E тестов

## Описание

Механизм автоматической подготовки пользователя и токена для E2E тестов. Реализованы два способа получения токена:

1. **Artisan команда** `e2e:auth-bootstrap`
2. **API endpoint** `POST /api/e2e/auth/token` (только в testing окружении)

## Реализация

### 1. Artisan команда

**Файл:** `backend/laravel/app/Console/Commands/E2EAuthBootstrap.php`

**Использование:**
```bash
# Базовое использование
php artisan e2e:auth-bootstrap

# С параметрами
php artisan e2e:auth-bootstrap --email=e2e@test.local --role=admin

# В docker-compose
docker-compose -f docker-compose.e2e.yml exec laravel php artisan e2e:auth-bootstrap
```

**Параметры:**
- `--email` - email пользователя (по умолчанию: `e2e@test.local`)
- `--role` - роль пользователя (по умолчанию: `admin`)

**Функциональность:**
- Создаёт пользователя с указанным email, если его нет
- Устанавливает роль пользователя
- Создаёт Sanctum токен
- Выводит токен в stdout (для удобства парсинга)

**DoD:** ✅ Один вызов → один валидный токен

### 2. API Endpoint

**Файл:** `backend/laravel/app/Http/Controllers/E2EAuthController.php`  
**Роут:** `POST /api/e2e/auth/token`  
**Доступ:** Только в окружениях `testing` или `e2e`

**Использование:**
```bash
curl -X POST http://localhost:8081/api/e2e/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"e2e@test.local","role":"admin"}'
```

**Ответ:**
```json
{
  "status": "ok",
  "data": {
    "token": "1|abc123...",
    "user": {
      "id": 1,
      "email": "e2e@test.local",
      "role": "admin"
    }
  }
}
```

**Параметры запроса:**
- `email` (optional) - email пользователя (по умолчанию: `e2e@test.local`)
- `role` (optional) - роль пользователя (по умолчанию: `admin`)

## Интеграция с run_e2e.sh

Скрипт `tools/testing/run_e2e.sh` автоматически получает токен при запуске тестов:

1. Сначала пробует получить токен через API endpoint
2. Если API недоступен, использует Artisan команду
3. Если оба метода не сработали, использует значение по умолчанию

## Тесты

**Файл:** `backend/laravel/tests/Unit/Console/E2EAuthBootstrapCommandTest.php`

Тесты проверяют:
- ✅ Команда зарегистрирована
- ✅ Создание пользователя если его нет
- ✅ Использование существующего пользователя
- ✅ Вывод токена в stdout
- ✅ Создание токена для пользователя
- ✅ Поддержка кастомных email и role

## Безопасность

- API endpoint доступен **только** в окружениях `testing` и `e2e`
- В других окружениях возвращает 404
- Rate limiting: 10 запросов в минуту

## Примеры использования

### Получение токена для ручного тестирования

```bash
# Через команду
TOKEN=$(docker-compose -f tests/e2e/docker-compose.e2e.yml exec -T laravel php artisan e2e:auth-bootstrap | tail -n 1)
export LARAVEL_API_TOKEN="$TOKEN"

# Через API
TOKEN=$(curl -s -X POST http://localhost:8081/api/e2e/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"e2e@test.local","role":"admin"}' | \
  python3 -c "import json,sys; print(json.load(sys.stdin)['data']['token'])")
export LARAVEL_API_TOKEN="$TOKEN"
```

### В скриптах CI/CD

```yaml
- name: Get E2E token
  run: |
    TOKEN=$(docker-compose -f tests/e2e/docker-compose.e2e.yml exec -T laravel php artisan e2e:auth-bootstrap | tail -n 1)
    echo "LARAVEL_API_TOKEN=$TOKEN" >> $GITHUB_ENV
```

## См. также

- [E2E_GUIDE.md](../../docs/testing/E2E_GUIDE.md) - Полное руководство по E2E тестам
- [run_e2e.sh](../../tools/testing/run_e2e.sh) - Скрипт запуска E2E тестов

