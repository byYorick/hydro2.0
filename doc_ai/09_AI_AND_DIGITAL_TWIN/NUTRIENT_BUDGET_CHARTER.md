# NUTRIENT_BUDGET_CHARTER.md
# Паспорт pipeline: баланс ионов (глубже, чем pH/EC)

**Статус:** 🟡 CHARTER
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/NUTRIENT_BUDGET_CHARTER.md`
**Связанные:** `ML_FEATURE_PIPELINE.md`, `VISION_PIPELINE.md` (tip-burn signals),
`IRRIGATION_ML_PIPELINE.md` (leaching fraction)

---

## 1. Назначение

EC говорит «сколько всего солей», но не «каких». Клубника критически зависит
от баланса K:Ca:Mg — избыток K блокирует Ca, что даёт tip-burn (основная
визуальная болячка клубники). pH/EC pipeline этого не видит.

С ion-selective probes (NO₃⁻, K⁺, Ca²⁺, минимум) мы переходим от реактивного
«EC упал, долить сток» к проактивному «через 8 часов K закончится первым,
корректировать стокa заранее».

## 2. Цели

- Реал-тайм мониторинг 4–6 ключевых ионов: NO₃⁻, NH₄⁺, K⁺, Ca²⁺, Mg²⁺, PO₄³⁻.
- Предсказание депляции каждого иона на 12–48 часов.
- Автоматический пересчёт рецепта стока в сторону компенсации быстро
  убывающих ионов.
- Обнаружение antagonism-паттернов (K↑ → Ca↓ → tip-burn через 72ч) —
  заблаговременно.

## 3. Ключевые дизайн-решения

1. **Иерархия точности измерений:**
   - Tier A (дорого, точно): ISE-пробы в баке, 1/час
   - Tier B (средне): раз в сутки вручную лаб-анализ, калибровка Tier A
   - Tier C (дёшево): расчётная оценка из EC + история (fallback, когда
     сенсоры недоступны)
2. **Bayesian update** — каждый Tier A читает обновляет posterior над
   концентрациями; Tier B даёт сильный prior на неделю.
3. **Uptake model** — Michaelis-Menten kinetics для каждого иона: потребление
   зависит от концентрации в растворе и температуры корней. Параметры
   калибруются по истории «сколько убыло за сутки при заданных условиях».
4. **Антагонизмы явно**: матрица известных взаимодействий в `ion_antagonisms`
   (K↔Ca, K↔Mg, Ca↔Mg, NH₄↔Ca, NH₄↔K и т.д.). ML-модель учит силу
   антагонизма в конкретной ванне.

## 4. Структура данных

```sql
CREATE TABLE ion_measurements (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  ts timestamptz NOT NULL,
  source_tier varchar(1) NOT NULL,       -- 'A'|'B'|'C'
  ion varchar(16) NOT NULL,              -- 'NO3'|'K'|'Ca'|'Mg'|'P'|'NH4'
  concentration_mmol_l double precision NOT NULL,
  uncertainty_mmol_l double precision,   -- для tier A — погрешность пробы
  sensor_id bigint REFERENCES sensors(id),
  lab_sample_id bigint,                  -- FK на lab_samples если tier B
  schema_version smallint DEFAULT 1
);
CREATE INDEX ion_meas_zone_ion_ts ON ion_measurements (zone_id, ion, ts DESC);
SELECT create_hypertable('ion_measurements','ts',chunk_time_interval=>interval '30 days');

CREATE TABLE ion_targets_by_phase (
  id bigserial PRIMARY KEY,
  recipe_phase varchar(32) NOT NULL,
  ion varchar(16) NOT NULL,
  target_mmol_l double precision NOT NULL,
  min_mmol_l double precision NOT NULL,
  max_mmol_l double precision NOT NULL,
  source varchar(32),                    -- 'de_kreij_2003'|'custom'
  UNIQUE (recipe_phase, ion)
);

CREATE TABLE ion_antagonisms (
  dominant_ion varchar(16) NOT NULL,
  suppressed_ion varchar(16) NOT NULL,
  antagonism_coef double precision NOT NULL,
  PRIMARY KEY (dominant_ion, suppressed_ion)
);

