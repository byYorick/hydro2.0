# План реализации системы пресетов автоматики зон

**Версия:** 1.0
**Дата:** 2026-04-17
**Статус:** draft — требует ack пользователя перед исполнением

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 0. Контекст и решения

Обсуждение 2026-04-17 зафиксировало следующие архитектурные решения:

| Решение | Выбор |
|---------|-------|
| Уровни пресетов | Два: мега-пресет (ZoneAutomationPreset) + секционные (correction preset и т.д.) |
| UX в мастере | Template-first: выбрать пресет → подкрутить по секциям |
| Привязка | К `tanks_count` + `irrigation_system_type` + `correction_profile` |
| Сохранение как пресет | Да, визард сохранения с именем и описанием |
| Start Cycle override | Variant A — override на уровне `grow_cycle`, зона не перезаписывается |
| Merge priority | `cycle.config_overrides > zone.logic_profile > system defaults` |
| Cycle override scope | Может перезаписывать всё, включая safety/failsafe |
| Видимость пресетов | Все видны всем (system + custom) |
| Correction presets | Остаются в миграциях, не переносить в seeders |
| Climate/Lighting в мега-пресете | Секции есть, помечены «на будущее» |
| Описания пресетов | На русском, с техническими деталями, генерируются |

**Эталоны:**
- `RuntimePlan` Pydantic: `ae3lite/config/schema/runtime_plan.py`
- Bundle compiler: `app/Services/AutomationConfigCompiler.php`
- Existing correction presets: `AutomationConfigPreset` model + 4 system presets в миграции `2026_03_08_120000`
- Zone logic profile: `ZoneLogicProfileService.php`
- Grow cycle bundle: `compileGrowCycleBundle()` — уже поддерживает `cycle.phase_overrides` и `cycle.manual_overrides`

---

## 1. Архитектура

### 1.1 Новая модель: ZoneAutomationPreset

```sql
CREATE TABLE zone_automation_presets (
    id            BIGSERIAL PRIMARY KEY,
    name          VARCHAR(128) NOT NULL,
    slug          VARCHAR(128) NOT NULL UNIQUE,
    description   TEXT,                          -- подробное описание для UI
    scope         VARCHAR(16) NOT NULL DEFAULT 'custom',  -- 'system' | 'custom'
    is_locked     BOOLEAN NOT NULL DEFAULT FALSE,

    -- Фильтры совместимости
    tanks_count          SMALLINT NOT NULL DEFAULT 2,        -- 2 | 3
    irrigation_system_type VARCHAR(32) NOT NULL DEFAULT 'dwc', -- drip_tape|drip_emitter|ebb_flow|nft|dwc|aeroponics

    -- Ссылка на секционный пресет коррекции
    correction_preset_id  BIGINT REFERENCES automation_config_presets(id)
                          ON DELETE SET NULL,
    correction_profile    VARCHAR(32),           -- 'safe'|'balanced'|'aggressive'|'test' (тег для UI)

    -- Inline конфиг секций (JSONB)
    config        JSONB NOT NULL DEFAULT '{}',

    created_by    BIGINT REFERENCES users(id) ON DELETE SET NULL,
    updated_by    BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_zap_scope ON zone_automation_presets(scope);
CREATE INDEX idx_zap_tanks_irr ON zone_automation_presets(tanks_count, irrigation_system_type);
```

### 1.2 Структура `config` JSONB

```jsonc
{
  "irrigation": {
    "duration_sec": 300,
    "interval_sec": 3600,
    "correction_during_irrigation": true,
    "correction_slack_sec": 30
  },
  "irrigation_decision": {
    "strategy": "task",              // "task" | "smart_soil_v1"
    "config": {                      // только если strategy != "task"
      "lookback_sec": 1800,
      "min_samples": 3,
      "stale_after_sec": 600,
      "hysteresis_pct": 2.0,
      "spread_alert_threshold_pct": 15.0
    }
  },
  "startup": {
    "clean_fill_timeout_sec": 1200,
    "solution_fill_timeout_sec": 1800,
    "prepare_recirculation_timeout_sec": 1200,
    "level_poll_interval_sec": 60,
    "clean_fill_retry_cycles": 1
  },
  // 🔮 На будущее — пока nullable/пустые
  "climate": null,
  "lighting": null
}
```

