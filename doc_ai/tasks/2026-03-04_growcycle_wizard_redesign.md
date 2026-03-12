# Задача: Переработка GrowthCycleWizard — логика автоматики + калибровка насосов + фикс AE

**Дата:** 2026-03-04
**Ветка:** `feature/growcycle-wizard-logic-calibration`
**Compatible-With:** Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0

---

## Контекст

Система управляет зонами теплицы через иерархию: Теплица → Зоны → Узлы → Каналы.
При запуске нового вегетационного цикла пользователь проходит **GrowthCycleWizard** (5 шагов).

После запуска выявлены три критических проблемы:

1. **EC не корректируется** — таблица `pump_calibrations` пуста (нет `ml_per_sec`), блок дозирования ломается на нулевом `ml_per_sec`. Зона 10: EC=0.49 при target=1.05.
2. **two_tank workflow использует захардкоженные pH/EC defaults** (ph=5.80, ec=1.60) вместо реальных из `grow_cycle_phases` (ph=5.75, ec=1.05). WARNING в логах: `"both target_ph and target_ec resolved to defaults"`.
3. **Wizard не настраивает автоматику** — после запуска цикла пользователь обязан отдельно идти в ZoneAutomationEditWizard. Параметры рецепта не подставляются автоматически.

**Архитектура flow данных:**
```
GrowthCycleWizard → POST /api/zones/{id}/grow-cycles
                  → POST /api/zones/{id}/automation-logic-profiles   (subsystems)
                  → POST /api/zones/{id}/calibrate-pump              (ml_per_sec)
                        ↓
grow_cycle_phases (ph_target, ec_target, ...)
zone_automation_logic_profiles (subsystems JSON)
pump_calibrations (ml_per_sec для каждого насоса)
                        ↓
EffectiveTargetsService → effective_targets (PHP)
effective_targets_sql_read_model.py (Python AE)
                        ↓
automation-engine → correction_controller → CommandBus → history-logger → MQTT → узлы
```

---

---

# АГЕНТ 1: Frontend — GrowthCycleWizard

## Задача агента 1

Переработать шаг "параметры" и добавить шаг "калибровка насосов" в `GrowthCycleWizard.vue`.

## Текущая ситуация (агент 1)

**GrowthCycleWizard** имеет 5 шагов: `zone → plant → recipe → params → confirm`.

Шаг `params` содержит: `systemType`, `intervalMinutes`, `durationSeconds`, `cleanTankFillL`, `nutrientTankTargetL`, `startedAt`, `expectedHarvestAt`. pH/EC targets, климат и свет — не настраиваются. Нет шага калибровки насосов.

**ВАЖНО об архитектуре компонента:** `GrowthCycleWizard.vue` держит ВСЕ шаги как `v-if` блоки INLINE внутри одного компонента. Нет отдельных sub-компонентов для шагов. Новые шаги также делать inline — не создавать `WizardLogicStep.vue` и `WizardCalibrationStep.vue` как отдельные файлы. Это обеспечивает архитектурное единообразие.

**ВАЖНО об индикаторе шагов:** Текущий step indicator — flex row с `v-for` по массиву `steps`. При 6 шагах на мобильном он переполнится. Заменить на точки (dots) или использовать числовой индикатор `"Шаг N из 6"`.

**ВАЖНО о props:** GrowthCycleWizard получает только `zoneId`, `zoneName`, `initialData`. Список devices/channels зоны НЕ передаётся в props — его нужно загружать через API.

## Цель (агент 1)

Превратить wizard в 6 шагов: `zone → plant → recipe → logic → calibration → confirm`.

## Входные данные (агент 1)

### Ключевые файлы для изменения

| Файл | Роль |
|------|------|
| `resources/js/Components/GrowCycle/GrowthCycleWizard.vue` | Основной компонент wizard (изменить step indicator, добавить шаги inline) |
| `resources/js/composables/useGrowthCycleWizard.ts` | Логика wizard (расширить form, submit, saveDraft, loadDraft, reset, canProceed) |

**Новые файлы НЕ создавать** — весь код шагов добавляется inline в `GrowthCycleWizard.vue`.

### Файлы для переиспользования (НЕ дублировать логику)

