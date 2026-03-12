# E2E прод-аудит (2026-02-26)

## Объём аудита
- Проверено сценариев: 60
- Разделы: alerts(6), automation_engine(7), chaos(3), commands(9), core(6), grow_cycle(10), infrastructure(3), scheduler(3), simulation(3), snapshot(3), workflow(7)

## Статус после фиксов (clean full-run)
- Дата/время прогона: 2026-02-26 16:28:37 -> 2026-02-26 16:49:49
- Команда: `tests/e2e/run_automation_engine_real_hardware.sh --set=full`
- Лог: `tests/e2e/reports/realhw_audit_postfix/full_run_clean_postfix_20260226_162708.log`
- Итог: `60/60 PASS`, `0 FAIL`
- Подтверждение в логе: `🎉 Все сценарии для real hardware завершены успешно (set=full)`

## Проверка критичного прод-пути
- Полный путь `zone -> plant -> recipe -> bind real nodes -> start cycle -> automation run` покрыт сценарием `E66`.
- Жёсткие проверки EC/pH в workflow уже есть (`E86`, `E87`, `E89`), но они не закрывали единым сценарием полный продовый путь с bind новых нод и строгими контрактами источника/терминальности коррекций.

## Найденный пробел
- Не хватало отдельного real-hardware gate-сценария, который одновременно:
  - создаёт новую зону и выполняет полноценный bind,
  - запускает automation,
  - строго требует обе коррекции (`run_pump(add_nutrients)` и `dose(add_acid)`),
  - проверяет terminal status и отсутствие `ack_done_timeout_5s`.

## Внесённые изменения
- Добавлен сценарий:
  - `tests/e2e/scenarios/automation_engine/E68_full_prod_path_strict_ec_ph_corrections.yaml`
- Обновлён real-hardware automation set:
  - `tests/e2e/run_automation_engine_real_hardware.sh`
  - теперь включает: `E61, E64, E65, E66, E67, E68, E74`
- Обновлён список сценариев в:
  - `tests/e2e/scenarios/README.md`
- Доработан command happy path для real node:
  - `tests/e2e/scenarios/commands/E10_command_happy.yaml`
  - переход на `TEST_NODE_*`, выбор actuator channel из БД, non-initial status check, optional DONE check для стабильного full-run на real HW.
- Исправлен infrastructure binding/role resolution:
  - `tests/e2e/scenarios/infrastructure/E42_bindings_role_resolution.yaml`
  - корректный SQL резолв node/zone/channel по `TEST_NODE_UID` и `TEST_NODE_ZONE_UID`, приоритет `pump_main/main_pump`, уникальный infra instance label.

## Что валидирует новый E68
- Новый `zone` создаётся через API.
- Реальные `irrig/ph/ec` ноды биндаются в зону и становятся online.
- Создаются `plant/recipe/revision/phase`, запускается `grow cycle`.
- Обязательные коррекции в окне сценария:
  - `run_pump` + `params.type=add_nutrients`
  - `dose` + `params.type=add_acid`
- Проверки строгости:
  - terminal status коррекций: только `DONE|NO_EFFECT`
  - source коррекций: automation-engine
  - запрет источников `web/api/laravel/scheduler`
  - есть `CORRECTION_STATE_TRANSITION -> act` и `-> cooldown`
  - отсутствует `CORRECTION_COMMAND_ATTEMPT_FAILED.reason=ack_done_timeout_5s`
  - отсутствуют неверные направления коррекции (`add_base`/`dilute`)

## Рекомендованный продовый прогон
1. `tests/e2e/run_automation_engine_real_hardware.sh --set=automation`
2. `tests/e2e/run_automation_engine_real_hardware.sh --set=workflow`
3. `tests/e2e/run_automation_engine_real_hardware.sh --set=full`
