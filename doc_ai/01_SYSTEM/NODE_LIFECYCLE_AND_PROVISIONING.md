# NODE_LIFECYCLE_AND_PROVISIONING.md
# Жизненный цикл узла 2.0
# Производство • Первая настройка • Эксплуатация • Замена • Списание

Документ описывает **полный жизненный цикл** узла системы 2.0.

Он связывает:

- прошивку (ESP32),
- MQTT и backend,
- UI (OLED и Android),
- процессы эксплуатации.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

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
 - factory-config (тип ноды: pH/EC/климат/свет),
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

### `greenhouse_token` (устарело)

- Токен больше **не используется** для автоматической привязки теплицы/зоны при `node_hello`.
- Backend игнорирует поля `greenhouse_token` и `zone_id` в `provisioning_meta`, фиксируя только `hardware_id`, `node_type`, `fw_version` и `node_name`.
- Привязка к теплице и зоне выполняется **только вручную** через UI/Android (оператор выбирает зону и подтверждает).

Backend:

- проверяет, есть ли запись с таким `hardware_id`;
- если нет → создаёт новый `DeviceNode` и задаёт `logical_node_id`;
- если есть → связывает подключение с существующим узлом;
- всегда оставляет состояние `REGISTERED_BACKEND` до ручной привязки.

---

## 3.4. Привязка к зоне (REGISTERED_BACKEND → ASSIGNED_TO_ZONE)

Привязка управляется через UI (frontend/Android):

1. **Оператор выбирает зону и тип ноды**
2. **Backend обновляет `DeviceNode`:**
   - `zone_id`,
   - `node_role` (например, `ZONE_PH_CONTROLLER`),
   - имя
3. **Нода остается в состоянии `REGISTERED_BACKEND`**
4. **Нода подключается и отправляет `config_report`** в топик `hydro/{gh}/{zone}/{node}/config_report`
5. **Нода использует встроенный конфиг**, валидирует, сохраняет в NVS и применяет
6. **Backend обрабатывает `config_report`** и переводит ноду в `ASSIGNED_TO_ZONE`
8. **После перехода в `ASSIGNED_TO_ZONE`** узел участвует в **зонной логике** 
   (`../06_DOMAIN_ZONES_RECIPES/ZONE_CONTROLLER_FULL.md`, `../06_DOMAIN_ZONES_RECIPES/RECIPE_ENGINE_FULL.md`)

**Важно:** Переход в `ASSIGNED_TO_ZONE` происходит только после получения `config_report` от ноды. Это гарантирует, что сервер использует актуальный конфиг. Любые `greenhouse_token`/`zone_id`, присланные в `node_hello`, на привязку не влияют.

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
- любые подключения с этим hardware-ID обрабатываются как «неизвестные/legacy».

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
- ✅ Сервис `NodeLifecycleService` для управления переходами с валидацией
- ✅ Методы в модели `DeviceNode` для работы с состояниями

**Файлы:**
- `backend/laravel/database/migrations/2025_11_17_174432_add_lifecycle_to_nodes_table.php`
- `backend/laravel/app/Enums/NodeLifecycleState.php`
- `backend/laravel/app/Services/NodeLifecycleService.php`
- `backend/laravel/app/Models/DeviceNode.php`

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
- ✅ Автопривязка по `greenhouse_token` отключена; привязка выполняется только вручную через UI

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
