# E2E Testing Tools

Инструменты для запуска end-to-end тестов системы Hydro 2.0.

## Быстрый старт

### One-command запуск

```bash
./tools/testing/run_e2e.sh
```

Этот скрипт:
1. Поднимает все сервисы через Docker Compose
2. Дожидается readiness всех сервисов
3. Запускает обязательные E2E сценарии
4. Генерирует отчёты
5. Выводит summary с результатами

### Результат

При успешном выполнении:
```
E2E Test Summary
==========================================
Total scenarios: 5
Passed: 5
Failed: 0

All scenarios passed! ✓

Reports location: tests/e2e/reports/
  - junit.xml
  - timeline.json
```

При ошибках:
```
E2E Test Summary
==========================================
Total scenarios: 5
Passed: 3
Failed: 2

Failed scenarios:
  - commands/E10_command_happy
  - alerts/E20_error_to_alert_realtime

Service logs:
  docker compose -f tests/e2e/docker-compose.e2e.yml logs laravel
  docker compose -f tests/e2e/docker-compose.e2e.yml logs history-logger
  docker compose -f tests/e2e/docker-compose.e2e.yml logs node-sim
```

## Настройка

### Переменные окружения

Скрипт использует файл `tests/e2e/.env.e2e` для конфигурации.

Если файл отсутствует, создайте его из примера:
```bash
cp tests/e2e/.env.e2e.example tests/e2e/.env.e2e
# Отредактируйте значения при необходимости
```

### Основные параметры

- `LARAVEL_PORT` - порт Laravel API (по умолчанию 8081)
- `POSTGRES_PORT` - порт PostgreSQL (по умолчанию 5433)
- `MQTT_PORT` - порт MQTT брокера (по умолчанию 1884)
- `LARAVEL_API_TOKEN` - опционально (legacy), по умолчанию используется AuthClient

## Ручной запуск

Если нужно запустить тесты вручную:

```bash
cd tests/e2e

# Поднять сервисы
docker compose -f docker-compose.e2e.yml up -d

# Дождаться готовности
sleep 30

# Запустить сценарий
python3 -m runner.e2e_runner scenarios/core/E01_bootstrap.yaml

# Остановить сервисы
docker compose -f docker-compose.e2e.yml down
```

## Отчёты

После выполнения тестов отчёты сохраняются в `tests/e2e/reports/`:

- `junit.xml` - JUnit XML формат для CI/CD
- `timeline.json` - JSON timeline с детальной информацией
- Последние 50 WS/MQTT сообщений включены в timeline

## Troubleshooting

### Сервисы не поднимаются

```bash
# Проверить логи
docker compose -f tests/e2e/docker-compose.e2e.yml logs

# Проверить статус
docker compose -f tests/e2e/docker-compose.e2e.yml ps

# Пересоздать контейнеры
docker compose -f tests/e2e/docker-compose.e2e.yml down -v
docker compose -f tests/e2e/docker-compose.e2e.yml up -d
```

### node-sim не подключается к MQTT

```bash
# Проверить логи node-sim
docker compose -f tests/e2e/docker-compose.e2e.yml logs node-sim

# Проверить MQTT брокер
docker compose -f tests/e2e/docker-compose.e2e.yml logs mosquitto

# Проверить конфигурацию
cat tests/e2e/node-sim-config.yaml
```

### Тесты падают

1. Проверить логи сервисов
2. Проверить отчёты в `tests/e2e/reports/`
3. Проверить переменные окружения
4. Убедиться, что все сервисы healthy

## Дополнительная информация

- Полная документация: `../../docs/testing/E2E_GUIDE.md`
- Troubleshooting: `../../docs/testing/TROUBLESHOOTING.md`
- Node Simulator: `../../docs/testing/NODE_SIM.md`