CREATE TABLE ion_depletion_forecasts (
  id bigserial PRIMARY KEY,
  zone_id bigint REFERENCES zones(id),
  generated_at timestamptz NOT NULL,
  ion varchar(16) NOT NULL,
  hours_until_below_target double precision,
  hours_until_below_min double precision,
  recommended_correction_mmol double precision,
  confidence double precision,
  model_id bigint REFERENCES ml_models(id),
  PRIMARY KEY (id)
);

CREATE TABLE lab_samples (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id),
  collected_at timestamptz NOT NULL,
  collected_by bigint REFERENCES users(id),
  lab_received_at timestamptz,
  results_returned_at timestamptz,
  results jsonb,                         -- {NO3: x, K: y, ...}
  lab_id varchar(64)
);
```

Расширение `nutrient_products`: поле `ion_composition_mmol_per_ml` (JSONB)
— сколько каждого иона даёт 1 мл продукта.

## 5. Сервисы

| Сервис | Роль |
|---|---|
| `ion-probe-reader` | Новый MQTT-подписчик на топики ISE-проб, запись в `ion_measurements` tier A |
| `nutrient-forecaster` | Расширение `feature-builder`: forecast депляции + update `ion_depletion_forecasts` |
| `stock-composer` | Автоматически пересчитывает рецепт стока A+B при обнаружении депляции |

## 6. Модели

- **Per-ion depletion forecaster** (XGBoost / Prophet) — время до
  `below_target` на основе истории uptake, фазы, canopy_area, forecast света.
- **Antagonism strength estimator** — ElasticNet на истории, какие ionics
  реально давят друг друга в этой ванне.
- **Stock optimization** — LP (linear program) на cvxpy: найти объёмы
  добавления каждого стока так, чтобы все ионы попали в коридор.

## 7. Safety

- Ion-based recommendations **никогда не шлют команды насосам напрямую** —
  только через существующий dose-response pipeline (advisory).
- `MAX_DAILY_IONIC_DOSE_MMOL_PER_ION` — хард-лимит (anti-перебор при ошибке
  пробы).
- Tier A probe с `uncertainty > threshold` → игнорируется до калибровки.

## 8. Фазы

| Phase | Задача | DoD |
|---|---|---|
| N0 | Инвентарь: какие ISE-пробы есть/нужны | Зона помечена как `ion_monitoring_ready` |
| N1 | Миграции + `ion-probe-reader` | Измерения пишутся в `ion_measurements` |
| N2 | UI для ручных lab_samples | Агроном вводит результаты сдачи проб |
| N3 | Baseline uptake model | Калибровка Michaelis-Menten параметров |
| N4 | Depletion forecaster | Прогноз на 24ч, MAE ≤ 15% |
| N5 | Stock-composer advisory | UI показывает рекомендации по коррекции |
| N6 | Auto-correction canary | С явным согласованием |

## 9. Интеграция

- **VISION_PIPELINE**: `tip_burn_score_max` → сильный сигнал Ca-дефицита,
  модель депляции Ca должна его учитывать как observation.
- **ML_FEATURE_PIPELINE**: расширение `zone_features_5m` колонками
  `ion_{no3,k,ca,mg}_mmol_l` (NULL если нет tier A).
- **IRRIGATION_ML_PIPELINE**: leaching fraction влияет на soluble-ion
  balance (промывка → вымываются все ионы пропорционально); модель стока
  учитывает это.

## 10. Правила для ИИ-агентов

### Можно:
- Добавлять ионы в enum (с миграцией и заполнением ion_targets для всех фаз).
- Расширять `ion_antagonisms` с цитатой источника.

### Нельзя:
- Писать в `ion_targets_by_phase` из кода — только через UI с ревью
  агронома.
- Использовать tier C (расчёт из EC) без явного флага "estimated=true".
- Доверять tier A без tier B-калибровки свежее 7 дней.

## 11. Открытые вопросы

1. Какие ISE-пробы покупаем? Horiba LAQUAtwin (дёшево, периодические
   измерения) vs Bluelab (online, дороже)?
2. Интервал лаб-проб tier B: еженедельно vs раз в 2 недели? Зависит от
   скорости дрейфа ISE.
3. Для NH₄⁺ в гидропонике (клубника предпочитает NO₃⁻) — мониторить
   или запрещать в рецепте?
4. Нужна ли модель per-zone или глобальная на всю ферму?

---

# Конец NUTRIENT_BUDGET_CHARTER.md
