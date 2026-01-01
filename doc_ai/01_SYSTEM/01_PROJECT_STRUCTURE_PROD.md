# Спецификация структуры боевого проекта `hydro2.0`

## 0. Цели и принципы

Боевой проект `hydro2.0` — это монорепозиторий, содержащий:

- прошивки всех нод на ESP32 (чистый C, ESP-IDF, `sdkconfig`),
- backend-сервисы (API, MQTT-мост, логика автоматизации),
- мобильное приложение,
- инфраструктуру (деплой, мониторинг, Grafana),
- полную документацию и спецификации.

**Принципы:**

1. **Одна точка входа**: вся система собирается и настраивается из одного репозитория.
2. **Ясное разделение слоёв**: `firmware / backend / mobile / infra / docs`.
3. **Повторяемость сборки**: всё описано через конфиги и скрипты (`Makefile`, `CMake`, `docker-compose`, `terraform` и т.д.).
4. **Конфиг через файлы, не код**: `*.yaml` / `*.json` для нод, MQTT, правил автоматизации и т.п.
5. **Масштабируемость**: новая нода/тип ноды добавляется по одному шаблону.

---

## 1. Общий обзор директорий

Структура корня монорепо:

```text
hydro2.0/
├─ ../               # Документация и спецификации (эталонная)
├─ docs/                  # Mirror документации (опционально, для совместимости)
├─ firmware/              # Прошивки для всех нод на ESP32
├─ backend/               # Backend-сервисы, API, MQTT-мост
├─ mobile/                # Мобильное приложение
├─ infra/                 # Инфраструктура и деплой
├─ tools/                 # Скрипты, утилиты, генераторы
├─ configs/               # Общие конфиги проекта (JSON/YAML)
├─ .gitignore
├─ README.md
└─ Makefile               # Сборка верхнего уровня (опционально)
```

Дальше — детали по каждому блоку.

---

## 2. `../` — документация и спеки

**Примечание:** Основная документация находится в `../`. Папка `docs/` может существовать как mirror для совместимости, но эталоном является `../`.

```text
../
├─ 01_SYSTEM/
│  ├─ LOGIC_ARCH.md
│  ├─ DATAFLOW_FULL.md
│  ├─ NODE_LIFECYCLE_AND_PROVISIONING.md
│  ├─ 01_PROJECT_STRUCTURE_PROD.md
│  └─ ...
├─ 02_HARDWARE_FIRMWARE/
│  ├─ HARDWARE_ARCH_FULL.md
│  ├─ NODE_ARCH_FULL.md
│  ├─ NODE_TYPES.md               # Описание типов нод (pH, EC, климат, насосы и т.д.)
│  ├─ NODE_LOGIC_FULL.md          # Логика работы нод
│  ├─ NODE_CONFIG_SPEC.md
│  └─ ...
├─ 03_TRANSPORT_MQTT/
│  ├─ MQTT_SPEC_FULL.md
│  ├─ BACKEND_NODE_CONTRACT_FULL.md
│  ├─ MQTT_NAMESPACE.md
│  └─ ...
├─ 04_BACKEND_CORE/
│  ├─ BACKEND_ARCH_FULL.md
│  ├─ PYTHON_SERVICES_ARCH.md
│  ├─ API_SPEC_FRONTEND_BACKEND_FULL.md
│  ├─ REST_API_REFERENCE.md
│  └─ ...
├─ 05_DATA_AND_STORAGE/
│  ├─ DATA_MODEL_REFERENCE.md
│  ├─ TELEMETRY_PIPELINE.md
│  ├─ DATA_RETENTION_POLICY.md
│  └─ ...
├─ 06_DOMAIN_ZONES_RECIPES/
│  ├─ ZONE_CONTROLLER_FULL.md
│  ├─ RECIPE_ENGINE_FULL.md
│  ├─ SCHEDULER_ENGINE.md
│  ├─ EVENTS_AND_ALERTS_ENGINE.md
│  └─ ...
├─ 07_FRONTEND/
│  ├─ FRONTEND_ARCH_FULL.md
│  ├─ FRONTEND_UI_UX_SPEC.md
│  └─ ...
├─ 08_SECURITY_AND_OPS/
│  ├─ SECURITY_ARCHITECTURE.md
│  ├─ AUTH_SYSTEM.md
│  ├─ LOGGING_AND_MONITORING.md
│  ├─ OPERATIONS_GUIDE.md
│  └─ ...
├─ 09_AI_AND_DIGITAL_TWIN/
│  ├─ AI_ARCH_FULL.md
│  ├─ DIGITAL_TWIN_ENGINE.md
│  └─ ...
├─ 10_AI_DEV_GUIDES/
│  ├─ TASKS_FOR_AI_AGENTS.md
│  └─ PROMPTS_LIBRARY.md
├─ 11_LEGACY_ARCHIVES/
│  └─ ...                         # Исторические архивы документации
├─ 12_ANDROID_APP/
│  ├─ ANDROID_APP_ARCH.md
│  ├─ ANDROID_APP_SCREENS.md
│  ├─ ANDROID_APP_API_INTEGRATION.md
│  └─ ...
├─ INDEX.md                       # Главный индекс документации
└─ README_STRUCTURE.md            # Описание структуры папок
```

