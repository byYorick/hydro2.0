# Realhw test_node — инструкция для ИИ-агента

**Дата обновления:** 2026-08-18  
**Статус:** Канон запуска YAML E2E на физической `firmware/test_node`  
**Локальные правила:** `tests/e2e/AGENTS.md`

Этот документ — source of truth **как агенту запускать и чинить** прогон на реальной ESP32 `test_node`.  
Контракт самой прошивки — `doc_ai/02_HARDWARE_FIRMWARE/TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md`.  
Список YAML и DoD — `tests/e2e/README.md` и `tests/e2e/scenarios/README.md`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Цель

Физическая `test_node` (один ESP32, шесть виртуальных UID `nd-test-*`) гоняет AE3 two-tank / irrigation / calibration **без node-sim**. Launcher сам поднимает e2e-стек и **останавливает** сервисы `node-sim*`.

Агент обязан:

1. Сначала сузить scope и сказать пользователю, что именно гоняет.
2. Не путать этот контур с Playwright, `tools/testing/run_e2e.sh` (node-sim) и HIL lab.
3. Не «чинить» ожидаемые ERROR и канон sequential nutrient / water baseline.

---

## 2. Три контура — не смешивать

| Контур | Compose / команда | Порты | Железо |
|--------|-------------------|-------|--------|
| **Realhw YAML** (этот документ) | `tests/e2e/docker-compose.e2e.yml` + `tests/e2e/run_automation_engine_real_hardware.sh` | Laravel **8081**, MQTT **1884**, AE **9505**, HL **9302**, PG **5433** (`hydro_e2e`) | ESP32 `test_node` |
| **YAML + node-sim** | `./tools/testing/run_e2e.sh` | те же e2e-порты | симулятор, **не** ACM0 |
| **HIL lab** | `infra/hil/docker-compose.hil.yml --profile automation` | **8080** / MQTT **1883** / AE **9405** | отдельный lab, не realhw launcher |
| **Playwright** | `backend/laravel`: `npm run e2e` | **8010** (или browser smoke **8081**) | браузер, не ESP32 |
| **Dev стек** | `backend/docker-compose.dev.yml` / `make up` | **8080** / MQTT **1883** / AE **9405** / PG **5432** (`hydro_dev`) | повседневная разработка |

Запрещено: гонять realhw launcher против HIL/dev портов; держать `node-sim` с UID `nd-test-*` на том же брокере, что и живая нода.

---

## 3. Что прочитать перед работой

Минимум:

1. Этот файл.
2. `tests/e2e/AGENTS.md`
3. `tests/e2e/README.md` (набор `--set`, список сценариев)
4. При правке прошивки/MQTT retarget: `firmware/test_node/README.md`, spec §7.2.1

По задаче:

- AE3 FSM / sequential nutrient — `doc_ai/04_BACKEND_CORE/ae3lite.md`
- Застрявший two-tank (не e2e БД) — skill `.claude/skills/two-tank-debug/SKILL.md` (**`hydro_dev:5432`**, не `hydro_e2e`)
- Lease / `set_fault_mode` — `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md`

---

## 4. Предусловия железа

Лабораторный канон (если пользователь не задал иное):

| Параметр | Значение |
|----------|----------|
| Serial | обычно `/dev/ttyACM0` (ESP32-S3) |
| Прошивка | **только** `firmware/test_node` |
| Namespace | `gh-test-1` / `zn-test-1` |
| UID | `nd-test-irrig-1`, `nd-test-ph-1`, `nd-test-ec-1`, `nd-test-soil-1`, … (`E2E_NODE_UID_REGEX=^nd-test-`) |
| Wi-Fi | та же LAN, что и хост Docker |
| MQTT host для ноды | **LAN IP хоста**, не `localhost` / `mosquitto` / `host.docker.internal` |

Чеклист до запуска:

```bash
# 1) Нода на USB
ls -l /dev/ttyACM0 /dev/ttyUSB0 2>/dev/null

# 2) Heartbeat на e2e-брокере (после retarget)
mosquitto_sub -h 127.0.0.1 -p 1884 -t 'hydro/gh-test-1/zn-test-1/#' -v
```

Если heartbeat есть на **1883**, а launcher ждёт **1884** — нода на dev-брокере. Сначала retarget (раздел 5).

Прошивать production-ноду (`pump_node`, `ph_node`, …) для этого suite **нельзя**: нет lightweight MQTT retarget, нет `set_fault_mode` seed, нет шести виртуальных UID.

---

## 5. MQTT retarget (обязательно)

