# Troubleshooting - Решение типовых проблем

Руководство по решению типовых проблем при работе с системой тестирования Hydro 2.0.

## Общие проблемы

### Проблема: Сервисы не запускаются

**Симптомы:**
- `docker-compose up` завершается с ошибкой
- Сервисы не проходят healthcheck

**Решение:**

1. Проверьте доступность портов:
```bash
# Проверка занятых портов
netstat -tuln | grep -E "5433|1884|8081|6002"
```

2. Остановите конфликтующие сервисы или измените порты в `docker-compose.e2e.yml`

3. Проверьте логи:
```bash
docker-compose -f docker-compose.e2e.yml logs
```

4. Пересоздайте контейнеры:
```bash
docker-compose -f docker-compose.e2e.yml down -v
docker-compose -f docker-compose.e2e.yml up -d
```

### Проблема: База данных не доступна

**Симптомы:**
- Ошибки подключения к PostgreSQL
- Тесты падают с ошибкой `Connection refused`

**Решение:**

1. Проверьте статус контейнера:
```bash
docker-compose -f docker-compose.e2e.yml ps postgres
```

2. Проверьте логи:
```bash
docker-compose -f docker-compose.e2e.yml logs postgres
```

3. Проверьте переменные окружения:
```bash
# Должны быть установлены
echo $POSTGRES_HOST
echo $POSTGRES_PORT
echo $POSTGRES_DB
```

4. Попробуйте подключиться вручную:
```bash
docker-compose -f docker-compose.e2e.yml exec postgres psql -U hydro -d hydro_e2e -c "SELECT 1;"
```

### Проблема: MQTT брокер не доступен

**Симптомы:**
- node_sim не может подключиться к MQTT
- Ошибки `Connection refused` при публикации сообщений

**Решение:**

1. Проверьте статус контейнера:
```bash
docker-compose -f docker-compose.e2e.yml ps mosquitto
```

2. Проверьте доступность:
```bash
# Тестовая публикация
docker-compose -f docker-compose.e2e.yml exec mosquitto mosquitto_pub -h localhost -t test -m "test"
```

3. Проверьте конфигурацию:
```bash
cat tests/e2e/mosquitto.e2e.conf
```

4. Проверьте порты:
```bash
# Должен быть доступен на порту 1884 (или другом указанном)
telnet localhost 1884
```

## Node Simulator

### Проблема: node_sim не подключается к MQTT

**Симптомы:**
```
ERROR: Failed to connect to MQTT broker
Connection refused
```

**Решение:**

1. Проверьте настройки MQTT в конфигурации:
```yaml
mqtt:
  host: localhost  # Должен быть доступен
  port: 1883       # Правильный порт
```

2. Проверьте доступность брокера:
```bash
mosquitto_pub -h localhost -p 1883 -t test -m "test"
```

3. Если используется Docker, используйте имя сервиса:
```yaml
mqtt:
  host: mosquitto  # Имя сервиса в Docker Compose
  port: 1883
```

### Проблема: Узел не публикует телеметрию

**Симптомы:**
- Симулятор запущен, но сообщения не приходят
- В логах нет ошибок

**Решение:**

1. Проверьте подписку на топики:
```bash
mosquitto_sub -h localhost -p 1883 -t "hydro/+/+/+/+/telemetry" -v
```

2. Проверьте конфигурацию узла:
```yaml
node:
  channels:      # Должны быть указаны каналы
    - ph_sensor
```

3. Увеличьте уровень логирования:
```bash
python -m node_sim.cli run --config sim.example.yaml --log-level DEBUG
```

4. Проверьте интервал публикации:
```yaml
telemetry:
  interval_seconds: 5.0  # Слишком большой интервал?
```

### Проблема: Команды не обрабатываются

**Симптомы:**
- Команды отправляются, но нет ответа
- Узел не отвечает на команды

**Решение:**

1. Проверьте подписку на топик команд:
```bash
mosquitto_sub -h localhost -p 1883 -t "hydro/+/+/+/+/cmd" -v
```

2. Проверьте, что узел в правильном режиме:
```yaml
node:
  mode: configured  # Должен быть configured, а не preconfig
```

3. Проверьте наличие активаторов:
```yaml
node:
  actuators:  # Должны быть указаны активаторы
    - main_pump
```

4. Проверьте логи с DEBUG уровнем:
```bash
python -m node_sim.cli run --config sim.example.yaml --log-level DEBUG
```

### Проблема: Импорт модулей node_sim не работает

**Симптомы:**
```
ModuleNotFoundError: No module named 'node_sim'
```

**Решение:**

