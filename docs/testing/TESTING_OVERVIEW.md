# Обзор системы тестирования Hydro 2.0

Документация по системе тестирования проекта Hydro 2.0. Содержит quickstart, обзор компонентов и ссылки на детальную документацию.

## Быстрый старт (Quickstart)

### Предварительные требования

- Python 3.10+
- Docker и Docker Compose
- PostgreSQL (через Docker Compose)
- MQTT брокер (Mosquitto через Docker Compose)
- Node.js и npm (для frontend тестов, опционально)

### 1. Установка зависимостей

```bash
# Установка зависимостей для node_sim
cd tests/node_sim
pip install -r requirements.txt

# Установка зависимостей для E2E тестов
cd ../e2e
pip install -r requirements.txt
```

### 2. Запуск тестового окружения

```bash
# Переход в директорию E2E тестов
cd tests/e2e

# Запуск всех сервисов через Docker Compose
docker-compose -f docker-compose.e2e.yml up -d

# Ожидание готовности сервисов (может занять 1-2 минуты)
docker-compose -f docker-compose.e2e.yml ps
```

### 3. Запуск первого теста

```bash
# Простой тест с node_sim
cd tests/node_sim
python -m node_sim.cli run --config sim.example.yaml

# E2E тест (пример)
cd ../e2e
python -m runner.e2e_runner scenarios/E01_bootstrap.yaml
```

## Компоненты системы тестирования

### 1. Node Simulator (node_sim)

Симулятор узлов для эмуляции работы реальных устройств через MQTT.

**Основные возможности:**
- Публикация телеметрии и heartbeat
- Обработка команд от backend
- Эмуляция различных режимов работы (preconfig, configured)
- Режимы отказов для тестирования устойчивости

**Документация:** [NODE_SIM.md](./NODE_SIM.md)

### 2. E2E Test Runner

Фреймворк для выполнения end-to-end тестов системы.

**Основные возможности:**
- Запуск YAML сценариев
- Проверки через API, БД, WebSocket, MQTT
- Автоматическая генерация отчетов
- Поддержка параллельного выполнения

**Документация:** [E2E_GUIDE.md](./E2E_GUIDE.md)

### 3. E2E Сценарии

Набор критичных сценариев для проверки инвариантов пайплайна.

**Доступные сценарии:**
- `E01_bootstrap.yaml` - Bootstrap и телеметрия
- `E02_command_happy.yaml` - Успешное выполнение команд
- `E03_duplicate_cmd_response.yaml` - Обработка дубликатов
- `E04_error_alert.yaml` - Создание алертов
- `E05_unassigned_attach.yaml` - Привязка непривязанных узлов
- `E06_laravel_down_queue_recovery.yaml` - Восстановление после падения
- `E07_ws_reconnect_snapshot_replay.yaml` - WebSocket reconnect

**Расположение:** `tests/e2e/scenarios/`

## Переменные окружения

### Общие переменные

```bash
# Окружение
APP_ENV=testing                    # Режим тестирования
LOG_LEVEL=DEBUG                    # Уровень логирования

# База данных
POSTGRES_HOST=localhost            # Хост PostgreSQL
POSTGRES_PORT=5433                 # Порт PostgreSQL (E2E использует 5433)
POSTGRES_DB=hydro_e2e              # Имя базы данных
POSTGRES_USER=hydro                # Пользователь
POSTGRES_PASSWORD=hydro_e2e        # Пароль

# MQTT
MQTT_HOST=localhost                # Хост MQTT брокера
MQTT_PORT=1884                     # Порт MQTT (E2E использует 1884)
MQTT_USER=                         # Пользователь (опционально)
MQTT_PASS=                         # Пароль (опционально)

# Laravel API
LARAVEL_URL=http://localhost:8081  # URL Laravel API (E2E использует 8081)
LARAVEL_API_TOKEN=dev-token-12345  # Токен аутентификации

# WebSocket (Reverb)
WS_URL=ws://localhost:6002         # URL WebSocket сервера (E2E использует 6002)
REVERB_APP_KEY=local               # Reverb app key
REVERB_APP_SECRET=secret           # Reverb app secret
```

### Переменные для node_sim

