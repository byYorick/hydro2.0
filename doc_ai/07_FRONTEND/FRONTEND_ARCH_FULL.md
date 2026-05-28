# FRONTEND_ARCH_FULL.md
# Полная архитектура Frontend 2.0 (UI/UX + функционал, детальная версия)
# **ОБНОВЛЕНО ПОСЛЕ МЕГА-РЕФАКТОРИНГА 2025-12-25**
# **СИНХРОНИЗИРОВАНО С КОДОМ 2026-05-28** (Unified Dashboard, единый Launch flow, фактический список табов зоны)

Этот документ описывает полный, детальный и расширенный фронтенд системы управления теплицей 2.0.

**КЛЮЧЕВЫЕ ИЗМЕНЕНИЯ ПОСЛЕ РЕФАКТОРИНГА:**
- ✅ Версионирование рецептов в UI
- ✅ Scheduler workspace cutover: `ZoneSchedulerTab.vue` работает через `schedule-workspace` / `executions`
- ✅ Unified Dashboard как production canonical UI (см. §3.1 и §3.1bis)
- ✅ Единая точка запуска grow cycle — `/launch` (`Pages/Launch/Index.vue`); `/cycles` редиректится на `/`; `/setup/wizard` → `/launch`

**Status: planned / not implemented** для следующих ранее анонсированных элементов:
- `GrowCycles/Wizard.vue` — не существует в `resources/js/Pages/`; production entry point — `Pages/Launch/Index.vue`
- `Cycles/Center.vue` — не подключён в маршруты; `/cycles` редиректит на `/`. Файл `Pages/Cycles/Center.vue` существует, но не используется в production UI
- `AttachRecipeModal.vue` — файл и тесты ещё есть в репо, но не используется в production flow
- Трёхколоночная структура `[Nav | Content | Context]` — реализована как двухколоночная (sidebar + main) в `Layouts/AppLayout.vue`; правая context/events panel остаётся roadmap

Здесь собраны принципы UI/UX, структура интерфейса, экраны, реалтайм-механики, компоненты, state‑management, интеграция с backend и ИИ.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

# 1. Цели и принципы UI/UX

## 1.1. Главная цель фронтенда
Создать **современную профессиональную панель управления агросистемой**, которая:

- работает в реалтайме,
- помогает оператору быстро реагировать на события,
- даёт инженеру глубокую диагностику оборудования,
- даёт агроному инструменты для работы с культурами и рецептами,
- расширяется под новые зоны, устройства, фичи,
- интегрируется с ИИ (подсказки, оптимизация, автоматизация процессов).

---

## 1.2. Основные UX-принципы

### ✔ Интуитивная трёхколоночная структура
```
[Навигация] | [Контент] | [Контекст/панель событий]
```

### ✔ Единая визуальная система статусов
- **зелёный** — OK 
- **жёлтый** — WARNING 
- **красный** — ALARM 
- **серый** — OFFLINE / PAUSED / SETUP

### ✔ Реалтайм-обновления без перезагрузки
WebSocket → обновление данных зон / нод / алертов / telemetry.

### ✔ Command Palette (Ctrl+K)
Как в VS Code:
- быстрые действия,
- поиск зон, нод, рецептов,
- “поставить зону 5 на паузу”,
- “открыть ноду nd-ph-3”.

### ✔ Тёмная тема по умолчанию
Профессиональный, современный интерфейс.

---

# 2. Основные разделы фронтенда

Фактический набор production маршрутов (`backend/laravel/routes/web.php`):

**Основные:**
1. **Dashboard** (`/`) — Unified Dashboard (`Pages/Dashboard/Index.vue`); рендерится одинаково для всех ролей, доступ к действиям фильтруется через `useRole()`
2. **Greenhouses** (`/greenhouses`, `/greenhouses/create`, `/greenhouses/{id}`, `/greenhouses/{id}/climate`) — список, создание, страница теплицы, climate-вкладка
3. **Zones** (`/zones`) — список зон
4. **Zone Detail** (`/zones/{id}`) — главный рабочий экран зоны
5. **Zones Simulation** (`/zones/{id}/simulation`) — симулятор/digital twin зоны
6. **Devices** (`/devices`, `/devices/add`, `/devices/{id}`) — узлы ESP, каналы, диагностика
7. **Recipes** (`/recipes`, `/recipes/create`, `/recipes/{id}/edit`) — рецепты выращивания
8. **Alerts** (`/alerts`) — алерты и события
9. **Settings** (`/settings`, `/settings/preferences`) — настройки системы и пользовательские preferences
10. **Admin** (`/admin`, `/admin/zones`, `/admin/recipes`) — административная панель
11. **Profile** (`/profile`) — профиль пользователя
12. **Launch** (`/launch/{zoneId?}`) — единый мастер настройки зоны и запуска grow cycle; `/setup/wizard` редиректится сюда; `/cycles` редиректит на `/`

