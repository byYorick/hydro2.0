---
name: two-tank-debug
description: "Диагностика застрявшего two-tank startup workflow зоны. Используй когда зона не проходит idle/startup → tank_filling → tank_recirc → ready → irrigating → ready, зависла в промежуточной фазе, или корректировки pH/EC не запускаются."
metadata:
  type: workflow
  lifecycle: active
  version: "0.2.0"
---

# Диагностика two-tank Hydro 2.0

## Контекст и границы

Выбери zone_id и контур из запроса; уточняй только отсутствующее. Dev — hydro_dev,
AE integration — hydro_test, realhw — hydro_e2e. Для realhw сначала прочитай
[guide](../../../doc_ai/13_TESTING/REALHW_TEST_NODE_AGENT_GUIDE.md); не переключай
устройство на другой broker и не запускай тесты только ради диагностики.

Читай AGENTS.md, backend/services/AGENTS.md и automation-engine/AGENT.md.
Диагностика начинается с read-only запросов и GET состояния. Секреты/NodeConfig
не выводятся. Не используй пароль hydro по умолчанию и не копируй credentials
из документации; используй настроенное соединение. psql -w не ждёт ввода пароля.

## Состояния и химия

Различай workflow_phase (idle/tank_filling/tank_recirc/ready/irrigating),
current_stage и task status. Stage не выводится только из workflow_phase.

- Startup проходит clean_fill → solution_fill → prepare_recirculation → ready.
- Solution fill: calcium (pump_b) после water-baseline, без pH.
- Recirculation: последовательный nutrient pipeline с pH-gate и dilute по контракту.
- Irrigation: pH и один разрешённый EC-компонент calcium/npk; pH-only задаётся
  irrigation_ec_component=none. Не считай любую EC-дозу на поливе ошибкой.

Проверяй фактический RuntimePlan и pinned bundle; нормы —
[CORRECTION_CYCLE_SPEC](../../../doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md)
и [EFFECTIVE_TARGETS_SPEC](../../../doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md).
Correction-capable стадии определены в
[workflow_topology.py](../../../backend/services/automation-engine/ae3lite/application/services/workflow_topology.py).

## Сбор доказательств

1. Запусти [diagnostics.sql](references/diagnostics.sql) для выбранной зоны.
   Запросы используют текущий snapshot: telemetry_last.last_value/last_ts через
   sensors, nodes.zone_id, commands.node_id и ae_tasks.error_code/deadlines.
   Таблицы node_zones и поле ae_tasks.details не предполагаются.
2. Сопоставь stage, task/stage deadline, lease и последний ae_commands.external_id
   с commands.cmd_id. Статус waiting_command не доказывает потерю команды;
   DONE одного planner_step не означает DONE всего batch.
3. Для уровней смотри sensor label/spec и свежесть. Wire-метрика — WATER_LEVEL_SWITCH;
   названия level_clean_min/max и level_solution_min/max обозначают каналы.
   Нулевые значения сами по себе не доказывают broken wire: сверяй state/events/quality.
4. Проверь nodes.status/last_seen_at, события LEVEL_SWITCH_CHANGED, ошибки E-Stop,
   timestamp/HMAC и актуальность телеметрии. Начальный event будит reconcile,
   но не заменяет DB-confirmation завершения stage.
5. Сверь GET /api/zones/{id}/state через авторизованный Laravel UI/API.
   Действующие startup recovery и waiting-command reconcile описаны в
   [ae3lite.md §9](../../../doc_ai/04_BACKEND_CORE/ae3lite.md).

Пример для уже подготовленного dev Compose, из корня репозитория (замени 12
на выбранный zone_id; соединение должно быть настроено без вывода пароля):

~~~bash
docker compose -f backend/docker-compose.dev.yml exec -T db \
  psql -U hydro -d hydro_dev -w --set=zone_id=12 \
  < .claude/skills/two-tank-debug/references/diagnostics.sql
~~~

При несовпадении установленной схемы со snapshot зафиксируй drift. Не переключайся
на выдуманную legacy-таблицу. Не делай вывод «hang» по произвольным 5 минутам:
сравни реальные stage_deadline_at/overall_deadline_at и состояние reconciliation.

## Результат и следующие действия

Сообщи контур/zone_id, phase/stage/status, последнюю подтверждённую команду,
свежесть сигналов, доказанную причину или оставшиеся гипотезы. Предложи действие
с учётом готовности оборудования и существующей авторизации пользователя.
Не подделывай terminal SQL-записью, не удаляй lease и не повторяй дозу для проверки.
Операторский запуск/recovery — отдельное действие через штатный owner-path,
а не автоматическое следствие диагностического GET/SELECT.
