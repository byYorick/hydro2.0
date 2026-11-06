# Быстрый старт для разработчиков

## 📚 Документация

Поведение runtime определяется кодом. Защищённые контракты описаны в `doc_ai/`
и должны совпадать с реализацией; правила сверки — в
[`doc_ai/DEV_CONVENTIONS.md`](doc_ai/DEV_CONVENTIONS.md).

### Ключевые документы

- **📖 Начните с:** `doc_ai/INDEX.md` — главный индекс документации
- **Архитектура системы:** `doc_ai/SYSTEM_ARCH_FULL.md`
- **Пайплайны и инварианты AE3:** `doc_ai/ARCHITECTURE_FLOWS.md`
- **Структура проекта:** `doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`
- **Конвенции разработки:** `doc_ai/DEV_CONVENTIONS.md`

### Специфические документы

- **Backend (Laravel):** `doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`
- **Python-сервисы:** `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
- **AE3 (automation-engine):** `doc_ai/04_BACKEND_CORE/ae3lite.md`
- **Firmware (ESP32):** `doc_ai/02_HARDWARE_FIRMWARE/`
- **NodeConfig:** `firmware/NODE_CONFIG_SPEC.md`
- **MQTT:** `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- **Frontend:** `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md`
- **Android:** `doc_ai/12_ANDROID_APP/`
- **Тестирование / E2E:** `doc_ai/13_TESTING/`

---

## 🚀 Быстрый запуск

### Backend (Laravel + Python-сервисы)

```bash
make up
make migrate
```

Опционально: `make up-obs` — мониторинг (profile `obs`);
`make up-sim` — digital-twin + node-sim-manager (profile `sim`);
`make up-ml` — feature-builder (profile `ml`). Они не входят в обычный `make up`.

Для полного чистого dev-refresh с удалением volume, сервисных image и пересборкой без cache.
После `refresh` в local dev в БД остаются только `admin@example.com` и `agronomist@example.com`:

```bash
make refresh
```

Сервисы (dev, `backend/docker-compose.dev.yml`):
- Laravel: http://localhost:8080
- mqtt-bridge: http://localhost:9000
- history-logger REST: http://localhost:9300
- history-logger metrics: http://localhost:9300/metrics
- automation-engine REST: http://localhost:9405
- automation-engine metrics: http://localhost:9405/metrics
- Laravel scheduler-dispatch metrics: http://localhost:8080/api/system/scheduler/metrics

Поток команд к узлам (инвариант): `Laravel scheduler-dispatch → automation-engine → history-logger (POST /commands) → MQTT → ESP32` — см. `doc_ai/ARCHITECTURE_FLOWS.md`.

### Просмотр логов

```bash
make logs-core      # laravel + automation-engine + history-logger + mqtt-bridge
make logs-ae        # automation-engine
make logs-hl        # history-logger
make logs-laravel   # laravel
make logs-mqttb     # mqtt-bridge
```

Оператор запускает workflow через Laravel UI/API. Внутренние AE3 ingress требуют
сервисной авторизации и `X-Trace-Id`; их контракт —
[`ae3lite.md`](doc_ai/04_BACKEND_CORE/ae3lite.md). Health-check ниже не запускает актуаторы.

### Проверка работы

```bash
# После make up и make migrate; команды выполняются на хосте.
curl --fail --silent --show-error http://localhost:9300/health
curl --fail --silent --show-error http://localhost:9405/health/live
curl --fail --silent --show-error http://localhost:9405/health/ready
curl --fail --silent --show-error http://localhost:9000/metrics > /dev/null
```

Ожидается HTTP 200. При ошибке readiness проверьте миграции и `make logs-core`.
`mqtt-bridge` — ops probe: его command/config routes удалены и возвращают 404.
Функциональный запуск полива проверяется отдельно на подготовленной зоне через
Laravel/AE3, с учётом авторизации, готовности нод и lease gate; см.
[`REST_API_REFERENCE.md`](doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md).

---

## 📁 Структура проекта

```
hydro2.0/
├── doc_ai/          # Source of truth документации (единственный)
├── backend/         # Backend сервисы
│   ├── laravel/     # Laravel приложение (API Gateway)
│   └── services/    # Python-сервисы (history-logger, automation-engine, mqtt-bridge)
├── firmware/        # Прошивки ESP32
├── mobile/          # Мобильное приложение
├── infra/           # Инфраструктура
├── tools/           # Утилиты
├── tests/           # E2E и интеграционные тесты
└── configs/         # Конфигурации
```

---

## 🔍 Поиск информации

### Где найти информацию о...

- **Архитектуре системы:** `doc_ai/SYSTEM_ARCH_FULL.md`
- **Python-сервисах:** `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
- **NodeConfig:** `firmware/NODE_CONFIG_SPEC.md`
- **MQTT протоколе:** `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- **Backend API:** `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`
- **Firmware структуре:** `doc_ai/02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md`

---

## ⚠️ Важные замечания

1. **Спецификации системы** находятся в `doc_ai/`; README, quickstart и проектные skills ссылаются на них.
2. **При несоответствиях** сверяем код и защищённый контракт: исправляем устаревший документ или явно исправляем реализацию по правилам `AGENTS.md`.
3. **Статусы компонентов** указаны в README файлах (PLANNED, MVP_DONE и т.д.)
4. **MQTT_EXTERNAL_HOST**: в dev по умолчанию используется `host.docker.internal`;
   для ESP32 в реальной сети укажите IP хоста в `MQTT_EXTERNAL_HOST` (на Linux может
   понадобиться явная настройка `host.docker.internal` или явный IP)
5. **Команды узлам** идут только через `history-logger` — не публиковать MQTT напрямую из Laravel/AE

## 🛠️ Разработка

### Добавление нового компонента

1. Изучить документацию в `doc_ai/`
2. Создать компонент согласно документации
3. Обновить соответствующий README с ссылками на документацию
4. Указать статус (PLANNED, IN_PROGRESS, MVP_DONE)

### Работа с ИИ-агентами

См. `doc_ai/TASKS_FOR_AI_AGENTS.md` и `doc_ai/DEV_CONVENTIONS.md`

---

## 📞 Полезные ссылки

- Полная архитектура: `doc_ai/SYSTEM_ARCH_FULL.md`
- Конвенции: `doc_ai/DEV_CONVENTIONS.md`