| Файл | Что взять |
|------|-----------|
| `resources/js/composables/zoneAutomationPayloadBuilders.ts` | `buildGrowthCycleConfigPayload()` — скопировать `two_tank_commands` структуру и адаптировать для `buildLogicSubsystems` |
| `resources/js/composables/zoneAutomationTypes.ts` | `WaterFormState`, `ClimateFormState`, `LightingFormState` — переиспользовать типы |
| `resources/js/composables/usePumpCalibration.ts` | `PumpChannelOption`, логика сохранения калибровки |
| `resources/js/types/Calibration.ts` | `PumpCalibrationComponent`, `PumpCalibrationSavePayload` |
| `resources/js/types/Device.ts` | `DeviceChannel`, `Device` |

### API endpoints (уже существуют, использовать как есть)

```
POST /api/zones/{zoneId}/automation-logic-profiles  — сохранить subsystems (с /api/ префиксом!)
POST /api/zones/{zoneId}/calibrate-pump             — сохранить калибровку (использовать skip_run: true)
GET  /api/grow-cycle-wizard/data                    — данные для wizard (рецепты + фазы)
GET  /api/zones/{zoneId}/nodes?with_channels=1      — ДОБАВИТЬ: загрузить каналы для шага калибровки
POST /api/zones/{zoneId}/grow-cycles                — создание цикла (расширяется агентом 2)
```

### Загрузка данных для шага калибровки

Wizard НЕ имеет devices в props. Добавить в `useGrowthCycleWizard.ts`:

```typescript
// Загружать при монтировании wizard или при переходе на шаг calibration
const zoneChannels = ref<DeviceChannel[]>([])

async function fetchZoneChannels() {
  if (zoneChannels.value.length > 0) return  // не перезагружать
  const res = await axios.get(`/api/zones/${zoneId}/nodes?with_channels=1`)
  const allChannels: DeviceChannel[] = res.data.flatMap((node: any) => node.channels ?? [])
  // Фильтр: actuator-каналы с типами насосов дозирования
  const PUMP_ACTUATOR_TYPES = ['ph_acid_pump', 'ph_base_pump', 'ec_npk_pump', 'ec_calcium_pump', 'ec_magnesium_pump', 'ec_micro_pump']
  zoneChannels.value = allChannels.filter(ch =>
    ch.type === 'ACTUATOR' && PUMP_ACTUATOR_TYPES.includes(ch.actuator_type ?? '')
  )
  buildCalibrationEntries(zoneChannels.value)
}
```

Вызывать `fetchZoneChannels()` при переходе на шаг `calibration` (watch currentStep).

## Ожидаемый результат (агент 1)

### Индикатор шагов (исправить)

Заменить текущий flex-row step indicator на компактный вариант. Например:

```html
<!-- Вместо flex-row с v-for (переполняется на 6+ шагах): -->
<div class="flex items-center justify-center gap-1.5">
  <template v-for="(step, i) in steps" :key="step.key">
    <div
      class="w-2.5 h-2.5 rounded-full transition-colors"
      :class="i < currentStep ? 'bg-primary' : i === currentStep ? 'bg-primary ring-2 ring-primary/30' : 'bg-gray-300'"
    />
  </template>
</div>
<p class="text-center text-sm text-gray-500 mt-1">
  {{ steps[currentStep]?.label }} ({{ currentStep + 1 }} / {{ steps.length }})
</p>
```

### Шаг 3 "Логика и автоматика" (inline в GrowthCycleWizard.vue)

Секции внутри одного шага (без дополнительных вложенных шагов):

#### 0. Период цикла (перенести из старого шага params)

- `startedAt` (date, по умолчанию сегодня) — дата начала цикла
- `expectedHarvestAt` (date, nullable) — ожидаемая дата сбора

**ВАЖНО:** `startedAt` и `expectedHarvestAt` уже есть в `form.value` и в `saveDraft`/`loadDraft`. Просто перенести их отображение с шага params на шаг logic (шаг params удаляется, его поля распределяются по logic).

#### 1. Питательный раствор (pH + EC)

- `ph_target` (число, 4–9, шаг 0.1), `ph_min`, `ph_max`
- `ec_target` (число, 0–10, шаг 0.01), `ec_min`, `ec_max`
- Предзаполнить из первой фазы выбранного рецепта: `recipe.phases[0].ph_target` и т.д.
- Показывать badge "из рецепта" если значение не изменено пользователем (`_recipeLoaded = true`)

#### 2. Система полива

