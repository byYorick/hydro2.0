# MASTER TASK: End-to-End тестовый контур - Статус выполнения

## Цель
Сделать так, чтобы проект гарантированно поднимался одной командой, эмулятор нод подключался по MQTT, проходили ключевые e2e сценарии, и все найденные ошибки были исправлены.

## Текущий статус

### ✅ Шаг 1 — Поднять e2e стенд (compose) — ВЫПОЛНЕНО

**Создано:**
- ✅ `tests/e2e/docker-compose.e2e.yml` - полная конфигурация со всеми сервисами
- ✅ `tests/e2e/.env.e2e.example` - пример конфигурации (требует создания .env.e2e)
- ✅ Health endpoints настроены для Laravel и history-logger
- ✅ node-sim контейнер настроен и готов к запуску

**Сервисы в compose:**
- ✅ postgres (TimescaleDB)
- ✅ redis
- ✅ mosquitto (MQTT broker)
- ✅ laravel (+ queue-worker через supervisor)
- ✅ reverb (WebSocket)
- ✅ history-logger
- ✅ mqtt-bridge
- ✅ telemetry-aggregator
- ✅ automation-engine (опционально, через profile)
- ✅ node-sim

**Проверка:**
```bash
docker compose -f tests/e2e/docker-compose.e2e.yml up -d
curl http://localhost:8081/api/system/health  # → OK
docker logs node-sim | grep "Connected to MQTT"  # → должно быть
```

---

### ✅ Шаг 2 — Реализовать node-sim — ВЫПОЛНЕНО

**Реализовано:**
- ✅ `tests/node_sim/` - полный Python пакет с CLI
- ✅ Публикация telemetry (интервал настраивается)
- ✅ Публикация status/heartbeat
- ✅ Подписка на команды и ответы (ACCEPTED→DONE)
- ✅ Публикация ошибок
- ✅ Режим preconfig (temp topics)
- ✅ Dockerfile для контейнеризации

**Проверка:**
- ✅ Telemetry появляется в БД (через history-logger)
- ✅ Команда из API доходит до node-sim и возвращается DONE
- ✅ Конфигурация обновлена для нового формата (sensors вместо channels)

---

### ⚠️ Шаг 3 — Реализовать e2e runner и сценарии — ЧАСТИЧНО ВЫПОЛНЕНО

**Реализовано:**
- ✅ `tests/e2e/runner/e2e_runner.py` - основной раннер
- ✅ `tests/e2e/runner/api_client.py` - HTTP клиент
- ✅ `tests/e2e/runner/ws_client.py` - WebSocket клиент
- ✅ `tests/e2e/runner/db_probe.py` - проверки БД
- ✅ `tests/e2e/runner/mqtt_probe.py` - проверки MQTT
- ✅ `tests/e2e/runner/assertions.py` - кастомные assertions
- ✅ `tests/e2e/runner/reporting.py` - генерация отчётов

**Сценарии созданы:**
- ✅ `E01_bootstrap.yaml` - telemetry + online статус
- ✅ `E02_command_happy.yaml` - команда → DONE + WS + zone_events
- ✅ `E03_duplicate_cmd_response.yaml` - duplicate responses
- ✅ `E04_error_alert.yaml` - error → alert + WS
- ✅ `E05_unassigned_attach.yaml` - temp error → unassigned → attach
- ✅ `E06_laravel_down_queue_recovery.yaml` - queue recovery
- ✅ `E07_ws_reconnect_snapshot_replay.yaml` - snapshot + replay

**Требует проверки:**
- ⚠️ Поддержка всех типов шагов в сценариях (start_simulator, publish_mqtt и т.д.)
- ⚠️ Интеграция с docker-compose для управления node-sim
- ⚠️ Обработка переменных окружения в сценариях

**Проверка:**
```bash
python tests/e2e/runner/e2e_runner.py tests/e2e/scenarios/E01_bootstrap.yaml
# → должен быть зелёный
```

---

### ⚠️ Шаг 4 — Прогон тестов → фиксы → повтор до Green — В ПРОЦЕССЕ

**Создано:**
- ✅ `tools/testing/run_e2e.sh` - one-command entrypoint
- ✅ `tools/testing/README.md` - документация

**Требуется:**
- ⚠️ Запустить все обязательные сценарии
- ⚠️ Исправить найденные баги
- ⚠️ Добавить регрессионные проверки
- ⚠️ Довести до стабильного зелёного состояния

---

## One-command entrypoint

**Создан:** `tools/testing/run_e2e.sh`

**Использование:**
```bash
./tools/testing/run_e2e.sh
```

**Что делает:**
1. Поднимает docker-compose
2. Дожидается readiness всех сервисов
3. Запускает обязательные сценарии (E01, E02, E04, E05, E07)
4. Генерирует отчёты
5. Выводит summary

