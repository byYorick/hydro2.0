# IMPLEMENTATION_STATUS.md

Краткая сводка статуса. **Не SoT runtime** — поведение смотреть в коде.

Product-gaps и агро-автономия: [`AGRO_AUTONOMY_MASTER_PLAN.md`](AGRO_AUTONOMY_MASTER_PLAN.md) (`plan`, не SoT runtime).

Легенда:

| Метка | Значение |
|-------|----------|
| **live** | есть в default runtime / рабочем коде |
| **planned** | спецификация или намерение; не выдавать за готовое |
| **frozen** | код или доки есть, но не default `make up` и не расширять без запроса |

---

## live

| Слой | Что в коде |
|------|------------|
| Laravel | API Gateway, Sanctum, Inertia/Vue, NodeConfig, recipes, scheduler-dispatch |
| Python core (боевое ядро default `make up`) | mqtt, db, redis, laravel, `history-logger` (единственный MQTT-publish команд), `automation-engine`/`ae3lite`, `telemetry-aggregator` |
| `mqtt-bridge` | **ops leftover / probe**, не боевой command path (410 на command-роутах zones/nodes до P1) |
| Firmware | `ph`/`ec`/`climate`/`pump`/`storage_irrigation`/`relay` + `light_node` **как сенсор** (`LIGHT`) + `test_node` — **MVP_DONE** |
| Frontend | Unified Dashboard, Zones/Devices/Recipes/Alerts, WebSocket |
| Data/ops | PostgreSQL+Timescale, retention 30d raw, backups; Grafana/Prometheus — **ops** (пока ещё в default compose; вынос в profile `obs` = P3) |
| Android | `mobile/app/android/` — **IN_PROGRESS** (login, greenhouses/zones, telemetry, alerts, `sendCommand`, provisioning scaffold) |

HW-стенд / полный HW acceptance нод — **IN_PROGRESS** (не путать с отсутствием прошивок).

---

## planned

| Тема | Заметка |
|------|---------|
| OTA | schema `firmware_files` + `OTA_UPDATE_PROTOCOL.md`; pipeline Laravel/HL/`ota_engine` нет |
| `light_node` actuator | PWM/WS2811 **не** в текущей прошивке |
| pump dry-run guards | не реализованы |
| climate аварии/пороги | PLANNED |
| Android | Clean Architecture / node-details / MQTT-клиент / internal testing |
| AI Panel | чат/advanced recommend; сейчас overlay/toy: `AIPredictionsSection` + linear `PredictionService` — **не** ML pipeline |
| FE тесты | Recipes pages, Devices/Show, WebSocket — PLANNED |
| UI extras | theme switcher, hotkeys, pin zones |

---

## frozen

| Тема | Заметка |
|------|---------|
| `digital-twin`, `node-emulator` | код/доки есть; **не** часть default `make up` |
| `feature-builder` | **frozen skeleton**; не writer витрин в runtime; не часть default `make up` (profile `ml`) |
| `/admin`, `/admin/zones`, `/admin/recipes` | overlay/дубль Unified Dashboard + Settings; код пока жив (удаление = P4) |
| AI-карточки (`AIPredictionsSection`, linear `PredictionService`) | overlay/toy, не ML pipeline |
| `09_AI_AND_DIGITAL_TWIN` | `plan` / engine draft, не default runtime |
| отдельный Python `scheduler` / `device-registry` / `api-gateway` | деревья сняты; owner — Laravel |
