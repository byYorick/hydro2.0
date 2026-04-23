# AI_ROADMAP.md
# Мастер-дорожная карта AI/ML слоя hydro2.0
# Навигатор по всем pipeline-документам, зависимостям и очерёдности внедрения

**Статус:** DRAFT · живой документ
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/AI_ROADMAP.md`
**Compatible-With:** Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0

Документ — **первая точка входа** для любого человека или ИИ-агента,
работающего с AI/ML слоем. Остальные документы являются его детализациями.

---

## 1. Карта pipeline'ов

### Статусы:
- 🟢 **FULL** — есть развёрнутый PIPELINE.md (≥ 800 строк, готов к реализации)
- 🟡 **CHARTER** — есть паспорт темы (направление, структура данных, фазы);
  разворачивается в FULL по мере приближения к реализации
- ⚪️ **IDEA** — только упоминание в §8

### Ядро (уже покрыто полными планами)

| # | Pipeline | Статус | Что делает |
|---|---|---|---|
| 1 | `ML_FEATURE_PIPELINE` | 🟢 | Witness для pH/EC/телеметрии: прогноз дрейфа, детекция аномалий, модель дозирования |
| 2 | `VISION_PIPELINE` | 🟢 | CV: рост, цвет/дефициты, болезни, плоды. Клубника + top-down камера |
| 3 | `IRRIGATION_ML_PIPELINE` | 🟢 | Умный полив: VPD/ET baseline + learned Kc + weather forecast |

### Tier 1 — синергичные расширения (внедрять в первую очередь)

| # | Charter | Статус | Зависит от | Что даёт |
|---|---|---|---|---|
| 4 | `CLIMATE_CONTROL_CHARTER` | 🟡 | 1, 3 | Управление HVAC/шторами/CO2. Замыкает физический контур |
| 5 | `NUTRIENT_BUDGET_CHARTER` | 🟡 | 1 | Переход от EC (общее) к балансу ионов (NO₃⁻/K⁺/Ca²⁺). Решает tip-burn у клубники |
| 6 | `YIELD_FORECASTING_CHARTER` | 🟡 | 2 | Прогноз урожая в кг/дни + экономический слой. Превращает ML в деньги |
| 7 | `IPM_CHARTER` | 🟡 | 2 | Integrated Pest Management: клейкие ловушки + биоагенты |
| 8 | `DIGITAL_TWIN_SIMULATOR_CHARTER` | 🟡 | 1, 3 | Полноценный what-if engine → RL-среда + recipe optimization |
| 9 | `EXPLAINABILITY_UX_CHARTER` | 🟡 | 1, 2, 3 | SHAP + counterfactuals + operator trust. Без этого ML выключают |

### Tier 2 — поддерживающая инфраструктура

| # | Charter | Статус | Что даёт |
|---|---|---|---|
| 10 | `MULTI_ZONE_COORDINATION_CHARTER` | 🟡 | Общие ресурсы (баки, HVAC), load balancing |
| 11 | `ENERGY_OPTIMIZATION_CHARTER` | 🟡 | Dynamic pricing + thermal mass, подсветка в дешёвые часы |
| 12 | `ROOT_ZONE_MONITORING_CHARTER` | 🟡 | DO, температура корней, под-субстратная камера |
| 13 | `SENSOR_HEALTH_CHARTER` | 🟡 | Cross-check датчиков, drift detection, auto-calibration |
| 14 | `UNIFIED_ALERTING_CHARTER` | 🟡 | Приоритизация/дедуп/escalation |
| 15 | `AB_TESTING_CHARTER` | 🟡 | Строгие эксперименты с рецептами |
| 16 | `DISASTER_RECOVERY_CHARTER` | 🟡 | Offline-режимы, local fallback |
| 17 | `MOBILE_AR_CHARTER` | 🟡 | Оператор наводит телефон → overlay |

---

## 2. Граф зависимостей (упрощённо)

```
                     ┌─────────────────────────┐
                     │ ML_FEATURE_PIPELINE (1) │ ◄── фундамент всего
                     └──┬───────────────────┬──┘
                        │                   │
                        ▼                   ▼
        ┌─────────────────────┐  ┌─────────────────────────┐
        │ VISION_PIPELINE (2) │  │ IRRIGATION_ML_PIPE (3)  │
        └──┬──────────────────┘  └──┬──────────────────────┘
           │                        │
           ├── YIELD_FORECASTING (6) ┤
           ├── IPM (7)               │
           │                         ├── CLIMATE_CONTROL (4) ◄── собирает физ. контур
           │                         │
           │                         ├── NUTRIENT_BUDGET (5) ◄── если есть ion probes
           │                         ├── ROOT_ZONE (12)      ◄── если есть DO
           │                         │
           └── EXPLAINABILITY (9) ◄──┤
                                     │
                       DIGITAL_TWIN_SIM (8) ◄── cross-cutting (симулятор под всё)

       Поддержка (cross-cutting):
        · SENSOR_HEALTH (13)
        · UNIFIED_ALERTING (14)
        · AB_TESTING (15)
        · MULTI_ZONE_COORD (10)
        · ENERGY_OPT (11)
        · DISASTER_RECOVERY (16)
        · MOBILE_AR (17)