**Результат:**
- При успехе: summary с количеством пройденных тестов
- При ошибках: список упавших сценариев + ссылки на логи

---

## Обязательные сценарии (матрица)

| Сценарий | Описание | Статус |
|----------|----------|--------|
| E01_bootstrap | telemetry + online | ✅ Создан |
| E02_command_happy | command→DONE + WS + zone_events | ✅ Создан |
| E04_error_alert | error→alert dedup + WS + zone_events | ✅ Создан |
| E05_unassigned_attach | temp error→unassigned→attach→alert | ✅ Создан |
| E07_ws_reconnect_snapshot_replay | snapshot+events догоняют gap | ✅ Создан |

---

## Критические типы багов (для исправления)

### 1. Несоответствие топиков (normal/temp)
**Проверка:**
- node-sim использует правильные топики в зависимости от mode
- Backend обрабатывает оба типа топиков

### 2. Потеря cmd_id
**Проверка:**
- Команда содержит cmd_id
- command_response содержит тот же cmd_id
- Идемпотентность работает корректно

### 3. Не создаётся alert / не пушится WS
**Проверка:**
- Ошибки от node-sim создают alerts в БД
- WS события отправляются через Reverb
- Frontend получает события

### 4. Unassigned не сохраняется или не attach'ится
**Проверка:**
- temp_error сохраняется в unassigned_node_errors
- После attach ошибки переносятся в alerts
- Архив работает корректно

### 5. Snapshot не возвращает корректный last_event_id или replay нарушает порядок
**Проверка:**
- `/api/zones/{id}/snapshot` возвращает last_event_id
- `/api/zones/{id}/events?after_id={id}` возвращает события в правильном порядке
- Gap закрывается корректно

---

## Выходные артефакты

### ✅ Создано:
- ✅ `tests/node_sim/` - полный пакет эмулятора
- ✅ `tests/e2e/docker-compose.e2e.yml` + `.env.e2e.example`
- ✅ `tests/e2e/runner/` - раннер framework
- ✅ `tests/e2e/scenarios/*.yaml` - все сценарии
- ✅ `tools/testing/run_e2e.sh` - one-command entrypoint
- ✅ `docs/testing/NODE_SIM.md` - документация
- ✅ `docs/testing/E2E_GUIDE.md` - документация
- ✅ `docs/testing/TROUBLESHOOTING.md` - документация

### ⚠️ Требует проверки:
- ⚠️ `tests/e2e/reports/` - генерируемые отчёты (JUnit + JSON timeline)
- ⚠️ Стабильность всех сценариев (10 прогонов подряд)

---

## Следующие шаги

### 1. Проверить и исправить E2E runner
- [ ] Убедиться, что все типы шагов поддерживаются
- [ ] Добавить поддержку start_simulator / stop_simulator
- [ ] Добавить поддержку publish_mqtt
- [ ] Проверить обработку переменных окружения

### 2. Запустить первый прогон
```bash
cd tests/e2e
docker compose -f docker-compose.e2e.yml up -d
python runner/e2e_runner.py scenarios/E01_bootstrap.yaml
```

### 3. Исправить найденные баги
- [ ] Зафиксировать каждый баг (лог + артефакт + место в коде)
- [ ] Внести правку в соответствующий сервис
- [ ] Добавить регрессионную проверку
- [ ] Прогнать снова

### 4. Довести до зелёного состояния
- [ ] Все сценарии E01, E02, E04, E05, E07 проходят
- [ ] Стабильность проверена (10 прогонов подряд)
- [ ] Отчёты генерируются корректно

### 5. Финальная проверка
```bash
./tools/testing/run_e2e.sh
# → должен быть полностью зелёный
```

---

## Команды для проверки

### Поднять стенд
```bash
cd tests/e2e
docker compose -f docker-compose.e2e.yml up -d
```

### Проверить readiness
```bash
curl http://localhost:8081/api/system/health
curl http://localhost:9302/health
docker logs node-sim | grep "Connected to MQTT"
```

### Запустить тест
```bash
python tests/e2e/runner/e2e_runner.py tests/e2e/scenarios/E01_bootstrap.yaml
```

### One-command запуск
```bash
./tools/testing/run_e2e.sh
```

---

## Примечания

- Все сервисы должны быть healthy перед запуском тестов
- node-sim должен быть подключен к MQTT
- База данных должна быть инициализирована (миграции выполнены)
- Переменные окружения должны быть настроены

---

## Статус: 70% готово

**Выполнено:**
- ✅ Инфраструктура (docker-compose, node-sim, runner)
- ✅ Сценарии созданы
- ✅ One-command entrypoint

**Требует работы:**
- ⚠️ Интеграция и проверка runner с реальными сценариями
- ⚠️ Исправление найденных багов
- ⚠️ Доведение до стабильного зелёного состояния