### 1.3 Cycle config overrides

Новый namespace в `AutomationConfigRegistry`:

```php
const NAMESPACE_CYCLE_CONFIG_OVERRIDES = 'cycle.config_overrides';
```

Document scope: `grow_cycle`, scope_id: `cycle.id`.

Payload — частичный snapshot `zone.logic_profile` + `zone.correction`, применяемый поверх zone config при компиляции bundle.

**Merge priority в `compileGrowCycleBundle()`:**
```
cycle.config_overrides  →  перезаписывает zone.*
zone.logic_profile      →  базовая настройка
zone.correction         →  базовая коррекция
system defaults         →  fallback
```

---

## 2. System presets (в миграции)

6 начальных пресетов, `scope='system'`, `is_locked=true`:

### DWC Balanced (slug: `dwc-balanced`)
- `tanks_count: 2`, `irrigation_system_type: 'dwc'`, `correction_profile: 'balanced'`
- `correction_preset_id` → balanced system correction preset
- Описание: «Стандартный профиль для DWC системы с двумя баками. Оптимальный баланс между скоростью коррекции и стабильностью. Подходит для большинства культур. Интервал полива 60 мин, длительность 5 мин. Таймаут заполнения чистой воды 20 мин, раствора 30 мин.»
- Config:
  ```json
  {
    "irrigation": {"duration_sec": 300, "interval_sec": 3600, "correction_during_irrigation": true, "correction_slack_sec": 30},
    "irrigation_decision": {"strategy": "task"},
    "startup": {"clean_fill_timeout_sec": 1200, "solution_fill_timeout_sec": 1800, "prepare_recirculation_timeout_sec": 1200, "level_poll_interval_sec": 60, "clean_fill_retry_cycles": 1}
  }
  ```

### DWC Safe (slug: `dwc-safe`)
- `tanks_count: 2`, `irrigation_system_type: 'dwc'`, `correction_profile: 'safe'`
- `correction_preset_id` → safe system correction preset
- Описание: «Консервативный профиль для DWC. Мягкие дозы, увеличенное время стабилизации между дозированиями. Рекомендуется для новых систем, первого запуска, чувствительных культур (салат, микрозелень). Увеличенные таймауты заполнения для надёжности.»
- Config:
  ```json
  {
    "irrigation": {"duration_sec": 300, "interval_sec": 3600, "correction_during_irrigation": true, "correction_slack_sec": 45},
    "irrigation_decision": {"strategy": "task"},
    "startup": {"clean_fill_timeout_sec": 1500, "solution_fill_timeout_sec": 2400, "prepare_recirculation_timeout_sec": 1500, "level_poll_interval_sec": 60, "clean_fill_retry_cycles": 1}
  }
  ```

### DWC Aggressive (slug: `dwc-aggressive`)
- `tanks_count: 2`, `irrigation_system_type: 'dwc'`, `correction_profile: 'aggressive'`
- `correction_preset_id` → aggressive system correction preset
- Описание: «Быстрый профиль для хорошо откалиброванных DWC систем. Высокие дозы, минимальная стабилизация. Только для опытных пользователей с проверенной калибровкой насосов. Позволяет быстрее выйти на целевые значения pH/EC. Сокращённые таймауты заполнения.»
- Config:
  ```json
  {
    "irrigation": {"duration_sec": 300, "interval_sec": 3600, "correction_during_irrigation": true, "correction_slack_sec": 15},
    "irrigation_decision": {"strategy": "task"},
    "startup": {"clean_fill_timeout_sec": 900, "solution_fill_timeout_sec": 1200, "prepare_recirculation_timeout_sec": 900, "level_poll_interval_sec": 45, "clean_fill_retry_cycles": 1}
  }
  ```

