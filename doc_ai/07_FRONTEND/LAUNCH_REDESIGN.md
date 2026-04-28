# Launch Wizard Redesign — План

**Версия:** 1.1
**Дата:** 2026-04-28
**Автор:** Georgiy
**Статус:** approved / implementation in progress
**Референс:** `/home/georgiy/esp/hydro/hydro2.0/hydroflow/` (React 18 prototype)

---

## 1. Цель

Полный визуальный и UX-редизайн страницы `/launch` ([Pages/Launch/Index.vue](../../backend/laravel/resources/js/Pages/Launch/Index.vue)) под референс `hydroflow/`. Существующие backend API сохраняются; правки бэкенда — только при отсутствии нужного контракта (audit показал, что всё критичное уже есть).

## 2. Контекст

- До редизайна `/launch` использовал [BaseWizard](../../backend/laravel/resources/js/Components/Shared/BaseWizard/BaseWizard.vue) и manifest от `GET /api/launch-flow/manifest`. Новый UI использует `LaunchShell` поверх того же manifest. Шаги: `zone | recipe | automation | calibration | preview`.
- Референс `hydroflow` (10 файлов JSX, 3611 строк) задаёт собственный shell (TopBar+Stepper+FooterNav), палитру (teal `#0e8a8f` + growth/warn/alert), типографику (IBM Plex Sans + JetBrains Mono), 6 подразделов в шаге «Автоматика» и 5 в «Калибровке», correction profile presets, water presets, lock recipe-derived полей.
- Старый `Pages/Setup/Wizard.vue` (787 строк) — мёртвый код в роутинге, удаляется этим PR.

## 3. Решения (ответы на вопросы аудита)

| # | Вопрос | Ответ |
|---|---|---|
| 1 | Scope | Редизайн UI/UX поверх существующих API; backend трогать только если нужно |
| 2 | Старый Setup/Wizard | Удалить целиком (компонент, тесты, типы) |
| 3 | `setupWizardApi` | Остаётся, вызывается из live `/launch` на submit |
| 4 | Объём подразделов | Не сокращаем: 6 в шаге 3, 5 в шаге 4 |
| 5 | Inline-создание теплицы в шаге 1 | Нет, оставляем кнопку «перейти на /greenhouses» |
| 6 | Backend для калибровки | Доделать, если что-то отсутствует (audit: всё есть) |
| 7 | Палитра | (a) — токены в `tailwind.config.js`, переписать классы |
| 8 | Шрифты | IBM Plex Sans + JetBrains Mono локально (`public/fonts/`) |
| 9 | Density / Stepper toggle | Сохранять в `localStorage` |
| 10 | TweaksPanel из рефа | Не переносим в продакшн |
| 11 | Dark/Light темы | Обе обязательны, default = dark (как в репо) |
| 12 | Каркас | Свой `LaunchShell` для `/launch` внутри `AppLayout` (без `BaseWizard`, без full-screen режима) |
| 13 | Service health endpoint | Есть: `/api/system/health` + `/api/pipeline/health` |
| 14 | Vertical stepper | Только на ≥ 1280px, на узких прячем |
| 15 | recipe-derived поля на шаге 3 | Read-only, редактирование только в шаге 2 |
| 16 | Presets storage | Есть: `ZoneAutomationPreset` + `ZoneCorrectionPreset` (DB-driven) |
| 17 | State management | Оставить как есть (`useFormSchema` + `automationProfile` + `currentRecipePhase`) |
| 18 | Тесты | Писать чистые с нуля под новые компоненты |
| 19 | Объём PR | Один PR, разбитый на логические коммиты |
| 20 | Work doc | Этот файл |
| 21 | Структура коммитов | Логические коммиты по фазам |

## 4. Backend audit — итоги

Все нужные endpoints **существуют**. Отдельные правки бэкенда не планируются. Если по ходу реализации найдётся отсутствующее поле в payload — фиксим точечно.