- `systemType`: `drip` | `substrate_trays` | `nft` (select)
  - pre-fill из `recipe.phases[0].irrigation_mode`
- `tanksCount`: **только для отображения** (drip/substrate → 2, nft → **0**), поле read-only
  - NFT не использует баки-накопители → `tanksCount = 0`
- `intervalMinutes` (5–1440)
- `durationSeconds` (10–3600)
- `cleanTankFillL`, `nutrientTankTargetL`, `irrigationBatchL` (показывать только при `tanksCount === 2`)
- Предзаполнить из `recipe.phases[0].irrigation_interval_sec / 60`, `duration_sec`

#### 3. Климат (collapsible, toggle)

- Toggle `climateEnabled`
- Если включён: `dayTemp`, `nightTemp` (°C), `dayHumidity`, `nightHumidity` (%)
- Предзаполнить из `recipe.phases[0].temp_air_target`, `humidity_target`

#### 4. Освещение (collapsible, toggle)

- Toggle `lightingEnabled`
- Если включён: `hoursOn` (часов, 1–24), `scheduleStart` (HH:MM), `scheduleEnd` (HH:MM)
- Предзаполнить из `recipe.phases[0].lighting_photoperiod_hours`, `lighting_start_time`

### Шаг 4 "Калибровка насосов" (inline в GrowthCycleWizard.vue)

- Показывать только каналы с actuator_type в списке: `['ph_acid_pump', 'ph_base_pump', 'ec_npk_pump', 'ec_calcium_pump', 'ec_magnesium_pump', 'ec_micro_pump']`
- Для каждого канала строка: иконка компонента + название + поле `ml_per_sec` (шаг 0.01)
- Дефолтные значения `ml_per_sec` если не задано:
  ```
  ph_acid_pump / ph_down: 0.5
  ph_base_pump / ph_up:   0.5
  ec_npk_pump:            1.0
  ec_calcium_pump:        1.0
  ec_magnesium_pump:      0.8
  ec_micro_pump:          0.8
  ```
- Кнопка "Пропустить шаг" — разрешено пропустить, но показывать предупреждение что EC не будет корректироваться
- Если каналы не загружены (загрузка) — показывать спиннер
- Если нет каналов — показать сообщение "Насосы не найдены, настройте привязку нод"

### Расширение `useGrowthCycleWizard.ts`

#### Шаги (обновить массив)

```typescript
const steps = [
  { key: 'zone',        label: 'Зона' },
  { key: 'plant',       label: 'Растение' },
  { key: 'recipe',      label: 'Рецепт' },
  { key: 'logic',       label: 'Логика' },
  { key: 'calibration', label: 'Насосы' },
  { key: 'confirm',     label: 'Запуск' },
]
```

#### Новые поля в form

```typescript
// form.logic
logic: {
  ph_target: number; ph_min: number; ph_max: number
  ec_target: number; ec_min: number; ec_max: number
  systemType: 'drip' | 'substrate_trays' | 'nft'
  tanksCount: number                    // computed из systemType, не редактируется напрямую
  intervalMinutes: number
  durationSeconds: number
  cleanTankFillL: number
  nutrientTankTargetL: number
  irrigationBatchL: number
  climateEnabled: boolean
  dayTemp: number; nightTemp: number
  dayHumidity: number; nightHumidity: number
  lightingEnabled: boolean
  hoursOn: number
  scheduleStart: string; scheduleEnd: string  // HH:MM
  _recipeLoaded: boolean               // внутренний флаг для badge "из рецепта"
}

// form.calibrations
calibrations: Array<{
  node_channel_id: number
  component: PumpCalibrationComponent
  channel_label: string
  ml_per_sec: number
  skip: boolean
}>
calibrationSkipped: boolean             // пропустить весь шаг
```

#### tanksCount — computed

```typescript
// Добавить computed (НЕ хранить в form, только читать)
const tanksCount = computed(() => {
  if (form.value.logic.systemType === 'nft') return 0
  return 2  // drip, substrate_trays
})
```

#### Предзаполнение формы из рецепта

