# AGENTS.md — `tests/e2e/`

Локальные правила для ИИ при работе с Python YAML E2E. Дополняет корневой `AGENTS.md`, не противоречит `doc_ai/`.

**Канон запуска на физической test_node:**  
[`doc_ai/13_TESTING/REALHW_TEST_NODE_AGENT_GUIDE.md`](../../doc_ai/13_TESTING/REALHW_TEST_NODE_AGENT_GUIDE.md)

Перед любым realhw-прогоном прочитай этот канон целиком.

---

## Три suite — не смешивать

| Что просят | Команда | Порты |
|------------|---------|--------|
| Реальная ESP32 `test_node` | `tests/e2e/run_automation_engine_real_hardware.sh --set=…` | 8081 / MQTT **1884** / AE **9505** / HL **9302** / PG **5433** |
| YAML + node-sim | `./tools/testing/run_e2e.sh` | те же e2e-порты, **без** ACM0 |
| Playwright UI | `backend/laravel` → `npm run e2e` | **не** этот каталог |

HIL lab (`infra/hil/…`, 8080/1883/9405) — **не** этот launcher.

---

## Realhw: обязательно

1. Прошивка только `firmware/test_node`. Serial обычно `/dev/ttyACM0`.
2. Перед прогоном: `tests/e2e/scripts/retarget_test_node_mqtt.sh --e2e` (LAN IP → **:1884**). После: `--dev` (**:1883**).
3. Payload retarget — `{mqtt:{host,port}}` **без** `channels[]`. Не слать на production-ноды. Не `hydro/system/`.
4. **Запрещён node-sim** (`REAL_HW_USE_NODE_SIM_SESSION=0`). Launcher сам `stop` `node-sim*`.
5. Сначала `--list` и узкий `E2E_SCENARIO_INCLUDE_REGEX`, не сразу `--set=full`.
6. Команды на ноду только через history-logger. `set_fault_mode` lease bypass только `nd-test-*`.
7. БД прогона — `hydro_e2e`:**5433**, не `hydro_dev`:**5432**.
8. Не коммитить `reports/junit.xml` / `timeline.json`.

---

## Не чинить как баги

- Уровни на test_node задаёт `storage_state` / `set_fault_mode` (`level_*_override`), не MQTT node-sim.
- `1` на `level_*_min` — бак не пуст. Оба `min=0` — `both_tanks_empty`, `run_pump` нет.
- Кадр AE 1.0.0 — `irrigation_start` → `run_pump` `DONE` → `irrigation_stop`. Маршрута `start-cycle` нет.

---

## Контракты без железа

```bash
cd tests/e2e
./venv/bin/python -m pytest -q tests/test_realhw_launcher_contract.py \
  tests/test_suite_catalog.py \
  tests/test_ae4_scenario_contract.py
```

Каталог сценариев: `README.md`, `scenarios/README.md`.
