# Digital Twin Engine

Python-сервис симуляции и калибровки моделей зоны (pH/EC/климат).

**Порты (dev):** REST `8003`, Prometheus `9403`.

## Канон API

| Метод | Путь | Примечание |
|-------|------|------------|
| POST | `/simulate/zone` | Batch/offline симуляция |
| POST | `/v1/calibrate/zone/{zone_id}?persist=true` | **Канон** — persist в `zone_dt_params` |
| GET | `/v1/zone-dt-params/{zone_id}` | Параметры модели |
| POST | `/v1/simulate/replay` | Replay |
| POST | `/simulations/live/start` / `/stop` | Live sim → `zone_simulations` |
| POST | `/calibrate/zone/{zone_id}` | **Legacy**, без гарантированного persist — не использовать для cron/replay |

Laravel: `DigitalTwinClient`, `DigitalTwinCalibrateAll` → `/v1/calibrate?...persist=true`.

SoT docs: `doc_ai/09_AI_AND_DIGITAL_TWIN/DIGITAL_TWIN_ENGINE.md`.

## Запуск

```bash
python main.py
# или через docker compose service `digital-twin`
```