Добавить функцию `fillLogicFromRecipePhase(phase)`:
```typescript
function fillLogicFromRecipePhase(phase: RecipePhase) {
  form.value.logic.ph_target = phase.ph_target ?? 5.8
  form.value.logic.ph_min    = phase.ph_min    ?? 5.6
  form.value.logic.ph_max    = phase.ph_max    ?? 6.0
  form.value.logic.ec_target = phase.ec_target ?? 1.2
  form.value.logic.ec_min    = phase.ec_min    ?? 1.0
  form.value.logic.ec_max    = phase.ec_max    ?? 1.4
  form.value.logic.systemType = phase.irrigation_mode ?? 'drip'
  form.value.logic.intervalMinutes  = Math.round((phase.irrigation_interval_sec ?? 1800) / 60)
  form.value.logic.durationSeconds  = phase.irrigation_duration_sec ?? 120
  form.value.logic.dayTemp    = phase.temp_air_target ?? 23
  form.value.logic.nightTemp  = (phase.temp_air_target ?? 23) - 3
  form.value.logic.dayHumidity   = phase.humidity_target ?? 62
  form.value.logic.nightHumidity = (phase.humidity_target ?? 62) + 8
  form.value.logic.hoursOn    = phase.lighting_photoperiod_hours ?? 16
  form.value.logic.scheduleStart = phase.lighting_start_time ?? '06:00'
  form.value.logic._recipeLoaded = true
}
```

Вызывать при каждой смене `form.value.recipeRevisionId`.

#### canProceed — добавить case для новых шагов

```typescript
// Добавить в switch внутри canProceed computed:
case 3: // logic
  return form.value.logic.ph_target >= 4
    && form.value.logic.ph_target <= 9
    && form.value.logic.ph_min < form.value.logic.ph_max
    && form.value.logic.ec_target >= 0
    && form.value.logic.intervalMinutes >= 5
    && form.value.logic.durationSeconds >= 10

case 4: // calibration
  return true  // всегда можно продолжить (skip разрешён)
```

#### saveDraft / loadDraft — расширить

```typescript
// В saveDraft(): добавить сохранение новых полей
function saveDraft() {
  localStorage.setItem(DRAFT_KEY, JSON.stringify({
    // существующие поля (dates и т.д.):
    startedAt: form.value.startedAt,
    expectedHarvestAt: form.value.expectedHarvestAt,
    // новые:
    logic: form.value.logic,
    calibrationSkipped: form.value.calibrationSkipped,
    // калибровки НЕ сохранять в draft (зависят от живых каналов)
  }))
}

// В loadDraft(): восстанавливать logic и calibrationSkipped
```

#### reset() — добавить новые поля

```typescript
// В reset(): добавить обнуление новых полей
form.value.logic = {
  ph_target: 5.8, ph_min: 5.6, ph_max: 6.0,
  ec_target: 1.2, ec_min: 1.0, ec_max: 1.4,
  systemType: 'drip',
  intervalMinutes: 30, durationSeconds: 120,
  cleanTankFillL: 20, nutrientTankTargetL: 15, irrigationBatchL: 2,
  climateEnabled: false,
  dayTemp: 23, nightTemp: 20, dayHumidity: 65, nightHumidity: 70,
  lightingEnabled: false,
  hoursOn: 16, scheduleStart: '06:00', scheduleEnd: '22:00',
  _recipeLoaded: false,
}
form.value.calibrations = []
form.value.calibrationSkipped = false
```

#### Расширение `onSubmit()` — с обработкой ошибок

