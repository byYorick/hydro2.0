# 06_DOMAIN_ZONES_RECIPES — Доменная логика

Этот раздел содержит документацию по контроллерам зон, рецептам, планировщикам и событиям.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 📋 Документы раздела

### Основные документы

#### [ZONE_CONTROLLER_FULL.md](ZONE_CONTROLLER_FULL.md)
**Полная документация контроллеров зон**
- ZoneNutrientController (pH + EC)
- ZoneClimateController (температура, влажность, CO₂)
- ZoneIrrigationController (полив и рециркуляция)
- ZoneLightController (освещение)
- ZoneHealthMonitor (мониторинг состояния)

#### [RECIPE_ENGINE_FULL.md](RECIPE_ENGINE_FULL.md)
**Полная архитектура Recipe Engine**
- Назначение Recipe Engine
- Модель данных (ревизии, фазы, GrowCycle)
- Логика работы по зоне
- Связь с контроллерами

> Единственный нормативный документ по рецептам и фазам в дереве `doc_ai/` — `RECIPE_ENGINE_FULL.md` (модель GrowCycle / RecipeRevision).

#### [ZONES_AND_PRESETS.md](ZONES_AND_PRESETS.md)
**Зоны и пресеты**
- Типы зон
- Пресеты культур
- Шаблоны зон

#### [SCHEDULER_ENGINE.md](SCHEDULER_ENGINE.md)
**Планировщик**
- Расписания поливов
- Расписания света
- Расписания климата

#### [EVENTS_AND_ALERTS_ENGINE.md](EVENTS_AND_ALERTS_ENGINE.md)
**События и алерты**
- Типы событий
- Генерация алертов
- Обработка событий

### Специализированные документы

#### [ZONE_LOGIC_FLOW.md](ZONE_LOGIC_FLOW.md)
Логический поток работы зоны

#### [WATER_FLOW_ENGINE.md](WATER_FLOW_ENGINE.md)
Движок управления водой

#### [ALERTS_AND_NOTIFICATIONS_CHANNELS.md](ALERTS_AND_NOTIFICATIONS_CHANNELS.md)
Каналы уведомлений и алертов

#### [CORRECTION_CYCLE_SPEC.md](CORRECTION_CYCLE_SPEC.md)
Машина состояний циклов коррекции pH/EC (AE3)

#### [EFFECTIVE_TARGETS_SPEC.md](EFFECTIVE_TARGETS_SPEC.md)
Effective targets для контроллеров и authority bundles

#### [PID_CONFIG_REFERENCE.md](PID_CONFIG_REFERENCE.md)
Справочник настроек PID / калибровок в контрактах зоны

---

## 🔗 Связанные разделы

- **[01_SYSTEM](../01_SYSTEM/)** — системная архитектура
- **[04_BACKEND_CORE](../04_BACKEND_CORE/)** — backend интеграция
- **[05_DATA_AND_STORAGE](../05_DATA_AND_STORAGE/)** — модель данных

---

## 🎯 С чего начать

1. **Контроллеры зон?** → Изучите [ZONE_CONTROLLER_FULL.md](ZONE_CONTROLLER_FULL.md)
2. **Рецепты?** → См. [RECIPE_ENGINE_FULL.md](RECIPE_ENGINE_FULL.md)
3. **Планировщик?** → Прочитайте [SCHEDULER_ENGINE.md](SCHEDULER_ENGINE.md)
4. **События и алерты?** → См. [EVENTS_AND_ALERTS_ENGINE.md](EVENTS_AND_ALERTS_ENGINE.md)

---

**См. также:** [Главный индекс документации](../INDEX.md)