1. Установите зависимости:
```bash
cd tests/node_sim
pip install -r requirements.txt
```

2. Установите модуль в режиме разработки:
```bash
pip install -e .
```

3. Используйте правильную команду запуска:
```bash
python -m node_sim.cli run --config sim.example.yaml
```

## E2E Tests

### Проблема: Тест не может подключиться к Laravel API

**Симптомы:**
```
ConnectionError: Failed to connect to Laravel API
```

**Решение:**

1. Проверьте статус Laravel контейнера:
```bash
docker-compose -f docker-compose.e2e.yml ps laravel
```

2. Проверьте доступность API:
```bash
curl http://localhost:8081/api/system/health
```

3. Проверьте переменные окружения:
```bash
echo $LARAVEL_URL
echo $LARAVEL_API_TOKEN
```

4. Проверьте логи Laravel:
```bash
docker-compose -f docker-compose.e2e.yml logs laravel
```

### Проблема: WebSocket соединение не устанавливается

**Симптомы:**
```
WebSocket connection failed
Timeout waiting for connection
```

**Решение:**

1. Проверьте статус Reverb:
```bash
docker-compose -f docker-compose.e2e.yml logs laravel | grep reverb
```

2. Проверьте доступность WebSocket:
```bash
# Используйте wscat или другой WebSocket клиент
wscat -c ws://localhost:6002
```

3. Проверьте переменные окружения:
```bash
echo $WS_URL
echo $REVERB_APP_KEY
```

4. Проверьте настройки Reverb в Laravel:
```bash
docker-compose -f docker-compose.e2e.yml exec laravel cat .env | grep REVERB
```

### Проблема: Database query не находит данные

**Симптомы:**
- Проверки в БД падают
- `expected_rows: 1` не выполняется

**Решение:**

1. Проверьте подключение к БД:
```bash
docker-compose -f docker-compose.e2e.yml exec postgres psql -U hydro -d hydro_e2e -c "SELECT COUNT(*) FROM nodes;"
```

2. Выполните запрос вручную:
```bash
# Скопируйте запрос из теста и выполните
docker-compose -f docker-compose.e2e.yml exec postgres psql -U hydro -d hydro_e2e -c "SELECT * FROM commands WHERE cmd_id = 'test';"
```

3. Проверьте таймауты:
```yaml
- type: database_query
  wait_seconds: 5  # Увеличьте таймаут
```

4. Добавьте задержку перед проверкой:
```yaml
- step: wait_processing
  type: wait
  seconds: 3
```

### Проблема: Тест падает на assertion

**Симптомы:**
- Тест выполняется, но проверка не проходит
- Assertion failed

**Решение:**

1. Проверьте отчет timeline.json:
```bash
cat tests/e2e/reports/timeline.json | jq '.assertions[] | select(.name == "assertion_name")'
```

2. Проверьте фактические данные:
```yaml
# Добавьте capture для отладки
- step: check_data
  type: database_query
  capture: debug_data
  
# Выведите данные
- step: debug
  type: log
  message: "Data: ${debug_data}"
```

3. Проверьте оператор сравнения:
```yaml
expected:
  - field: status
    operator: equals  # Правильный оператор?
    value: "DONE"
```

### Проблема: Симулятор узла не запускается в тесте

**Симптомы:**
- Ошибка при запуске симулятора
- Timeout при ожидании симулятора

**Решение:**

1. Проверьте конфигурацию в setup:
```yaml
setup:
  node_sim:
    config:
      mqtt:
        host: ${MQTT_HOST:-localhost}  # Правильный хост?
```

2. Проверьте доступность MQTT:
```bash
mosquitto_pub -h localhost -p 1884 -t test -m "test"
```

3. Увеличьте wait_seconds:
```yaml
- step: start_node_simulator
  type: start_simulator
  wait_seconds: 10  # Увеличьте время ожидания
```

### Проблема: Тест работает локально, но падает в CI

**Симптомы:**
- Тест проходит локально
- Падает в CI/CD пайплайне

**Решение:**

1. Проверьте переменные окружения в CI:
```yaml
# GitHub Actions
env:
  LARAVEL_URL: http://localhost:8081
  MQTT_HOST: localhost
  MQTT_PORT: 1884
```

2. Увеличьте таймауты для CI:
```bash
export E2E_TIMEOUT=600  # 10 минут вместо 5
```

3. Добавьте ожидание запуска сервисов:
```yaml
- name: Wait for services
  run: sleep 120  # Достаточно времени для запуска
```

4. Проверьте логи в CI:
```yaml
- name: Show logs on failure
  if: failure()
  run: docker-compose -f docker-compose.e2e.yml logs
```