```typescript
async function onSubmit() {
  isSubmitting.value = true
  submitError.value = null

  let cycleId: number | null = null

  try {
    // 1. Создать grow cycle (расширенный payload)
    const cycleResponse = await axios.post(`/api/zones/${zoneId}/grow-cycles`, {
      ...existingPayload,
      phase_overrides: {
        ph_target: form.value.logic.ph_target,
        ph_min:    form.value.logic.ph_min,
        ph_max:    form.value.logic.ph_max,
        ec_target: form.value.logic.ec_target,
        ec_min:    form.value.logic.ec_min,
        ec_max:    form.value.logic.ec_max,
      },
    })
    cycleId = cycleResponse.data?.id

    // 2. Сохранить automation logic profile (не блокирующий для цикла)
    const subsystems = buildLogicSubsystems(form.value.logic)
    await axios.post(`/api/zones/${zoneId}/automation-logic-profiles`, {
      mode: 'setup',
      activate: true,
      subsystems,
    })
  } catch (err) {
    // Если цикл создан но profile упал — сообщить пользователю,
    // цикл уже активен и можно настроить profile через ZoneAutomationEditWizard
    if (cycleId !== null) {
      submitError.value = 'Цикл создан, но не удалось сохранить профиль автоматики. Настройте его в разделе автоматики зоны.'
    } else {
      submitError.value = 'Ошибка создания цикла: ' + (err as any)?.message
    }
    isSubmitting.value = false
    return
  }

  // 3. Сохранить калибровки насосов (некритичные, не останавливают при ошибке)
  if (!form.value.calibrationSkipped) {
    const activeCalibrations = form.value.calibrations.filter(c => !c.skip && c.ml_per_sec > 0)
    const calibrationErrors: string[] = []
    await Promise.allSettled(activeCalibrations.map(c =>
      axios.post(`/api/zones/${zoneId}/calibrate-pump`, {
        node_channel_id: c.node_channel_id,
        component: c.component,
        // При skip_run=true фактический прогон не нужен; ml_per_sec задаётся напрямую
        // Проверить: если API calibrate-pump принимает ml_per_sec напрямую — передать его,
        // иначе: actual_ml = c.ml_per_sec * duration_sec, duration_sec = 1 (нормировать к 1 сек)
        actual_ml: c.ml_per_sec,   // actual_ml при duration_sec=1 = ml_per_sec
        duration_sec: 1,
        skip_run: true,
      }).catch(e => {
        calibrationErrors.push(c.channel_label)
      })
    ))
    if (calibrationErrors.length > 0) {
      // Некритичная ошибка — сообщить но не блокировать завершение
      console.warn('Не удалось сохранить калибровки:', calibrationErrors)
    }
  }

  isSubmitting.value = false
  // Закрыть wizard / перейти к зоне
  emit('completed', { cycleId })
}
```

**ВАЖНО по `actual_ml`:** Уточнить у бэкенда контракт `calibrate-pump`. Если endpoint хранит `actual_ml / duration_sec = ml_per_sec`, то при `duration_sec=1` → `actual_ml=ml_per_sec`. Если endpoint принимает `ml_per_sec` напрямую — использовать поле `ml_per_sec` без пересчёта. Проверить в `usePumpCalibration.ts` как делается сохранение там.

#### Функция `buildLogicSubsystems(logic)`

Адаптировать из `zoneAutomationPayloadBuilders.ts:buildGrowthCycleConfigPayload()`.
**Скопировать `two_tank_commands` блок из `buildGrowthCycleConfigPayload` без изменений** — он содержит команды клапанов/насосов которые hard-coded в AE и менять их нельзя.

```typescript
function buildLogicSubsystems(logic: WizardLogicForm) {
  const isTwoTank = tanksCount.value === 2

  // two_tank_commands — скопировать ТОЧНО из buildGrowthCycleConfigPayload
  // (valve_clean_fill, valve_clean_supply, valve_nutrient_fill, nutrient_pump, etc.)
  const TWO_TANK_COMMANDS = isTwoTank
    ? buildGrowthCycleConfigPayload(/* адаптировать параметры */).diagnostics?.execution?.two_tank_commands
    : undefined

  return {
    ph: { enabled: true },
    ec: { enabled: true },
    irrigation: {
      enabled: true,
      execution: {
        interval_minutes: logic.intervalMinutes,
        duration_seconds: logic.durationSeconds,
        system_type: logic.systemType,
        tanks_count: tanksCount.value,
        ...(isTwoTank ? {
          clean_tank_fill_l: logic.cleanTankFillL,
          nutrient_tank_target_l: logic.nutrientTankTargetL,
          irrigation_batch_l: logic.irrigationBatchL,
        } : {}),
        valve_switching_enabled: true,
        correction_during_irrigation: true,
        correction_node: {
          target_ph: logic.ph_target,
          target_ec: logic.ec_target,
          sensors_location: 'correction_node',
        },
        topology: isTwoTank ? 'two_tank_drip_substrate_trays' : 'three_tank_drip',
        ...(isTwoTank ? { two_tank_commands: TWO_TANK_COMMANDS } : {}),
      },
    },
    diagnostics: {
      enabled: true,
      execution: {
        interval_sec: 900,
        workflow: 'startup',
        target_ph: logic.ph_target,    // ← ВАЖНО: передавать сюда для two_tank_runtime_config!
        target_ec: logic.ec_target,    // ← ВАЖНО: передавать сюда для two_tank_runtime_config!
        topology: isTwoTank ? 'two_tank_drip_substrate_trays' : 'three_tank_drip',
        startup: { /* стандартные значения из buildGrowthCycleConfigPayload */ },
        ...(isTwoTank ? { two_tank_commands: TWO_TANK_COMMANDS } : {}),
      },
    },
    climate: {
      enabled: logic.climateEnabled,
      execution: logic.climateEnabled ? {
        interval_sec: 300,
        temperature: { day: logic.dayTemp, night: logic.nightTemp },
        humidity: { day: logic.dayHumidity, night: logic.nightHumidity },
      } : {},
    },
    lighting: {
      enabled: logic.lightingEnabled,
      execution: logic.lightingEnabled ? {
        interval_sec: 1800,
        photoperiod: { hours_on: logic.hoursOn, hours_off: 24 - logic.hoursOn },
        schedule: [{ start: logic.scheduleStart, end: logic.scheduleEnd }],
      } : {},
    },
  }
}
```

