Backend-сервисы для hydro2.0.

## Структура

### Laravel (API Gateway)
Laravel выполняет роль API Gateway и предоставляет:
- REST API для фронтенда и мобильного приложения (`/api/*`)
- WebSocket/Realtime обновления (Laravel Reverb)
- Управление конфигурацией (зоны, ноды, рецепты)
- Авторизация и управление пользователями

См. документацию: `doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`

### Python-сервисы
- `mqtt-bridge` — FastAPI мост REST→MQTT (порт 9000)
- `history-logger` — подписка на MQTT, запись телеметрии в PostgreSQL
- `automation-engine` — контроллер зон, проверка targets, публикация команд
- `scheduler` — расписания поливов/света из recipe phases
- `device-registry` — реестр устройств (статус: PLANNED, функционал частично в Laravel)

См. документацию: `doc_ai/04_BACKEND_CORE/` и `backend/services/README.md`

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