```bash
# Настройки симулятора
NODE_SIM_CONFIG=/path/to/config.yaml  # Путь к конфигурации
MQTT_HOST=localhost                   # MQTT хост
MQTT_PORT=1883                        # MQTT порт
```

### Переменные для E2E тестов

```bash
# E2E Runner
E2E_REPORT_DIR=./reports              # Директория для отчетов
E2E_TIMEOUT=300                       # Таймаут теста в секундах
E2E_RETRIES=3                         # Количество повторов при ошибке
```

## Структура тестов

```
tests/
├── node_sim/                 # Симулятор узлов
│   ├── node_sim/            # Python модуль
│   ├── sim.example.yaml     # Пример конфигурации
│   ├── requirements.txt     # Зависимости
│   └── README.md            # Документация
│
├── e2e/                      # E2E тесты
│   ├── runner/              # Фреймворк для запуска тестов
│   ├── scenarios/           # YAML сценарии тестов
│   ├── docker-compose.e2e.yml  # Docker Compose для тестового окружения
│   └── requirements.txt     # Зависимости
│
└── integration_tests/        # Интеграционные тесты (Python)
    ├── setup_test_data.py
    └── test_error_reporting.py
```

## Типовые сценарии использования

### Тестирование отдельного узла

```bash
# Запуск симулятора одного узла
cd tests/node_sim
python -m node_sim.cli run --config sim.example.yaml --log-level DEBUG
```

### Тестирование множества узлов

```bash
# Запуск симулятора нескольких узлов
python -m node_sim.cli multi --config multi.example.yaml
```

### Запуск всех E2E сценариев

```bash
# Запуск всех сценариев последовательно
cd tests/e2e
for scenario in scenarios/E*.yaml; do
    python -m runner.e2e_runner "$scenario"
done
```

### Запуск конкретного E2E сценария

```bash
# Запуск одного сценария
cd tests/e2e
python -m runner.e2e_runner scenarios/E01_bootstrap.yaml
```

### Отладка E2E теста

```bash
# Запуск с подробным логированием
export LOG_LEVEL=DEBUG
python -m runner.e2e_runner scenarios/E01_bootstrap.yaml --verbose
```

## Отчеты и результаты

### JUnit XML отчеты

После выполнения E2E тестов генерируются отчеты в формате JUnit XML:

```bash
# Отчеты находятся в
tests/e2e/reports/junit.xml
```

### JSON Timeline

Детальная информация о выполнении теста в формате JSON:

```bash
# Timeline с событиями
tests/e2e/reports/timeline.json
```

Включает:
- WebSocket сообщения (последние 50)
- MQTT сообщения (последние 50)
- API ответы
- Временные метки событий

## Интеграция с CI/CD

### GitHub Actions пример

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -r tests/node_sim/requirements.txt
          pip install -r tests/e2e/requirements.txt
      
      - name: Start services
        run: |
          cd tests/e2e
          docker-compose -f docker-compose.e2e.yml up -d
      
      - name: Wait for services
        run: sleep 60
      
      - name: Run E2E tests
        run: |
          cd tests/e2e
          python -m runner.e2e_runner scenarios/E01_bootstrap.yaml
        env:
          LARAVEL_URL: http://localhost:8081
          MQTT_HOST: localhost
          MQTT_PORT: 1884
      
      - name: Upload reports
        uses: actions/upload-artifact@v3
        with:
          name: e2e-reports
          path: tests/e2e/reports/
```

## Решение проблем

Если возникли проблемы при запуске тестов, см. [TROUBLESHOOTING.md](./TROUBLESHOOTING.md).

## Дополнительные ресурсы

- [NODE_SIM.md](./NODE_SIM.md) - Детальная документация по симулятору узлов
- [E2E_GUIDE.md](./E2E_GUIDE.md) - Руководство по E2E тестам
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) - Решение типовых проблем
- [MQTT_SPEC_FULL.md](../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md) - Спецификация MQTT протокола
- [BACKEND_NODE_CONTRACT_FULL.md](../03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md) - Контракт между backend и узлами

## Поддержка

При возникновении проблем:
1. Проверьте [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)
2. Проверьте логи сервисов: `docker-compose -f tests/e2e/docker-compose.e2e.yml logs`
3. Создайте issue с описанием проблемы и логами








