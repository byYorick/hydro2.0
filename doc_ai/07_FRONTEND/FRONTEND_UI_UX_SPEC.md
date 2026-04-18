# FRONTEND_UI_UX_SPEC.md
# Полная спецификация UI/UX фронтенда 2.0 (Laravel + Inertia + Vue 3)
# Инструкция для ИИ-агентов

Этот документ определяет **правила, архитектуру и UX-паттерны** фронтенда 
гидропонной системы 2.0, работающего на:

- Laravel (Inertia backend)
- Vue 3 (Composition API)
- Tailwind CSS
- PostgreSQL (данные через Inertia)
- WebSockets (опционально)

Документ обязателен для ИИ-агентов при создании/изменении фронтенда.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

# 1. Основные цели UI

UI должен быть:

- **информационно насыщенным**, но не перегруженным;
- **реалтайм**, если доступен websockets;
- **модульным**, легко расширяемым;
- **совместимым с мобильными устройствами**;
- минималистичным, вдохновлённым стилями:
 - Vercel/Dashboard,
 - shadcn/ui,
 - Linear.app,
 - Home Assistant.

---

# 2. Структура страниц (Inertia Pages)

```
resources/js/Pages/
 Dashboard/Index.vue (ролевые дашборды)
 Dashboard/Dashboards/
   - AgronomistDashboard.vue
   - AdminDashboard.vue
   - EngineerDashboard.vue
   - OperatorDashboard.vue
   - ViewerDashboard.vue
 Zones/Index.vue
 Zones/Show.vue
   - Zones/Tabs/ZoneSchedulerTab.vue
 Zones/ZoneCard.vue
 Zones/ZoneTelemetryChart.vue
 Devices/Index.vue
 Devices/Show.vue
 Devices/Add.vue
 Devices/DeviceChannelsTable.vue
 Recipes/Index.vue
 Recipes/Show.vue
 Recipes/Edit.vue
 Alerts/Index.vue
 Settings/Index.vue
 Admin/Index.vue
 Admin/Zones.vue
 Admin/Recipes.vue
 Greenhouses/Create.vue
 Profile/Edit.vue
 Setup/Wizard.vue
 Auth/ (Login, Register, etc.)
```

### Правило для ИИ:
- каждая новая страница должна быть создана в Pages и входить через Inertia.

---

# 3. Навигация и лейауты

## 3.1. Главный Layout: AppLayout.vue

Содержит:

- левое меню:
 - Dashboard
 - Zones
 - Devices
 - Recipes
 - Alerts
 - Settings
- основной контейнер
- заголовок (page title)
- слот для действий справа (`actions`)

### UX требования:
- стабильное меню слева, скрытие на мобильных;
- тёмная тема по умолчанию, переключатель в Settings.

---

# 4. Dashboard (Главная)

`Pages/Dashboard/Index.vue`

### Отображает:

- Карточки теплиц (Greenhouses)
- Количество зон
- Количество активных alert’ов
- Последние события ZoneEvents
- Самые проблемные зоны (по статусу/алертам)

### Компоненты:

- `StatCard.vue`
- `ZoneCard.vue`
- `Alerts/AlertCard.vue`
- `Events/EventRow.vue`

### Правила UX:
- показывать только самую важную информацию,
- удобная навигация «в одну плитку».

---

# 5. Zones (Список зон)

`Pages/Zones/Index.vue`

Содержит:

- плитки всех зон
- фильтрация по статусу (RUNNING / PAUSED / ALARM / WARNING)
- сортировка (по имени, по алертам)

### Каждая зона — `ZoneCard.vue`:

- имя зоны
- статус в виде `Badge.vue`
- быстрые метрики:
 - pH
 - EC
 - Temp
 - Humidity
- кнопка перехода «Подробнее»

---

# 6. Zone Details (Главная страница зоны)

`Pages/Zones/Show.vue`

Это **центральный экран фронтенда**.

Секции:

## 6.1. Заголовок
- имя зоны
- статус
- активная фаза (seedling / veg / bloom)
- кнопки:
 - Pause/Resume Zone
 - Next Phase
 - Irrigate Now
 - Recalibrate pH/EC (если устройство поддерживает)

## 6.2. Стат-карточки

`ZoneTargets.vue` + `StatCard.vue`:

- pH (current vs target)
- EC
- Температура воздуха
- Влажность воздуха
- Температура воды
- Уровень воды
- Световой режим

## 6.3. Графики

`ZoneTelemetryChart.vue` показывает:

- pH vs время
- EC vs время
- Temp vs время
- Humidity vs время

Особенности:
- auto-refresh
- кнопки: 1H / 24H / 7D / 30D / ALL
- smooth линия (ApexCharts или ECharts)

## 6.4. Devices

Список устройств, привязанных к зоне.

Компоненты:
- `DeviceCard.vue`
- `DeviceChannelsTable.vue`

Каждый узел показывает:
- статус
- каналы
- действие (test channel → send command)

## 6.5. Events (История событий)

`ZoneEventsList.vue`

