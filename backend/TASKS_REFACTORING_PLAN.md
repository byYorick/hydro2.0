# TASKS_REFACTORING_PLAN.md
# Задачи по рефакторингу backend (10–20 теплиц, 1–5 зон каждая)
# Основано на AUDIT_REPORT, AUDIT_ACTION_PLAN, DEEP_BUGS_AND_ARCHITECTURE_ANALYSIS

## 1. Критические (сначала)
- Регистрация нод: добавить SELECT FOR UPDATE по hardware_id + retry при UID коллизии.
- PublishNodeConfigJob: дедупликация через pg_try_advisory_xact_lock + SELECT FOR UPDATE; Redis lock оставить как быстрый фильтр.
- Обновление нод: optimistic/pessimistic locking (zone_id/pending_zone_id), исключить lost updates.
- HMAC команд (ts+sig): генерация в Laravel, проверка на узлах; интеграция в PythonBridgeService.
- Безопасность API: rate limit + IP whitelist для /api/nodes/register; убрать логирование токенов; поиск через ILIKE с экранированием; скрыть config через $hidden и API Resources.

## 2. Масштабирование и стабильность
- automation-engine: адаптивная конкурентность (цель цикл ≤15s, max_concurrent 10–50), метрика optimal_concurrency; опциональный шардинг зон (ZONE_SHARD_ID/TOTAL).
- Обработка ошибок: gather с явным учетом ошибок по зонам; метрики zone_processing_errors; алерты >10% fail.
- history-logger: кеш uid→id (refresh ttl), batch resolve, batch insert telemetry, batch upsert telemetry_last; метрики queue_size/dropped/overflow, backpressure >90%.

## 3. Транзакции и БД
- Isolation: SERIALIZABLE для критических операций (привязка, swap, публикация конфига) с retry; REPEATABLE READ для консистентных чтений.
- Индексы: nodes(zone_id, uid, hardware_id, status, lifecycle_state); telemetry_last(zone_id, metric_type, updated_at); commands(status, zone_id, created_at).

## 4. Laravel архитектура
- Form Requests: store/update/register/publishConfig/command для нод.
- Policies: DeviceNode, Zone; авторизация через authorize().
- API Resources: DeviceNodeResource, NodeChannelResource (скрытый config).
- Дробление крупных методов NodeController (update, publishConfig) на приватные.

## 5. Тесты
- PHP Feature: доступ к нодам, отсутствие config в ответах, сервисный токен, поиск без SQLi.
- PHP Unit: Policies, Form Requests.
- Python pytest: batch/locking пути (history-logger, automation-engine), обработка ошибок в gather.
- Нагрузочное (локально): 100 зон, проверка latency p99 и переполнения очереди.

## 6. Документация и CI
- Обновить SECURITY_ARCHITECTURE (HMAC, rate limit, IP whitelist).
- Обновить PYTHON_SERVICES_ARCH (фактическая структура, batch-процессинг).
- Обновить IMPLEMENTATION_STATUS по задачам выше.
- Добавить artisan security:check-config в CI (prod env).

## 7. Метрики успеха
- 0 дубликатов публикации конфига, 0 lost updates.
- Telemetry latency p99 ≤ 500 мс при ~100 зонах.
- Queue overflow incidents: 0 (alerts только при тестах).
- Ошибки обработки зон < 1% за цикл.


