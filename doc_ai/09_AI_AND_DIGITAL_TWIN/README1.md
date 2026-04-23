# hydro2.0 — AI/ML Plans Archive

Архив со всеми документами AI/ML слоя для проекта hydro2.0.

## Структура

Файлы расположены в целевой структуре репо:

```
doc_ai/09_AI_AND_DIGITAL_TWIN/
├── AI_ROADMAP.md                          ← начинать отсюда
│
├── ML_FEATURE_PIPELINE.md                 🟢 FULL
├── VISION_PIPELINE.md                     🟢 FULL
├── IRRIGATION_ML_PIPELINE.md              🟢 FULL
│
├── CLIMATE_CONTROL_CHARTER.md             🟡 Tier 1
├── NUTRIENT_BUDGET_CHARTER.md             🟡 Tier 1
├── YIELD_FORECASTING_CHARTER.md           🟡 Tier 1
├── IPM_CHARTER.md                         🟡 Tier 1
├── DIGITAL_TWIN_SIMULATOR_CHARTER.md      🟡 Tier 1
├── EXPLAINABILITY_UX_CHARTER.md           🟡 Tier 1
│
├── MULTI_ZONE_COORDINATION_CHARTER.md     🟡 Tier 2
├── ENERGY_OPTIMIZATION_CHARTER.md         🟡 Tier 2
├── ROOT_ZONE_MONITORING_CHARTER.md        🟡 Tier 2
├── SENSOR_HEALTH_CHARTER.md               🟡 Tier 2 (внедрять рано!)
├── UNIFIED_ALERTING_CHARTER.md            🟡 Tier 2 (до canary любой модели)
├── AB_TESTING_CHARTER.md                  🟡 Tier 2
├── DISASTER_RECOVERY_CHARTER.md           🟡 Tier 2
└── MOBILE_AR_CHARTER.md                   🟡 Tier 2
```

## Как использовать

1. Распаковать архив в корень репозитория hydro2.0
2. Все файлы попадут в правильное место (`doc_ai/09_AI_AND_DIGITAL_TWIN/`)
3. Обновить `doc_ai/INDEX.md` ссылкой на `09_AI_AND_DIGITAL_TWIN/AI_ROADMAP.md`
4. Начать чтение с `AI_ROADMAP.md` — там навигация, граф зависимостей и
   порядок внедрения

## Статусы

- **🟢 FULL** — развёрнутый план 800–1100 строк, готов к реализации,
  включает DDL, сервисы, фазы с DoD, правила для ИИ-агентов
- **🟡 CHARTER** — паспорт темы 150–250 строк; разворачивается в FULL при
  приближении к реализации по шаблону FULL-документов

## Дата

2026-04-22