### Drip Tape Balanced (slug: `drip-tape-balanced`)
- `tanks_count: 2`, `irrigation_system_type: 'drip_tape'`, `correction_profile: 'balanced'`
- `correction_preset_id` → balanced system correction preset
- Описание: «Стандартный профиль для капельного полива. Двухбаковая система с оптимальными параметрами коррекции. Интервал полива 90 мин с учётом времени доставки раствора по капельным линиям. Увеличенный slack для стабилизации после полива.»
- Config:
  ```json
  {
    "irrigation": {"duration_sec": 180, "interval_sec": 5400, "correction_during_irrigation": false, "correction_slack_sec": 60},
    "irrigation_decision": {"strategy": "task"},
    "startup": {"clean_fill_timeout_sec": 1200, "solution_fill_timeout_sec": 1800, "prepare_recirculation_timeout_sec": 1200, "level_poll_interval_sec": 60, "clean_fill_retry_cycles": 1}
  }
  ```

### NFT Balanced (slug: `nft-balanced`)
- `tanks_count: 2`, `irrigation_system_type: 'nft'`, `correction_profile: 'balanced'`
- `correction_preset_id` → balanced system correction preset
- Описание: «Стандартный профиль для NFT (Nutrient Film Technique). Непрерывная тонкая плёнка раствора. Короткий интервал полива с частой подачей. Коррекция во время полива включена — раствор постоянно циркулирует. Быстрый отклик системы.»
- Config:
  ```json
  {
    "irrigation": {"duration_sec": 900, "interval_sec": 1800, "correction_during_irrigation": true, "correction_slack_sec": 15},
    "irrigation_decision": {"strategy": "task"},
    "startup": {"clean_fill_timeout_sec": 1200, "solution_fill_timeout_sec": 1800, "prepare_recirculation_timeout_sec": 1200, "level_poll_interval_sec": 60, "clean_fill_retry_cycles": 1}
  }
  ```

### Test Node (slug: `test-node`)
- `tanks_count: 2`, `irrigation_system_type: 'dwc'`, `correction_profile: 'test'`
- `correction_preset_id` → test-node system correction preset
- Описание: «Профиль для тестовой ноды и HIL-тестирования. Малый объём раствора (20 л), мягкие дозы, сокращённые таймауты. Используется при разработке и отладке. Не для production.»
- Config:
  ```json
  {
    "irrigation": {"duration_sec": 120, "interval_sec": 1800, "correction_during_irrigation": true, "correction_slack_sec": 15},
    "irrigation_decision": {"strategy": "task"},
    "startup": {"clean_fill_timeout_sec": 600, "solution_fill_timeout_sec": 600, "prepare_recirculation_timeout_sec": 600, "level_poll_interval_sec": 30, "clean_fill_retry_cycles": 1}
  }
  ```

---

## 3. Executable runbook

Каждая фаза = отдельный PR, независимо revert-able.

### Phase 1 — Backend: модель + CRUD + system presets (1-2 дня)

**Цель:** создать `ZoneAutomationPreset` модель, сервис, контроллер, миграцию с system presets.

**Actions:**
1. Миграция `create_zone_automation_presets_table.php` — DDL из §1.1.
2. Модель `ZoneAutomationPreset.php` — fillable, casts, relationships (`belongsTo(AutomationConfigPreset, 'correction_preset_id')`, `belongsTo(User, 'created_by')`).
3. `ZoneAutomationPresetService.php`:
   - `list(filters: {tanks_count?, irrigation_system_type?}): Collection`
   - `findOrFail(id): ZoneAutomationPreset`
   - `create(payload, userId): ZoneAutomationPreset` — только custom
   - `update(preset, payload, userId): ZoneAutomationPreset` — только custom, не locked
   - `delete(preset): void` — только custom, не locked
   - `duplicate(preset, userId): ZoneAutomationPreset`
4. `ZoneAutomationPresetController.php` — REST CRUD:
   - `GET /api/zone-automation-presets?tanks_count=2&irrigation_system_type=dwc`
   - `POST /api/zone-automation-presets`
   - `PUT /api/zone-automation-presets/{id}`
   - `DELETE /api/zone-automation-presets/{id}`
   - `POST /api/zone-automation-presets/{id}/duplicate`
5. Миграция (или в той же): INSERT 6 system presets из §2.
6. `FormRequest` для валидации payload.
7. PHPUnit тесты: CRUD + фильтрация + защита system presets.

**DoD:**
- `php artisan test --filter=ZoneAutomationPreset` — green
- 6 system presets в БД после migrate
- API endpoints работают

