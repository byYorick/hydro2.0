# ROOT_ZONE_MONITORING_CHARTER.md
# Паспорт pipeline: мониторинг корневой зоны (DO, температура, подводная камера)

**Статус:** 🟡 CHARTER (опциональный, при наличии железа)
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/ROOT_ZONE_MONITORING_CHARTER.md`
**Связанные:** `ML_FEATURE_PIPELINE.md`, `NUTRIENT_BUDGET_CHARTER.md`,
`IRRIGATION_ML_PIPELINE.md` (WC-сенсор — аналогичная логика)

---

## 1. Назначение

Все видимые проблемы растения приходят из корневой зоны, но с большой
задержкой. Невидимые симптомы (низкий DO → anaerobic condition → root rot)
обнаруживаются слишком поздно. Этот pipeline даёт ранние сигналы.

## 2. Цели

- Непрерывный мониторинг DO (dissolved oxygen) в растворе → алерт при < 5
  mg/L (критично для корней клубники).
- Root-zone temperature — пара-датчик на субстрат или в корневой объём,
  важен для uptake kinetics (Mg, Fe резко падает при < 15°C).
- Опционально: подводная/под-субстратная камера для визуального ревью
  корневой системы раз в неделю (detection root rot, abundance).

## 3. Ключевые дизайн-решения

1. **Минимальная конфигурация**: DO-probe + root-temp-probe. Оба в каждой
   зоне. Камера опциональна.
2. **DO как safety-критичная метрика**: резкий провал → немедленный alert
   + автозапуск oxygenation (аэратор, если есть) или advisory оператору.
3. **Ризосферная камера** (если есть): прозрачная вставка в субстрат
   (minirhizotron) с периодической камерой. Разметка root growth rate,
   health score.
4. **Интеграция с UPTAKE model из NUTRIENT_BUDGET**: rate → функция от
   `root_temp_c` (Arrhenius / Q10).

## 4. Структура данных

```sql
-- Расширение sensors.type enum: 'DO', 'ROOT_TEMP', 'ROOT_CAMERA'

CREATE TABLE root_zone_features_5m (
  ts timestamptz NOT NULL,
  zone_id bigint NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  do_mg_l double precision,
  do_saturation_pct double precision,
  root_temp_c double precision,
  root_temp_minus_air double precision,   -- важный diff
  q10_uptake_factor double precision,     -- derived
  valid_ratio double precision,
  feature_schema_version smallint DEFAULT 1,
  PRIMARY KEY (zone_id, ts)
);
SELECT create_hypertable('root_zone_features_5m','ts',chunk_time_interval=>interval '7 days');

CREATE TABLE root_health_assessments (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id),
  assessed_at timestamptz NOT NULL,
  source varchar(16) NOT NULL,            -- 'cv'|'manual'|'lab'
  image_id bigint REFERENCES plant_images(id),
  health_score double precision,
  root_density_index double precision,
  browning_score double precision,
  rot_probability double precision,
  notes text
);
```

## 5. Сервис

- Переиспользуется `vision-analyzer` с отдельной subtask под rhizosphere
  camera (редкий inference, 1/неделя).
- Данные с DO/temp probes — обычный `mqtt-bridge` → `telemetry_samples` →
  `feature-builder`.

## 6. Safety

- **DO < 4 mg/L более 10 мин** → immediate critical alert +
  «start_aeration» command (если есть аэратор).
- **Root rot probability > 0.6** → critical alert, плановое обследование
  оператором.

## 7. Интеграция

- **ML_FEATURE_PIPELINE** — добавить DO, root_temp в `zone_features_5m`
  как опциональные (NULL если нет сенсора).
- **NUTRIENT_BUDGET** — uptake rate функция от root_temp через Q10.
- **YIELD_FORECASTING** — root_health как ранний предиктор yield loss.

## 8. Фазы

| Phase | Задача | DoD |
|---|---|---|
| R0 | Инвентаризация: DO+root-temp в каждой зоне | Если нет — закупить |
| R1 | MQTT + миграции | Данные пишутся |
| R2 | DO safety triggers | Alert работает E2E |
| R3 | Q10-корректировка uptake | Параметр в `NUTRIENT_BUDGET.zone_dt_params` |
| R4 | Rhizosphere camera (optional) | Если куплено |
| R5 | Root rot classifier | На собственных данных + публичных |

## 9. Правила для ИИ-агентов

### Можно:
- Расширять классы root health assessments.
- Улучшать Q10 параметры.

### Нельзя:
- Объединять DO из разных зон в одну метрику (каждая зона — сама).
- Доверять DO без еженедельной калибровки (пробы деградируют быстро).

## 10. Открытые вопросы

1. Тип DO-пробы: optical (Hamilton VisiFerm) дорогая надёжная vs clark
   electrode дешёвая, требует обслуживания.
2. Rhizosphere camera: коммерческое решение (CID Bio-Science CI-600) vs
   самодельное на Pi + endoscope?
3. Частота root camera сбора: 1/день vs 1/неделя? Компромисс между данными
   и операторским временем разметки.

---

# Конец ROOT_ZONE_MONITORING_CHARTER.md