**Дополнительные:**
13. **Analytics** (`/analytics`)
14. **Monitoring** (`/monitoring`) — статусы Python-сервисов, MQTT, БД (пункт меню «Сервисы»)
15. **Logs** (`/logs`)
16. **Audit** (`/audit`) — admin audit trail
17. **Users** (`/users`) — admin user management
18. **Plants** (`/plants`) — таксономия культур
19. **Nutrients** (`/nutrients`) — справочник питательных продуктов
20. **Documentation** (`/documentation/fertigation`, ...) — встроенные гайды

## 3.0a. Recipes (`/recipes`, `/recipes/create`, `/recipes/{id}/edit`)

Canonical recipe UX:

- `Recipes/Edit`, `RecipeCreateWizard` и recipe-step в `PlantCreateModal` используют один shared `RecipeEditor`;
- primary source of truth в UI: flat phase fields + `extensions.day_night` + `extensions.subsystems.irrigation.targets.system_type`;
- `targets` используется только как derived read-helper;
- `PlantCreateModal` не создаёт `plant -> recipe -> revision -> phases` последовательностью запросов с фронта, а вызывает атомарный backend endpoint `POST /api/plants/with-recipe`.

---

# 3. Подробное описание экранов

# 3.1. Dashboard

**Файл:** `Pages/Dashboard/Index.vue` (Unified Dashboard, canonical в production)

### Реализация:

**Status: Unified Dashboard.** Production-UI — единый `Pages/Dashboard/Index.vue`, который рендерится одинаково для всех ролей. Контроллер: `UnifiedDashboardController` → `UnifiedDashboardService`. Доступ к действиям, видимость пунктов меню и колонок управляется через `useRole()` composable и `RoleBasedNavigation.vue`.

### Status: planned / not implemented — отдельные ролевые дашборды

Компоненты ролевых дашбордов **существуют в `Pages/Dashboard/Dashboards/`**:
- `AgronomistDashboard.vue` — для агрономов (фокус на рецептах и аналитике)
- `AdminDashboard.vue` — для администраторов (полный контроль системы)
- `EngineerDashboard.vue` — для инженеров (диагностика устройств)
- `OperatorDashboard.vue` — для операторов (мониторинг зон)
- `ViewerDashboard.vue` — для зрителей (read-only)

…но они **не подключены к маршрутам** и не используются в production. UI единый.

Решение по будущему направлению (подключать ролевые дашборды или удалить файлы) — отдельная продуктовая задача. До принятия решения новый код **не должен ссылаться на ролевые дашборды как на canonical**; используйте Unified Dashboard + `useRole()`.
  - `ViewerDashboard` - для наблюдателей (только просмотр)
  - Дефолтный дашборд - для пользователей без роли

### Содержимое (общее для всех ролей):
- Общее состояние теплицы:
 - количество зон RUNNING / PAUSED / ALARM
 - количество узлов ONLINE / OFFLINE
- Последние алерты
- Последние события (Events)
- Проблемные зоны
- Список теплиц

---

## 3.0. Launch Wizard (`/launch/{zoneId?}`)

Canonical мастер запуска состоит из 5 manifest-driven шагов:

1. `zone` — выбор теплицы/зоны или работа с переданным `zoneId`;
2. `recipe` — растение, published revision рецепта, дата посадки и партия;
3. `automation` — привязки узлов, водный контур, полив, correction, свет, климат;
4. `calibration` — sensor/pump/process/PID readiness;
5. `preview` — diff `zone.logic_profile`, readiness blockers/warnings и запуск.

Новый canonical UX:

- entry point один: `/launch/{zoneId?}`; старые `/setup/wizard` и legacy wizard entry points редиректятся на `/launch`;
- `/launch` остаётся внутри `AppLayout`, но использует собственный embedded `LaunchShell` с `LaunchTopBar`, `LaunchStepper`, `StepHeader` и `LaunchFooterNav`;
- manifest загружается через `GET /api/launch-flow/manifest`; на loading показывается skeleton, а blocker reason выводится в footer рядом с навигацией;
- шаг `automation` собран блоками, а не отдельными шагами `devices/profile`:
  - `Водный контур` объединяет обязательные zonal bindings (`irrigation`, `ph_correction`, `ec_correction`) и всю water logic;
  - `Климат зоны` начинается со switch `enabled`; если блок включён, UI раскрывает привязку CO2/root-vent нод и настройки логики;
  - `Освещение` устроено так же: switch `enabled` + раскрытие binding/logics только для включённой подсистемы;
- сохранение automation-конфига идёт по блокам (`water_contour`, `zone_climate`, `lighting`), но readiness шага считается единой зональной automation-конфигурацией;
- шаг `calibration` идёт в логическом порядке: `sensor calibration -> pump calibration -> process calibration`;
- zone-level `runtime bounds` для pump calibration не вынесены в отдельный блок шага и живут внутри `pump calibration wizard` как advanced settings для редких override-сценариев;
- `PID/autotune` не участвует в основном linear-flow шага и живёт в отдельном advanced-блоке `Расширенная тонкая настройка PID и autotune`;
- шаг `preview` объединяет `correction runtime readiness`, launch checklist и открытие мастера цикла;
- correction/calibration stack не дублируется вручную, а переиспользуется отдельным шагом тем же shared-блоком, что и на `Zone Detail`.

Экран `Greenhouses/Show.vue` использует ту же greenhouse-climate форму, что и launch/zone edit flow:

- устаревший modal массовой отправки `FORCE_CLIMATE` по зонам удалён;
- greenhouse climate сохраняется как отдельный greenhouse profile + greenhouse bindings;
- runtime dispatcher для greenhouse climate остаётся `WIP`, но UI уже редактирует и показывает сохранённый профиль.

---

# 3.2. Zones (список зон)

### Карточка зоны показывает:
- название
- статус (цвет + иконка)
- тип зоны (production, tank, irrigation…)
- культура + фаза
- pH / EC (если есть бак)
- температура / влажность (если климат)
- уровень воды / освещение

### Фильтры:
- по статусу
- по типу
- по культуре
- по активности (запущенные/на паузе)

### Действия:
- открыть Zone Detail
- закрепить в избранные (pin)
- быстрые действия:
 - pause/resume
 - manual irrigation

---

# 3.3. Zone Detail – главный экран системы

**Файл:** `Pages/Zones/Show.vue` + табы из `Pages/Zones/Tabs/`. Оркестратор — composable `useZoneShowPage.ts`.

### Фактический набор табов в production (порядок в UI):

1. **Цикл** (`ZoneCycleTab.vue`) — grow cycle, текущая фаза, controls (pause/resume/advance), irrigation/lighting overview
2. **Телеметрия** (`ZoneTelemetryTab.vue`) — графики pH/EC/температуры/влажности (ECharts)
3. **Автоматизация** (`ZoneAutomationTab.vue`) — PID config, correction setpoints, presets, live-edit для `config_mode='live'`
4. **Планировщик** (`ZoneSchedulerTab.vue`) — AE3 Scheduler Cockpit causal chain
5. **События** (`ZoneEventsTab.vue`) — лента zone_events с группировкой по causal context (`correction_window_id → task_id → snapshot_event_id/caused_by_event_id`)
6. **Алерты** (`ZoneAlertsTab.vue`) — активные/исторические алерты зоны
7. **Устройства** (`ZoneDevicesTab.vue`) — узлы зоны, pump calibration, sensor calibration

Wizard редактирования automation profile (`ZoneAutomationEditWizard.vue`) запускается из таба «Автоматизация» как modal/full-screen flow.

### Status: planned / not implemented

Старая структура `[Header → Target vs Actual → Charts → Devices → Cycles → Actions → Events]` (§§3.3.1–3.3.6, 3.3.8 ниже) описывает дизайн до миграции на табы. Отдельные блоки `Target vs Actual`, `Cycles (расписание)`, `Actions (действия)` как самостоятельные секции на странице зоны **не существуют** — соответствующая функциональность переехала внутрь табов «Цикл» и «Автоматизация».

«Service Mode» и «Apply Recipe» в header'е (см. §3.3.1) **не реализованы** как отдельные UI-controls — они интегрированы в Launch wizard (`/launch`) и табы автоматизации.