**Rollback:** revert PR + rollback migration.

---

### Phase 2 — Backend: cycle config overrides в bundle compiler (1 день)

**Цель:** добавить `cycle.config_overrides` namespace и merge в `compileGrowCycleBundle()`.

**Actions:**
1. В `AutomationConfigRegistry.php`:
   - Добавить `NAMESPACE_CYCLE_CONFIG_OVERRIDES = 'cycle.config_overrides'`
   - Зарегистрировать namespace
2. В `AutomationConfigCompiler::compileGrowCycleBundle()`:
   - Читать `cycle.config_overrides` document
   - Deep-merge поверх `zone.*` секций bundle **до** финальной записи
   - Порядок: `config_overrides` перезаписывает matching ключи в `zone.logic_profile` и `zone.correction`
3. В `GrowCycleOrchestrator` / `GrowCycleService`:
   - При создании цикла: если передан `config_overrides` payload → сохранить как document `cycle.config_overrides`
   - При старте: bundle compiler подхватит автоматически
4. PHPUnit тесты:
   - Bundle без overrides — как раньше
   - Bundle с overrides — override побеждает zone config
   - Bundle с partial overrides — не затронутые секции из zone config
5. JSON Schema для `cycle.config_overrides` (опционально, v1 — loose validation).

**DoD:**
- `php artisan test --filter=BundleCompiler` — green
- Override применяется в compiled bundle
- Без override — поведение не изменилось (backward compatible)

**Rollback:** revert PR. Namespace не использовался, нет данных.

---

### Phase 3 — Frontend: API client + типы + composable (1 день)

**Цель:** TypeScript типы, API client, composable для работы с ZoneAutomationPreset.

**Actions:**
1. `resources/js/types/ZoneAutomationPreset.ts`:
   ```typescript
   interface ZoneAutomationPreset {
     id: number
     name: string
     slug: string
     description: string | null
     scope: 'system' | 'custom'
     is_locked: boolean
     tanks_count: 2 | 3
     irrigation_system_type: string
     correction_preset_id: number | null
     correction_profile: string | null
     config: ZoneAutomationPresetConfig
     created_by: number | null
     updated_by: number | null
     created_at: string
     updated_at: string
   }

   interface ZoneAutomationPresetConfig {
     irrigation: { duration_sec: number; interval_sec: number; correction_during_irrigation: boolean; correction_slack_sec: number }
     irrigation_decision: { strategy: 'task' | 'smart_soil_v1'; config?: Record<string, number> }
     startup: { clean_fill_timeout_sec: number; solution_fill_timeout_sec: number; prepare_recirculation_timeout_sec: number; level_poll_interval_sec: number; clean_fill_retry_cycles: number }
     climate?: Record<string, unknown> | null
     lighting?: Record<string, unknown> | null
   }
   ```
2. `resources/js/services/api/zoneAutomationPresets.ts` — API client (list, create, update, delete, duplicate).
3. `resources/js/composables/useZoneAutomationPresets.ts`:
   - `listPresets(filters)` — с кэшированием
   - `applyPresetToForms(preset, formState)` — заполняет WaterFormState из пресета
   - `buildPresetFromForms(formState, meta)` — собирает пресет из текущих форм (для save-as)
   - `isPresetModified(preset, formState)` — проверяет отклонения
4. Vitest unit тесты: round-trip apply→build, фильтрация, modified detection.

**DoD:**
- `npm run typecheck` — green
- `npm run test -- --run zoneAutomationPresets` — green

**Rollback:** revert PR — ничего не использует.

---

### Phase 4 — Frontend: интеграция в Setup Wizard (2-3 дня)

**Цель:** добавить шаг выбора пресета в Setup Wizard, template-first flow.

**Actions:**
1. Создать `Components/AutomationForms/PresetSelector.vue`:
   - Grid карточек пресетов (с иконками, описаниями, тегами correction_profile)
   - Фильтрация по текущему tanks_count и irrigation_system_type (из предыдущих шагов wizard)
   - Разделение: «Системные» / «Мои пресеты» / «Настроить с нуля»
   - Каждая карточка:
     - Название + correction_profile badge (safe/balanced/aggressive)
     - Описание (2-3 строки)
     - Ключевые параметры (irrigation interval, stabilization, max_dose) как chips
   - Dark mode support