### Валидация шага "Логика"

```typescript
// в validateStep() или canProceed computed:
if (form.value.logic.ph_target < 4 || form.value.logic.ph_target > 9) return false
if (form.value.logic.ph_min >= form.value.logic.ph_max) return false
if (form.value.logic.ec_target < 0 || form.value.logic.ec_target > 30) return false
if (form.value.logic.intervalMinutes < 5) return false
if (form.value.logic.durationSeconds < 10) return false
if (form.value.logic.climateEnabled) {
  if (form.value.logic.dayTemp < 10 || form.value.logic.dayTemp > 40) return false
}
```

## Ограничения (агент 1)

- **Не трогать** ZoneAutomationEditWizard.vue — он остаётся для редактирования после запуска
- **Не изменять** существующий API контракт `/api/zones/{id}/grow-cycles` (только добавлять поля)
- **Не создавать** отдельные файлы компонентов для шагов — всё inline в GrowthCycleWizard.vue
- Использовать CSS классы `input-field`, `input-select` (стандарт проекта)
- Типизация строгая (TypeScript strict)
- После изменений: `npm run typecheck && npm run lint`

## Критерии приёмки (агент 1)

- [ ] GrowthCycleWizard показывает 6 шагов (zone/plant/recipe/logic/calibration/confirm)
- [ ] Step indicator работает корректно на 6 шагах (dots или "N из 6")
- [ ] Шаг "Логика" содержит поля дат (`startedAt`, `expectedHarvestAt`)
- [ ] Шаг "Логика" предзаполняется данными из `recipe.phases[0]`
- [ ] Изменённые поля показывают badge "переопределено" (через `_recipeLoaded` флаг)
- [ ] `climateEnabled=false` скрывает поля климата; `lightingEnabled=false` скрывает поля света
- [ ] NFT system type → `tanksCount=0`, скрывает поля баков
- [ ] Шаг "Калибровка" загружает каналы через `GET /api/zones/{id}/nodes?with_channels=1`
- [ ] Можно пропустить шаг "Калибровка" с предупреждением
- [ ] `onSubmit()` выполняет 3 шага с обработкой ошибок: создать цикл → сохранить profile → сохранить калибровки
- [ ] При ошибке profile (шаг 2) пользователь видит сообщение, цикл при этом уже создан
- [ ] `saveDraft` сохраняет `logic` и `calibrationSkipped`; `reset()` обнуляет все новые поля
- [ ] `canProceed` корректно работает для шагов 3 и 4
- [ ] `npm run typecheck` — без ошибок
- [ ] `npm run lint` — без ошибок

---

---

# АГЕНТ 2: Backend — Laravel API + Python AE fixes

## Задача агента 2

1. Расширить Laravel API создания grow cycle (`phase_overrides` + `irrigationBatchL`)
2. Исправить два бага в Python automation-engine

## Текущая ситуация (агент 2)

**Баг 1 (Python):** `executor/two_tank_runtime_config.py` — функция `resolve_two_tank_targets()` пытается читать `target_ph`/`target_ec` из `payload["config"]["execution"]`, но эти поля не передаются при enqueue. Fallback → defaults ph=5.80, ec=1.60. WARNING в логах каждые 60–90 сек.

**Баг 2 (Python):** `executor/workflow_phase_update.py` — при попытке перейти в текущую фазу (tank_recirc → tank_recirc) выбрасывается WARNING "invalid workflow phase transition ... (ignored)". Засоряет логи, transition должен быть no-op без WARNING.

