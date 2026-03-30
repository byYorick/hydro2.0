# Backend Services - hydro2.0

Backend-сервисы для гидропонной системы управления.

## 📚 Документация

### Основная документация
- **Полная документация проекта:** `../doc_ai/` - эталонная документация
- **Индекс документации:** `../doc_ai/INDEX.md`
- **Backend архитектура:** `../doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`
- **Python-сервисы:** `../doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`

### Быстрые гайды
- **Мониторинг:** `MONITORING_QUICK_START.md` - быстрый старт
- **Просмотр логов:** `docs/LOGS_VIEWING.md`

### История изменений
- **Changelog:** `CHANGELOG.md` - важные изменения

## Структура

### Laravel (API Gateway)
Laravel выполняет роль API Gateway и предоставляет:
- REST API для фронтенда и мобильного приложения (`/api/*`)
- WebSocket/Realtime обновления (Laravel Reverb)
- Управление конфигурацией (зоны, ноды, рецепты)
- Авторизация и управление пользователями

### Python-сервисы
- `mqtt-bridge` — FastAPI мост REST→MQTT (порт 9000)
- `history-logger` — подписка на MQTT, запись телеметрии в PostgreSQL; **единственная** публикация команд в MQTT (REST **9300**, метрики **9301**)
- `automation-engine` (AE3) — автоматизация зон, коррекции; device-команды только через REST `history-logger` (REST **9405**, метрики **9401**)
- расписания поливов/света из фаз рецепта — **Laravel** (`automation:dispatch-schedules`, см. `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md`)
- `device-registry` — реестр устройств (статус: PLANNED)

**Документация сервисов:** `services/<service>/README.md`

## Мониторинг

Система мониторинга включает:

### Компоненты

1. **Prometheus** (порт 9090)
   - Сбор метрик с Python-сервисов
   - Хранение метрик (retention: 15-30 дней)
   - Правила алертов

2. **Grafana** (порт 3000)
   - Визуализация метрик и телеметрии
   - Дашборды:
     - System Overview — состояние сервисов
     - Zone Telemetry — графики pH/EC/температуры
     - Node Status — статус узлов
     - Alerts Dashboard — активные алерты
     - Commands & Automation — статистика команд

3. **Alertmanager** (порт 9093)
   - Управление алертами
   - Маршрутизация уведомлений (Email, Telegram, UI webhook)

### Хранилище данных

- **PostgreSQL + TimescaleDB** — оптимизированное хранение временных рядов
- **Retention политики**:
  - Raw данные: 7-30 дней (настраивается)
  - Агрегированные данные (1m, 1h, daily): до 12 месяцев
- **Автоматическая агрегация**: Laravel команды `telemetry:cleanup-raw` и `telemetry:aggregate`

### Проверка работоспособности

```bash
./scripts/check_monitoring.sh
```

Скрипт проверяет доступность всех компонентов мониторинга.

### Конфигурация

- Dev: `configs/dev/prometheus.yml`, `configs/dev/alertmanager/config.yml`
- Prod: `configs/prod/prometheus.yml`, `configs/prod/alertmanager/config.yml`

### Алерты

Настроены алерты на:
- Падение узлов (offline > 5 минут)
- Недоступность сервисов (Python-сервисы, MQTT broker)
- Критические алерты в зонах
- Высокий процент ошибок команд

См. `configs/*/prometheus/alerts.yml` для деталей.

## Документация в этом каталоге

### Актуальные документы
- `MONITORING_QUICK_START.md` - быстрый старт мониторинга
- `docs/LOGS_VIEWING.md` - просмотр логов Grafana и БД
- `CHANGELOG.md` - история важных изменений

### Документация в подкаталогах
- `docs/` - документация по мониторингу, развертыванию, архитектуре
- `laravel/docs/` - документация Laravel (WebSocket, тестирование, оптимизация)
- `services/<service>/README.md` - документация Python-сервисов

### Примечание
Временные отчеты об исправлениях были удалены. Важные изменения всегда отражаются в `CHANGELOG.md`.

## Разработка

### Быстрый старт

```bash
# Запуск dev окружения
docker-compose -f docker-compose.dev.yml up -d

# Проверка статуса
docker-compose -f docker-compose.dev.yml ps

# Логи
docker-compose -f docker-compose.dev.yml logs -f laravel
```

### Тестирование

```bash
# Laravel тесты
docker-compose -f docker-compose.dev.yml exec laravel php artisan test

# Python тесты
docker-compose -f docker-compose.dev.yml exec mqtt-bridge pytest
```

---

**Полная документация проекта:** `../doc_ai/INDEX.md`
