# Launch Wizard — план переписки legacy-компонентов

**Версия:** 1.0
**Дата:** 2026-04-25
**Статус:** план (ожидает approval)
**Контекст:** ветка `feature/launch-redesign`, после коммита `28d69e6f`.
Полный визуальный shell + 6 Automation subview'ов уже Hydroflow; осталось
переписать legacy-компоненты, которые рендерятся через тонкие subview-обёртки
шага 4 «Калибровка» (и пара мелких в других шагах).

---

## 1. Аудит — что осталось legacy

### Внешние Components/* в Launch flow

Файлы импортируются `Pages/Launch` или `Components/Launch/**`, но сами
лежат вне Launch flow и используют legacy-стиль (`<style scoped>` или
старая палитра).

| # | Файл | Lines | Где рендерится | Поля | API | Стиль |
|---|---|---:|---|---:|---:|---|
| L1 | `CorrectionConfigForm.vue` | **1871** | Calibration → Correction | ~9 | live-edit + load | legacy CSS |
| L2 | `ProcessCalibrationPanel.vue` | **1315** | Calibration → Process | tabs + ~8 | save per mode | legacy CSS |
| L3 | `PidConfigForm.vue` | **1114** | Calibration → PID | ~21 | save | legacy CSS |
| L4 | `PumpCalibrationDrawer.vue` | **1365** | Calibration (modal) | ~16 | save | legacy CSS |
| L5 | `CalibrationPumpsSubpage.vue` | 566 | Calibration → Pumps | table | — | legacy CSS |
| L6 | `RecipePhasesSummary.vue` | 274 | Recipe + Preview | strip | — | legacy CSS |
| L7 | `CalibrationBlockersDrawer.vue` | 243 | Calibration (modal) | list | — | legacy CSS |
| L8 | `AutomationBlockersDrawer.vue` | 205 | Automation (modal) | list | — | legacy CSS |
| L9 | `SensorCalibrationStatus.vue` | 205 | Calibration → Sensors | 2 cards | load | без `<style>` |
| L10 | `PresetSelector.vue` | 195 | Automation → Contour | dropdown | — | без `<style>` |
| L11 | `RelayAutotuneTrigger.vue` | 173 | Calibration → PID | form | start | без `<style>` |

### Внутренние Launch wrapper'ы с `<style scoped>`

| # | Файл | Lines | Notes |
|---|---|---:|---|
| W1 | `Components/Launch/AutomationStep.vue` | 341 | Тонкий wrapper над `AutomationHub`; `.launch-step__*` styles. |
| W2 | `Components/Launch/CalibrationStep.vue` | ~50 | Тонкий wrapper над `CalibrationHub`. |

**Не legacy в текущем PR:** `ZoneAutomationProfileSections.vue` (60 KB) — больше не
импортируется из `/launch`, остаётся для `Pages/Zones/Tabs/ZoneAutomationEditWizard.vue`.

---

## 2. Группировка по приоритету

### 🟢 Phase A — мелкие, быстрые (≤1 коммит каждый)

Низкий риск, минимум API‑surface, чистая визуальная переписка.

| # | Файл | Оценка scope | Что делаем |
|---|---|---|---|
| A1 | `AutomationStep.vue` + `CalibrationStep.vue` (W1, W2) | 1 коммит | Удалить `<style scoped>`, перевести разметку на Hydroflow токены / ShellCard. |
| A2 | `SensorCalibrationStatus.vue` (L9) | 1 коммит | Переписать в Hydroflow: 2 ShellCard pH/EC с Stat (last value/offset/slope/calibrated_at) + Button «Калибровать», как в реф `steps.jsx::SensorsSub`. |
| A3 | `RelayAutotuneTrigger.vue` (L11) | 1 коммит | Hydroflow Card + Button «Autotune» + form fields. |
| A4 | `PresetSelector.vue` (L10) | 1 коммит | Hydroflow Card + Select из presets, кнопки «Применить» / «Снять». |
| A5 | `RecipePhasesSummary.vue` (L6) | 1 коммит | Использовать существующий `Recipe/PhaseStrip.vue` + расширить для full preview, либо переписать с tone‑полосами. |
| A6 | `CalibrationBlockersDrawer.vue` + `AutomationBlockersDrawer.vue` (L7, L8) | 1 коммит | Унифицировать как `BlockersDrawer.vue` в `Shell/`, Hydroflow Drawer с Chip‑rows. |

