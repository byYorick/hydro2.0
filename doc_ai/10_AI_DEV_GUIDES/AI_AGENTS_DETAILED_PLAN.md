# AI_AGENTS_DETAILED_PLAN.md
# Детальный план для ИИ‑агентов (масштаб: 10–20 теплиц, 1–5 зон в каждой)
# Основано на AI_ASSISTANT_DEV_GUIDE.md и результатах AUDIT_REPORT / DEEP_BUGS_AND_ARCHITECTURE_ANALYSIS

## 1. Цель и ограничения
- Обработать 10–20 теплиц (суммарно 10–100 зон), без деградации latency и потери данных.
- Строго соблюдать совместимость протокола 2.0: MQTT топики/пайлоады не менять, только расширять.
- Любые изменения проходят через pipeline: ESP32 → MQTT → Python → PostgreSQL → Laravel → Vue.

## 2. Приоритеты (спринтами)
### Спринт 1 (критика, 1 неделя)
- Исправить race condition регистрации нод (pessimistic lock + retry).
- Дедупликация публикации конфига через DB advisory lock (pg_try_advisory_xact_lock + SELECT FOR UPDATE).
- Включить optimistic locking / SELECT FOR UPDATE для обновлений нод.
- Добавить HMAC подпись команд (ts + sig) end-to-end.
- Валидация токенов: rate limit + IP whitelist для /api/nodes/register; убрать логирование токенов.

### Спринт 2 (масштабирование и стабильность, 1–2 недели)
- Adaptive concurrency для automation-engine (цель цикл ≤15s, 50 параллельно макс).
- Sharding зон по replica_id (ZONE_SHARD_ID / ZONE_SHARD_TOTAL) при необходимости.
- Batch-процессинг telemetry в history-logger (кеш uid→id, batch insert, batch upsert telemetry_last).
- Alerting/metrics: queue overflow, dropped telemetry, zone processing errors.
- Isolation levels: SERIALIZABLE для критики (привязка, swap), REPEATABLE READ для консистентных чтений.

### Спринт 3 (качество и покрытие, 1 неделя)
- Form Requests, Policies, API Resources для всех контроллеров нод/зон/команд.
- Unit/Feature тесты: NodeController, Policies, Form Requests; Python pytest на новые batch/locking ветки.
- Документация: обновить SECURITY_ARCHITECTURE (HMAC), PYTHON_SERVICES_ARCH (фактическая структура), IMPLEMENTATION_STATUS.

## 3. Задачи по слоям
### 3.1 MQTT / ESP32
- Добавить/подтвердить HMAC: cmd|ts, проверка ts ±30s на узлах; не менять существующие поля.
- Подтвердить, что команды идут только через Python bridge, не напрямую из фронта.

### 3.2 Python сервисы
- history-logger:
  - Кеш zone_uid/node_uid → id, batch resolve, batch insert, batch upsert telemetry_last.
  - Metrics: queue size, dropped, overflow alerts; backpressure (sampling при >90% заполнения).
  - Ограничение MAX_PAYLOAD_SIZE оставить, добавить алерты при частых validation_failed.
- automation-engine:
  - Adaptive concurrency + метрика optimal_concurrency.
  - Обработка ошибок по зоне (не глушить gather), метрика zone_processing_errors, алерты >10% failed.
- Общие:
  - Type hints дополнить (возвраты None).
  - SQL строго параметризованный.

### 3.3 PostgreSQL
- Индексы: nodes(zone_id, uid, hardware_id, status, lifecycle_state), telemetry_last(zone_id, metric_type, updated_at), commands(status, zone_id, created_at).
- Isolation: set transaction isolation level SERIALIZABLE для критических транзакций; retries при serialization failure.
- Advisory locks для дедупликации публикации конфигов.

### 3.4 Laravel backend
- Безопасность:
  - Middleware auth.service (Bearer для сервисов), rate limit node_register, IP whitelist.
  - Убрать логирование токенов; addcslashes/ILIKE для поиска; hidden config в моделях.
- HMAC:
  - CommandSignatureService; интеграция в PythonBridgeService sendNodeCommand/sendZoneCommand.
- Структура:
  - Form Requests (Store/Update/Register/PublishConfig/Command), Policies (DeviceNode, Zone), API Resources (DeviceNodeResource/NodeChannelResource).
  - Разбивка длинных методов NodeController (update, publishConfig) на маленькие приватные.
- Тесты:
  - Feature: доступ нод, отсутствие config в ответах, сервисный токен доступ.
  - Unit: Policies, Form Requests.

### 3.5 Frontend / Inertia
- Включить real-time обновления (если отключены) для ключевых экранов зон; убедиться, что props совместимы.
- Тесты E2E не трогаем, но проверить, что новые API поля не ломают UI (ресурсы скрывают config).

### 3.6 Мониторинг и оповещения
- Prometheus: queue_size, queue_dropped, queue_overflow_alerts, zone_processing_errors, optimal_concurrency.
- Алерты:
  - Queue utilization >90%, >95%.
  - Zone processing failure rate >10%.
  - Serialization failures spikes.

## 4. Чек-листы DoD для ИИ-задач
- Совместимость: MQTT топики/схемы не изменены, только расширены.
- БД: миграции без breaking changes, индексы добавлены, нет rename/drop.
- Безопасность: токены не логируются, HMAC добавлен, rate limiting/IP whitelist включены.
- Конкурентность: есть блокировки (advisory/pessimistic/optimistic), тесты на race/duplication.
- Тесты: PHP Feature/Unit и pytest покрывают новые пути; минимум 1 тест на happy-path + 1 на failure.
- Документация: обновлены SECURITY_ARCHITECTURE, PYTHON_SERVICES_ARCH, IMPLEMENTATION_STATUS.

## 5. Шаблон задачи для ИИ-агента
- Контекст: ссылка на spec (.md), файлы к правке, ожидаемый результат.
- Ограничения: не менять протокол, не ломать совместимость.
- План: шаги 1–N, какие тесты запускать (phpunit filter / pytest file).
- DoD: список проверок (из пункта 4) + обновленная документация.

## 6. Метрики успеха
- 0 дубликатов публикации конфига (по логам/метрикам).
- 0 lost updates при параллельных изменениях нод.
- Telemetry latency p99 ≤ 500 мс при 100 зонах.
- Queue overflow incidents: 0 (alerts только при тестовом нагрузочном сценарии).
- Ошибки обработки зон < 1% за цикл при 100 зонах.

## 7. Предлагаемый порядок старта
1) Критика: race condition регистрации, advisory lock в PublishNodeConfigJob, optimistic/pessimistic locking, HMAC команд, rate limit/IP whitelist.
2) Масштаб: adaptive concurrency + batch telemetry + алерты/метрики.
3) Качество: Form Requests, Policies, Resources, тесты, документация.


