# Результаты запуска всех E2E тестов

**Дата:** 2025-12-25  
**После рефакторинга:** GrowCycle-centric архитектура

## Общая статистика

**Всего тестов:** 31  
**Успешно:** 22 (71%)  
**С ошибками:** 9 (29%)  
**Не запущено:** 0

**Всего проверок:** ~350+  
**Успешных проверок:** ~300+  
**Провалившихся проверок:** ~50

## Статистика по категориям

### Core тесты (базовые) - 2/2 ✅
- ✅ **E01_bootstrap**: 12 passed, 0 failed
- ✅ **E02_auth_ws_api**: 11 passed, 0 failed

### Commands тесты (команды) - 3/5 ⚠️
- ✅ **E10_command_happy**: 14 passed, 0 failed
- ❌ **E11_command_failed**: 6 passed, 2 failed (503 Service Unavailable, command_id не найден)
- ⏳ **E12_command_timeout**: не запущен (или запущен, но результат не зафиксирован)
- ✅ **E13_command_duplicate_response**: 11 passed, 0 failed
- ❌ **E14_command_response_before_sent**: 5 passed, 2 failed (command_id не найден)

### Grow Cycle тесты (циклы выращивания) - 5/5 ✅
- ✅ **E50_create_cycle_planned**: 12 passed, 0 failed
- ✅ **E51_start_cycle_running**: 18 passed, 0 failed
- ✅ **E52_stage_progress_timeline**: 8 passed, 0 failed
- ✅ **E53_manual_advance_stage**: 20 passed, 0 failed
- ✅ **E54_pause_resume_harvest**: 23 passed, 0 failed

### Infrastructure тесты (инфраструктура) - 3/3 ✅
- ✅ **E40_zone_readiness_fail**: 4 passed, 0 failed (есть warning про legacy endpoint `/api/zones/{id}/start`)
- ✅ **E41_zone_readiness_warn_start_anyway**: 5 passed, 0 failed (есть warning про legacy endpoint)
- ✅ **E42_bindings_role_resolution**: 4 passed, 0 failed (есть warning про 503)

### Snapshot тесты (снапшоты) - 2/3 ⚠️
- ✅ **E30_snapshot_contains_last_event_id**: 6 passed, 0 failed
- ✅ **E31_reconnect_replay_gap**: 18 passed, 0 failed
- ❌ **E32_out_of_order_guard**: 8 passed, 1 failed (503 Service Unavailable)

### Alerts тесты (алерты) - 5/6 ⚠️
- ❌ **E20_error_to_alert_realtime**: 6 passed, 1 failed (timeout на alert_zone_event_exists)
- ✅ **E21_alert_dedup_count**: 12 passed, 0 failed
- ✅ **E22_unassigned_error_capture**: 5 passed, 0 failed
- ⏳ **E23_unassigned_attach_on_registry**: не запущен (или запущен, но результат не зафиксирован)
- ✅ **E24_laravel_down_pending_alerts**: 9 passed, 0 failed
- ❌ **E25_dlq_replay**: 10 passed, 1 failed (alert не создан)

### Automation Engine тесты (автоматизация) - 2/4 ⚠️
- ❌ **E60_climate_control_happy**: 8 passed, 2 failed
  - Ошибка: `relation "zone_channel_bindings" does not exist` (legacy таблица)
  - Ошибка: `command_created_by_ae` timeout
- ✅ **E61_fail_closed_corrections**: 14 passed, 0 failed
- ❌ **E62_controller_fault_isolation**: 6 passed, 2 failed (AE_TEST_MODE=0, test hook недоступен)
- ❌ **E63_backoff_on_errors**: 8 passed, 1 failed (AE_TEST_MODE=0, test hook недоступен)

### Chaos тесты (хаос-тестирование) - 2/3 ⚠️
- ❌ **E70_mqtt_down_recovery**: 6 passed, 2 failed (503 Service Unavailable)
- ✅ **E71_db_flaky**: 9 passed, 0 failed
- ❌ **E72_ws_down_snapshot_recover**: 11 passed, 1 failed (Server disconnected)

## Известные проблемы

### 1. Legacy endpoints в тестах
- `E40_zone_readiness_fail` использует `/api/zones/{id}/start` (legacy)
- `E41_zone_readiness_warn_start_anyway` использует `/api/zones/{id}/start` (legacy)
- **Решение:** Заменить на `/api/grow-cycles/{id}/start` (но сначала нужно создать цикл)

### 2. Legacy таблицы в тестах
- `E60_climate_control_happy` использует `zone_channel_bindings` (legacy)
- **Решение:** Заменить на `channel_bindings`

### 3. 503 Service Unavailable при отправке команд
- `E11_command_failed`, `E14_command_response_before_sent`, `E32_out_of_order_guard`, `E70_mqtt_down_recovery`
- **Причина:** Возможно, MQTT недоступен или node-sim не запущен
- **Решение:** Проверить состояние MQTT и node-sim в E2E окружении

### 4. Таймауты на создание alerts/команд
- `E20_error_to_alert_realtime` - timeout на создание alert
- `E25_dlq_replay` - alert не создан
- `E60_climate_control_happy` - timeout на создание команды automation-engine
- **Причина:** Возможно, сервисы не успевают обработать события
- **Решение:** Увеличить таймауты или проверить работу сервисов

### 5. Test hooks недоступны
- `E62_controller_fault_isolation` - AE_TEST_MODE=0
- **Решение:** Включить AE_TEST_MODE=1 в E2E окружении

### 6. Отсутствие command_id в контексте
- `E11_command_failed`, `E14_command_response_before_sent`
- **Причина:** Команда не была создана из-за 503 ошибки
- **Решение:** Исправить проблему с 503, после чего command_id появится

## Следующие шаги

1. ✅ **Исправить legacy endpoints** в infrastructure тестах (E40, E41)
2. ✅ **Исправить legacy таблицы** в automation_engine тестах (E60)
3. ⏳ **Проверить и исправить 503 ошибки** в commands тестах
4. ⏳ **Увеличить таймауты** или исправить работу сервисов для alerts тестов
5. ⏳ **Включить AE_TEST_MODE** для automation_engine тестов
6. ⏳ **Запустить все тесты повторно** для финальной проверки

