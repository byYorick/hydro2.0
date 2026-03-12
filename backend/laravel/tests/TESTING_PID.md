# Запуск тестов PID конфигурации

## Быстрый старт

Все тесты запускаются через скрипт `run_pid_tests.sh` в Docker контейнерах:

```bash
# Все тесты
./run_pid_tests.sh all

# Только PHP тесты
./run_pid_tests.sh php

# Только Python тесты
./run_pid_tests.sh python

# Только E2E тесты
./run_pid_tests.sh e2e
```

## Требования

1. Docker и docker-compose должны быть установлены
2. Контейнеры должны быть запущены (скрипт автоматически запустит их при необходимости)

## Структура тестов

### Backend (Laravel) тесты

**Расположение:** `backend/laravel/tests/`

- `Feature/ZonePidConfigControllerTest.php` - API контроллер
- `Feature/ZonePidLogControllerTest.php` - контроллер логов
- `Unit/Services/ZonePidConfigServiceTest.php` - сервис
- `Unit/Models/ZonePidConfigTest.php` - модель

**Запуск:**
```bash
./run_pid_tests.sh php
```

Или вручную:
```bash
cd backend
docker-compose -f docker-compose.dev.yml exec laravel php artisan test --filter=ZonePidConfig
```

### Python тесты

**Расположение:** `backend/services/automation-engine/`

- `tests/test_pid_config_service.py` - тесты PidConfigService
- `test_pid_integration.py` - интеграционные тесты

**Запуск:**
```bash
./run_pid_tests.sh python
```

Или вручную:
```bash
cd backend
COMPOSE_PROFILES=tests docker-compose -f docker-compose.dev.yml run --rm pid-tests
```

### E2E тесты (Playwright)

**Расположение:** `backend/laravel/tests/E2E/pid-config.spec.ts`

**Запуск:**
```bash
./run_pid_tests.sh e2e
```

Или вручную:
```bash
cd backend
docker-compose -f docker-compose.dev.yml exec laravel npx playwright test tests/E2E/pid-config.spec.ts
```

## Что тестируется

### PHP тесты
- ✅ CRUD операции с PID конфигами
- ✅ Валидация полей конфига
- ✅ Rate limiting (10 запросов в минуту)
- ✅ Создание событий `PID_CONFIG_UPDATED`
- ✅ Получение логов PID
- ✅ Фильтрация логов по типу (pH/EC)
- ✅ Пагинация логов
- ✅ Связи модели `ZonePidConfig`
- ✅ Accessors модели

### Python тесты
- ✅ Загрузка конфигов из БД
- ✅ Использование дефолтных конфигов при отсутствии в БД
- ✅ Кеширование конфигов (TTL 60 сек)
- ✅ Инвалидация кеша при обновлении
- ✅ Построение дефолтных конфигов для pH и EC
- ✅ Интеграция с `CorrectionController`

### E2E тесты
- ✅ Отображение вкладки "Automation Engine"
- ✅ Переключение между табами "PID Settings" и "PID Logs"
- ✅ Загрузка формы PID настроек
- ✅ Валидация формы
- ✅ Сохранение конфига
- ✅ Отображение логов PID
- ✅ Фильтрация логов

## Устранение неполадок

### Контейнеры не запускаются

```bash
cd backend
docker-compose -f docker-compose.dev.yml up -d db
docker-compose -f docker-compose.dev.yml up -d laravel
```

### Python тесты не находят модули

Убедитесь, что `PYTHONPATH=/app` установлен в контейнере.

### PHP тесты не находят базу данных

Убедитесь, что контейнер `db` запущен и доступен:
```bash
docker-compose -f docker-compose.dev.yml ps db
```

### E2E тесты требуют настройки Playwright

В контейнере Laravel выполните:
```bash
docker-compose -f docker-compose.dev.yml exec laravel npx playwright install
```

## Дополнительная информация

Подробная документация по тестам: `backend/laravel/tests/README_PID_TESTS.md`