2. Встроить `PresetSelector` в Setup Wizard **после** шага выбора типа системы (шаг 2→3):
   - Выбор пресета → `applyPresetToForms()` → заполняет все последующие шаги
   - «Настроить с нуля» → формы с defaults как сейчас
3. На последующих шагах (irrigation, correction):
   - Показать badge «Из пресета: DWC Balanced» если применён пресет
   - При изменении любого поля — badge меняется на «Изменено (на основе DWC Balanced)»
4. Обновить `useSetupWizard.ts`:
   - Новое состояние `selectedPresetId` / `presetModified`
   - При submit — передавать `applied_preset_id` в payload (для audit trail)
5. Vitest тесты: PresetSelector render, apply, modified detection.
6. **Ручная проверка в браузере:** Setup Wizard → выбор пресета → шаги заполняются → save.

**DoD:**
- Setup Wizard показывает шаг выбора пресета
- Выбор пресета заполняет все формы
- Изменения на последующих шагах помечаются как «modified»
- `npm run test && npm run typecheck` — green
- Визуальная проверка в браузере (dark mode)

**Rollback:** revert PR; Setup Wizard возвращается к flow без пресетов.

---

### Phase 5 — Frontend: «Сохранить как пресет» визард (1-2 дня)

**Цель:** кнопка «Сохранить как пресет» на финальном шаге Setup Wizard + Start Cycle.

**Actions:**
1. Создать `Components/AutomationForms/SavePresetWizard.vue` — modal/dialog:
   - Шаг 1: Имя пресета (required), slug (auto-generated)
   - Шаг 2: Описание (textarea, placeholder с подсказкой «Опишите для какой системы и условий подходит этот пресет»)
   - Шаг 3: Обзор — что будет сохранено (irrigation params, correction profile, startup params) в read-only виде
   - Кнопка «Сохранить» → `POST /api/zone-automation-presets`
   - Success → toast «Пресет сохранён» + появляется в списке
2. Встроить кнопку:
   - Setup Wizard финальный шаг → «Сохранить эту конфигурацию как пресет»
   - Start Cycle финальный шаг → та же кнопка
3. `buildPresetFromForms()` — собирает payload из текущего состояния форм:
   - Определяет `correction_preset_id` — если correction не менялась → ссылка на applied preset; если менялась → null
   - `correction_profile` — тег из applied correction preset или null
   - `tanks_count`, `irrigation_system_type` — из формы
   - `config` — из текущих значений форм
4. Vitest тесты: SavePresetWizard render, validation, submit.

**DoD:**
- Кнопка «Сохранить как пресет» на финальных шагах обоих мастеров
- Сохранённый пресет появляется в списке при следующем открытии мастера
- `npm run test && npm run typecheck` — green

**Rollback:** revert PR.

---

### Phase 6 — Frontend: пресеты в Start Cycle + cycle override (2-3 дня)

**Цель:** интегрировать пресеты в Start Cycle; override на цикл без перезаписи зоны.

**Actions:**
1. В Start Cycle wizard (GrowthCycleWizard.vue):
   - **Если зона уже настроена** (есть logic_profile с subsystems) → показать summary-карточку текущих настроек + кнопку «Изменить для этого цикла»
   - **Если зона не настроена** → показать полный PresetSelector (как в Setup Wizard)
   - «Изменить для этого цикла» → разворачивает PresetSelector + секционные формы
2. При выборе пресета / изменении настроек в Start Cycle:
   - **Не вызывать** `PUT zone.logic_profile` (в отличие от текущего поведения!)
   - Вместо этого: сформировать `config_overrides` payload
   - При `POST /zones/{id}/grow-cycles` → передать `config_overrides` в payload
   - Backend сохраняет как document `cycle.config_overrides`
3. Обновить `useGrowthCycleWizard.ts`:
   - Убрать (или сделать optional) `persistLaunchPrerequisites()` для секций которые идут в override
   - Новый метод `buildConfigOverrides()` — diff между выбранным пресетом и текущим zone config