**Баг 3 (Laravel):** `POST /api/zones/{zoneId}/grow-cycles` не принимает `phase_overrides` — нельзя переопределить ph_target/ec_target из wizard.

## Входные данные (агент 2)

### Python файлы для исправления

```
backend/services/automation-engine/executor/two_tank_runtime_config.py
backend/services/automation-engine/executor/workflow_phase_update.py
```

### Python контекст для бага 1

**Где читаются targets в two_tank:**
```python
# executor/two_tank_runtime_config.py
def resolve_two_tank_targets(payload: dict, execution_config: dict) -> dict:
    target_ph = (
        payload.get("target_ph")
        or execution_config.get("target_ph")
        or payload.get("config", {}).get("execution", {}).get("target_ph")
    )
    # ... если None → WARNING + default 5.80
```

**Где доступны реальные targets:**
В executor context при каждом вызове executor есть `targets` dict — это effective_targets зоны, включающий `targets["ph"]["target"]` и `targets["ec"]["target"]` из grow_cycle_phases.
В `executor/executor_constants.py` и `executor/task_context.py` — context содержит `zone_targets`.

**Где вызывается resolve_two_tank_targets:**
В `executor/two_tank_phase_starters_startup.py` (и recovery/prepare аналогах) при формировании payload для следующего enqueue-задания.

**Рекомендуемый фикс** — передавать zone_targets в функцию:
```python
def resolve_two_tank_targets(
    payload: dict,
    execution_config: dict,
    zone_targets: Optional[dict] = None
) -> dict:
    # Priority: payload > execution_config > zone effective targets > hardcoded default
    target_ph = (
        payload.get("target_ph")
        or execution_config.get("target_ph")
        or (zone_targets or {}).get("ph", {}).get("target")
    )
    target_ec = (
        payload.get("target_ec")
        or execution_config.get("target_ec")
        or (zone_targets or {}).get("ec", {}).get("target")
    )
    # Логировать WARNING ТОЛЬКО если использован жёстко-заданный default (не zone_targets)
    if target_ph is None:
        logger.warning("Zone target_ph not found, using default 5.80")
        target_ph = 5.80
    if target_ec is None:
        logger.warning("Zone target_ec not found, using default 1.60")
        target_ec = 1.60
    return {"target_ph": target_ph, "target_ec": target_ec}
```

Найти все вызовы `resolve_two_tank_targets` и добавить передачу `zone_targets` из context.

### Python контекст для бага 2

```python
# executor/workflow_phase_update.py — найти блок проверки transition
# Сейчас:
if current_phase == new_phase:
    logger.warning("Zone %s: invalid workflow phase transition %s -> %s (ignored)", ...)
    return False

# Фикс: сменить WARNING на DEBUG
    logger.debug("Zone %s: workflow phase already at %s, no transition needed", zone_id, current_phase)
    return True  # no-op, не ошибка
```

### Laravel файлы для изменения

```
backend/laravel/app/Http/Controllers/GrowCycleWizardController.php
# или (проверить какой именно обрабатывает POST /api/zones/{id}/grow-cycles):
backend/laravel/app/Http/Controllers/GrowCycleController.php
backend/laravel/app/Http/Requests/CreateGrowCycleRequest.php  (если существует)
```

### Laravel контекст

**Найти:** в `routes/web.php` или `routes/api.php` — маршрут `POST /api/zones/{zone}/grow-cycles`.

**Текущий payload:**
```json
{
  "recipe_revision_id": 123,
  "plant_id": 5,
  "planting_at": "2026-03-04",
  "start_immediately": true,
  "irrigation": {
    "system_type": "drip",
    "interval_minutes": 30,
    "duration_seconds": 120,
    "clean_tank_fill_l": 20,
    "nutrient_tank_target_l": 15
  }
}
```