| Endpoint | Файл | Примечание |
|---|---|---|
| `POST /api/zones/{id}/calibrate-pump` | [routes/api.php:221](../../backend/laravel/routes/api.php#L221) | `ZoneController@calibratePump` |
| `PUT /api/automation-configs/zone/{id}/zone.process_calibration.{mode}` | [routes/api.php:222](../../backend/laravel/routes/api.php#L222) | через registry, mode ∈ {generic, solution_fill, tank_recirc, irrigation} |
| `PUT /api/automation-configs/zone/{id}/zone.correction` | [routes/api.php:252](../../backend/laravel/routes/api.php#L252) | + `ZoneCorrectionLiveEditController` |
| `PUT /api/automation-configs/zone/{id}/zone.pid.{ph,ec}` | registry | `ZonePidConfig` модель |
| `POST /api/zones/{zone}/sensor-calibrations` | [routes/api.php:306](../../backend/laravel/routes/api.php#L306) | + `/point`, `/cancel` |
| `GET/POST /api/zone-automation-presets` | [routes/api.php:232](../../backend/laravel/routes/api.php#L232) | water presets |
| `ZoneCorrectionPreset` | модель | safe/balanced/aggressive/test slugs |
| `GET /api/system/health` | [routes/api.php:76](../../backend/laravel/routes/api.php#L76) | для service status pills |
| `GET /api/pipeline/health` | [routes/api.php:398](../../backend/laravel/routes/api.php#L398) | детальный health |
| `POST /api/greenhouses` | [routes/api.php:200](../../backend/laravel/routes/api.php#L200) | для отдельной страницы создания |

**Замечание про process-calibrations:** реф рисует endpoint `PUT /api/zones/{id}/process-calibrations/{mode}`. У нас он работает через общий automation-configs registry с namespace `zone.process_calibration.{mode}`. Фронт должен использовать существующий путь.

## 5. Архитектура target

### 5.1. Shell для `/launch`

Не используем `BaseWizard.vue`. `/launch` остаётся обычной Inertia-страницей внутри
`AppLayout.vue`, чтобы сохранить навигацию, command palette, toast/error boundary и
общий рабочий контекст оператора. Внутри основного слота `AppLayout` рендерится
собственный wizard-каркас:

```
AppLayout
└─ LaunchShell          (embedded wizard card, not full-screen)
   ├─ LaunchTopBar      (logo + breadcrumbs + service health pills + user)
   ├─ LaunchStepper     (HStepper по умолчанию, VStepper при ≥1280px и stepper='vertical')
   ├─ <main>            (manifest skeleton/loading, текущий шаг + StepHeader)
   └─ LaunchFooterNav   (sticky, прогресс, blocker reason, Назад/Далее/Запустить)
```

Full-screen режим для `/launch` не используется. Визуальный фокус достигается не
удалением глобального layout, а вложенной `LaunchShell`-карточкой с собственным
topbar/stepper/footer. При загрузке manifest показывается skeleton-состояние;
если текущий шаг или запуск заблокирован, причина выводится в `LaunchFooterNav`.

### 5.2. Дизайн-токены

**`tailwind.config.js`** — расширить `theme.extend.colors`:

```js
colors: {
  brand: { DEFAULT: 'var(--brand)', soft: 'var(--brand-soft)', ink: 'var(--brand-ink)' },
  growth: { DEFAULT: 'var(--growth)', soft: 'var(--growth-soft)' },
  warn: { DEFAULT: 'var(--warn)', soft: 'var(--warn-soft)' },
  alert: { DEFAULT: 'var(--alert)', soft: 'var(--alert-soft)' },
}
```

`fontFamily`:
```js
fontFamily: {
  sans: ['IBM Plex Sans', ...defaultTheme.fontFamily.sans],
  mono: ['JetBrains Mono', ...defaultTheme.fontFamily.mono],
}
```

**`resources/css/app.css`** — добавить переменные:

```css
:root { /* dark by default */
  --brand:#3ab9bd; --brand-ink:#a3e4e6; --brand-soft:#0d3a3c;
  --growth:#66c562; --growth-soft:#113d1f;
  --warn:#e0a341; --warn-soft:#3d2e12;
  --alert:#e06b62; --alert-soft:#3d1a17;
}
:root[data-theme='light'] {
  --brand:#0e8a8f; --brand-ink:#065154; --brand-soft:#d9f0ef;
  --growth:#4f9d4a; --growth-soft:#e1f1dc;
  --warn:#c8871a; --warn-soft:#faecd1;
  --alert:#c0433b; --alert-soft:#fadcd9;
}
```

**Локальные шрифты:** `public/fonts/ibm-plex-sans/{400,500,600,700}.woff2` + `public/fonts/jetbrains-mono/{400,500}.woff2`. Подключение через `@font-face` в `app.css`. Удалить bunny.net Figtree из `app.blade.php`, если он больше нигде не используется (проверить).

### 5.3. Density / Stepper preferences

```ts
// composables/useLaunchPreferences.ts
const STORAGE_KEY = 'hydro.launch.prefs';
type Prefs = { density:'compact'|'comfortable'; stepper:'horizontal'|'vertical'; showHints:boolean };
```

Применяется через `data-density` / `data-stepper` атрибуты на корне `LaunchShell`. Toggle’ы рендерятся в `LaunchTopBar` (settings popover, без отдельной TweaksPanel).

### 5.4. Service health pills

```ts
// composables/useServiceHealth.ts
const { data } = useQuery({
  queryKey: ['system','health'],
  queryFn: () => apiGet('/api/system/health'),
  refetchInterval: 15_000,
});
// маппинг: data.services.{mqtt_bridge|history_logger|automation_engine}.status → pill tone
```

Кэш 15 секунд, обновление в фоне; pill `online | degraded | offline`.

### 5.5. UI примитивы (новые)

В `Components/Shared/Primitives/`:

| Компонент | Источник | Назначение |
|---|---|---|
| `Select.vue` | `ui.jsx::Select` | Custom select с chevron, mono, invalid state |
| `Field.vue` | `ui.jsx::Field` | Label + required + hint + error wrapper |
| `Chip.vue` | `ui.jsx::Chip` | Tone-based bage (brand/growth/warn/alert/neutral) |
| `Stat.vue` | `steps.jsx::Stat` | Label + value + tone + mono + icon |
| `Hint.vue` | `ui.jsx::Hint` | Info-блок с info-иконой и dashed border |
| `KV.vue` | `steps.jsx::KV` | Двухколоночная таблица «ключ — значение» |
| `IconChip.vue` | `app.jsx` | Pill со статус-точкой (для service pills) |

Существующие используем как есть: `Button.vue`, `Card.vue`, `TextInput.vue`, `Badge.vue`. **Не дублируем** — `Chip` ≠ `Badge` (Badge у нас для счётчиков, Chip для tone-based status); их разделение фиксируем в JSDoc.

### 5.6. Иконки

В рефе ~12 SVG иконок (Ic.check, dot, warn, x, plus, edit, drop, beaker, zap, chev, chevDown, lock, leaf, gh, grid, info, wave, play, bookmark, chip). Расширяем существующий иконсет проекта. Проверить, какие уже есть в `Components/Icons/` — недостающие добавить.

### 5.7. State management

Оставляем разделённым по решению **#17**:
- `useFormSchema(growCycleLaunchSchema)` — payload запуска
- `automationProfile = ref<AutomationProfile>()` — профиль автоматизации
- `currentRecipePhase` / `recipePhases` — для расчёта PID-targets
- `currentLogicProfile` — текущий `zone.logic_profile` для diff

Pinia store **не вводим** этим PR (out of scope). Если в процессе реализации станет очевидно — выносим в follow-up.

## 6. Карта шагов

### Шаг 1 — Зона ([Components/Launch/ZoneStep.vue](../../backend/laravel/resources/js/Components/Launch/ZoneStep.vue))

- Layout: 1fr + 320px правая панель (Hint + GH plan placeholder + MQTT/Bridge KV).
- Card «Теплица»: select из `api.greenhouses.list()` с метаданными (тип, площадь, зоны, узлы online).
- Card «Зона»: вкладки `select | create`. Список зон с status pill (active/draft/idle).
- Без inline-создания теплицы (#5). Кнопка `→ Перейти на /greenhouses` в правом верхнем углу карточки.

### Шаг 2 — Рецепт ([Components/Launch/RecipeStep.vue](../../backend/laravel/resources/js/Components/Launch/RecipeStep.vue))

- Layout: 1fr + 360px правая панель (Hint + KV «активная ревизия» + PhaseStrip).
- Режимы: `select | create | edit`.
- В `select` — выбор рецепта + plant + planting_at + batch + read-only stats (system, substrate, target pH/EC) + PhaseStrip.
- В `create | edit` — встраиваем существующий [RecipeEditor.vue](../../backend/laravel/resources/js/Components/RecipeEditor.vue) (~56KB монолит) **как подвид без декомпозиции**. Декомпозиция RecipeEditor — out of scope этого PR (см. §10).
- При `edit` рецепта в активной зоне — варнинг про DRAFT-ревизию (как в `steps12.jsx::RecipeEditor`).

### Шаг 3 — Автоматика ([Components/Launch/Automation/](../../backend/laravel/resources/js/Components/Launch/Automation))

Новая структура с собственным sidebar (240px) + breadcrumb + readiness-bar:

```
AutomationHub (router-shell)
├─ AutomationReadinessBar  (общий индикатор + 6 navchips)
├─ RecipeBadge             (recipe-derived fields lock)
├─ AutomationSidebar       (6 пунктов в 3 группах)
└─ <subview>
   ├─ BindingsSubview      — 3 required + 5 optional ролей × Select(node)
   ├─ ContourSubview       — водный контур (PresetSelector + waterForm full)
   ├─ IrrigationSubview    — стратегия (task | smart_soil_v1) + recovery
   ├─ CorrectionSubview    — correction presets (safe/balanced/aggressive/test) + сравнение
   ├─ LightingSubview      — расписание + lux + manual override
   └─ ClimateSubview       — CO₂ + вентиляция (опц.)
```

`RECIPE_LOCKED = ['systemType','targetPh','targetEc']` — read-only с `<Ic.lock/>`, синхронизируются `watchEffect`-ом из `currentRecipePhase`.

`PresetSelector.vue` (существующий) и `SavePresetWizard.vue` встраиваются в `ContourSubview`. Маппинг `automationProfile` → preset payload — через существующие composables (`useAutomationContracts`, `automationProfileConverters`).

Существующий `AutomationHub.vue` (17.8KB монолит) — переписываем; `AutomationReadinessBar.vue` и `AutomationBlockersDrawer.vue` — адаптируем.

### Шаг 4 — Калибровка ([Components/Launch/Calibration/](../../backend/laravel/resources/js/Components/Launch/Calibration))

```
CalibrationHub
├─ CalibrationReadinessBar
├─ CalibrationSidebar (5 пунктов в 2 группах: «базовая» / «тонкая»)
└─ <subview>
   ├─ SensorsSubview      — pH + EC карточки, offset/slope, история, кнопка калибровки
   ├─ PumpsSubview        — таблица 6 насосов + PumpCalibrationDrawer (существующий)
   ├─ ProcessSubview      — 4 режима (solution_fill/tank_recirc/irrigation/generic) × 8 коэффициентов
   ├─ CorrectionSubview   — authority editor (recipe/zone/manual) + diff vs preset
   └─ PidSubview          — pH/EC tabs, zone_coeffs (close/far × kp/ki/kd) + PidChart SVG
```

Sidebar состояния: `passed | active | blocker | waiting | optional` (как в реф `steps.jsx::CalSidebar`).

`CalibrationHub.vue` (19.6KB) — переписываем; `CalibrationPumpsSubpage.vue` и `PumpCalibrationDrawer.vue` (44.9KB) — переиспользуем как есть, адаптируя оборачивающую часть.

`PidChart` — новый SVG-компонент (3 концентрические зоны dead/close/far + target line).

### Шаг 5 — Подтверждение ([Components/Launch/PreviewStep.vue](../../backend/laravel/resources/js/Components/Launch/PreviewStep.vue))

```
PreviewStep
├─ left (1.3fr)
│  ├─ SummaryCard       — gh/zone/plant/system + pH/EC targets + irrigation + harvest ETA
│  └─ DiffCard          — DiffTable (op/path/from/to)
└─ right (1fr)
   ├─ ReadinessCard     — список 9 проверок с tone-иконками
   ├─ LaunchCard        — gradient + «Готово. Посадка сейчас, первый полив через…» + кнопка
   └─ Hint              — endpoint + flow
```

[DiffPreview.vue](../../backend/laravel/resources/js/Components/Launch/DiffPreview.vue) — переписываем как `DiffTable` с tone-точками для add/replace/remove.

## 7. Изменения файлов

### Удаляем

- `backend/laravel/resources/js/Pages/Setup/Wizard.vue`
- `backend/laravel/resources/js/Pages/Setup/__tests__/Wizard.spec.ts`
- `backend/laravel/resources/js/Pages/Setup/` (пустую директорию)
- `backend/laravel/resources/js/types/SetupWizard.ts`

Редирект `/setup/wizard → /launch` в [routes/web.php:327](../../backend/laravel/routes/web.php#L327) **сохраняем** (внешние ссылки).

### Изменяем

| Файл | Что меняем |
|---|---|
| `backend/laravel/tailwind.config.js` | + colors (brand/growth/warn/alert), fontFamily (sans/mono) |
| `backend/laravel/resources/css/app.css` | + CSS-переменные тем + `@font-face` локальные шрифты |
| `backend/laravel/resources/views/app.blade.php` | удалить bunny.net Figtree (или оставить, если используется на других страницах — проверить `git grep -F 'fonts.bunny'`) |
| `backend/laravel/resources/js/Pages/Launch/Index.vue` | переписать под embedded `LaunchShell` внутри `AppLayout`, добавить manifest skeleton и footer blocker reason |
| `backend/laravel/resources/js/Components/Launch/ZoneStep.vue` | переписать |
| `backend/laravel/resources/js/Components/Launch/RecipeStep.vue` | переписать (встраивает RecipeEditor) |
| `backend/laravel/resources/js/Components/Launch/Automation/AutomationHub.vue` | переписать как router-shell |
| `backend/laravel/resources/js/Components/Launch/Automation/AutomationReadinessBar.vue` | адаптировать |
| `backend/laravel/resources/js/Components/Launch/Calibration/CalibrationHub.vue` | переписать как router-shell |
| `backend/laravel/resources/js/Components/Launch/Calibration/CalibrationReadinessBar.vue` | адаптировать |
| `backend/laravel/resources/js/Components/Launch/PreviewStep.vue` | переписать |
| `backend/laravel/resources/js/Components/Launch/DiffPreview.vue` | переписать |
| `backend/laravel/resources/js/Components/Launch/CalibrationStep.vue` | стать тонким wrapper'ом или удалить |
| `backend/laravel/resources/js/Components/Launch/AutomationStep.vue` | стать тонким wrapper'ом или удалить |

### Создаём

**Shell:**
- `Components/Launch/Shell/LaunchShell.vue`
- `Components/Launch/Shell/LaunchTopBar.vue`
- `Components/Launch/Shell/LaunchStepper.vue` (внутри HStepper + VStepper switch)
- `Components/Launch/Shell/LaunchFooterNav.vue`
- `Components/Launch/Shell/StepHeader.vue`

**Composables:**
- `composables/useLaunchPreferences.ts`
- `composables/useServiceHealth.ts`

**Примитивы:**
- `Components/Shared/Primitives/Select.vue`
- `Components/Shared/Primitives/Field.vue`
- `Components/Shared/Primitives/Chip.vue`
- `Components/Shared/Primitives/Stat.vue`
- `Components/Shared/Primitives/Hint.vue`
- `Components/Shared/Primitives/KV.vue`

**Подвиды Automation (Шаг 3):**
- `Components/Launch/Automation/Subviews/BindingsSubview.vue`
- `Components/Launch/Automation/Subviews/ContourSubview.vue`
- `Components/Launch/Automation/Subviews/IrrigationSubview.vue`
- `Components/Launch/Automation/Subviews/CorrectionSubview.vue`
- `Components/Launch/Automation/Subviews/LightingSubview.vue`
- `Components/Launch/Automation/Subviews/ClimateSubview.vue`
- `Components/Launch/Automation/AutomationSidebar.vue`
- `Components/Launch/Automation/RecipeBadge.vue`

**Подвиды Calibration (Шаг 4):**
- `Components/Launch/Calibration/Subviews/SensorsSubview.vue`
- `Components/Launch/Calibration/Subviews/ProcessSubview.vue`
- `Components/Launch/Calibration/Subviews/CorrectionSubview.vue` (≠ Automation/CorrectionSubview)
- `Components/Launch/Calibration/Subviews/PidSubview.vue`
- `Components/Launch/Calibration/Subviews/PumpsSubview.vue` (адаптер вокруг существующего CalibrationPumpsSubpage)
- `Components/Launch/Calibration/CalibrationSidebar.vue`
- `Components/Launch/Calibration/PidChart.vue`

**Иконки (если их нет):**
- `Components/Icons/IconLock.vue`, `IconLeaf.vue`, `IconBookmark.vue`, `IconChip.vue`, `IconBeaker.vue`, `IconWave.vue` etc.

**Шрифты (assets):**
- `backend/laravel/public/fonts/ibm-plex-sans/{400,500,600,700}.woff2`
- `backend/laravel/public/fonts/jetbrains-mono/{400,500}.woff2`

Источник: https://fonts.google.com/specimen/IBM+Plex+Sans + https://fonts.google.com/specimen/JetBrains+Mono. Лицензия — OFL-1.1 (можно коммитить).

## 8. Структура коммитов (один PR)

Порядок выбран так, чтобы каждый коммит был обозримым ревьюером и не ломал зелёные тесты по дороге. File size guard ([backend/laravel/scripts/check-file-size-guard.sh](../../backend/laravel/scripts/check-file-size-guard.sh): `MAX_LINES=900`, `MAX_INCREASE=30`) — учитывается; новые subview-компоненты держим под 350 строк каждый.

| # | Коммит | Затрагиваемые файлы |
|---|---|---|
| 1 | `chore(launch): drop legacy Setup/Wizard` | удаление 4 файлов из §7 |
| 2 | `feat(launch): design tokens + IBM Plex/JetBrains Mono` | tailwind.config.js, app.css, public/fonts/, app.blade.php |
| 3 | `feat(shared): UI primitives (Select/Field/Chip/Stat/Hint/KV)` | 6 новых компонентов в Components/Shared/Primitives/ |
| 4 | `feat(launch): own shell (TopBar/Stepper/FooterNav)` | LaunchShell + 4 component'а + 2 composable'а |
| 5 | `feat(launch): step 1 — Zone redesign` | ZoneStep.vue rewrite |
| 6 | `feat(launch): step 2 — Recipe redesign` | RecipeStep.vue rewrite + inline RecipeEditor |
| 7 | `feat(launch): step 3 — Automation hub (6 subviews)` | AutomationHub rewrite + 6 Subviews + Sidebar + RecipeBadge |
| 8 | `feat(launch): step 4 — Calibration hub (5 subviews)` | CalibrationHub rewrite + 5 Subviews + Sidebar + PidChart |
| 9 | `feat(launch): step 5 — Preview redesign` | PreviewStep + DiffPreview rewrite |
| 10 | `feat(launch): wire shell + steps in Index.vue` | Pages/Launch/Index.vue rewrite |
| 11 | `test(launch): Vitest coverage for primitives + shell + steps` | Vitest specs (по решению #18 — с нуля) |

Каждый коммит проходит `npm run typecheck` + `npm run lint` + `npm run test`.

## 9. Критерии приёмки

- `npm run typecheck` — pass
- `npm run lint` — pass
- `npm run test` — Vitest зелёный
- `npm run e2e:ci` — playwright не падает (если есть сценарии для `/launch`)
- `php artisan test` — PHPUnit зелёный (контроллеры не трогали — должен остаться зелёным)
- Все 5 шагов работают через `GET /api/launch-flow/manifest` без правок бэка
- `POST /api/zones/{id}/grow-cycles` вызывается успешно при `readiness.ready === true`
- Dark + Light темы корректно применяют все 8 цветовых токенов
- Density (compact/comfortable) и Stepper (horizontal/vertical) сохраняются в localStorage между загрузками
- Service health pills отражают реальный `/api/system/health` (auto-refresh 15с)
- На экране ≥1280px доступен vertical stepper; на ≤1279px — только horizontal
- Файл-size guard `check-file-size-guard.sh` проходит

## 10. Out of scope

- Декомпозиция [RecipeEditor.vue](../../backend/laravel/resources/js/Components/RecipeEditor.vue) (~56KB монолит) — встраиваем как есть, отдельный refactor follow-up.
- Декомпозиция [PumpCalibrationDrawer.vue](../../backend/laravel/resources/js/Components/Launch/Calibration/PumpCalibrationDrawer.vue) (~45KB) — используем как есть.
- Inline-создание теплицы в шаге 1 (решение #5).
- TweaksPanel из рефа (решение #10).
- Миграция остальных страниц приложения на новые токены (`brand`/`growth`/`warn`/`alert`). Этот PR ограничивается `/launch`. Глобальная миграция — отдельная задача.
- Pinia store для launch-state (решение #17).
- Backend-правки (если по ходу обнаружится — фиксим точечно отдельным коммитом в этом же PR).

## 11. Риски

| Риск | Митигация |
|---|---|
| RecipeEditor 56KB — тяжело вписать в новый layout без декомпозиции | Встраиваем в `<Card>` без изменений; визуальная гармония — через wrapper-padding. Если совсем плохо — частичная декомпозиция как 12-й коммит этого PR |
| File-size guard срабатывает на больших Subview | Subview > 350 строк — обязательная декомпозиция (extract row/column components) |
| Визуальный фокус wizard'а теряется из-за глобального `AppLayout` | `LaunchShell` оформляется как отдельная embedded wizard-card; `AppLayout` сохраняет command palette, toast/error boundary и навигационный контекст |
| Health endpoint возвращает другой формат, чем ожидает реф | Адаптируем в `useServiceHealth` (маппинг). Backend не трогаем |
| Локальные шрифты добавляют 200-400 KB к bundle | Subset до latin+cyrillic, weights 400/500/600/700 для sans, 400/500 для mono — итог ~80-120 KB |
| Process-calibrations endpoint — другой URL, чем в рефе | Используем существующий `automation-configs/zone/.../zone.process_calibration.{mode}` |
| Decomposition AutomationHub без потери логики | Перед перепиской — снять диff текущих props/emit, написать contract test для `useAutomationContracts` |

## 12. Связанные документы

- [FRONTEND_ARCH_FULL.md](FRONTEND_ARCH_FULL.md)
- [FRONTEND_UI_UX_SPEC.md](FRONTEND_UI_UX_SPEC.md)
- [ROLE_BASED_UI_SPEC.md](ROLE_BASED_UI_SPEC.md)
- [AUTOMATION_WIZARD_UNIFICATION_PLAN.md](AUTOMATION_WIZARD_UNIFICATION_PLAN.md)
- [ZONE_AUTOMATION_PRESETS_PLAN.md](ZONE_AUTOMATION_PRESETS_PLAN.md)
- [SCHEDULER_COCKPIT_REDESIGN.md](SCHEDULER_COCKPIT_REDESIGN.md) — образец планирования cockpit-страниц