Нода должна видеть брокер **с LAN**. Payload только `{mqtt:{host,port}}` **без** `channels[]`, топик зональный `hydro/{gh}/{zone}/nd-test-irrig-1/config`, **не** `hydro/system/`.

Этот путь есть **только** у `firmware/test_node`. На production firmware не слать.

```bash
# Перед realhw: e2e compose MQTT :1884
tests/e2e/scripts/retarget_test_node_mqtt.sh --e2e

# После работы: вернуть на повседневный dev :1883
tests/e2e/scripts/retarget_test_node_mqtt.sh --dev
```

Override: `TEST_NODE_GH_UID` / `TEST_NODE_ZONE_UID` / `TEST_NODE_UID` / `MQTT_EXTERNAL_HOST`.  
Если нода уже на 1884, а скрипт шлёт на 1883: `--from-port 1884`.

Ждать reboot + heartbeat на целевом порту (`--wait` при сомнении).

---

## 6. Канонический запуск

Единственный launcher:

```bash
# Сначала список — не запускать вслепую
tests/e2e/run_automation_engine_real_hardware.sh --set=ae3lite --list
tests/e2e/run_automation_engine_real_hardware.sh --set=full --list

# Узкий прогон (предпочтительно для агента)
E2E_SCENARIO_INCLUDE_REGEX='E100_ae3_two_tank_realhw_smoke' \
  tests/e2e/run_automation_engine_real_hardware.sh --set=ae3lite

# Наборы
tests/e2e/run_automation_engine_real_hardware.sh --set=ae3lite            # 15 two-tank
tests/e2e/run_automation_engine_real_hardware.sh --set=smart_irrigation   # E107–E109
tests/e2e/run_automation_engine_real_hardware.sh --set=calibration        # E110, E111, E117
tests/e2e/run_automation_engine_real_hardware.sh --set=full               # 21 = 15+3+3
```

Launcher:

- поднимает e2e compose **без** node-sim (`REAL_HW_USE_NODE_SIM_SESSION=0`);
- `stop` сервисов `node-sim`, `node-sim-workflow`, `node-sim-test-node`, `node-sim-manager`;
- discover UID по heartbeat `^nd-test-`;
- чистит зональные OPEN alerts между сценариями.

Не вызывать `python -m runner.e2e_runner` вручную для realhw, пока пользователь явно не попросил обойти launcher: discovery, bind, `reset_state` и запрет node-sim живут в скрипте.

Полный `--set=full` — десятки минут. Не стартовать его «на всякий случай».

---

## 7. Политика scope для ИИ (обязательно сказать пользователю)

Перед **любым** запуском realhw агент кратко пишет:

1. какой `--set` / regex;
2. что нода должна быть на MQTT **1884**;
3. что полный `full` не нужен, если задача — один сценарий;
4. что в анализ пойдёт **хвост лога / упавший YAML**, не полный dump.

Дальше:

- упал один сценарий → ретрай **только его** (`E2E_SCENARIO_INCLUDE_REGEX`), не весь suite;
- junit/timeline в git **не коммитить** (gitignore: `tests/e2e/tests/e2e/reports/`, `tests/e2e/reports/`);
- Playwright trace/video к этому контуру **не относятся**.

Контракты YAML **без железа** (менять сценарии / launcher — сначала они):

```bash
cd tests/e2e
./venv/bin/python -m pytest -q tests/test_realhw_launcher_contract.py \
  tests/test_ae3lite_realhw_scenario_contract.py \
  tests/test_ae3lite_realhw_seed_safety_contract.py \
  tests/test_ae3lite_pipeline_sequence_realhw_contract.py \
  tests/test_suite_catalog.py \
  tests/test_retarget_test_node_mqtt_script.py
```

---

## 8. Инварианты — не «чинить» как баги

| Симптом / идея фикса | Канон |
|----------------------|--------|
| Сидить T_full EC (~2.2) при `level_solution_max=true` на fill | Запрещено. Fill: `solution_max=false`, seed EC **~0.45**, calcium `pump_b`. Иначе `ae3_water_baseline_invalid` / `recirc_dilute_blocked_solution_max`. Helper: `scenarios/ae3lite/_two_tank_fill_helper.yaml` (`include_sequence: two_tank_fill_ca`). |
| `ec_overshoot_dilute_pct=100` «чтобы dilute всегда сработал» | Schema max 100, но канон **15**. Pct=100 только если цель теста — сам dilute (E120). |
| E103 first-run `prepare_recirculation_attempt_limit_reached` | **Ожидаемый** ERROR; чинить «чтобы first-run стал ready» нельзя. |
| E106 ждать `ae_tasks.status=completed` после mid-pipeline seed T_full | DoD — live-band телеметрии; pipeline может висеть на Mg. |
| Sequential pumps | Ca `pump_b`, Mg `pump_c`, NPK `pump_a`, micro `pump_d`. Fill — только Ca, без pH. Irrigation inline — **только pH**. |
| `set_fault_mode` на прод-узле / без `nd-test-*` | HL: lease bypass **только** `nd-test-*` или `nodes.type` ∈ {`test`,`test_node`}. Иначе 409 `ae3_zone_lease_held`. |
| Публиковать команды в MQTT из AE/Laravel/агента | Запрещено. Только history-logger `POST /commands`. Diagnostic seed в YAML идёт через HL. |
| Lightweight MQTT retarget на `ph_node`/`pump_node` | Запрещено. Только `test_node`. |
| Включить node-sim «чтобы стабильнее» | Запрещено. Смешает `nd-test-*` ответы. |
| Water baseline «с прошлого task» | Baseline только текущего task; fill-path обязателен. |

