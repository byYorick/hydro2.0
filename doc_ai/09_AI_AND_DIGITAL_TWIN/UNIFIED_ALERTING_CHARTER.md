# UNIFIED_ALERTING_CHARTER.md
# Паспорт pipeline: единая система алертов, приоритизации, escalation

**Статус:** 🟡 CHARTER (внедрять ДО запуска ML в canary/active)
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/UNIFIED_ALERTING_CHARTER.md`
**Связанные:** ВСЕ pipeline'ы (все — источники alert'ов), `FRONTEND_ARCH_FULL.md`

---

## 1. Назначение

Сейчас alert'ы потенциально размазаны по четырём местам: `alerts` таблица,
`zone_events` с типом `*_ALERT_*`, `plant_visual_alerts`, `climate_safety_*`.
При росте числа pipeline'ов оператор быстро утонет в шуме. Нужна единая
шина: приоритизация + дедупликация + escalation + acknowledgement.

## 2. Цели

- **Single source of truth** для «что оператору сейчас важно».
- **Дедупликация**: один и тот же `powdery_mildew_detected` каждые 15 минут
  → один открытый alert с обновляющейся информацией.
- **Escalation**: если critical не acknowledged за N минут → уведомление
  следующему в списке (telegram, email, звонок).
- **Severity-based routing**: info → только в UI-центре, warning → push в
  мобильный, critical → call + SMS.
- **Метрики алертов как KPI**: `mean time to ack`, `false positive rate`.

## 3. Ключевые дизайн-решения

1. **Alert как first-class entity** (не attribute события). Имеет lifecycle:
   `open → acknowledged → resolved` (или `→ suppressed`).
2. **Producers и consumers разделены**: producer объявляет `raise_alert(...)`
   → центральный сервис дедуплирует, диспатчит consumer'ам.
3. **Notification channels** как pluggable: UI, push, Telegram, email, SMS,
   webhook.
4. **Suppression rules**: «не будить ночью по warning», «не дублировать
   если за 60 мин уже был такой же в той же зоне».
5. **Alert quality feedback**: каждый resolved alert помечается оператором
   как `useful / false_positive / too_late / duplicate` — в метрики и
   возможное переобучение trigger'ов.

## 4. Структура данных

```sql
CREATE TABLE alerts (
  id bigserial PRIMARY KEY,
  dedup_key varchar(128) NOT NULL,       -- {source}:{zone}:{type}
  source_pipeline varchar(32) NOT NULL,  -- 'ml_feature'|'vision'|'irrigation'|'climate'|...
  zone_id bigint REFERENCES zones(id),
  type varchar(64) NOT NULL,
  severity varchar(16) NOT NULL,         -- 'info'|'warning'|'critical'|'emergency'
  first_raised_at timestamptz NOT NULL,
  last_raised_at timestamptz NOT NULL,
  raise_count integer NOT NULL DEFAULT 1,
  title text NOT NULL,
  body text,
  evidence jsonb,                        -- links to predictions/images/events
  recommended_action text,
  confidence double precision,
  status varchar(16) NOT NULL,           -- 'open'|'acknowledged'|'resolved'|'suppressed'
  acknowledged_by bigint REFERENCES users(id),
  acknowledged_at timestamptz,
  resolved_by bigint REFERENCES users(id),
  resolved_at timestamptz,
  resolution_notes text,
  quality_rating varchar(16),            -- 'useful'|'false_positive'|'too_late'|'duplicate'
  UNIQUE (dedup_key, status) DEFERRABLE
);
CREATE INDEX alerts_open_severity_idx ON alerts (status, severity, last_raised_at DESC)
  WHERE status IN ('open','acknowledged');

CREATE TABLE alert_routes (
  id bigserial PRIMARY KEY,
  severity varchar(16) NOT NULL,
  zone_id bigint REFERENCES zones(id),    -- NULL = default
  channel varchar(32) NOT NULL,          -- 'ui'|'push'|'telegram'|'email'|'sms'|'webhook'
  target varchar(256) NOT NULL,          -- user_id / chat_id / email / url
  escalation_after_minutes integer,      -- null = no escalation
  escalation_to_id bigint REFERENCES alert_routes(id),
  quiet_hours jsonb,                     -- {"from":"22:00","to":"06:00","except_severity":"critical"}
  enabled boolean DEFAULT true
);

