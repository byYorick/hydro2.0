# Тесты для PID конфигурации

## Структура тестов

### Backend (Laravel) тесты

**Feature тесты:**
- `tests/Feature/ZonePidConfigControllerTest.php` - тесты API контроллера
- `tests/Feature/ZonePidLogControllerTest.php` - тесты контроллера логов

**Unit тесты:**
- `tests/Unit/Services/ZonePidConfigServiceTest.php` - тесты сервиса
- `tests/Unit/Models/ZonePidConfigTest.php` - тесты модели

### Python тесты

- `backend/services/automation-engine/tests/test_pid_config_service.py` - тесты PidConfigService
- `backend/services/automation-engine/test_pid_integration.py` - интеграционные тесты

### E2E тесты

- `tests/E2E/pid-config.spec.ts` - Playwright тесты для UI

## Запуск тестов

### В Docker контейнерах (рекомендуется)

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

### Вручную через docker-compose

**PHP тесты:**
```bash
cd backend
docker-compose -f docker-compose.dev.yml exec laravel php artisan test --filter=ZonePidConfig
```

**Python тесты:**
```bash
cd backend
docker-compose -f docker-compose.dev.yml run --rm pid-tests
```

**E2E тесты:**
```bash
cd backend
docker-compose -f docker-compose.dev.yml exec laravel npx playwright test tests/E2E/pid-config.spec.ts
```

### Локально (без Docker)

**PHP тесты:**
```bash
cd backend/laravel
php artisan test --filter=ZonePidConfig
```

**Python тесты:**
```bash
cd backend/services/automation-engine
pytest tests/test_pid_config_service.py test_pid_integration.py -v
```

## Покрытие тестами

### PHP тесты покрывают:
- ✅ CRUD операции с PID конфигами
- ✅ Валидацию полей конфига
- ✅ Rate limiting
- ✅ Создание событий PID_CONFIG_UPDATED
- ✅ Получение логов PID
- ✅ Фильтрацию логов по типу
- ✅ Пагинацию логов
- ✅ Связи модели ZonePidConfig
- ✅ Accessors модели

### Python тесты покрывают:
- ✅ Загрузку конфигов из БД
- ✅ Использование дефолтных конфигов
- ✅ Кеширование конфигов
- ✅ Инвалидацию кеша
- ✅ Построение дефолтных конфигов
- ✅ Интеграцию с CorrectionController

### E2E тесты покрывают:
- ✅ Отображение Automation Engine
- ✅ Переключение между табами
- ✅ Загрузку формы PID настроек
- ✅ Валидацию формы
- ✅ Сохранение конфига
- ✅ Отображение логов PID
- ✅ Фильтрацию логов

## Требования

- Docker и docker-compose
- Для PHP тестов: контейнер laravel должен быть запущен
- Для Python тестов: контейнер db должен быть запущен
- Для E2E тестов: контейнер laravel и Playwright должны быть настроены

