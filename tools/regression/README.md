# Golden Path Regression Suite (P1)

Быстрый локальный прогон базовых инвариантов пайплайна без Docker.

## Описание

Набор регрессионных тестов для проверки критичных инвариантов системы:
- **Команда**: отправка команды и проверка выполнения
- **Ошибка**: публикация ошибки и проверка алерта
- **Snapshot**: получение snapshot и проверка данных

## Требования

### Зависимости

- Python 3.8+
- curl
- Python библиотеки:
  ```bash
  pip install paho-mqtt pyyaml requests
  ```

### Сервисы

- MQTT брокер (по умолчанию: `localhost:1883`)
- Laravel API (по умолчанию: `http://localhost:8080`)
- PostgreSQL (для проверок БД, опционально)

## Использование

### Быстрый запуск

```bash
./tools/regression/run_golden_path.sh
```

### С переменными окружения

```bash
MQTT_HOST=localhost \
MQTT_PORT=1883 \
LARAVEL_URL=http://localhost:8080 \
API_TOKEN=your-token \
./tools/regression/run_golden_path.sh
```

### Прямой запуск Python скрипта

```bash
python3 tools/regression/golden_path_runner.py tools/regression/golden_path.yaml
```

## Конфигурация

Конфигурация находится в `golden_path.yaml`:

```yaml
config:
  mqtt:
    host: ${MQTT_HOST:-localhost}
    port: ${MQTT_PORT:-1883}
  
  laravel:
    url: ${LARAVEL_URL:-http://localhost:8080}
    api_token: ${API_TOKEN:-}
  
  test_data:
    gh_uid: gh-test-1
    zone_uid: zn-test-1
    node_uid: nd-ph-test-1
```

## Сценарии

### 1. Команда (command)

Проверяет:
- Отправку команды через API
- Проверку статуса команды
- Наличие команды в БД

### 2. Ошибка (error)

Проверяет:
- Публикацию ошибки через MQTT
- Создание алерта в БД
- Наличие алерта через API

### 3. Snapshot (snapshot)

Проверяет:
- Получение snapshot зоны
- Структуру snapshot данных
- Наличие обязательных полей

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `MQTT_HOST` | Хост MQTT брокера | `localhost` |
| `MQTT_PORT` | Порт MQTT брокера | `1883` |
| `MQTT_USER` | Пользователь MQTT | (пусто) |
| `MQTT_PASS` | Пароль MQTT | (пусто) |
| `LARAVEL_URL` | URL Laravel API | `http://localhost:8080` |
| `API_TOKEN` | Токен для API | (пусто) |

## Выходные коды

- `0` - все тесты пройдены
- `1` - некоторые тесты провалились или ошибка выполнения

## Очистка

После выполнения тестов автоматически выполняется очистка:
- Удаление тестовых алертов (код `GOLDEN_PATH_TEST`)
- Удаление тестовых команд (созданных за последний час)

## Отладка

Для детального вывода установите переменную окружения:

```bash
DEBUG=1 ./tools/regression/run_golden_path.sh
```

## Интеграция в CI/CD

Пример для GitHub Actions:

```yaml
- name: Run Golden Path Regression
  run: |
    cd backend
    ./tools/regression/run_golden_path.sh
  env:
    MQTT_HOST: localhost
    LARAVEL_URL: http://localhost:8080
    API_TOKEN: ${{ secrets.API_TOKEN }}
```

## Ограничения

- Тесты работают против dev окружения
- Требуется доступ к MQTT и Laravel API
- Проверки БД упрощены (в полной версии требуют прямого доступа к PostgreSQL)

## См. также

- [E2E сценарии](../../tests/e2e/scenarios/README.md) - полные E2E тесты
- [Node Simulator](../../tests/node_sim/README.md) - симулятор узлов для тестирования