Линтер сидов: `tests/e2e/tests/test_ae3lite_realhw_seed_safety_contract.py`.

---

## 9. Диагностика падения

БД realhw — **`hydro_e2e` на localhost:5433**, пароль `hydro_e2e`. Не `hydro_dev:5432`.

```bash
# Хвост прогона (не весь файл)
tail -n 120 tests/e2e/reports/realhw_audit/*.log 2>/dev/null
# или последний вывод launcher в терминале

PGPASSWORD=hydro_e2e psql -h localhost -p 5433 -U hydro -d hydro_e2e -w -c "
SELECT id, task_type, status, current_stage, workflow_phase, updated_at
FROM ae_tasks ORDER BY created_at DESC LIMIT 8;"

# Heartbeat жив на 1884?
timeout 8 mosquitto_sub -h 127.0.0.1 -p 1884 -t 'hydro/gh-test-1/zn-test-1/+/heartbeat' -C 3 -v

docker compose -f tests/e2e/docker-compose.e2e.yml logs --tail=80 automation-engine history-logger
```

Типичные корни:

| Ошибка | Что проверить |
|--------|----------------|
| Нет discovery UID / timeout heartbeat | Нода не на 1884; Wi-Fi; namespace не `gh-test-1/zn-test-1` |
| `ae3_zone_lease_held` на seed | UID не `nd-test-*`; чужая lease; не тот HL (9302 vs 9300) |
| `ae3_water_baseline_invalid` | Fill стартовал с max ON / без низкого EC |
| `recirc_dilute_blocked_solution_max` | T_full сид в calcium при max ON |
| Смешение команд / странный DONE | Живой node-sim на 1884 — launcher должен был его stop |
| Нода «пропала» после теста | Осталась на 1884; `retarget --dev` |

---

## 10. После прогона

1. `tests/e2e/scripts/retarget_test_node_mqtt.sh --dev` — вернуть ноду на **1883**, иначе повседневный `make up` её не увидит.
2. Не коммитить `junit.xml` / `timeline.json`.
3. Пользователю: какие сценарии зелёные/красные, **одна** гипотеза и следующий узкий ретрай.

---

## 11. Наборы `--set` (счётчик)

Источник списка в коде: `AE3LITE_SCENARIOS` / `SMART_IRRIGATION_SCENARIOS` / `CALIBRATION_SCENARIOS` в `tests/e2e/run_automation_engine_real_hardware.sh`.

| Set | Состав | Кол-во |
|-----|--------|--------|
| `ae3lite` | E100, E101×2, E103–E106, E112–E116, E118, E119, E120 | 15 |
| `smart_irrigation` | E107, E108, E109 | 3 |
| `calibration` | E110, E111, E117 | 3 |
| `full` | объединение | **21** |

Live-short (не полный pipeline до T_full ready): E118 (Ca fill), E119 (Ca→pH→Mg + `PIPELINE_STEP_CHANGED`), E120 (dilute).  
Stubs `E119_*_test_node.yaml` / `E121` — **не** в realhw suite (`skip_live`).

---

## 12. Связанные документы

- `tests/e2e/AGENTS.md` — обязательный локальный чеклист
- `tests/e2e/README.md` — команды и каталог сценариев
- `tests/e2e/scripts/retarget_test_node_mqtt.sh` — CLI retarget
- `firmware/test_node/README.md` — прошивка, seed `set_fault_mode`
- `doc_ai/02_HARDWARE_FIRMWARE/TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md`
- `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md` — lease bypass
- `doc_ai/13_TESTING/E2E_GUIDE.md` — общий Python E2E (в т.ч. node-sim)
- `doc_ai/13_TESTING/NODE_SIM.md` — симулятор; **не** включать в realhw
