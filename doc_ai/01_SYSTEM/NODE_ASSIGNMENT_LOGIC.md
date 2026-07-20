# Логика привязки ноды к зоне

**Дата:** 2026-07-20


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## Изменение логики

### Старая логика:
1. При установке `zone_id` нода сразу переводилась в `ASSIGNED_TO_ZONE`
2. Конфиг публиковался асинхронно через событие
3. Если публикация не удалась, нода все равно считалась привязанной

### Новая логика (pending bind + wire confirmation):
1. UI / swap выставляют `pending_zone_id`, оставляя `zone_id = null` и lifecycle `REGISTERED_BACKEND`
2. Laravel публикует целевой NodeConfig через `PublishNodeConfigJob` (часто на temp topic при bind)
3. Нода применяет конфиг и публикует `config_report` из целевого namespace
4. **Только после observed `config_report` с совпавшим `gh_uid/zone_uid`** Laravel делает `pending_zone_id → zone_id` и `ASSIGNED_TO_ZONE`

---

## Измененные файлы

### 1. NodeService::update()
- UI bind/rebind всегда через `pending_zone_id` (не пишет `zone_id` напрямую)
- Нода остаётся в `REGISTERED_BACKEND` до получения `config_report`

### 2. history-logger::handle_config_report
- Обрабатывает `config_report` от ноды
- Сохраняет `nodes.config`, синхронизирует `node_channels`
- Сообщает Laravel observed-факт `config_report`

### 3. NodeConfigReportObserverService
- Laravel-owner сервис финализации bind/rebind
- Проверяет совпадение `gh_uid/zone_uid` с целевой зоной
- Выполняет `pending_zone_id -> zone_id`
- Переводит ноду в `ASSIGNED_TO_ZONE`

### 4. NodeRegistryService::registerNodeFromHello()
- Убрана автоматическая установка `ASSIGNED_TO_ZONE`
- Всегда оставляет ноду в `REGISTERED_BACKEND`

### 5. NodeSwapService
- Swap идёт тем же pending-контрактом: новый узел получает `pending_zone_id`, `zone_id = null`
- Старый узел: best-effort firmware unbind (NodeConfig `gh-temp`/`zn-temp`) **до** очистки `zone_id`, затем `DECOMMISSIONED` + mirror temp в `nodes.config`
- Финализация нового узла — только через `config_report`

### 6. PublishNodeConfigJob + PublishNodeConfigOnUpdate
- Публикация MQTT NodeConfig при `pending_zone_id && !zone_id` (bind/rebind/swap)
- Temp topic используется на этапе привязки, пока нода ещё не в целевом namespace

### 7. nodes:expire-pending-bindings
- Janitor TTL (`config('hydro.pending_bind_ttl_minutes')`, default 30) очищает зависший `pending_zone_id`
- Якорь времени: `nodes.pending_zone_set_at`
- Retry: повторный UI assign (`PATCH zone_id`) заново ставит pending и публикует конфиг

### 8. Frontend (Add.vue)
- Обновлено сообщение об успешной привязке
- Показывает ожидание `config_report` от ноды

---

## Поток привязки ноды

1. Пользователь привязывает ноду к зоне через UI (или swap)
2. `NodeService::update()` / `NodeSwapService` ставят `pending_zone_id`, `zone_id = null`, lifecycle `REGISTERED_BACKEND`
3. `DeviceNode` → `NodeConfigUpdated` → `PublishNodeConfigOnUpdate` → `PublishNodeConfigJob` публикует NodeConfig (bind: temp topic)
4. Нода применяет конфиг и публикует `config_report` в `hydro/{gh}/{zone}/{node}/config_report`
5. **history-logger обрабатывает `config_report`:**
   - сохраняет NodeConfig и синхронизирует каналы
   - сообщает Laravel observed-факт
6. **Laravel завершает bind/rebind:**
   - валидирует namespace observed `config_report`
   - переводит `pending_zone_id -> zone_id`
   - переводит ноду в `ASSIGNED_TO_ZONE`
7. Нода считается привязанной

---

## Преимущества

1. ✅ Нода считается привязанной только после `config_report` из целевого namespace
2. ✅ Сервер публикует целевой NodeConfig для bootstrap bind (temp topic), но не считает bind завершённым без wire ACK
3. ✅ Swap не обходит pending-контракт
4. ✅ Зависший pending (offline / namespace mismatch) истекает по TTL с алертом и возможностью retry

---

## Важные замечания

- Нода должна быть в состоянии `REGISTERED_BACKEND` (или допустимом для rebind) для привязки к зоне
- `zone_id` без подтверждения с провода — запрещён (fail-closed)
- Повторная привязка после TTL/expire — через UI assign / publish-config retry