**Всего Phase A:** ~6 коммитов, ~1500 строк (с тестами).

### 🟡 Phase B — средние, требуют переписки таблиц/форм

Средний риск, требуют сохранять save-логику.

| # | Файл | Оценка scope | Что делаем |
|---|---|---|---|
| B1 | `CalibrationPumpsSubpage.vue` (L5, 566) | 1‑2 коммита | Переписать таблицу 6 насосов как реф `steps.jsx::PumpsSub`: header `Компонент / Канал / Длит / Факт мл / мл/сек / Статус / Действие` + Chip per row. |
| B2 | `PumpCalibrationDrawer.vue` (L4, 1365) | 2‑3 коммита | Decompose: каркас Drawer (Hydroflow), 16 полей через Field/Select/TextInput. Save remain via existing endpoints. |

**Всего Phase B:** ~3‑5 коммитов, ~3000 строк.

### 🔴 Phase C — крупные формы

Высокий риск, серьёзный refactor с сохранением всех save endpoints. Нужны
unit + integration тесты до и после.

| # | Файл | Оценка scope | Что делаем |
|---|---|---|---|
| C1 | `PidConfigForm.vue` (L3, 1114, 21 поле) | 3‑5 коммитов | Hydroflow form: tabs pH/EC + dead/close/far + zone_coeffs (close+far × kp/ki/kd) + max_output / min_interval_ms / max_integral. Сохранить save endpoint и контракт `phase-targets`. |
| C2 | `ProcessCalibrationPanel.vue` (L2, 1315) | 3‑5 коммитов | Hydroflow: 4 mode tabs (`solution_fill / tank_recirc / irrigation / generic`) + 8 коэффициентов (ec_gain_per_ml / ph_up/down_gain_per_ml / ph_per_ec_ml / ec_per_ph_ml / confidence / transport_delay / settle). |
| C3 | `CorrectionConfigForm.vue` (L1, 1871) | 5‑8 коммитов | Самый большой: authority editor (recipe / zone / manual) + 6+ полей + `correctionDeadband*`, `correctionStep*`, `correctionMaxDose*`, гистерезис, аварийные стопы, recovery, per-контурные authority overrides. Реф `automation-hub.jsx::CorrectionTargetsSub` lines 549-685. |

**Всего Phase C:** ~11‑18 коммитов, ~6000 строк (включая тесты).

---

## 3. Структура коммитов внутри одного PR

Каждая фаза — серия атомарных коммитов с зелёными гарда­ми (typecheck +
lint + vitest + build + file‑size guard). Коммитимся в `feature/launch-redesign`
(или новая ветка `feature/launch-legacy-cleanup`, если scope сильно растёт).

```
feature/launch-redesign  (текущий PR, опционально extend)
└── feature/launch-legacy-cleanup  (новая ветка для phase A+B)
└── feature/launch-pid-form         (отдельный PR для C1)
└── feature/launch-process-panel    (отдельный PR для C2)
└── feature/launch-correction-form  (отдельный PR для C3)
```

**Рекомендация:** Phase A + B — closing текущего PR (или follow‑up
сразу после merge). Phase C — каждый компонент отдельным PR из‑за
объёма и риска (3 крупных формы по 1‑2 КБ каждая).

---

## 4. Критерии переписки для каждого компонента

Для всех:

- ❌ Удалить `<style scoped>` целиком; всё через Tailwind классы
  + Hydroflow токены (`bg-[var(--bg-surface-strong)]`, `text-brand-ink`,
  `border-[var(--border-muted)]`).
- ✅ Использовать только primitives:
  `Field` / `Select` / `Chip` / `Stat` / `Hint` / `KV` / `ToggleField`,
  `ShellCard`, `Ic`, `Button`.
