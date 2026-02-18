# AE2_STAGE_S10_TASK.md
# Stage S10: Resilience Consolidation

**Версия:** v0.1  
**Дата:** 2026-02-18  
**Статус:** IN_PROGRESS  
**Роль:** AI-CORE + AI-RELIABILITY  
**Режим:** implementation

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Входной контекст (что прочитать)
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `backend/services/automation-engine/main.py`
- `backend/services/automation-engine/services/zone_automation_service.py`
- `backend/services/automation-engine/correction_controller.py`

## 2. Текущий инкремент (выполнено)
1. Реализован file-based crash-recovery snapshot runtime-state:
- `infrastructure/runtime_state_store.py`.
2. Добавлен экспорт/restore runtime-state:
- `ZoneAutomationService.export_runtime_state()/restore_runtime_state()`.
- `CorrectionController.export_runtime_state()/restore_runtime_state()`.
3. Подключен lifecycle в `main.py`:
- restore snapshot после инициализации `ZoneAutomationService`;
- save snapshot при graceful shutdown.
4. Добавлен auto-recovery gate required-nodes online:
- policy `services/zone_node_recovery.py`;
- fail-closed/freeze при `missing required node types`;
- throttled offline сигнал + recovered reconcile сигнал;
- интеграция в `process_zone_cycle` до controller execution.
5. Расширен `resilience_contract`:
- unified infra/reason codes для runtime/backoff/recovery/guardrails;
- подключено в `zone_runtime_signals`, `zone_skip_signals`, `zone_controller_guardrails`, `zone_correction_signals`, `zone_node_recovery`.
6. `correction_command_retry` выровнен по `resilience_contract` кодам infra-alert для retry/unconfirmed путей.
7. `zone_housekeeping`/`zone_controller_processors` и event-write path выровнены по `resilience_contract` кодам.
8. Добавлен restart-parity acceptance кейс для offline required-nodes recovery state.
9. `correction gating` reason-коды выровнены по `resilience_contract` (`missing_flags/stale_flags/gating_passed`).
10. `correction anomaly block` infra-alert code выровнен по `resilience_contract`.

## 3. Остаток S10 (open)
1. Дополнить dedupe/retry/backoff/circuit-breaker слой единым контрактом/метриками.
2. Расширить acceptance набор auto-recovery loop offline-нод (chaos/restart parity).
3. Подготовить финальный `S10` report с закрытием всех подпунктов stage.

## 4. Тесты текущего инкремента
- `docker compose -f backend/docker-compose.dev.yml exec -T automation-engine pytest -q test_runtime_state_store.py test_zone_node_recovery.py test_main.py test_zone_automation_service.py test_correction_controller.py test_config_settings.py`

## 5. Критерий продолжения
- Следующий коммит `S10` должен закрыть п.1/2 раздела «Остаток S10 (open)» или явно зафиксировать ADR-границы.
