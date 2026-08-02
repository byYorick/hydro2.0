# 07_FRONTEND — Frontend и UI/UX

Этот раздел содержит документацию по архитектуре фронтенда, UI/UX спецификации и тестированию.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 📋 Документы раздела

### Основные документы

#### [FRONTEND_ARCH_FULL.md](FRONTEND_ARCH_FULL.md)
**Полная архитектура фронтенда**
- Цели и принципы UI/UX
- Основные разделы фронтенда
- Подробное описание экранов
- Компоненты и UI элементы
- Real-time и WebSocket
- State Management

#### [FRONTEND_UI_UX_SPEC.md](FRONTEND_UI_UX_SPEC.md)
**Спецификация UI/UX**
- Дизайн-система
- Компоненты интерфейса
- Пользовательские сценарии
- Навигация

#### [FRONTEND_TESTING.md](FRONTEND_TESTING.md)
**Стратегия тестирования фронтенда**
- Unit/Component тесты (Vitest)
- Интеграционные тесты
- E2E тесты (Playwright)
- Конфигурация тестов

### Вспомогательные документы

#### [API_MAPPING.md](API_MAPPING.md)
Маппинг API endpoints между фронтендом и бэкендом

#### [ROLE_BASED_UI_SPEC.md](ROLE_BASED_UI_SPEC.md)
Спецификация ролевого UI (`canonical`)

### Living plans (`plan`)

- [LAUNCH_REDESIGN.md](LAUNCH_REDESIGN.md)
- [AUTOMATION_WIZARD_UNIFICATION_PLAN.md](AUTOMATION_WIZARD_UNIFICATION_PLAN.md)
- [ZONE_AUTOMATION_PRESETS_PLAN.md](ZONE_AUTOMATION_PRESETS_PLAN.md)
- [SCHEDULER_COCKPIT_REDESIGN.md](SCHEDULER_COCKPIT_REDESIGN.md)
- [SCHEDULER_COCKPIT_IMPLEMENTATION.md](SCHEDULER_COCKPIT_IMPLEMENTATION.md)
- [SCHEDULER_COCKPIT_MONITORING.md](SCHEDULER_COCKPIT_MONITORING.md)

### Архив plans (`archive` stubs → [`../00_ARCHIVE/PLANS/`](../00_ARCHIVE/PLANS/))

- [UI_UX_IMPROVEMENT_PLAN.md](UI_UX_IMPROVEMENT_PLAN.md)
- [FRONTEND_REWORK_PLAN.md](FRONTEND_REWORK_PLAN.md)
- [LAUNCH_LEGACY_CLEANUP_PLAN.md](LAUNCH_LEGACY_CLEANUP_PLAN.md)

Канон UI/UX — `FRONTEND_UI_UX_SPEC.md` + `FRONTEND_ARCH_FULL.md`; планы не подменяют спеки.

---

## 🔗 Связанные разделы

- **[01_SYSTEM](../01_SYSTEM/)** — системная архитектура
- **[04_BACKEND_CORE](../04_BACKEND_CORE/)** — backend интеграция и API
- **[06_DOMAIN_ZONES_RECIPES](../06_DOMAIN_ZONES_RECIPES/)** — доменная логика

---

## 🎯 С чего начать

1. **Архитектура фронтенда?** → Изучите [FRONTEND_ARCH_FULL.md](FRONTEND_ARCH_FULL.md)
2. **UI/UX спецификация?** → См. [FRONTEND_UI_UX_SPEC.md](FRONTEND_UI_UX_SPEC.md)
3. **Тестирование?** → Прочитайте [FRONTEND_TESTING.md](FRONTEND_TESTING.md)

---

**См. также:** [Главный индекс документации](../INDEX.md)
