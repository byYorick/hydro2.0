# EXPLAINABILITY_UX_CHARTER.md
# Паспорт pipeline: объяснимость ML-решений + UX доверия оператора

**Статус:** 🟡 CHARTER
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/EXPLAINABILITY_UX_CHARTER.md`
**Связанные:** `ML_FEATURE_PIPELINE.md`, `IRRIGATION_ML_PIPELINE.md`,
`DIGITAL_TWIN_SIMULATOR_CHARTER.md`, существующий `FRONTEND_ARCH_FULL.md`

---

## 1. Назначение

ML без explainability — это чёрный ящик, который операторы перестают
доверять после первого странного решения. Этот pipeline обеспечивает:
- каждую рекомендацию ML видно с разложением «почему»;
- counterfactuals «что изменится, если параметр Z будет другим»;
- ретроспективный анализ «почему модель ошиблась вчера»;
- механизм feedback: оператор может «не согласен» + причина, это feedback
  уходит в переобучение.

## 2. Цели

- Каждая запись в `ml_predictions` / `*_advisories` снабжена объяснением
  в терминах, понятных оператору.
- UI-компонент «Why this?» доступен на всех advisory-карточках.
- Counterfactual simulator — «если бы VPD был 0.8 вместо 1.2, что бы
  изменилось» через `DIGITAL_TWIN_SIMULATOR`.
- Operator override: дизагри с объяснением пишется в БД, влияет на training
  (с явным label шумом, не blindly).

## 3. Ключевые дизайн-решения

1. **SHAP-values для структурных моделей** (XGBoost, LightGBM) — считаются
   на inference и сохраняются рядом с предсказанием.
2. **Attention maps для CV** (Grad-CAM / attention rollout для DINOv2) —
   визуализация, где модель смотрела.
3. **Тест на интерпретируемость** — модель считается «active-ready» только
   если её объяснения проходят human review (random 20 решений, ≥ 80%
   «разумных» согласно агроному).
4. **Textual summaries** — на каждое решение генерируется 1–2 предложения
   («полив сработал из-за высокого VPD-integral 3.1 kPa·h и прогноза solar
   в ближайшие 2 часа 650 W/m²»). Шаблоны, не LLM (детерминизм).
5. **Counterfactual UI**: оператор двигает слайдер фичи → UI вызывает
   `digital-twin` с модифицированным входом → показывает delta.

## 4. Структура данных

```sql
-- расширение ml_predictions (или отдельная таблица)
ALTER TABLE ml_predictions
  ADD COLUMN explanation jsonb,           -- {shap: {...}, saliency_uri: 's3://', ...}
  ADD COLUMN text_summary text,
  ADD COLUMN explainability_version smallint DEFAULT 1;

CREATE TABLE operator_feedback (
  id bigserial PRIMARY KEY,
  prediction_id bigint REFERENCES ml_predictions(id) ON DELETE CASCADE,
  advisory_id bigint,                     -- опц. ссылка
  zone_id bigint NOT NULL REFERENCES zones(id),
  operator_id bigint NOT NULL REFERENCES users(id),
  submitted_at timestamptz NOT NULL,
  agreement varchar(16) NOT NULL,         -- 'agree'|'disagree'|'uncertain'
  reason_code varchar(32),                -- 'context_missed'|'wrong_action'|'wrong_timing'|'sensor_doubt'|'other'
  free_text text,
  alternative_suggestion jsonb,           -- что сделал бы оператор сам
  used_for_retrain boolean DEFAULT false
);

CREATE TABLE counterfactual_runs (
  id bigserial PRIMARY KEY,
  prediction_id bigint REFERENCES ml_predictions(id),
  operator_id bigint REFERENCES users(id),
  run_at timestamptz NOT NULL,
  modified_inputs jsonb NOT NULL,         -- {vpd: 0.8, solar: 400, ...}
  simulation_run_id bigint REFERENCES simulation_runs(id),
  delta_summary jsonb,                    -- {ph_delta_2h: +0.05, ec_delta_2h: -0.1, ...}
  shareable boolean DEFAULT false
);