- сортировка по времени
- цветовая кодировка типов событий
- пагинация
- AE3/runtime события на фронте должны группироваться по causal-context:
  `correction_window_id -> task_id -> snapshot_event_id/caused_by_event_id`
- для grouped runtime events UI обязан показывать оператору связку
  `decision -> correction started -> dosing -> snapshot/causal ids`, а не только плоскую ленту

## 6.6. Automation Tab: Runtime Operations

`Pages/Zones/Tabs/ZoneAutomationTab.vue`

Обязательные UX-инварианты:
- вкладка показывает только runtime/operations слой зоны: текущий workflow, control-mode, quick actions, профиль, коррекцию/калибровки и low-level AE settings;
- не смешивает operator flow с scheduler/execution detail-view;
- manual-step controls рендерятся из `allowed_manual_steps`, а не из зашитого списка кнопок;
- workflow/timeline в automation-панели строятся из canonical automation state и `zone_events`, без снимков `scheduler-task`;
- оператор должен получать быстрый доступ к управлению зоной, не переключаясь в developer diagnostics.

### 6.6.1. Shared UI автоматики зоны

Shared-компоненты автоматики зоны обязаны использовать одинаковый UX и contract ownership
в `/setup/wizard` и в zone edit screens.

Water / irrigation / correction rules:

- low-level 2-tank relay sequencing не редактируется на фронте;
- в блоке `Водный контур` из advanced остаются только runtime timeout-поля;
- `timed irrigation` принадлежит recipe phase и отображается как readonly summary;
- `smart irrigation` принадлежит zone automation и редактируется только для `decision.strategy=smart_soil_v1`;
- `correction_during_irrigation` рендерится внутри блока `Полив`, а не в chemistry block;
- inline irrigation correction отображается как fixed domain summary:
  `Ca/Mg/Micro + pH`, `NPK` исключён;
- `pH/EC target|min|max` и EC strategy принадлежат recipe и не редактируются в зоне;
- `prepare tolerance` не редактируется в shared форме зоны.

Process calibration / PID rules:

- базовый экран показывает preset + effective summary;
- подробная форма открывается только через `Расширенные настройки`;
- source of truth для preset UX: `zone.runtime_tuning_bundle`;
- source of truth для runtime reading: `zone.process_calibration.*`, `zone.pid.*`;
- bootstrap/system defaults считаются валидной стартовой конфигурацией и не маркируются как fail-closed только из-за `source=bootstrap/system_default`.

## 6.7. Scheduler Tab: Schedule Workspace

`Pages/Zones/Tabs/ZoneSchedulerTab.vue`

Назначение:
- отдельная вкладка зоны для scheduler workspace `Plan + Execution`;
- использует canonical backend-контракт `GET /api/zones/{id}/schedule-workspace?horizon=24h|7d`, detail lookup `GET /api/zones/{id}/executions/{executionId}` и snapshot `GET /api/zones/{id}/state` для фактического operator summary;
- по умолчанию показывает операторскую сводку: `что происходит сейчас`, `требует внимания`, `ближайшие исполнимые окна`;
- не рендерит сотни raw `plan windows`; показывает только ближайшие окна из `capabilities.executable_task_types[]`, а `config-only` lane сводит в компактный summary;
- execution detail рендерит `lifecycle` и сжатый timeline из canonical `ae_tasks` + `zone_events`, группируя повторяющиеся `AE_TASK_STARTED`;
- отдельный diagnostics block допускается только для `admin|engineer` и читает `GET /api/zones/{id}/scheduler-diagnostics`;
- `scheduler_logs` и старые `scheduler-tasks` не являются частью operator UX;
- основной фокус экрана: понять текущее состояние зоны, операционные проблемы и ближайшие исполнимые действия без инженерного шума.

---

# 7. Pages for Devices

`Pages/Devices/Index.vue`
`Pages/Devices/Show.vue`

Отображают:

- список всех узлов
- фильтрация по типу: PH / EC / Climate / Irrigation
- статус (ONLINE/OFFLINE)
- RSSI
- прошивка узла (fw version)
- действия диагностики (restart, test channels)

UX:
- минимализм
- всё, что касается железа, — только здесь

---

# 8. Recipes (Рецепты)

## 8.1. Index

`Pages/Recipes/Index.vue`

Показывает:

- список рецептов
- кнопка “Создать рецепт”

## 8.2. Show

`Pages/Recipes/Show.vue`

Включает:

- список фаз
- цели (targets)
- длительность
- кривые роста

## 8.3. Edit

Форма редактирования рецепта:

- таблица фаз
- цели pH / EC / temp / humidity / light
- drag-and-drop изменения фаз
- валидация

---

# 9. Alerts (Алерты)

`Pages/Alerts/Index.vue`

Каждый alert показывает:

- тип (PH_HIGH, TEMP_LOW и т.д.)
- зона
- время
- статус ACTIVE/RESOLVED
- кнопку “Подтвердить”

UX:
- показывать цветовые индикаторы,
- сгруппировать по зонам,
- фильтр только активные.

---

# 10. Settings

Содержит:

- переключатель темы (light/dark)
- настройки ESP автообновления (если появится)
- управление пользователями (если нужно)
- системные параметры

---

# 11. Компоненты (стандарты)

## 11.1. Badge.vue

Варианты:

- success
- warning
- danger
- info
- neutral

## 11.2. Modal.vue

Поддерживает:
- title
- description
- slot для форм
- footer с кнопками

## 11.3. DataTable.vue

Функции:
- серверная пагинация
- сортировка
- фильтрация
- sticky header
- адаптивный дизайн

## 11.4. ConfigModeCard.vue (Phase 6, 2026-04-15)

Путь: `resources/js/Components/ZoneAutomation/ConfigModeCard.vue`

Рендерит текущий `config_mode` зоны + переключатель locked↔live:

- Badge `🔒 Locked` / `✏️ Live tuning`
- Countdown до `live_until` (обновляется каждую секунду)
- Revision counter (`config_revision`)
- Inline-dialog при переходе в live: TTL minutes (5..10080) + reason (&ge; 3 символов)
- Кнопка «Продлить TTL» в live режиме

Props: `zoneId: number`, `controlMode: 'auto' | 'semi' | 'manual'`, `role: string`.
Events: `@changed(state)`, `@state-loaded(state)`.

Role gating (UI side, backend matches):
- `operator` — только возврат в locked (`update` policy)
- `agronomist | engineer | admin` — любые переходы (`setLive` policy)
- Кнопка `live` disabled при `controlMode='auto'` (matching backend 409 `CONFIG_MODE_CONFLICT_WITH_AUTO`)

API client: `services/api/zoneConfigMode.ts` (`zoneConfigModeApi.show/update/extend`).

## 11.5. ConfigChangesTimeline.vue (Phase 6)

Путь: `resources/js/Components/ZoneAutomation/ConfigChangesTimeline.vue`

Список audit entries из `zone_config_changes` с namespace filter (`zone.config_mode` / `zone.correction` / `recipe.phase`) + collapsible diff viewer.

Props: `zoneId: number`, `reloadKey: number` (parent bumps для invalidation).

## 11.6. RecipePhaseLiveEditCard.vue (Phase 6.1)

Путь: `resources/js/Components/ZoneAutomation/RecipePhaseLiveEditCard.vue`

Compact form — 6 numeric inputs (pH target/min/max, EC target/min/max) + reason. Отправляет только filled fields через `zoneConfigModeApi.updatePhaseConfig(growCycleId, payload)` (фильтр `typeof v === 'number' && Number.isFinite(v)`).

Рендерится **только** когда zone в `config_mode='live'` AND role ∈ `{agronomist, engineer, admin}` AND есть active grow cycle. Контроллируется из `ZoneAutomationTab.vue`:

```vue
<RecipePhaseLiveEditCard
  v-if="liveEditEnabled && activeGrowCycleId"
  :grow-cycle-id="activeGrowCycleId"
  :initial="recipePhaseInitial"
  @applied="onConfigModeChanged"
/>
```

End-to-end UX (Phase 5 + 6/6.1):
1. Agronomist переключает `control_mode → manual`
2. `ConfigModeCard` → live dialog (TTL + reason)
3. Backend 409 если `control_mode=auto` (interlock)
4. `RecipePhaseLiveEditCard` appears → edits pH/EC targets
5. `ConfigChangesTimeline` auto-reloads (reload-key bumped)
6. AE3 hot-swap на следующем handler checkpoint
7. TTL cron auto-revert в locked при expire

См. также: [AUTOMATION_CONFIG_AUTHORITY.md](../04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md) § 6.2 config modes и hot-swap.

---

# 12. Стиль UI (Tailwind)

### Основная палитра:
- тёмно-синий фон (для dark)
- светлый серый фон (для light)
- акцентный синий/бирюзовый
- мягкие радиусы и тени (shadow-sm, rounded-xl)

### Правила:
- избегать крупных теней
- избегать цветастых кнопок
- использовать цветовые акценты **только** в статуc-бейджах

---

# 13. Реалтайм данные (WebSockets)

Laravel → WebSockets может отправлять:

- обновления last telemetry,
- появление alert,
- смену статуса зоны,
- завершение команды (ACK).

ИИ должен:
- использовать Laravel Echo,
- обновлять только локальное состояние (не перезапрашивать Inertia страницу).

---

# 14. Правила для ИИ-агентов

### ИИ может:

- добавлять новые UI-секции,
- улучшать табличные компоненты,
- добавлять новые графики,
- создавать новые страницы в Pages.

### ИИ не может:

- менять существующую структуру Pages,
- переименовывать каналы/статусы/зоны,
- ломать AppLayout,
- менять структуру Inertia props без обновления backend-контроллеров.

---

# 15. Чек-лист для ИИ

1. Страница создаётся в Pages?
2. Компоненты лежат в Components?
3. Используется `<script setup>`?
4. Нет лишней логики во Vue?
5. Tailwind-классы читаемые?
6. Не изменён формат доменных данных?
7. Взаимодействие выполняется только через Inertia router?

---

# Конец файла FRONTEND_UI_UX_SPEC.md
