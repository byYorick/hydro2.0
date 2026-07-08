# SINGLE_INSTANCE_SPOF_RUNBOOK.md
# Single-Point-of-Failure ограничения и recovery-процедуры (hydro2.0)

**Дата:** 2026-07-08  
**Версия:** 1.0  
**Статус:** Операционный runbook (дополняет `SYSTEM_FAILURE_RECOVERY.md`, `BACKUP_AND_RECOVERY.md`)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Цель

Зафиксировать **осознанные single-instance ограничения** v1 стека и короткие процедуры восстановления без HA-кластера. HA вне скоупа текущего релиза (см. `AUDIT_2026_07_07_RELIABILITY_PLAN.md` R7.2).

---

## 2. SPOF-карта компонентов

| Компонент | SPOF? | Последствие при падении | Recovery (кратко) |
|-----------|-------|-------------------------|-------------------|
| **Mosquitto** | Да | Узлы не получают команды; телеметрия не доходит | `docker compose restart mqtt`; проверить `probe_success{job="mqtt-broker"}` |
| **history-logger** | Да | Нет ingest телеметрии/команд в PG; **единственный MQTT publisher команд** | `restart history-logger`; Redis processing-list reclaim при старте |
| **automation-engine (AE3)** | Да (single-writer) | Нет исполнения automation tasks | `restart automation-engine`; startup recovery + waiting_command reconcile |
| **Laravel scheduler** | Да | Нет dispatch intents / wake-up AE3 | `restart laravel`; проверить `laravel_scheduler_lock_skipped_total`, cache-lock |
| **PostgreSQL** | Да | Полная остановка пайплайна | Restore из `/backups` (см. `BACKUP_AND_RECOVERY.md`); RTO/RPO по restore-тесту |
| **Redis** | Да | Очереди Laravel/telemetry buffer | `restart redis`; telemetry processing-list reclaim в HL |
| **Prometheus/Alertmanager** | Да (observability) | Нет алертов, метрики на диске | `restart prometheus alertmanager`; проверить `check_monitoring.sh` |

**Не SPOF на уровне логики:** ESP32 узлы (автономный fail-safe по `link_loss_timeout_sec`), TimescaleDB retention jobs (дублируются Laravel + Python aggregator при синхронизированном `TELEMETRY_RETENTION_DAYS`).

---

## 3. Критичные инварианты при recovery

1. **Команды к узлам** — только через `history-logger` → MQTT (`POST /commands`). Не использовать deprecated `mqtt-bridge` `/bridge/.../commands` (HTTP 410).
2. **Одна активная ae_task на зону** — partial unique index + `ZoneLease`. При split-brain: проверить `ae3_oldest_active_task_age_seconds`, `laravel_zone_hang_hints_active{code="waiting_command_stuck"}`.
3. **Telemetry Redis queue** — при рестарте HL: processing-list reclaim; dead-list — `telemetry_dead_cli.py list|replay`.
4. **Intent drift** — Laravel `ae3:reap-stale-tasks` + метрика `laravel_zone_hang_hints_active{code="scheduler_intent_task_drift"}`.

---

## 4. Runbook: типовые сценарии

### 4.1 Mosquitto недоступен

1. Alert: `MQTTBrokerDown` / `probe_success{job="mqtt-broker"}==0`
2. `docker compose -f backend/docker-compose.dev.yml restart mqtt`
3. Узлы: LWT → offline; после восстановления — heartbeat, time-sync gate
4. AE3: задачи в `waiting_command` — reconcile доиграет или fail по poll-deadline

### 4.2 history-logger down (ingest + commands)

1. Alerts: `HistoryLoggerDown`, `telemetry_queue_depth`, `command_status_dlq_size`
2. `restart history-logger`
3. Проверить: `/health`, `telemetry_dead_list_size`, нет роста `telemetry_pg_write_failed_total`
4. При длительном простое: `telemetry_dead_cli.py metrics` → replay при необходимости

### 4.3 AE3 down mid-task

1. Alert: `ae3_oldest_active_task_age_seconds` > 15m, `AE3ReconcileLoopDegraded`
2. `restart automation-engine`
3. Startup recovery: foreign lease guard — не трогает чужие in-flight задачи
4. Проверить: intent terminal в Laravel, нет orphan `zone_automation_intents`

### 4.4 Laravel scheduler stopped (2+ interval ticks)

1. Metrics: `laravel_scheduler_missed_windows_total`, `laravel_scheduler_lock_skipped_total`
2. `restart laravel` (scheduler + queue workers)
3. **Автоматический replay interval-тиков не выполняется** (by design) — оператор проверяет пропущенные окна полива в UI/alerts

### 4.5 PostgreSQL corruption / disk full

1. Остановить writers: `history-logger`, `automation-engine`, Laravel queue
2. Restore: `scripts/restore/*` + последний `backup:full` из `/backups`
3. После restore: `migrate`, smoke `make protocol-check`

---

## 5. Мониторинг (минимальный чеклист)

```bash
./backend/scripts/check_monitoring.sh
./backend/scripts/check-prod-ready.sh   # prod: secret, backups mount
```

Grafana: dashboard **System Overview** → секция **Reliability (R2)**.

Ключевые Prometheus series:
- `telemetry_pg_write_failed_total`, `telemetry_dead_list_size`
- `command_status_dlq_size`, `ae3_oldest_active_task_age_seconds`
- `laravel_scheduler_missed_windows_total`, `laravel_zone_hang_hints_active`
- `node_last_seen_age_seconds`, `telemetry_last_age_seconds`

---

## 6. Retention (синхронизация)

Единый источник через env в docker-compose:
- `TELEMETRY_RETENTION_DAYS` (Laravel `telemetry:cleanup-raw`)
- `RETENTION_SAMPLES_DAYS` (Python telemetry-aggregator)

Дефолт v1: **30 дней** для обоих. См. `DATA_RETENTION_POLICY.md`.

---

## 7. Связанные документы

- `SYSTEM_FAILURE_RECOVERY.md` — полная модель L1–L5 recovery
- `BACKUP_AND_RECOVERY.md` — backup/restore RTO/RPO
- `RUNBOOKS.md` — операционные процедуры
- `AUDIT_2026_07_07_RELIABILITY_PLAN.md` — план надёжности R1–R7