**Боевой проект** подразумевает, что все ключевые `.md` из этих папок **заполнены полностью** и согласованы между собой.

---

## 3. `firmware/` — прошивки ESP32

Здесь живут все ESP-прошивки, на чистом C, под ESP-IDF.

```text
firmware/
├─ nodes/
│  ├─ common/                  # Общие библиотеки и компоненты для всех нод
│  │  ├─ components/
│  │  │  ├─ i2c_bus/
│  │  │  ├─ ina209/
│  │  │  ├─ oled_ui/           # OLED дисплей UI
│  │  │  ├─ sensors/            # pH, EC, SHT3x, CCS811, lux и т.д.
│  │  │  │  ├─ ph_sensor/
│  │  │  │  ├─ trema_ph/
│  │  │  │  ├─ ec_sensor/
│  │  │  │  ├─ trema_ec/
│  │  │  │  ├─ sht3x/
│  │  │  │  └─ ina209/
│  │  │  ├─ mqtt_client/       # MQTT клиент
│  │  │  ├─ mqtt_manager/       # MQTT менеджер
│  │  │  ├─ wifi_manager/       # Wi-Fi менеджер
│  │  │  ├─ config_storage/    # Загрузка NodeConfig из NVS/JSON
│  │  │  ├─ logging/
│  │  │  ├─ setup_portal/       # Setup portal для provisioning
│  │  │  └─ oled_ui/            # OLED UI
│  │  └─ README.md
│  ├─ pump_node/               # Нода насосов с INA209
│  │  ├─ main/
│  │  │  ├─ main.c
│  │  │  ├─ pump_node_app.c
│  │  │  └─ pump_node_tasks.c
│  │  ├─ components/           # Специфические компоненты, если нужны
│  │  ├─ sdkconfig.defaults
│  │  ├─ CMakeLists.txt
│  │  └─ Kconfig
│  ├─ ph_node/
│  │  ├─ main/
│  │  │  ├─ main.c
│  │  │  └─ ph_node_app.c
│  │  ├─ components/
│  │  ├─ sdkconfig.defaults
│  │  ├─ CMakeLists.txt
│  │  └─ Kconfig
│  ├─ ec_node/
│  │  ├─ main/
│  │  │  ├─ main.c
│  │  │  └─ ec_node_app.c
│  │  ├─ components/
│  │  ├─ sdkconfig.defaults
│  │  ├─ CMakeLists.txt
│  │  └─ Kconfig
│  ├─ climate_node/            # Температура/влажность/CO₂/освещение
│  ├─ root_node/               # Корень ESP-MESH (если корень тоже ESP)
│  └─ ...
├─ tools/
│  ├─ flash_all.sh             # Примеры скриптов прошивки
│  └─ gen_node_config.py       # Генерация NodeConfig из JSON / шаблонов
└─ README.md
```

**Ключевые моменты боевой структуры:**