- ✅ Сохранить все props/emits контракты (для backward compat с
  внешними usage этих компонентов в других страницах).
- ✅ Сохранить все API‑вызовы и save endpoints (никаких
  изменений в backend).
- ✅ Покрыть Vitest минимум: render + emit + edge case.
- ✅ Переход с любого внешнего usage без правок этих usage'ов
  (например, `ZoneAutomationEditWizard.vue` продолжает использовать
  `ZoneAutomationProfileSections` — это OK, мы её не трогаем).

Для form-компонентов C1‑C3 дополнительно:

- 🔍 Перед началом — снять snapshot существующих save‑endpoint'ов:
  `git grep -F "automationConfigs.update"` / `git grep -F "api.zones.calibratePump"`.
  После переписки — точно те же endpoints с теми же payload‑shape.
- 🧪 Перед началом — написать contract test (input fields → mock API
  call assertion). После переписки запустить тот же тест на новом
  компоненте — должны проходить идентично.

---

## 5. Что НЕ переписывается

- `ZoneAutomationProfileSections.vue` — out of scope (используется
  на `/zones/{id}/edit`, не на `/launch`).
- `RecipeEditor.vue` (~56 KB) — out of scope (зеркальное решение
  пользователя «шаг 2 не делай»).
- ZoneAutomation/* подкомпоненты (`RequiredDevicesSection`, `WaterContourSection`,
  и т.п.) — больше не используются на `/launch` (заменены на
  `Components/Launch/Automation/Subviews/*`), но остаются для
  `ZoneAutomationProfileSections`. Их переписка нужна только если будем
  переписывать `ZoneAutomationProfileSections` (отдельный PR).
- Backend changes — none. Все ZoneCorrectionPreset / ProcessCalibration /
  PidConfig endpoint'ы остаются как есть.

---

## 6. Риски

| Риск | Митигация |
|---|---|
| Поломка save-endpoint при переписке формы C1‑C3 | Snapshot endpoints перед, contract test до/после, manual smoke в браузере. |
| Внешние usage сломаются (например, если ZoneAutomationProfileSections.vue вызывает PidConfigForm) | Перед коммитом — `git grep -F "PidConfigForm"`, проверить все usage'ы. Контракт props/emits сохранить 1:1. |
| File-size guard срабатывает (Hydroflow версия может быть длиннее legacy из-за explicit Field/Hint) | Декомпозиция на под‑компоненты per logical group; добавление exception_limit для Page‑orchestrator если нужно. |
| Перевод 21 поля PidConfig на Hydroflow увеличит контекст PR | Дробить C1 на 3‑5 коммитов: tabs+targets / zone_coeffs grid / max_*+min_* поля / autotune wiring / tests. |

---

## 7. Текущая ситуация (как точка отсчёта)

- Ветка `feature/launch-redesign`: **22 коммита**, 187 vitest файлов /
  1443 + 1 skipped pass, build ✓ ~13s, file‑size guard PASS.
- Все 5 шагов wizard'а на Hydroflow shell + tokens + primitives.
- AutomationHub полностью декомпозирован (6 Hydroflow subview).
- CalibrationHub декомпозирован на 5 subview‑обёрток (тонкие; внутри
  legacy `SensorCalibrationStatus` / `ProcessCalibrationPanel` /
  `CorrectionConfigForm` / `PidConfigForm` / `RelayAutotuneTrigger` /
  `CalibrationPumpsSubpage`).
- Phase A → B → C из этого плана нужно решить, делать ли:
  - в текущем PR (продлить);
  - отдельным follow‑up PR (`feature/launch-legacy-cleanup`);
  - или закрыть текущий PR и дальше серию по приоритету.

---

## 8. Связанные документы

- [LAUNCH_REDESIGN.md](LAUNCH_REDESIGN.md) — основной план редизайна
  (текущий PR).
- [FRONTEND_ARCH_FULL.md](FRONTEND_ARCH_FULL.md)
- `hydroflow/automation-hub.jsx` (lines 549‑685 — реф для C3)
- `hydroflow/steps.jsx` (lines 526‑806 — рефы для A2 / C1 / C2)
