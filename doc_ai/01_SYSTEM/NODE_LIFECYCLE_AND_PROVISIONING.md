# NODE_LIFECYCLE_AND_PROVISIONING.md
# Жизненный цикл узла 2.0
# Производство • Первая настройка • Эксплуатация • Замена • Списание

Документ описывает **полный жизненный цикл** узла системы 2.0.

Он связывает:

- прошивку (ESP32),
- MQTT и backend,
- UI (OLED и Android),
- процессы эксплуатации.

## Термины (для единообразия)

- `firmware_module` — имя прошивочного ESP-IDF проекта (`ph_node`, `ec_node`, `climate_node`, `storage_irrigation_node`).
- `node_type` — тип узла в MQTT/API/БД (`nodes.type`) с каноническими значениями:
  `ph|ec|climate|irrig|light|relay|water_sensor|recirculation|unknown`.
- Имена `*_node` не используются как `node_type` в payload и базе данных.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

# 1. Состояния жизненного цикла узла

Бизнес-ориентированные состояния:

1. `MANUFACTURED` — узел произведён, прошивка записана, но не привязан к теплице.
2. `UNPROVISIONED` — нет Wi-Fi/привязки, узел в режиме AP.
3. `PROVISIONED_WIFI` — Wi-Fi настроен, но узел ещё не зарегистрирован в backend.
4. `REGISTERED_BACKEND` — узел известен backend (есть запись DeviceNode).
5. `ASSIGNED_TO_ZONE` — узел привязан к зоне/теплице.
6. `ACTIVE` — узел работает в нормальном режиме.
7. `DEGRADED` — узел работает, но с проблемами (ошибки сенсоров, нестабильная связь).
8. `MAINTENANCE` — узел переведён в режим обслуживания (возможно, временно отключен).
9. `DECOMMISSIONED` — узел списан, не должен использоваться в продакшене.

---

# 2. Идентификаторы узла

Узел имеет несколько уровней идентичности:

1. **Hardware ID**:
 - MAC-адрес Wi-Fi;
 - опциональный сериал (зашитый в прошивку/OTP).

2. **Logical Node ID**:
 - создаётся backend’ом, например: `node-1234`,
 - используется во всех API/интерфейсах.

3. **Human-Readable Name**:
 - задаётся пользователем: `PH Tank A`, `Climate Zone 1`.

Принцип:

- прошивка и MQTT оперируют **hardware-ID + optional token**;
- backend сопоставляет hardware-ID с logical ID;
- фронтенд/Android в первую очередь показывает human-friendly имя.

---

# 3. Этапы жизненного цикла

## 3.1. Производство (MANUFACTURED)

На производстве:

- шьётся базовая прошивка 2.0;
- задаются:
 - hardware-ID (MAC),
 - factory-config (канонический `node_type`: `ph|ec|climate|irrig|light|relay|water_sensor|recirculation|unknown`),
 - версия схемы NVS;
- узел проходит минимальный self-test.

Состояние после отгрузки: `UNPROVISIONED`.

---

## 3.2. Первая настройка (UNPROVISIONED → PROVISIONED_WIFI)

Этап:

1. Узел включают на объекте.
2. Прошивка не находит валидный Wi-Fi-конфиг → `WIFI_STATE_UNPROVISIONED`.
3. Узел поднимает AP (см. `../02_HARDWARE_FIRMWARE/WIFI_PROVISIONING_FIRST_RUN.md`).
4. Оператор с Android-приложения:
 - находит узел,
 - вводит Wi-Fi + привязку к теплице/зоне (или только Wi-Fi).
5. Узел сохраняет конфиг в NVS и перезапускается.

После успешного Wi-Fi-подключения: `PROVISIONED_WIFI`.

---

## 3.3. Регистрация в backend (PROVISIONED_WIFI → REGISTERED_BACKEND)

При первом выходе в интернет узел:

1. Подключается к MQTT-брокеру.
2. Публикует **registration-сообщение**, например:

```json
{
 "message_type": "node_hello",
 "hardware_id": "esp32-ABCD1234",
 "node_type": "ph",
 "fw_version": "2.0.1",
 "capabilities": ["ph", "temperature"],
 "provisioning_meta": {
 "node_name": null,
 "greenhouse_token": null,
 "zone_id": null
 }
}
```

`node_type` в `node_hello` передается только в канонической схеме (см. блок терминов выше).

### Соответствие идентификаторов

- `hardware_id` — низкоуровневый ID устройства (MAC/серийный номер), используется только для bootstrap и диагностики.
- После обработки `node_hello` backend:
 - создаёт или находит запись в таблице `nodes`;
 - генерирует строковый `uid` (например `gh1-ph-01`);
 - сохраняет его как внешний идентификатор узла.
- Этот `uid`:
 - передаётся узлу в конфигурации (NodeConfig);
 - далее используется узлом как сегмент `{node}` во всех MQTT-топиках;
 - соответствует `nodes.uid` в БД и `node_uid` в hardware-справочнике (`../02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`).

Во всех документах 2.0 под `logical_node_id` понимается именно этот строковый `uid` (`nodes.uid`), а не числовой PK `nodes.id`.

### `greenhouse_token` / `provisioning_token` (removed from bind path)

- **Статус bind-path:** removed. Токен **не используется** для привязки узла к теплице/зоне.
- Backend игнорирует поля `greenhouse_token` и `zone_id` в `provisioning_meta` (`node_hello`); фиксирует только `hardware_id`, `node_type`, `fw_version`, `node_name` / `node_uid`.
- Привязка к теплице и зоне — **только вручную** через UI/Android.
- **Колонка БД** `greenhouses.provisioning_token`: deprecated, **pending drop**. Пока остаётся NOT NULL unique (генерация при create Greenhouse — только для DB constraint / seeders; значение в `$hidden`, API не отдаёт token как способ bind). Artisan `security:check-config` напоминает о deprecation.

Backend:

- проверяет, есть ли запись с таким `hardware_id`;
- если нет → создаёт новый `DeviceNode` и задаёт `logical_node_id`;
- если есть → связывает подключение с существующим узлом;
- всегда оставляет состояние `REGISTERED_BACKEND` до ручной привязки.

---

## 3.4. Привязка к зоне (REGISTERED_BACKEND → ASSIGNED_TO_ZONE)

Привязка управляется через UI (frontend/Android) по pending-контракту
(см. `NODE_ASSIGNMENT_LOGIC.md`):

1. **Оператор выбирает зону**
2. **Backend выставляет `pending_zone_id`**, оставляя `zone_id = null`, lifecycle `REGISTERED_BACKEND`
3. **Laravel публикует целевой NodeConfig** через `PublishNodeConfigJob` → history-logger
   (часто на temp topic `hydro/gh-temp/zn-temp/{hardware_id|uid}/config`)
4. **Нода применяет конфиг** (NVS + MQTT namespace), затем публикует `config_report`
   в `hydro/{gh}/{zone}/{node}/config_report`
5. **Только после observed `config_report`** с совпавшим `gh_uid`/`zone_uid` Laravel делает
   `pending_zone_id → zone_id` и `ASSIGNED_TO_ZONE`
6. **После перехода в `ASSIGNED_TO_ZONE`** узел участвует в **зонной логике**
   (`../06_DOMAIN_ZONES_RECIPES/ZONE_CONTROLLER_FULL.md`, `../06_DOMAIN_ZONES_RECIPES/RECIPE_ENGINE_FULL.md`)

**Важно:** сервер **публикует** целевой NodeConfig для bootstrap bind; bind считается завершённым
только после `config_report` с провода. Любые `greenhouse_token`/`zone_id` из `node_hello` на привязку не влияют.

Инварианты bind/rebind:

