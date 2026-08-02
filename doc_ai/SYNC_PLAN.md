# План синхронизации документации с кодом

**Дата обновления:** 2026-08-02  
**Статус:** `plan` (активный backlog drift-аудитов; не structural plan 2025)

## Принцип SoT (инверсия относительно версии 2025-01-27)

1. **Код = source of truth** для фактического поведения runtime.
2. **`doc_ai/` canonical/guide** обновляются под код при drift (не наоборот).
3. Менять код «под старый doc» — только если doc описывает ещё не реализованный `plan` и задача явно требует реализации.
4. Исторический SYNC_PLAN (структура `docs/` vs `doc_ai/`, api-gateway placeholder и т.п.) выполнен/устарел; детали ниже в § Архив.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## Активный backlog (code-first audits 2026-08)

### P0 — сделано / в работе (domain/data/system, 2026-08-02)

| Тема | Действие | Статус |
|------|----------|--------|
| Retention telemetry 30 vs 90 | Docs: DATA_MODEL + POLICY описывают app cleanup 30 + Timescale drift 90; Python fallback → 30 | ✅ docs+fallback |
| `ae_tasks` retention 90 | DATA_MODEL §6.11.3 + POLICY §6.1 | ✅ |
| Archive commands/events secondary path | POLICY: Timescale 365 hot; artisan archive 90/180 not in Schedule | ✅ |
| Scheduler matrix topup/change | SCHEDULER_ENGINE, SCHEDULER_AE3_NON_IRRIGATION, ARCHITECTURE_FLOWS; capabilities ↔ dispatcher | ✅ |
| IMPLEMENTATION_STATUS scheduler ownership | Laravel dispatch, не Python MQTT scheduler | ✅ |
| LOGIC_ARCH NodeConfig / AE3 read-model | PublishNodeConfigJob; SQL bundle для AE3 | ✅ |
| Timescale `telemetry_samples` policy 90→30 | `2026_08_02_120000_align_telemetry_samples_timescale_retention_to_30_days.php` | ✅ |
| Полный rewrite IMPLEMENTATION_STATUS firmware statuses | light/pump/storage_irrigation/digital-twin | ✅ |
| DATA_MODEL post-May + process_calibration authority | stamp 2026-08-02 + §2.2.3 + scheduler totals | ✅ |

### Аудиты 2026-08-02 → P0/P1 правки

| Аудит | Статус |
|-------|--------|
| domain/data/system | ✅ |
| MQTT/firmware | ✅ |
| AE3/backend | ✅ |
| API/FE/AUTH | ✅ |
| AE3 read-model / events / failsafe | ✅ |
| E2E suites + Unified Dashboard UI_UX | ✅ |

### P2 backlog

| Тема | Статус |
|------|--------|
| REST hot-path gaps (config-mode, manual-schedules, ET, launch-flow, zone-automation-presets, detach/swap, sync) | ✅ |
| MQTT_NAMESPACE `hydro/system/*` planned + channel topic ids | ✅ |
| ROLE_BASED_UI_SPEC DefaultDashboard hypothetical | ✅ |
| Полный enumeration всех ~219 Route:: | ❌ out of scope (держать hot-path) |
| LOGIC_ARCH `channels.key` | ✅ → name/channel |
| REST IRRIG_RECIRC → legacy | ✅ |
| `backend/services/scheduler/README` (не MQTT publisher) | ✅ |
| `backend/services/AGENTS.md` solution_* ingress | ✅ |
| IMPLEMENTATION_STATUS relay_node | ✅ |
| Docs legacy cleanup 2026-08-02 | ✅ удалены `11_LEGACY_ARCHIVES` zip; superseded/plans → `00_ARCHIVE/{SUPERSEDED,PLANS}` + stubs |
| HL API + Android/firmware status audit 2026-08-02 | ✅ `HISTORY_LOGGER_API` webhook/DLQ/health/ingest/idempotency; `IMPLEMENTATION_STATUS` firmware+Android; `QUICK_START` HL metrics `:9300` |
| mqtt-bridge / NodeConfig / AUTH / retention audit 2026-08-02 | ✅ mqtt-bridge README+§2.4; NODE_CONFIG version/mqtt/HMAC; AUTH lockout/middleware/abilities; alerts retention planned; warm agg table; Docker internal=prod target |
| digital-twin + E2E/testing audit 2026-08-02 | ✅ DT `/v1/calibrate`+`zone_dt_params`; PYTHON §2.5–2.6; AI MVP status; `run_e2e.sh test` vs smoke; protocol-check local≠CI |

---

## Как проводить следующий аудит

1. Зафиксировать слой (AE3 / MQTT / data / API).
2. Сверить canonical docs с кодом (пути, endpoints, defaults, FSM).
3. При конфликте: **правка docs** (или явная пометка drift + задача на код, если код сам себе противоречит).
4. Обновить эту таблицу + `IMPLEMENTATION_STATUS.md` при смене ownership.

---

## Архив: структурный SYNC_PLAN 2025-01-27

Прежняя версия утверждала «`doc_ai/` не изменяются, правим только код» — **отменено**.

Выполненные структурные пункты (не повторять):
- корневой legacy `docs/` удалён → SoT = `doc_ai/`;
- `api-gateway` / `device-registry` помечены legacy; роль API Gateway = Laravel;
- PYTHON_SERVICES_ARCH / NODE_CONFIG_SPEC синхронизированы в прошлых итерациях.

Неактуальные ⏳ пункты про «firmware только pump_node» и плоскую структуру `services/` — **игнорировать**; смотреть актуальный backlog выше.