4. Обновить `GrowCycleController::store()` / `GrowCycleOrchestrator`:
   - Принять optional `config_overrides` в request
   - Сохранить как `cycle.config_overrides` document через `AutomationConfigService`
   - Bundle compiler (Phase 2) подхватит при компиляции
5. Badge на running cycle: «Запущен с override (Aggressive)» — в zone automation tab.
6. Vitest + Playwright тесты.

**DoD:**
- Start Cycle с override → зона нетронута, bundle содержит merged config
- Start Cycle без override → поведение как раньше
- Badge override на running cycle
- `npm run test && npm run typecheck` — green
- Playwright e2e: start cycle с override → verify zone config unchanged → verify bundle contains override

**Rollback:** revert PR; Start Cycle возвращается к записи в zone.logic_profile.

---

## 4. Таймлайн

| Фаза | Длительность | Риск | Зависит от |
|------|-------------|------|------------|
| 1: Backend модель + CRUD + system presets | 1-2 дня | low | — |
| 2: Bundle compiler cycle override | 1 день | medium | — |
| 3: Frontend типы + API + composable | 1 день | low | 1 |
| 4: Setup Wizard интеграция | 2-3 дня | medium | 1, 3 |
| 5: Save-as-preset визард | 1-2 дня | low | 3, 4 |
| 6: Start Cycle + cycle override | 2-3 дня | high | 1, 2, 3 |

**Итого:** ~8-12 дней. Phase 1 и 2 параллелизуемы. Phase 4 и 5 последовательны. Phase 6 после всего.

---

## 5. Risk register

| # | Риск | Вероятность | Импакт | Митигация |
|---|------|------------|--------|-----------|
| R1 | Deep merge в bundle compiler теряет ключи | средняя | data loss → неверная коррекция | Extensive unit-тесты merge с nested objects; characterization tests |
| R2 | Start Cycle без override ломается (regression) | средняя | блокер запуска | Backward-compatible: если `config_overrides` null → пропустить merge |
| R3 | Пользователь не понимает что override на цикл, а не на зону | высокая | UX confusion | Явный badge, tooltip «Эти настройки действуют только на текущий цикл» |
| R4 | correction_preset_id FK → deletion cascade issues | низкая | orphan presets | ON DELETE SET NULL — пресет остаётся, ссылка обнуляется |
| R5 | Много system presets засоряют UI | низкая | UX noise | Группировка по irrigation_system_type; фильтрация по текущей системе |
| R6 | Описания пресетов устаревают после изменения параметров | средняя | misleading UI | Описание привязано к пресету, не к runtime — обновлять при изменении |

---

## 6. Stop-and-ask points

- **Phase 1:** перед merge — ревью system preset значений (irrigation timing для каждого типа)
- **Phase 4:** после реализации — ручная проверка UX в браузере (карточки, описания, flow)
- **Phase 6:** перед merge — ручная проверка override flow; verify что зона не перезаписывается

---

## 7. Post-completion invariants

1. **Любой новый system preset** добавляется через миграцию, не через seeder.
2. **Custom пресеты** создаются только через API / UI; system presets — read-only.
3. **Start Cycle** никогда не перезаписывает `zone.logic_profile` напрямую — только `cycle.config_overrides`.
4. **Bundle compiler** обязан поддерживать отсутствие `config_overrides` (backward compatible).
5. **PresetSelector** фильтрует по `tanks_count` + `irrigation_system_type` из контекста wizard.
6. **Описания пресетов** — на русском, содержат технические детали (время, дозы, для кого подходит).

---

## 8. Связанные документы

- [AUTOMATION_WIZARD_UNIFICATION_PLAN.md](AUTOMATION_WIZARD_UNIFICATION_PLAN.md) — параллельный план унификации форм (shared components, dead fields cleanup)
- [AE3_CONFIG_REFACTORING_PLAN.md](../04_BACKEND_CORE/AE3_CONFIG_REFACTORING_PLAN.md) — backend config authority
- [AUTOMATION_CONFIG_AUTHORITY.md](../04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md) — config namespaces
- [ZONES_AND_PRESETS.md](../06_DOMAIN_ZONES_RECIPES/ZONES_AND_PRESETS.md) — общая архитектура пресетов