```

Ключевые зависимости, которые нельзя нарушать:
- `ML_FEATURE_PIPELINE` идёт первым. Его `feature-builder`, `ml_models`,
  `ml_predictions` переиспользуются всеми остальными.
- `YIELD_FORECASTING` не имеет смысла без `VISION_PIPELINE` (подсчёт плодов).
- `CLIMATE_CONTROL` и `IRRIGATION_ML` должны быть co-optimized — «проветрить»
  vs «полить» пересекаются физически.
- `EXPLAINABILITY_UX` включается **после** того, как в prod живёт хоть одна
  ML-модель, иначе объяснять нечего.

---

## 3. Рекомендуемая очерёдность (12 месяцев)

### Квартал 1 — Data foundation
1. `ML_FEATURE_PIPELINE` Phase 0–3 (расширение агрегатов + feature-builder + dose-response)
2. `SENSOR_HEALTH_CHARTER` Phase 0–1 (sensor sanity перед тем как всё строить поверх)
3. `VISION_PIPELINE` Phase V0–V2 (железо + ingest + базовая сегментация)

### Квартал 2 — Первые модели в shadow
4. `ML_FEATURE_PIPELINE` Phase 4–6 (training notebooks → shadow models)
5. `VISION_PIPELINE` Phase V3–V4 (ground truth UI + болезни)
6. `IRRIGATION_ML_PIPELINE` Phase I0–I3 (weather + rule-based + ET baseline)
7. `UNIFIED_ALERTING_CHARTER` (минимум — перед canary rollout любой модели)

### Квартал 3 — Canary → Active
8. `IRRIGATION_ML_PIPELINE` Phase I4–I6 (canary, потом ML shadow)
9. `EXPLAINABILITY_UX_CHARTER` (одновременно с canary, иначе доверия не будет)
10. `CLIMATE_CONTROL_CHARTER` Phase 0–2
11. `YIELD_FORECASTING_CHARTER` Phase 0–2 (когда накопится 3 мес визуальных данных)

### Квартал 4 — Economic wrap + advanced
12. `YIELD_FORECASTING` Phase 3 (экономический слой)
13. `NUTRIENT_BUDGET_CHARTER` (если поставлены ion probes)
14. `DIGITAL_TWIN_SIMULATOR_CHARTER` (параметры калиброваны на накопленных данных)
15. `IPM_CHARTER` (запуск раз в сезон, попадает когда теплица позволяет)

### Далее (по мере масштаба)
- `MULTI_ZONE_COORDINATION` при ≥ 10 зон в проде
- `ENERGY_OPTIMIZATION` при переходе на dynamic-pricing тариф
- `AB_TESTING_CHARTER` когда рецептов становится > 3 параллельно
- `ROOT_ZONE_MONITORING` если потребуется
- `MOBILE_AR`, `DISASTER_RECOVERY` — оппортунистически

---

## 4. Общие конвенции (ссылки, не дублировать)

Все документы слоя AI/ML следуют одним и тем же правилам. Базовые приняты
в трёх FULL-документах, здесь только ссылки:

| Тема | Где описано |
|---|---|
| Point-in-time correctness | `ML_FEATURE_PIPELINE §8` |
| Feature schema versioning | `ML_FEATURE_PIPELINE §7.1` |
| Model lifecycle (shadow→canary→active) | `ML_FEATURE_PIPELINE §12` |
| Safety: ML advisory only, не control | `ML_FEATURE_PIPELINE §12.2` + `IRRIGATION_ML_PIPELINE §9` |
| Naming ML-моделей | `ml_models.name` из `ML_FEATURE_PIPELINE §5.6` |
| Owner-таблица (single writer) | `ML_FEATURE_PIPELINE §7.1` |
| Quality windows (исключения из тренировки) | `ML_FEATURE_PIPELINE §5.8` |
| Inference log | `ml_predictions` из `ML_FEATURE_PIPELINE §5.7` |
| Retention policy шаблон | `DATA_RETENTION_POLICY.md` |
| MQTT топики | `TELEMETRY_PIPELINE.md §2` |
| Зонные настройки | `automation_config_documents` из `DATA_MODEL_REFERENCE` |

**ИИ-агенту:** не дублируй эти конвенции в новых документах — ссылайся на
первоисточник. Дубликаты быстро разъезжаются и становятся источником багов.

---

## 5. Именование документов

- Полный план: `{DOMAIN}_PIPELINE.md` или `{DOMAIN}_ML_PIPELINE.md`
- Паспорт: `{DOMAIN}_CHARTER.md`
- Расширения: `{DOMAIN}_{SPECIFIC}.md` (например `VISION_STICKY_TRAPS.md`)
- Каждый файл — в `doc_ai/09_AI_AND_DIGITAL_TWIN/`
- Каждый документ обязан начинаться с блока:
  ```
  **Статус:** DRAFT | IMPLEMENTED | DEPRECATED
  **Целевое размещение:** ...
  **Связанные документы:** ...
  **Compatible-With:** ...
  ```

---

## 6. Разделение ответственности между документами

Во избежание пересечений:

| Тема | Owner-документ | Кто может читать |
|---|---|---|
| pH/EC прогноз, доза | `ML_FEATURE_PIPELINE` | все |
| CV (растение, плод, болезнь) | `VISION_PIPELINE` | yield, ipm, irrigation |
| Полив (когда, сколько) | `IRRIGATION_ML_PIPELINE` | climate |
| HVAC, CO2, шторы | `CLIMATE_CONTROL` | irrigation, energy |
| Yield/economics | `YIELD_FORECASTING` | все (высокоуровневый KPI) |
| IPM (ловушки, биоагенты) | `IPM` | — |
| Ion balance, nutrient depletion | `NUTRIENT_BUDGET` | ML_FEATURE |
| Simulator / digital twin | `DIGITAL_TWIN_SIMULATOR` | все (как источник what-if) |
| UX объяснения | `EXPLAINABILITY_UX` | все (cross-cutting UI) |
| Алерты, приоритизация | `UNIFIED_ALERTING` | все (как sink для alert'ов) |
| Cross-check датчиков | `SENSOR_HEALTH` | все (как preflight для данных) |
| Эксперименты | `AB_TESTING` | все (как методология) |

Если возникает вопрос «где описать новую фичу» — он описывается в owner-документе,
а в остальных ссылается.

---

## 7. Правила для ИИ-агентов (глобальные)

### Можно:
- Продвигать статус документа 🟡 CHARTER → 🟢 FULL, дописывая недостающие
  разделы (DDL, формулы, фазы с DoD, safety).
- Создавать новые charter'ы под направления из §8 ниже, следуя шаблону.
- Обновлять `AI_ROADMAP.md` при добавлении/удалении pipeline'ов.

### Нельзя:
- Создавать FULL-документ без ревью charter-версии первым (чтобы не
  строить 1000 строк вокруг неправильной идеи).
- Изменять общие конвенции §4 в одном pipeline, не обновляя остальные.
- Вводить новые `ml_models.name` без записи в `AI_ROADMAP §1`.
- Выводить модель в `active` без соответствующих записей в
  `EXPLAINABILITY_UX` (без UI-объяснения).

### Обязательно:
- Каждый PR, меняющий AI-слой, обновляет этот `AI_ROADMAP.md` если меняется
  состав, зависимости или статус pipeline'ов.
- Каждый charter отвечает на вопрос «как это связано с §1 ядром» явно.

---

## 8. Идеи в зоне IDEA (когда-нибудь потом, не планировать сейчас)

- **Federated learning между фермами** — модель обучается на N теплицах без
  обмена сырыми данными. Интересно, но требует критической массы клиентов.
- **LLM-ассистент для оператора** — «почему вчера урожай упал?» с доступом к
  БД и объяснением на естественном языке. Нужна отдельная безопасностная
  модель (retrieval + guardrails).
- **Multi-crop support** — сейчас всё под клубнику. Если появятся помидоры
  или огурцы — сквозные классы фенологий и Kc-таблиц.
- **Genetic algorithm для подбора рецептов** — верхний слой поверх
  `DIGITAL_TWIN_SIMULATOR`, когда симулятор точен.
- **Causal inference для A/B тестов** — DoWhy / CausalML для
  confounder-adjustment, когда факторов > 5.
- **Edge AI на узлах** — изначально отклонили (стр. V), но могут понадобиться
  для больших ферм с плохим интернетом.

---

## 9. Живой раздел: changelog

| Дата | Изменение | Автор |
|---|---|---|
| 2026-04-22 | Первая версия, 3 FULL + 14 CHARTER | claude |

---

# Конец файла AI_ROADMAP.md