- Повторная привязка уже привязанной ноды к **той же самой зоне** должна быть идемпотентной: `zone_id` не очищается, новый pending-cycle не открывается.
- Если нода уже находится в `pending_zone_id = target_zone`, повторный запрос на привязку считается retry того же bind-flow и не должен переводить ноду в противоречивое состояние.
- Перепривязка в **другую** зону всегда проходит через pending-state: сервер очищает текущий `zone_id`, выставляет `pending_zone_id = target_zone_id`, переводит lifecycle в `REGISTERED_BACKEND` и ждёт `config_report` из целевого namespace.
- Финализация bind/rebind выполняется только после `config_report` из целевого namespace MQTT; до этого нода не считается закреплённой за новой зоной.
- `history-logger` в этом flow выступает только observer/transport: он сохраняет `config_report` и сообщает Laravel наблюдаемый факт. Саму финализацию bind/rebind (`zone_id`, `pending_zone_id`, lifecycle) выполняет только Laravel.

### 3.4.1. FSM: сброс в `REGISTERED_BACKEND` (rebind / detach)

Канонические переходы «назад в пул незакреплённых» (только через `NodeLifecycleService`, без прямой записи `lifecycle_state`):

| Из | В | Когда |
|----|---|--------|
| `ASSIGNED_TO_ZONE` | `REGISTERED_BACKEND` | rebind в другую зону, detach, retry pending |
| `ACTIVE` | `REGISTERED_BACKEND` | rebind / detach активной ноды |
| `DEGRADED` | `REGISTERED_BACKEND` | detach деградированной ноды |
| `MAINTENANCE` | `REGISTERED_BACKEND` | detach из обслуживания |

**Единственный owner переходов lifecycle:** `NodeLifecycleService`.

- `NodeService` (UI bind/rebind/detach) → `transitionToRegistered`.
- `NodeSwapService` → `transitionToDecommissioned` / `ensureRegistered` (pending bind сохраняется: `pending_zone_id`, `zone_id=null`).
- `NodeRegistryService` (регистрация / `node_hello`) → `ensureRegistered` (путь `UNPROVISIONED → PROVISIONED_WIFI → REGISTERED_BACKEND`).
- `DeviceNode::transitionTo*()` — тонкие делегаты в `NodeLifecycleService` (FSM обязателен; запрещённый переход возвращает `false` и не меняет состояние).
- Прямое присваивание `lifecycle_state` вне `NodeLifecycleService` (и fixtures/seeders/тестов) запрещено.

Состояние: `ASSIGNED_TO_ZONE`.

---

## 3.5. Нормальная эксплуатация (ACTIVE / DEGRADED / MAINTENANCE)

В нормальном режиме:

- узел регулярно шлёт телеметрию,
- принимает команды от backend (рецепты, настройки),
- локальный UI показывает статус и измерения.

При возникновении проблем:

- backend/диагностика переводят узел в `DEGRADED`:
 - частые дисконнекты,
 - ошибки сенсоров,
 - подозрительные измерения.

Оператор может вручную перевести в `MAINTENANCE`:

- для калибровки,
- для физического обслуживания узла.

---

## 3.6. Замена ноды (node swap)

Типичный сценарий:

1. Старый узел `node-1234` вышел из строя или подлежит замене.
2. Новый узел устанавливают на его место (с новым hardware-ID).
3. В UI оператор выбирает:
 - исходный `DeviceNode` (`node-1234`),
 - новую физическую ноду (по списку доступных/новых hardware-ID).
4. Backend:
 - перепривязывает `logical_node_id` к новому hardware-ID,
 - сохраняет историю телеметрии,
 - помечает старый hardware-ID как `DECOMMISSIONED` или `MIGRATED`.

Это должно быть отражено в моделях данных (см. `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`).

---

## 3.7. Списание (DECOMMISSIONED)

При списании:

- узел помечается как `DECOMMISSIONED`,
- backend перестаёт ожидать от него телеметрию,
- любые подключения с этим hardware-ID обрабатываются как «неизвестные / вне текущего реестра».

