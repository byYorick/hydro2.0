# AB_TESTING_CHARTER.md
# Паспорт pipeline: A/B эксперименты над рецептами и моделями

**Статус:** 🟡 CHARTER (включать при > 3 параллельных рецептах / моделей)
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/AB_TESTING_CHARTER.md`
**Связанные:** `YIELD_FORECASTING_CHARTER.md`, `ML_FEATURE_PIPELINE.md§12`

---

## 1. Назначение

Ферма как научная лаборатория: сравниваем рецепты, модели, стратегии
полива/климата строго, чтобы решения основывались на фактах, а не на «у
Васи прошлый сезон был лучше».

## 2. Цели

- Регистрировать эксперимент с явными hypothesis, primary/secondary
  metrics, analysis plan.
- Считать power-analysis до старта (сколько зон × сколько недель нужно).
- Контролировать multiple comparisons (Bonferroni / BH) для не-ложных
  открытий.
- Интеграция с `yield-forecasting.cost_rates/revenue_rates` → результат
  в деньгах.
- Audit trail: кто запустил, кто закрыл, почему.

## 3. Ключевые дизайн-решения

1. **Zone как unit of randomization** — не грядка, не растение (слишком
   сильные spillover effects).
2. **Two-stage**: pre-registration (до старта фиксируем план) → exec →
   analysis (по фиксированному плану).
3. **Mandatory holdout**: в любой момент ≥ 20% зон держатся на baseline
   стратегии для контроля.
4. **Sequential analysis**: разрешаются «заглядывания» при использовании
   alpha-spending (Pocock / O'Brien-Fleming), не классический fixed-sample
   t-test.
5. **Confounder logging**: сорт, возраст растений, климат-зоны —
   явно в дизайне.

## 4. Структура данных

```sql
CREATE TABLE experiments (
  id bigserial PRIMARY KEY,
  name varchar(128) NOT NULL,
  hypothesis text NOT NULL,
  description text,
  created_by bigint REFERENCES users(id),
  created_at timestamptz NOT NULL,

  -- pre-registration
  primary_metric varchar(64) NOT NULL,   -- 'yield_kg_per_m2_28d'|'water_L_per_kg'|'mae_ph_forecast'
  primary_metric_mde double precision,   -- minimum detectable effect
  secondary_metrics jsonb,
  analysis_method varchar(32),           -- 't_test'|'wilcoxon'|'bayesian_ab'|'sequential_pocock'
  alpha double precision NOT NULL DEFAULT 0.05,
  power double precision NOT NULL DEFAULT 0.8,
  n_zones_required integer,
  duration_days integer,

  -- lifecycle
  status varchar(16) NOT NULL,           -- 'draft'|'active'|'analyzing'|'closed'|'aborted'
  started_at timestamptz,
  closed_at timestamptz,
  conclusion varchar(32),                -- 'A_wins'|'B_wins'|'no_diff'|'inconclusive'|'aborted'
  final_report_uri text
);

CREATE TABLE experiment_variants (
  id bigserial PRIMARY KEY,
  experiment_id bigint NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  variant_code varchar(16) NOT NULL,     -- 'control'|'A'|'B'|'C'
  description text,
  spec jsonb NOT NULL,                   -- рецепт/модель-настройки
  is_control boolean DEFAULT false,
  UNIQUE (experiment_id, variant_code)
);

CREATE TABLE experiment_assignments (
  id bigserial PRIMARY KEY,
  experiment_id bigint NOT NULL REFERENCES experiments(id),
  zone_id bigint NOT NULL REFERENCES zones(id),
  variant_id bigint NOT NULL REFERENCES experiment_variants(id),
  assigned_from timestamptz NOT NULL,
  assigned_to timestamptz,
  stratum jsonb,                         -- confounders: cultivar, age, climate_zone
  UNIQUE (experiment_id, zone_id, assigned_from)
);

CREATE TABLE experiment_results (
  id bigserial PRIMARY KEY,
  experiment_id bigint NOT NULL REFERENCES experiments(id),
  computed_at timestamptz NOT NULL,
  variant_code varchar(16) NOT NULL,
  metric_name varchar(64) NOT NULL,
  n_observations integer,
  mean double precision,
  stderr double precision,
  p_value double precision,
  confidence_interval jsonb,
  is_final boolean
);
```

## 5. Сервис `experiment-runner`

- API для создания эксперимента (pre-registration).
- Zone assignment: stratified randomization.
- Еженедельная aggregation метрик.
- Statistical tests по `analysis_method`.
- Final report generation (template + auto-charts).

## 6. Фазы

| Phase | Задача | DoD |
|---|---|---|
| AB0 | Миграции + API pre-registration | UI позволяет создать эксперимент в draft |
| AB1 | Power analysis calculator | Показывает «нужно N зон на M недель» |
| AB2 | Zone assignment + holdout reserve | Auto-assign работает |
| AB3 | Weekly aggregation + Bayesian A/B | Результаты обновляются |
| AB4 | Report generation | PDF / HTML отчёт в конце |
| AB5 | Sequential stopping rules | Можно безопасно останавливать досрочно |

## 7. Интеграция

- **YIELD_FORECASTING** — primary metric часто yield-based.
- **ML_FEATURE_PIPELINE** — модели сравниваются как variants, этот pipeline
  оценивает их.
- **UNIFIED_ALERTING** — эксперимент закончен → alert оператору.

## 8. Правила для ИИ-агентов

### Можно:
- Добавлять новые metrics templates.
- Улучшать statistical methods.

### Нельзя:
- Изменять analysis plan после старта эксперимента (p-hacking).
- Раскрывать промежуточные результаты операторам (bias в ходе).
- Стартовать эксперимент без power analysis и pre-registration.

## 9. Открытые вопросы

1. Одновременные эксперименты на одних зонах (multi-factor design)? Риск
   interference.
2. Как обрабатывать «variant-specific» проблемы (сломалось только в варианте B)?
3. Что делать, если сорт в part зон заменили в ходе эксперимента?

---

# Конец AB_TESTING_CHARTER.md