CREATE TABLE alert_notifications (
  id bigserial PRIMARY KEY,
  alert_id bigint NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
  channel varchar(32) NOT NULL,
  target varchar(256) NOT NULL,
  sent_at timestamptz NOT NULL,
  delivery_status varchar(16) NOT NULL,  -- 'sent'|'failed'|'delivered'|'read'
  error text,
  retry_count smallint DEFAULT 0
);
```

## 5. Сервис `alerting-service`

- **API для producers**: `POST /v1/alerts/raise` с `dedup_key`.
- **Dispatcher**: fetch unrouted alerts каждые 5 сек → route по
  `alert_routes` с учётом quiet hours и suppression.
- **Escalator**: проверяет acknowledged deadline на critical/emergency.
- **UI**: «Inbox» страница в mobile/web app.

## 6. Severity definitions

| Severity | Описание | Channels | Escalation |
|---|---|---|---|
| info | Информация, можно проигнорировать | ui | нет |
| warning | Нужно обратить внимание в течение суток | ui+push (не в quiet) | 8 часов |
| critical | Нужно действие в течение 2 часов | ui+push+telegram | 30 мин |
| emergency | Немедленное действие, риск потерь | все каналы + sms + call | 5 мин |

## 7. Фазы

| Phase | Задача | DoD |
|---|---|---|
| A0 | Миграции + skeleton `alerting-service` | `/healthz`, таблицы готовы |
| A1 | Producer API + дедупликация | ML_FEATURE даёт alert через API |
| A2 | Миграция существующих alert-источников | Все alerts через сервис |
| A3 | UI Inbox + ack/resolve | Оператор может работать с alert'ами |
| A4 | Routes + channels (UI, push) | Push на мобилу работает |
| A5 | Telegram / email / SMS каналы | Доставка в них |
| A6 | Escalation logic | Не ack'нутый critical эскалирует |
| A7 | Quality rating + дашборд качества | MTTR, FP rate видны в Grafana |

## 8. Интеграция

**Каждый pipeline объявляет типы alert'ов:**

| Pipeline | Types |
|---|---|
| ML_FEATURE | `ph_forecast_ood`, `ec_anomaly`, `dose_response_failed` |
| VISION | `disease_*`, `deficiency_*`, `growth_stalled`, `wilting` |
| IRRIGATION | `wc_floor_breached`, `leaching_out_of_range`, `no_flow`, `over_dosing` |
| CLIMATE | `dew_point_risk`, `temp_excursion`, `co2_excess` |
| IPM | `pest_threshold_*`, `biocontrol_overdue` |
| SENSOR_HEALTH | `sensor_drift`, `sensor_stale`, `sensor_disagreement` |
| NUTRIENT_BUDGET | `ion_depletion_imminent_*`, `ion_lab_overdue` |
| ENERGY | `peak_load_approaching`, `tariff_forecast_missing` |

## 9. Правила для ИИ-агентов

### Можно:
- Добавлять новые `alerts.type` (в документированный enum с описанием).
- Улучшать suppression-логику.

### Нельзя:
- Публиковать alert без `dedup_key` (иначе дублирование).
- Обходить severity ради приоритета в UI (оператор теряет trust).
- Автоматически снимать (`suppress`) критичные alert'ы.

## 10. Открытые вопросы

1. Transport для notifications: inline через сервис vs через message bus
   (Redis Streams / Kafka)?
2. Как кастомизировать severity под разные типы теплиц? Per-greenhouse
   override?
3. Integration с on-call ротациями (PagerDuty-like)?
4. Как предотвратить alert storm в catastrophic situations (всё сломалось
   — 100 alerts за секунду) — rate limiting на уровне сервиса?

---

# Конец UNIFIED_ALERTING_CHARTER.md