1. **Общие компоненты** (датчики, INA209, дисплей, MQTT, Wi-Fi, config) живут в `firmware/nodes/common/components/`.
2. Каждая нода — отдельный ESP-IDF-проект в `firmware/nodes/<node_type>/`.
3. Для каждой ноды:
   - есть `sdkconfig.defaults` с боевыми дефолтами,
   - есть `Kconfig` для выбора настроек,
   - есть `NodeConfig` (через JSON/NVS) для параметров: ID ноды, тип, каналы, предельные токи, пороги pH/EC и т.п.
4. Вся логика **подтверждения команд насосной нодой через INA209** реализуется в `pump_node_app.c` / `pump_node_tasks.c` с использованием компонента `ina209`.

---

## 4. `backend/` — серверная часть

```text
backend/
├─ laravel/                     # Laravel-приложение (выполняет роль API Gateway)
│  ├─ app/
│  ├─ routes/
│  ├─ tests/
│  └─ ...
├─ services/
│  ├─ api-gateway/             # LEGACY / NOT USED — роль API Gateway выполняет Laravel
│  │  ├─ README.md             # Описание legacy статуса
│  │  └─ Dockerfile            # Placeholder
│  ├─ mqtt-bridge/             # MQTT-мост: подписка на ноды, публикация команд
│  │  ├─ main.py               # Основной код (FastAPI)
│  │  ├─ publisher.py           # Публикация в MQTT
│  │  ├─ requirements.txt
│  │  ├─ Dockerfile
│  │  └─ README.md
│  ├─ device-registry/         # LEGACY / NOT USED — функционал реализован в Laravel
│  ├─ automation-engine/       # Правила автоматизации (по расписанию/датчикам)
│  ├─ history-logger/          # Логирование телеметрии в БД/TSDB
│  └─ common/                  # Общие библиотеки для Python-сервисов (модели, DTO, клиенты MQTT/БД)
├─ configs/
│  ├─ dev/
│  │  ├─ mqtt.yaml
│  │  ├─ db.yaml
│  │  └─ ...
│  ├─ prod/
│  │  ├─ mqtt.yaml
│  │  ├─ db.yaml
│  │  └─ ...
│  └─ staging/
├─ docker-compose.dev.yml      # Локальный стенд (MQTT, БД, backend-сервисы)
├─ docker-compose.prod.yml
└─ README.md
```

**Минимальный набор боевых сервисов:**

- `Laravel` (выполняет роль API Gateway и Device Registry):
  - REST API для фронтенда и мобильного приложения (`/api/*`);
  - WebSocket/Realtime обновления (Laravel Reverb);
  - Управление конфигурацией (зоны, ноды, рецепты);
  - Реестр устройств: хранение информации о нодах (ID, тип, конфиг каналов, пороги, лимиты тока);
  - Авторизация и управление пользователями.
- `mqtt-bridge`:
  - подписывается на `node/+/+/telemetry`, `node/+/+/command_response`;
  - публикует `node/+/+/command`;
  - валидирует и логирует всё, что идёт от/к нодам.
- `automation-engine`:
  - принимает события (`telemetry`, `command_response`);
  - решает, когда включить насос/свет/климат в зависимости от состояния.
- `history-logger`:
  - пишет телеметрию в БД/TSDB (InfluxDB, PostgreSQL + Timescale и т.п.).

**Примечание:** Сервисы `api-gateway` и `device-registry` помечены как LEGACY / NOT USED — их функционал полностью реализован в Laravel.

---

## 5. `mobile/` — мобильное приложение

```text
mobile/
├─ app/                        # Исходники приложения (например, Flutter/React Native)
│  ├─ lib/                     # Или src/ — в зависимости от стека
│  ├─ assets/
│  ├─ android/
│  ├─ ios/
│  └─ ...
├─ configs/
│  ├─ env.dev.json
│  ├─ env.staging.json
│  └─ env.prod.json
└─ README.md
```

**Боевой минимум:**

- экран списка нод и их статуса,
- детальный экран ноды:
  - текущие значения датчиков,
  - состояние насосов,
  - последние `command_response` (в том числе ошибки по току INA209),
- экран графиков (агрегация из backend, не напрямую из MQTT),
- экран настроек Wi-Fi / привязки ноды (через root/ESP-mesh или локальный AP ноды).

---

## 6. `infra/` — инфраструктура и деплой

