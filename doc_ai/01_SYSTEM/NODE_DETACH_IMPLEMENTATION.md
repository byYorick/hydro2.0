# Реализация отвязки ноды от зоны

**Дата:** 2026-07-20


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## Канонический unbind (v1)

**Канон:** NodeConfig temp namespace — `gh_uid=gh-temp`, `zone_uid=zn-temp` через history-logger `POST /nodes/{uid}/config` в **текущий** zone-топик.

Пути, использующие один и тот же `NodeFirmwareUnbindService`:

| Операция | Когда публикуется |
|----------|-------------------|
| `NodeService::detach()` | До очистки `zone_id` |
| `NodeService::update()` (zone → null) | Best-effort после commit |
| `NodeSwapService::swapNode()` | До очистки `zone_id` у old node (decommission) |

Новый MQTT `cmd=reset_binding` **не** является каноном v1: нет HL command validation / production framework handler; добавление ломало бы пайплайн. `reset_binding` в `test_node` / `node_sim` — **sim-only** (см. mapping matrix).

---

## Реализованная функциональность

### Backend

1. **NodeService::detach()**
   - Best-effort публикует unbind NodeConfig (`gh_uid=gh-temp`, `zone_uid=zn-temp`) в **текущий** zone-топик через history-logger (`POST /nodes/{uid}/config`), пока нода ещё assigned
   - Отвязывает ноду от зоны (`zone_id = null`, `pending_zone_id = null`)
   - Зеркалит temp namespace в `nodes.config`
   - Сбрасывает `lifecycle_state` в `REGISTERED_BACKEND` через FSM
   - Чистит `channel_bindings`
   - Нода становится доступной для повторной привязки
   - Ошибка/offline HL **не блокирует** detach (см. fail-safe ниже)

2. **NodeFirmwareUnbindService**
   - Собирает NodeConfig из stored config / каналов
   - Переопределяет namespace на `gh-temp` / `zn-temp`
   - Публикует через HL на топик `hydro/{real_gh}/{real_zone}/{node_uid}/config` (нода ещё слушает старый namespace)

3. **NodeService::update()**
   - При отвязке через `zone_id = null` — тот же mirror + best-effort firmware unbind после commit

4. **NodeSwapService::swapNode()**
   - Перед decommission old node: тот же unbind publish (если был `zone_id`)
   - Mirror temp namespace в `nodes.config` old node
   - Pending-flow нового узла не затрагивается

5. **NodeController::detach()**
   - Endpoint `POST /api/nodes/{node}/detach`

### Firmware

- Production `node_config_handler`: если нода **не** в temp-режиме и приходит конфиг с `gh-temp`/`zn-temp` — конфиг **применяется** (detach/unbind), MQTT переподписывается на temp namespace (смена `gh_uid`/`zone_uid` → mqtt restart)
- Guard «игнор temp→temp» остаётся только для нод, уже находящихся в `gh-temp`/`zn-temp` (ожидание bind)
- `reset_binding` — **sim-only** (`test_node` / `node_sim`); production parity через cmd **не** planned для v1 (канон = NodeConfig)

### Fail-safe (history-logger)

- Телеметрия от ноды с `zone_id=null` и `pending_zone_id=null` дропается (`TELEMETRY_DROPPED reason=node_unassigned`, alert `infra_telemetry_node_unassigned`)
- Это страховка, если нода offline во время detach и продолжает слать в старый namespace

### Ops: retained zombie status после rebind/detach

После смены namespace на брокере часто остаётся **retained** `ONLINE` на старом топике
(`hydro/gh-temp/zn-temp/{uid}/status` или прежняя зона). Однострочник:

```bash
# сбросить retained status (пустой payload + retain)
mosquitto_pub -h localhost -p 1883 -t 'hydro/gh-temp/zn-temp/nd-test-ph-1/status' -n -r -q 1
```

Пакетная чистка по каноническому namespace из БД:

```bash
./backend/scripts/clear-zombie-mqtt-status.sh --from-db --prefix nd-test-
# dry-run: ./backend/scripts/clear-zombie-mqtt-status.sh --from-db --prefix nd-test- --dry-run
```

### Frontend

1. **Devices/Show.vue**
   - Кнопка "Отвязать от зоны", confirm, toast, reload

---

## Поток отвязки

1. Пользователь нажимает "Отвязать от зоны"
2. `POST /api/nodes/{node}/detach`
3. Backend:
   1. **Best-effort:** HL publish NodeConfig с `gh-temp`/`zn-temp` в текущий zone-топик
   2. `zone_id` / `pending_zone_id` → `null`, lifecycle → `REGISTERED_BACKEND`, mirror config, clear bindings
   3. `NodeConfigUpdated` (WS)
4. Firmware (если online): применяет конфиг → NVS/MQTT → `gh-temp`/`zn-temp`
5. Нода снова в списке новых (`/devices/add`)

---

## Особенности

- ✅ Firmware сбрасывается через существующий config path (без нового MQTT cmd / без breaking protocol)
- ✅ Detach/swap не fail-closed на MQTT: offline-нода всё равно отвязывается в БД
- ✅ HL fail-safe режет zombie telemetry в старом namespace
- ✅ После detach (`zone_id = null`, `pending_zone_id = null`) `PublishNodeConfigOnUpdate` **не** публикует bind-конфиг; unbind идёт отдельно через `NodeFirmwareUnbindService` → HL
- ✅ Bind-публикация (`pending_zone_id && !zone_id`) — отдельный путь: `PublishNodeConfigJob` → HL → MQTT temp topic (см. `NODE_ASSIGNMENT_LOGIC.md`)

### Ограничения / риски

- Offline при detach/swap → нода остаётся в старом NVS до следующего online+повторного detach/manual factory reset / успешного unbind publish
- Future (не v1): опциональный усиленный путь `reset_binding` + reboot — только если появится HL validation и common firmware handler

---

## Проверка

- PHPUnit: `NodeServiceBindingTest`, `NodeFirmwareUnbindServiceTest`, `NodeSwapServiceTest` (Http::fake → HL `/nodes/{uid}/config`)
- HL: существующий drop `node_unassigned` (см. `telemetry_processing.py`)

---

## Статус

✅ Detach/swap чистят БД **и** best-effort возвращают firmware в temp namespace
✅ Канон v1 = NodeConfig temp namespace; `reset_binding` = sim-only