## База данных

### Проблема: Миграции не применены

**Симптомы:**
```
relation "nodes" does not exist
```

**Решение:**

1. Примените миграции:
```bash
docker-compose -f docker-compose.e2e.yml exec laravel php artisan migrate
```

2. Проверьте таблицы:
```bash
docker-compose -f docker-compose.e2e.yml exec postgres psql -U hydro -d hydro_e2e -c "\dt"
```

### Проблема: База данных не чистая между тестами

**Симптомы:**
- Данные от предыдущих тестов влияют на текущий тест
- Тесты непредсказуемо падают

**Решение:**

1. Очистите БД перед тестом:
```bash
docker-compose -f docker-compose.e2e.yml exec laravel php artisan migrate:fresh
```

2. Используйте транзакции в тестах (если поддерживается)

3. Используйте уникальные идентификаторы:
```yaml
node:
  node_uid: nd-test-${RANDOM}  # Уникальный UID
```

## MQTT

### Проблема: Сообщения теряются

**Симптомы:**
- Сообщения публикуются, но не доходят
- Подписчик не получает сообщения

**Решение:**

1. Проверьте QoS:
```yaml
- type: mqtt_publish
  qos: 1  # Используйте QoS 1 или 2 для гарантированной доставки
```

2. Проверьте retain:
```yaml
- type: mqtt_publish
  retain: true  # Для статусов используйте retain
```

3. Проверьте подписку до публикации:
```bash
# Подпишитесь ПЕРЕД публикацией
mosquitto_sub -h localhost -p 1883 -t "test" &
mosquitto_pub -h localhost -p 1883 -t "test" -m "message"
```

### Проблема: Топики не совпадают

**Симптомы:**
- Сообщения публикуются, но не обрабатываются
- Разные форматы топиков

**Решение:**

1. Проверьте формат топика согласно спецификации:
```
hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/telemetry
```

2. Используйте правильные UID:
```yaml
node:
  gh_uid: gh-test-1      # Должен совпадать с БД
  zone_uid: zn-test-1    # Должен существовать в БД
  node_uid: nd-test-1    # Уникальный UID
```

## WebSocket

### Проблема: События не приходят

**Симптомы:**
- Подписка установлена, но события не приходят
- Timeout при ожидании события

**Решение:**

1. Проверьте правильность имени события:
```yaml
event_type: ".App\\Events\\CommandStatusUpdated"  # Правильный формат
```

2. Проверьте канал:
```yaml
channel: "private-commands.{zone_id}"  # Правильный формат канала
```

3. Увеличьте timeout:
```yaml
timeout: 30.0  # Увеличьте время ожидания
```

4. Проверьте, что событие действительно отправляется:
```bash
# В логах Laravel должно быть
docker-compose -f docker-compose.e2e.yml logs laravel | grep "CommandStatusUpdated"
```

## Полезные команды

### Очистка окружения

```bash
# Остановка всех сервисов и удаление volumes
docker-compose -f docker-compose.e2e.yml down -v

# Удаление всех контейнеров
docker-compose -f docker-compose.e2e.yml rm -f

# Очистка неиспользуемых ресурсов
docker system prune -a
```

### Мониторинг в реальном времени

```bash
# Все логи
docker-compose -f docker-compose.e2e.yml logs -f

# Логи конкретного сервиса
docker-compose -f docker-compose.e2e.yml logs -f laravel

# Статус сервисов
watch -n 1 'docker-compose -f docker-compose.e2e.yml ps'
```

### Отладка

```bash
# Вход в контейнер Laravel
docker-compose -f docker-compose.e2e.yml exec laravel bash

# Выполнение artisan команд
docker-compose -f docker-compose.e2e.yml exec laravel php artisan tinker

# Просмотр переменных окружения
docker-compose -f docker-compose.e2e.yml exec laravel env | grep DB
```

## Получение помощи

Если проблема не решается:

1. Проверьте логи всех сервисов
2. Соберите информацию о системе:
   - Версия Python
   - Версия Docker
   - Операционная система
3. Создайте issue с:
   - Описанием проблемы
   - Логами
   - Шагами для воспроизведения
   - Конфигурационными файлами (без секретов)

## Дополнительные ресурсы

- [TESTING_OVERVIEW.md](./TESTING_OVERVIEW.md) - Общий обзор тестирования
- [NODE_SIM.md](./NODE_SIM.md) - Документация по симулятору узлов
- [E2E_GUIDE.md](./E2E_GUIDE.md) - Руководство по E2E тестам






