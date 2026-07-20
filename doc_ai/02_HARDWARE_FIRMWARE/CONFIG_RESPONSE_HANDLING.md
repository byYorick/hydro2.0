# config_response — устаревший документ

**Дата:** 2026-07-20

**Статус:** SUPERSEDED

---

## Важно

`config_response` **не** является каноном финализации bind/rebind.

Канон wire ACK и finalize:

| Этап | Канон |
|------|--------|
| Publish вниз | Laravel `PublishNodeConfigJob` → history-logger `POST /nodes/{uid}/config` → MQTT `…/config` |
| Wire ACK вверх | `config_report` из целевого namespace |
| Finalize | Laravel `NodeConfigReportObserverService` (`pending_zone_id → zone_id`, `ASSIGNED_TO_ZONE`) |

См. актуальные документы:

- [`CONFIG_REPORT_HANDLING.md`](CONFIG_REPORT_HANDLING.md) — обработка `config_report`
- [`../01_SYSTEM/NODE_ASSIGNMENT_LOGIC.md`](../01_SYSTEM/NODE_ASSIGNMENT_LOGIC.md) — pending bind + publish + wire ACK
- [`../01_SYSTEM/NODE_ADDITION_AND_ACTIVATION_FLOW.md`](../01_SYSTEM/NODE_ADDITION_AND_ACTIVATION_FLOW.md)
- [`../01_SYSTEM/DATAFLOW_FULL.md`](../01_SYSTEM/DATAFLOW_FULL.md) §5 CONFIG FLOW

Исторический текст про `config_response` как условие `ASSIGNED_TO_ZONE` считать ошибочным и не использовать.