CREATE TABLE model_review_sessions (
  id bigserial PRIMARY KEY,
  model_id bigint REFERENCES ml_models(id),
  reviewed_by bigint REFERENCES users(id),
  reviewed_at timestamptz NOT NULL,
  n_predictions_reviewed integer NOT NULL,
  n_reasonable integer NOT NULL,
  notes text,
  passed boolean NOT NULL                 -- ≥80% — true
);
```

## 5. Сервисы / компоненты

| Компонент | Роль |
|---|---|
| `explanation-generator` (часть inference-server) | Считает SHAP/attention + text summary на inference |
| Vue3 component `<AdvisoryExplanation>` | UI раскрывает «Why this?» |
| Vue3 component `<CounterfactualPanel>` | Слайдеры + вызов симулятора |
| Laravel endpoint `/feedback` | Принимает `operator_feedback` |
| `retrain-gateway` (часть training pipeline) | Использует feedback с учётом веса |

## 6. Модели / алгоритмы

- **SHAP**: TreeSHAP для XGBoost/LightGBM (быстро), KernelSHAP для nnets
  (дороже, но redundant если модель уже интерпретируется через attention).
- **Grad-CAM / AttentionRollout** для CV-моделей.
- **Text summary templates**: структурированные, per-model шаблоны:
  ```
  {action_verb} сработал из-за:
  • {top_feature_1}: {value_1} ({direction})
  • {top_feature_2}: {value_2} ({direction})
  Прогноз на следующие {horizon}: {forecast_value}.
  ```
- **Counterfactual**: слайдеры → вызов `digital-twin` / `SIMULATOR`.

## 7. Governance

- **Model promotion gate**: ни одна модель не выходит из shadow в canary без
  прохождения `model_review_sessions` (≥ 80% reasonable).
- **Feedback loop governance**: disagreement пишется, но в retraining идёт
  только после триажа (noise label отсекается).

## 8. Фазы

| Phase | Задача | DoD |
|---|---|---|
| E0 | SHAP computation в inference-server | `explanation.shap` пишется |
| E1 | Text summary templates per model | UI показывает 1-2 предложения |
| E2 | Vue `<AdvisoryExplanation>` | Оператор видит «Why this?» |
| E3 | Feedback UI + endpoint | Данные пишутся |
| E4 | Counterfactual panel + simulator integration | Слайдер работает |
| E5 | Model review session workflow | Перед canary — ревью пройдено |
| E6 | Feedback-weighted retraining | Feedback реально влияет на новые версии |

## 9. Интеграция

- **Все ML pipeline'ы обязаны** проходить через `explanation-generator`
  для production predictions.
- **SIMULATOR** используется counterfactual-панелью.
- **YIELD_FORECASTING** интегрируется в объяснения: «если принять это
  advisory, ожидается yield change = +X кг/зона/неделя».

## 10. Правила для ИИ-агентов

### Можно:
- Добавлять новые text-summary templates для новых моделей.
- Улучшать SHAP-визуализации.

### Нельзя:
- Деплоить новую модель в canary/active без `model_review_sessions.passed=true`.
- Использовать LLM для генерации summary в prod (недетерминизм + риск
  галлюцинаций). Только шаблоны.
- Использовать operator_feedback напрямую без triage (шумная разметка).

## 11. Открытые вопросы

1. Для CV-моделей — сохранять saliency map (PNG) для каждого inference или
   только top-N самых уверенных? Trade-off storage vs debugging.
2. Нужен ли A/B тест самой explainability: половина операторов видит
   объяснения, половина нет — кто больше доверяет системе?
3. Как отличить «информированное несогласие» оператора от простого
   saying-no на всё? Требует confidence rating на каждый feedback?

---

# Конец EXPLAINABILITY_UX_CHARTER.md
