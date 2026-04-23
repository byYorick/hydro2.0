# MULTI_ZONE_COORDINATION_CHARTER.md
# Паспорт pipeline: координация общих ресурсов между зонами

**Статус:** 🟡 CHARTER (активировать при ≥10 зон в проде)
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/MULTI_ZONE_COORDINATION_CHARTER.md`
**Связанные:** `IRRIGATION_ML_PIPELINE.md`, `CLIMATE_CONTROL_CHARTER.md`,
`ENERGY_OPTIMIZATION_CHARTER.md`

---

## 1. Назначение

При росте числа зон возникают конфликты за общие ресурсы: единый бак с
раствором, одна HVAC-установка на несколько зон, ограниченная мощность
насосов, пиковое потребление электричества. Каждый pipeline сейчас решает
«за себя»; этот — арбитр.

## 2. Цели

- Планировать одновременные поливы разных зон так, чтобы не превышать
  общий flow capacity насосной станции.
- Распределять CO2-инжекцию / отопление между зонами по приоритету фазы
  (плодоношение > вегетация).
- Сглаживать пиковое потребление электричества, откладывая некритичные
  actuations на off-peak.
- Избегать «все зоны дозируют одновременно» → резкие просадки pH в общем
  баке рецирк-системы.

## 3. Ключевые дизайн-решения

1. **Resource model**: система знает о ресурсах — `pump_station`, `hvac_unit`,
   `co2_tank`, `water_tank`, `power_quota` — с capacities.
2. **Priority-based scheduler**: зоны имеют dynamic priority (фаза × stress ×
   ROI). Coordinator при конфликте отдаёт капасити высокоприоритетной.
3. **Soft constraints, not hard**: большинство конфликтов разрешаются
   откладыванием на 5–30 минут, не отменой.
4. **Batch coalescing**: близкие по времени actuations одного типа на
   соседних зонах группируются для эффективности.

## 4. Структура данных

```sql
CREATE TABLE shared_resources (
  id bigserial PRIMARY KEY,
  resource_type varchar(32) NOT NULL,    -- 'pump_station'|'hvac_unit'|'power'|...
  resource_code varchar(64) NOT NULL,    -- 'PUMP-01'|'HVAC-MAIN'
  capacity_value double precision NOT NULL,
  capacity_unit varchar(16) NOT NULL,    -- 'L/min'|'kW'|'kg/h'
  greenhouse_id bigint REFERENCES greenhouses(id)
);

CREATE TABLE resource_allocations (
  id bigserial PRIMARY KEY,
  resource_id bigint NOT NULL REFERENCES shared_resources(id),
  zone_id bigint NOT NULL REFERENCES zones(id),
  allocated_from timestamptz NOT NULL,
  allocated_to timestamptz NOT NULL,
  allocated_value double precision NOT NULL,
  reason varchar(64),                    -- 'irrigation'|'hvac'|'co2_dose'
  advisory_id bigint,                    -- FK на один из *_advisories
  priority smallint NOT NULL
);
CREATE INDEX ra_resource_range ON resource_allocations (resource_id, allocated_from, allocated_to);

CREATE TABLE zone_priorities_snapshot (
  ts timestamptz NOT NULL,
  zone_id bigint NOT NULL,
  phase varchar(32),
  stress_index double precision,
  roi_weekly double precision,           -- из YIELD/economics
  computed_priority double precision,    -- композит
  PRIMARY KEY (ts, zone_id)
);
```

## 5. Сервис `zone-coordinator`

Уже упоминался в `CLIMATE_CONTROL_CHARTER §5`, здесь развёрнут.

- Принимает advisories от всех планировщиков (irrigation, climate, ipm,
  ...) с желательным time window.
- Проверяет конфликты по `shared_resources`.
- Если нет конфликта — пропускает.
- Если конфликт — откладывает advisory с меньшим priority, даёт ответ
  `delayed_by=N min`.
- Hard override: если safety advisory (emergency irrigation) — проходит
  немедленно, остальные откладываются.

## 6. Фазы

| Phase | Задача | DoD |
|---|---|---|
| M0 | Инвентаризация ресурсов + их capacity | `shared_resources` заполнена |
| M1 | `zone-coordinator` skeleton + API | Пропускает все advisories как сейчас |
| M2 | Конфликт-детектор по capacity | E2E тест: 3 зоны хотят 20 L/min при capacity 40 |
| M3 | Priority computation | `zone_priorities_snapshot` заполняется |
| M4 | Batch coalescing | 3 близкие дозы → 1 команда |
| M5 | Integration с существующими pipeline'ами | Все advisory проходят через coordinator |

## 7. Интеграция

- **All actuator-producing pipelines** (irrigation, climate, ipm, dosing)
  должны делать `POST /v1/coordinate` вместо прямого вызова
  `automation-engine`.
- Обратно: `automation-engine` гарантирует не исполнять команду без
  `coordinator_approval_id` (кроме emergency).

## 8. Правила для ИИ-агентов

### Можно:
- Добавлять новые ресурсы в `shared_resources`.
- Улучшать формулу приоритета (с unit-тестами).

### Нельзя:
- Обходить coordinator для non-emergency команд.
- Менять capacity ресурсов автоматически — только через ops-UI.

## 9. Открытые вопросы

1. Формула приоритета: фиксированные веса или ML-learned на основании
   «что произошло, когда мы задержали?»
2. Центральный coordinator (SPOF) vs distributed (etcd / consensus)?
   Для < 100 зон — центральный.
3. Max delay для non-emergency — 30 мин? 60? Влияет на качество каждого
   pipeline'а.

---

# Конец MULTI_ZONE_COORDINATION_CHARTER.md
