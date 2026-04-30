# 09_AI_AND_DIGITAL_TWIN — AI и цифровой двойник

Этот раздел содержит документацию по AI-архитектуре, оптимизации, симуляции и цифровому двойнику.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 📋 Документы раздела

### Основные документы

#### [AI_ARCH_FULL.md](AI_ARCH_FULL.md)
**Полная архитектура AI-слоя**
- Роль AI в системе
- Архитектура AI-слоя
- Источники данных
- Analytics Engine
- AI Reasoning Engine
- AI задания (Tasks)
- AI API
- Безопасность AI

#### [DIGITAL_TWIN_ENGINE.md](DIGITAL_TWIN_ENGINE.md)
**Движок цифрового двойника**
- Концепция цифрового двойника
- Моделирование зон
- Симуляция сценариев
- Оптимизация параметров

#### [ZONE_SIMULATION_ENGINE.md](ZONE_SIMULATION_ENGINE.md)
**Движок симуляции зон**
- Симуляция параметров зоны
- Прогнозирование поведения
- Тестирование рецептов

#### [AI_OPTIMIZATION_ENGINE.md](AI_OPTIMIZATION_ENGINE.md)
**Движок оптимизации**
- Оптимизация рецептов
- Оптимизация параметров
- Рекомендации по улучшению

#### [AI_ROADMAP.md](AI_ROADMAP.md)
**Дорожная карта AI/ML слоя**
- Очередность внедрения pipeline'ов
- Зависимости между AI/ML направлениями
- Статусы FULL/CHARTER/IDEA

### AI/ML pipeline plans

#### [ML_FEATURE_PIPELINE.md](ML_FEATURE_PIPELINE.md)
**Feature pipeline для ML-моделей**
- Витрины признаков
- Версионирование feature schemas
- Shadow/canary lifecycle моделей

#### [VISION_PIPELINE.md](VISION_PIPELINE.md)
**Computer vision pipeline**
- Ingest изображений
- Visual features
- Интеграция с прогнозами урожая и IPM

#### [IRRIGATION_ML_PIPELINE.md](IRRIGATION_ML_PIPELINE.md)
**ML pipeline умного полива**
- ET/VPD baseline
- Weather forecast integration
- Advisory/canary контур для irrigation decisions

### AI/ML charters

- [CLIMATE_CONTROL_CHARTER.md](CLIMATE_CONTROL_CHARTER.md)
- [NUTRIENT_BUDGET_CHARTER.md](NUTRIENT_BUDGET_CHARTER.md)
- [YIELD_FORECASTING_CHARTER.md](YIELD_FORECASTING_CHARTER.md)
- [IPM_CHARTER.md](IPM_CHARTER.md)
- [DIGITAL_TWIN_SIMULATOR_CHARTER.md](DIGITAL_TWIN_SIMULATOR_CHARTER.md)
- [EXPLAINABILITY_UX_CHARTER.md](EXPLAINABILITY_UX_CHARTER.md)
- [MULTI_ZONE_COORDINATION_CHARTER.md](MULTI_ZONE_COORDINATION_CHARTER.md)
- [ENERGY_OPTIMIZATION_CHARTER.md](ENERGY_OPTIMIZATION_CHARTER.md)
- [ROOT_ZONE_MONITORING_CHARTER.md](ROOT_ZONE_MONITORING_CHARTER.md)
- [SENSOR_HEALTH_CHARTER.md](SENSOR_HEALTH_CHARTER.md)
- [UNIFIED_ALERTING_CHARTER.md](UNIFIED_ALERTING_CHARTER.md)
- [AB_TESTING_CHARTER.md](AB_TESTING_CHARTER.md)
- [DISASTER_RECOVERY_CHARTER.md](DISASTER_RECOVERY_CHARTER.md)
- [MOBILE_AR_CHARTER.md](MOBILE_AR_CHARTER.md)

---

## 🔗 Связанные разделы

- **[01_SYSTEM](../01_SYSTEM/)** — системная архитектура
- **[06_DOMAIN_ZONES_RECIPES](../06_DOMAIN_ZONES_RECIPES/)** — доменная логика и рецепты
- **[10_AI_DEV_GUIDES](../10_AI_DEV_GUIDES/)** — гайды для ИИ-разработки

---

## 🎯 С чего начать

1. **AI/ML roadmap?** → Начните с [AI_ROADMAP.md](AI_ROADMAP.md)
2. **AI архитектура?** → Изучите [AI_ARCH_FULL.md](AI_ARCH_FULL.md)
3. **Цифровой двойник?** → См. [DIGITAL_TWIN_ENGINE.md](DIGITAL_TWIN_ENGINE.md)
4. **Симуляция?** → Прочитайте [ZONE_SIMULATION_ENGINE.md](ZONE_SIMULATION_ENGINE.md)
5. **Оптимизация?** → См. [AI_OPTIMIZATION_ENGINE.md](AI_OPTIMIZATION_ENGINE.md)

---

**См. также:** [Главный индекс документации](../INDEX.md)