```text
infra/
├─ docker/
│  ├─ mqtt-broker/             # Конфиги MQTT-брокера
│  ├─ grafana/
│  ├─ influxdb/                # или другая TSDB
│  └─ ...
├─ k8s/                        # Манифесты, если используется Kubernetes
│  ├─ namespaces/
│  ├─ deployments/
│  ├─ services/
│  └─ ingress/
├─ terraform/                  # Описание облачной инфраструктуры
├─ ansible/                    # Конфиги для bare-metal / VPS
└─ README.md
```

**Боевой минимум:**

- конфигурация MQTT-брокера (кластер/HA — по мере необходимости),
- развёртывание backend-сервисов,
- TSDB + Grafana (готовые dashboards),
- централизованный логинг (например, Loki/ELK).

---

## 7. `configs/` — общие конфиги системы

```text
configs/
├─ nodes/
│  ├─ pump_node_template.json
│  ├─ ph_node_template.json
│  ├─ ec_node_template.json
│  ├─ climate_node_template.json
│  └─ ...
├─ mesh/
│  ├─ wifi_provisioning.yaml   # Настройки первого подключения Wi-Fi/mesh
│  └─ mesh_topology.yaml
├─ automation/
│  ├─ rules_default.yaml       # Правила по умолчанию
│  └─ rules_examples.yaml
└─ security/
   ├─ tls_mqtt_example.md
   └─ keystore_structure.md
```

**Идея:** все ноды читают свои параметры из `NodeConfig` (JSON/CBOR), структура которого описана в `../02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md`. Backend и тулзы умеют генерировать/валидировать эти конфиги.

---

## 8. `tools/` — утилиты и генераторы

```text
tools/
├─ gen_node_config/
│  ├─ gen_node_config.py
│  └─ schemas/                 # JSON Schemas для валидации
├─ import_grafana_dashboards.py
├─ mqtt_debug_client.py
├─ stress_test_scenarios/
└─ README.md
```

**Роль:** помочь запускать боевой проект быстро и без ручного шаманства:
- генерация NodeConfig,
- импорт/обновление дашбордов Grafana,
- отладочные MQTT-клиенты.

---

## 9. Git-ветки, версии и среды

Рекомендуемый минимальный набор:

- `main` — стабильный боевой код,
- `develop` — интеграция новых фич перед релизом,
- `feature/*` — ветки фич.

**Переменные сред (env):**

- `DEV` — локальная разработка,
- `STAGING` — предбоевой стенд (максимально похож на prod),
- `PROD` — реальный прод.

Все сервисы (firmware, backend, mobile) должны уметь явно понимать окружение через конфиги/флаги.

---

## 10. Чек-лист “боевой готовности”

Проект можно считать **боевым**, если:

1. В `../` заполнены и согласованы:
   - `../../docs/01_OVERVIEW/SYSTEM_OVERVIEW.md`,
   - все ключевые спеки по нодам, MQTT и backend,
   - индексы и README отражают текущую структуру и код.
2. В `firmware/`:
   - есть рабочие проекты `pump_node`, `ph_node`, `ec_node`, `climate_node`,
   - реализован и протестирован `ina209`-драйвер,
   - насосная нода **гарантированно**:
     - включает насос по команде,
     - меряет ток через INA209,
     - отдаёт `command_response` с `ACK/ERROR` и кодами ошибок (`current_not_detected`, `overcurrent`, и т.д.),
     - уходит в `SAFE_MODE` при критических ситуациях.
3. В `backend/`:
   - поднят MQTT-мост и он строго следует `../03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`,
   - есть device-registry, automation-engine и history-logger,
   - настроено логирование и базовый мониторинг.
4. В `mobile/`:
   - можно:
     - видеть список нод,
     - смотреть телеметрию,
     - инициировать команды (в т.ч. на насосы),
     - видеть результат (успех/ошибки по току).
5. В `infra/`:
   - есть сценарий развёртывания (docker-compose или k8s),
   - подняты MQTT, БД/TSDB, Grafana,
   - есть хотя бы один преднастроенный dashboard.
6. В `configs/`:
   - есть валидные шаблоны NodeConfig для всех типов нод,
   - есть правила автоматизации по умолчанию (даже простые).