**Расширить** валидацию — добавить `phase_overrides` и `irrigation.irrigation_batch_l`:
```php
// phase_overrides — переопределение первой фазы цикла
'phase_overrides' => ['nullable', 'array'],
'phase_overrides.ph_target' => ['nullable', 'numeric', 'between:0,14'],
'phase_overrides.ph_min'    => ['nullable', 'numeric', 'between:0,14'],
'phase_overrides.ph_max'    => ['nullable', 'numeric', 'between:0,14'],
'phase_overrides.ec_target' => ['nullable', 'numeric', 'between:0,30'],
'phase_overrides.ec_min'    => ['nullable', 'numeric', 'between:0,30'],
'phase_overrides.ec_max'    => ['nullable', 'numeric', 'between:0,30'],

// irrigation — добавить поле
'irrigation.irrigation_batch_l' => ['nullable', 'numeric', 'min:0.1', 'max:100'],
```

**После создания grow_cycle и фаз** — применить overrides к первой фазе:
```php
if ($request->filled('phase_overrides')) {
    $overrides = array_filter($request->input('phase_overrides'), fn($v) => $v !== null);
    if (!empty($overrides)) {
        $growCycle->phases()->orderBy('phase_index')->first()?->update($overrides);
    }
}
```

**Важно:** не менять существующую логику создания фаз из рецепта, только ПОСЛЕ неё применять overrides.

## Ожидаемый результат (агент 2)

### Python: two_tank_runtime_config.py

- `resolve_two_tank_targets()` принимает дополнительный параметр `zone_targets: Optional[dict] = None`
- Читает ph/ec targets из zone_targets если не переданы в payload/config
- WARNING выводится ТОЛЬКО когда цель не найдена нигде (используется абсолютный default)
- Все вызовы функции обновлены с передачей `zone_targets`
- После правки: `pytest backend/services/automation-engine/ -v` — без регрессий

### Python: workflow_phase_update.py

- Переход фаза → та же фаза: уровень лога `DEBUG`, не `WARNING`; возвращает `True` (не ошибка)
- Сообщение информативное: "workflow phase already at X, skipping transition"

### Laravel: GrowCycle creation

- `POST /api/zones/{id}/grow-cycles` принимает `phase_overrides` (nullable)
- `POST /api/zones/{id}/grow-cycles` принимает `irrigation.irrigation_batch_l` (nullable)
- При наличии `phase_overrides` — первая фаза цикла обновляется этими значениями
- Existing behavior полностью сохраняется если `phase_overrides` не передан
- После изменений: `docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test` — без регрессий

## Ограничения (агент 2)

- **Не менять** MQTT протокол, схему БД (только через миграции Laravel — в данном случае миграции не нужны)
- **Не менять** публичный API контракт (только добавлять опциональные поля)
- Python код: PEP 8, type hints обязательны
- PHP код: следовать Laravel/Pint стандарту, запустить `make lint` после изменений

## Критерии приёмки (агент 2)

- [ ] В логах AE нет WARNING "both target_ph and target_ec resolved to defaults" когда grow_cycle_phase имеет ph_target/ec_target
- [ ] В логах AE нет WARNING "invalid workflow phase transition X -> X"
- [ ] `POST /api/zones/{id}/grow-cycles` с `phase_overrides.ph_target=6.0` обновляет первую фазу
- [ ] `POST /api/zones/{id}/grow-cycles` с `irrigation.irrigation_batch_l=2.0` принимается без ошибки
- [ ] `POST /api/zones/{id}/grow-cycles` без `phase_overrides` — поведение не изменилось
- [ ] `php artisan test` — без регрессий
- [ ] `pytest backend/services/automation-engine/ -v` — без регрессий
- [ ] `make lint` — без ошибок

---

## Порядок выполнения (параллельно)

```
Агент 1 (Frontend)              Агент 2 (Backend/Python)
──────────────────────────      ──────────────────────────
Step indicator → dots           workflow_phase_update.py fix
Step 3 "Логика" inline          two_tank_runtime_config.py fix
Step 4 "Калибровка" inline      Laravel: phase_overrides + irrigationBatchL
useGrowthCycleWizard.ts extend
  (form, canProceed, reset,
   saveDraft, fetchChannels,
   onSubmit с rollback)
```

Агенты независимы: агент 1 не ждёт агента 2 (submit сделан graceful — если backend ещё не принял phase_overrides, wizard просто не передаёт их, фаза создаётся из рецепта без override).

## Связь между агентами

Агент 1 в `onSubmit()` передаёт `phase_overrides` в payload — агент 2 добавляет их приём на backend. Если агент 2 ещё не завершил — `phase_overrides` в payload игнорируются Laravel (неизвестное поле), фаза создаётся из рецепта без override. Это приемлемо для промежуточного состояния.