Если физически узел ещё жив и включён, он будет рассматриваться как новый, 
и может быть переразвернут в другом месте.

---

# 4. Интеграция с UI и Android

- OLED показывает этапы:
 - BOOT, provisioning, подключение, нормальная работа, ошибки;
 - см. `../02_HARDWARE_FIRMWARE/NODE_OLED_UI_SPEC.md`.
- Android-приложение:
 - помогает в provisioning,
 - показывает список узлов и их статусы (`ACTIVE`, `DEGRADED`, и т.п.),
 - поддерживает операции `assign`, `swap`, `decommission`.

Подробности интеграции см. в документах `ANDROID_APP_*`.

---

# 5. Требования к ИИ-агенту

1. ИИ не должен менять общую структуру состояний lifecycle, может **добавлять подстатусы**.
2. Любые изменения в процессах регистрации/привязки узлов должны:
 - быть отражены в MQTT-контракте (`../03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`),
 - быть отражены в API (`../04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`),
 - обновить соответствующие схемы БД.
3. При добавлении новых типов нод нужно описать:
 - их роли в `DeviceNode`,
 - особенности привязки к зонам.

---

# 6. Статус реализации

**Дата:** 2025-11-17

## ✅ Реализовано

### 6.1. Состояния жизненного цикла
- ✅ Поле `lifecycle_state` в таблице `nodes` (enum, default: 'UNPROVISIONED')
- ✅ Enum `NodeLifecycleState` в Laravel со всеми состояниями
- ✅ Сервис `NodeLifecycleService` — **единственный owner** переходов с валидацией FSM
- ✅ Методы в модели `DeviceNode::transitionTo*()` — делегаты в `NodeLifecycleService` (не пишут state напрямую)
- ✅ `ensureRegistered()` для первичной регистрации и reset unbound-нод

**Файлы:**
- `backend/laravel/database/migrations/2025_11_17_174432_add_lifecycle_to_nodes_table.php`
- `backend/laravel/app/Enums/NodeLifecycleState.php`
- `backend/laravel/app/Services/NodeLifecycleService.php`
- `backend/laravel/app/Models/DeviceNode.php`
- `backend/laravel/app/Services/NodeService.php`
- `backend/laravel/app/Services/NodeSwapService.php`
- `backend/laravel/app/Services/NodeRegistryService.php`

### 6.2. Идентификаторы узла
- ✅ Поле `hardware_id` в таблице `nodes` (string, nullable, unique)
- ✅ Поиск узла по `hardware_id` при регистрации
- ✅ Генерация `uid` на основе `hardware_id` и типа узла

**Файлы:**
- `backend/laravel/app/Services/NodeRegistryService.php` (метод `registerNodeFromHello`)

### 6.3. Регистрация узла (node_hello)
- ✅ Обработчик `handle_node_hello` в `history-logger`
- ✅ Подписка на топики `hydro/node_hello` и `hydro/+/+/+/node_hello`
- ✅ Интеграция с Laravel API `/api/nodes/register`
- ✅ `greenhouse_token` / `provisioning_token` removed from bind path; колонка БД deprecated pending drop; привязка только вручную через UI

**Файлы:**
- `backend/services/history-logger/main.py`
- `backend/laravel/app/Services/NodeRegistryService.php`
- `backend/laravel/app/Http/Controllers/NodeController.php`

### 6.4. Замена узла (node swap)
- ✅ Сервис `NodeSwapService` для замены узлов
- ✅ API endpoint `POST /api/nodes/{node}/swap`
- ✅ Поддержка миграции истории телеметрии (опционально)
- ✅ Перепривязка каналов к новому узлу (опционально)

**Файлы:**
- `backend/laravel/app/Services/NodeSwapService.php`
- `backend/laravel/app/Http/Controllers/NodeController.php`
- `backend/laravel/routes/api.php`

---