Секции ниже сохранены как описание целевого UX-намерения и могут использоваться при будущих редизайнах. Реальная разметка — в файлах табов из `Pages/Zones/Tabs/`.

## 3.3.1. Верхний блок (Header)
- Название зоны
- Теплица
- Фаза роста, культура, рецепт
- День фазы / процент прогресса
- Статус
- Кнопки:
 - Pause / Resume
 - Service Mode
 - Apply Recipe
 - Next Phase
 - Open Device List

---

## 3.3.2. Target vs Actual (основная метрика зоны)

Карточки:

### pH
- цель: 5.8 
- диапазон: 5.6 – 6.0 
- факт: 5.9 
- индикатор: зелёный/жёлтый/красный 

### EC
- цель: 1.6 
- диапазон: 1.4 – 1.8 
- факт: 1.5 

### Температура / Влажность
- цели vs факт 
- индикаторы 

### Свет
- часы света план / факт 
- текущая интенсивность 

### Уровень воды / проток / давление

---

## 3.3.3. Графики (Charts)
Tabs:

- pH
- EC
- Температура
- Влажность
- Деятельность насосов / вентиляторов
- Свет (интенсивность + часы)

История:
- 24 часа
- 7 дней
- 30 дней

---

## 3.3.4. Devices зоны

### Таблица устройств:
- Node ID 
- Статус ONLINE/OFFLINE 
- Каналы: ph_sensor, pump_acid, fan_A, heater… 
- RSSI Wi-Fi 
- FW версия 
- Кнопка → Device Detail 

---

## 3.3.5. Cycles (расписание)

Для каждой подсистемы:

- PH_CONTROL 
- EC_CONTROL 
- IRRIGATION 
- LIGHTING 
- CLIMATE 

Каждый цикл:
- strategy: periodic / event / hybrid 
- interval 
- last run 
- next run 
- кнопка “Запустить сейчас”

---

## 3.3.6. Actions (действия)

- Ручной полив (секунды)
- Принудительное измерение pH/EC
- Применить рецепт
- Сменить фазу
- Остановить / запустить зону
- Обнулить ALARM

---

## 3.3.7. Scheduler (планировщик зоны)

`Pages/Zones/Tabs/ZoneSchedulerTab.vue`

Отдельная вкладка для scheduler workspace зоны:

- runtime control-mode, factual zone state и операторская attention-сводка;
- ближайшие executable `plan windows` по горизонту `24h/7d` без рендера всех raw planner rows;
- `active_run`, `recent_runs` и detail-view по `execution_id`;
- operator UI использует `GET /api/zones/{id}/schedule-workspace`, `GET /api/zones/{id}/executions/{executionId}` и `GET /api/zones/{id}/state`;
- engineer/admin получают отдельный diagnostics block через `GET /api/zones/{id}/scheduler-diagnostics`;
- `scheduler_logs` не используются в публичном UI path;
- текущая реализация оформлена как operator-first dashboard: current-state summary, attention block, next executable windows, recent runs и компактный detail card исполнения;
- на `automation_runtime=ae3` предупреждение в attention отражает типы из `non_executable_planned_task_types`; автодиспатч scheduler покрывает compat-path типы из `capabilities.executable_task_types` и сейчас включает **полив, освещение и diagnostics**.

---

## 3.3.8. Events (лог зоны)

Каждое событие:
- timestamp 
- тип (ALERT / INFO / ACTION / SENSOR) 
- текст:
 - “pH скорректирован на +1.5 мл base”
 - “Узел nd-ph-1 OFFLINE”
 - “Manual irrigation by user” 

Фильтры по типу, дате, пользователю.

Для AE3/runtime observability лог зоны не должен быть только плоской лентой:
- связанные события группируются по `correction_window_id`, затем по `task_id`;
- если window/task отсутствуют, UI использует fallback на `snapshot_event_id` или `caused_by_event_id`;
- группа должна визуально показывать causal-цепочку решения и исполнения:
  `decision snapshot -> correction started -> dosing -> snapshot linkage`.

---

# 3.4. Devices (Nodes)

## Device List
Столбцы:

- node_id
- зона
- статус
- RSSI (уровень Wi‑Fi)
- FW версия
- uptime
- last seen
- тип узла (ph, ec, climate…)

## Device Detail
Содержимое:

### 1. Основная информация:
- модель платы 
- ревизия 
- прошивка 
- IP, RSSI 

### 2. Каналы:
- имя канала 
- тип (SENSOR/ACTUATOR) 
- последнее значение (для сенсоров) 
- управление (для актуаторов) 
- безопасные ограничения 

### 3. NodeConfig:
- текущий JSON 
- кнопка “Переслать конфиг”

### 4. Диагностика:
- история ONLINE/OFFLINE 
- ошибки 

---

# 3.5. Recipes & Crops

## Recipe List (представление карточками)
- название
- культура
- версия
- количество фаз

## Recipe Detail
### Блоки:
1. Основные данные 
2. Фазы роста
3. Диапазоны pH/EC/t°/RH
4. Циклы подсистем
5. Привязанные зоны
6. Кнопки:
 - применить
 - создать копию
 - редактировать

---

# 3.6. Alerts & Events

## Alerts
- текущие аварии:
 - зона
 - причина
 - время
 - кнопка “устранено”

## Events (история)
- все события системы
- фильтры: зона, устройство, тип, время

---

# 4. Реалтайм

## REST:
- первичная загрузка UI
- история графиков
- устройства, каналы
- рецепты/фазы

## WebSocket:
- telemetry (поток обновлений)
- zone updates
- node status updates
- alerts/events

---

# 5. Хранилище состояния (Frontend Store)

```
rootStore
 ├─ greenhousesStore
 ├─ zonesStore
 ├─ devicesStore
 ├─ telemetryStore (live data)
 ├─ alertsStore
 ├─ recipesStore
 └─ uiStore (фильтры, темы, pinned zones)
```

---

# 6. Advanced UX

## Командная палитра (Ctrl+K)
Позволяет:

- открыть зону
- открыть устройство
- поставить на паузу
- запуск полива
- открыть рецепты
- переключение фазы

## Горячие клавиши:
- Shift+Z — Zones 
- Shift+D — Devices 
- Shift+R — Recipes 
- Shift+A — Alerts 

## Избранные зоны:
Закрепляются слева для быстрого доступа.

---

# 7. AI‑интеграция

## 7.1. AI Suggestions
ИИ может показывать:

- рекомендации по pH/EC
- прогноз выхода из диапазона
- анализ аномалий
- советы по фазам

## 7.2. AI Chat
Примеры запросов:

- “почему вчера pH прыгал в зоне 3?”
- “какие зоны имеют плохой EC сегодня?”
- “создай оптимизированный рецепт для салата зимой”

---

# 8. План внедрения фронта

1. Zones List 
2. Zone Detail (основные блоки) 
3. WebSocket telemetry 
4. Devices & Device Detail 
5. Recipes & редактор фаз 
6. Alerts / Events 
7. Улучшения UX 
8. Темизация (Dark/Light) 
9. AI панель 

---

## Scheduler Cockpit — causal chain panel (Phase 2)

`CausalChainPanel.vue` (в [`Components/Scheduler/Cockpit/`](../../backend/laravel/resources/js/Components/Scheduler/Cockpit/))
отображает «цепочку решений» для выбранного исполнения зоны — вертикальная
timeline из шагов `SNAPSHOT → DECISION → TASK → DISPATCH → RUNNING →
COMPLETE|FAIL|SKIP` с live-обновлением через Reverb.

Открывается из `CockpitSchedulerTab.vue` при клике на строку в
`RecentRunsTable` или автоматически — если на загрузке есть активный run.

**Данные:**

- Источник — `workspace.execution.active_run.chain[]` и
  `GET /api/zones/{id}/executions/{executionId}` (поле `chain`).
- Live-дельты — событие `ExecutionChainUpdated` на приватном канале
  `hydro.zone.executions.{zoneId}`; клиент — `ws/schedulerChainChannel.ts`.
  Zod-валидация payload — `schemas/execution.ts`.

**Действия:**

- `× Закрыть` — очищает `selectedExecution`.
- `Повторить` — только для FAIL-run; в v1 показывает toast (ре-trigger
  execution в backend — отдельный ticket).
- `В Events →` — переход на `/zones/{id}?tab=events&execution_id=...`.
- `⎘ copy` — копирование `correlation_id` через `navigator.clipboard`.

Cockpit-UI — единственный рабочий UI планировщика (с PR4 редизайна
2026-04-24 флаг `scheduler_cockpit_ui` и legacy-компоненты удалены).

---

# Конец файла
