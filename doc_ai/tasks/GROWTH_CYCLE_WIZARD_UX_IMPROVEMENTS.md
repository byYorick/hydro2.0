# Улучшение пайплайна GrowthCycleWizard: загрузка профиля, UX и стабильность черновика

Compatible-With: Frontend >=3.0, Backend >=3.0

---

## Контекст

Frontend — Vue 3 + TypeScript + Inertia.js, расположен в `backend/laravel/resources/js/`.

Пайплайн: `Setup Wizard (/setup/wizard)` → `GrowthCycleWizard` (модал запуска цикла).

После рефакторинга (ветка `ae3`) `GrowthCycleWizard` использует реальные формы
`ClimateFormState` / `WaterFormState` / `LightingFormState` и `buildGrowthCycleConfigPayload`
вместо упрощённой `WizardLogicForm`. Однако остались три нерешённые проблемы.

**Ключевые файлы:**

| Файл | Роль |
|------|------|
| `resources/js/composables/useGrowthCycleWizard.ts` | Главный composable wizard'а |
| `resources/js/Components/GrowCycle/GrowthCycleWizard.vue` | Шаблон wizard'а |
| `resources/js/Pages/Zones/Tabs/ZoneAutomationEditWizard.vue` | Вложенный редактор автоматики (props: `open`, `climateForm`, `waterForm`, `lightingForm`, `isApplying`, `isSystemTypeLocked`) |
| `resources/js/composables/zoneAutomationTypes.ts` | Типы: `ClimateFormState`, `WaterFormState`, `LightingFormState` |
| `resources/js/composables/zoneAutomationPayloadBuilders.ts` | `buildGrowthCycleConfigPayload(forms)` — канонический builder |

**Документация:**
- `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md`
- `doc_ai/07_FRONTEND/FRONTEND_TESTING.md`

---

## Задачи (выполнять по порядку)

---

### Задача 1 — Загрузка существующего профиля автоматики при открытии wizard'а

#### Текущая ситуация

`useGrowthCycleWizard.ts` инициализирует `climateForm`, `waterForm`, `lightingForm` через
`createDefaultClimateForm()` / `createDefaultWaterForm()` / `createDefaultLightingForm()`.
Если зона уже имеет профиль (сохранённый Setup Wizard'ом или предыдущим запуском),
wizard его игнорирует — пользователь видит дефолтные значения.

#### Цель

При открытии wizard'а (в `initializeWizardState()`) загружать текущий профиль зоны через API
и заполнять три формы из ответа. Если профиль не найден (404) или не выбрана зона — оставлять
дефолты.

#### API

```
GET /api/zones/{zoneId}/automation-logic-profile
```

Ответ (при наличии профиля):
```json
{
  "status": "ok",
  "data": {
    "subsystems": {
      "climate": { "enabled": true, "execution": { "temperature": { "day": 24, "night": 20 }, ... } },
      "irrigation": { "enabled": true, "execution": { "interval_minutes": 30, "duration_seconds": 120, "system_type": "drip", ... } },
      "lighting": { "enabled": false, "execution": {} },
      "diagnostics": { "execution": { "target_ph": 5.8, "target_ec": 1.2, ... } }
    }
  }
}
```

#### Входные данные

- `resources/js/composables/useGrowthCycleWizard.ts` — функция `initializeWizardState()`,
  вызывается при `props.show === true`
- Рядом уже есть `loadWizardData()` — добавить `loadAutomationProfile()` по аналогии

#### Ожидаемый результат

1. Новая функция `loadAutomationProfile(zoneId: number): Promise<void>` в composable.
2. Вызывается в `initializeWizardState()` если `zoneId` определён.
3. Парсит ответ: `subsystems.climate.execution` → `climateForm.value`,
   `subsystems.irrigation.execution` → `waterForm.value`,
   `subsystems.lighting.execution` → `lightingForm.value`,
   `subsystems.diagnostics.execution.target_ph/target_ec` → `waterForm.value.targetPh/targetEc`.
4. При ошибке (404, сеть) — тихо логирует через `logger.warn(...)`, не показывает toast.
5. Профиль загружается ДО `loadDraft()`, чтобы черновик мог перезаписать профиль (черновик приоритетнее).
6. Если `zoneId` ещё не выбран при открытии (пользователь выбирает зону вручную на шаге 0) —
   загружать профиль в `watch(() => form.value.zoneId, ...)` при первом выборе зоны,
   но только если черновик ещё не загружен.

#### Ограничения

- Не трогать `ZoneAutomationEditWizard.vue` и `zoneAutomationPayloadBuilders.ts`.
- Не добавлять отдельный loading state для профиля — использовать существующий `loading.value`.
- Парсинг должен быть graceful: каждое поле проверять на наличие перед присвоением.

#### Критерии приёмки

- [ ] При открытии wizard'а для зоны с профилем, step 3 сразу показывает реальные
  pH/EC/интервал, а не дефолты.
- [ ] При 404 — wizard открывается с дефолтами без ошибок в консоли (только `logger.warn`).
- [ ] Черновик из localStorage, если есть, имеет приоритет над загруженным профилем.
- [ ] TypeScript: `npm run typecheck` без новых ошибок.

---

### Задача 2 — Устранение race condition: черновик перезаписывается syncFormsFromRecipePhase

#### Текущая ситуация

```ts
// useGrowthCycleWizard.ts
watch(selectedRevision, (revision) => {
  const firstPhase = (revision?.phases?.[0] || null) as WizardRecipePhase | null;
  if (firstPhase) {
    syncFormsFromRecipePhase(firstPhase);   // ← перезатирает всё что загрузил loadDraft()
  }
});
```

Порядок при открытии wizard'а:
1. `loadDraft()` восстанавливает `climateForm` / `waterForm` / `lightingForm`
2. `applyInitialData()` восстанавливает `selectedRecipeId`
3. `watch(selectedRecipeId)` → `syncSelectedRecipe()` → `selectedRevision` меняется
4. `watch(selectedRevision)` → `syncFormsFromRecipePhase()` → **перезаписывает черновик**

#### Цель

`syncFormsFromRecipePhase` должна вызываться только при **реальном выборе нового рецепта
пользователем**, но не при восстановлении черновика.

#### Решение

Добавить флаг `const draftWasLoaded = ref(false)`:

```ts
function loadDraft(): void {
  // ... существующий код ...
  if (draft.climateForm || draft.waterForm || draft.lightingForm) {
    draftWasLoaded.value = true;
  }
}

watch(selectedRevision, (revision, prevRevision) => {
  // Не синхронизировать если черновик был загружен (пользователь не менял рецепт вручную)
  if (draftWasLoaded.value) {
    draftWasLoaded.value = false;   // сбросить флаг — следующая смена рецепта сработает
    return;
  }
  const firstPhase = (revision?.phases?.[0] || null) as WizardRecipePhase | null;
  if (firstPhase) {
    syncFormsFromRecipePhase(firstPhase);
  }
});
```

#### Входные данные

- `resources/js/composables/useGrowthCycleWizard.ts` — функции `loadDraft()` и
  `watch(selectedRevision, ...)`

#### Ожидаемый результат

1. Новый `ref<boolean>` `draftWasLoaded` (локальный, не экспортируется).
2. Устанавливается в `true` в `loadDraft()` если хотя бы одна из форм была загружена.
3. В `watch(selectedRevision)` — первый вызов после `loadDraft()` пропускается, флаг сбрасывается.
4. Сброс флага также в `reset()`.

#### Критерии приёмки

- [ ] Открыть wizard с черновиком (pH=6.5). Изменить рецепт — pH должен обновиться из рецепта.
- [ ] Открыть wizard с черновиком (pH=6.5). Не менять рецепт — pH остаётся 6.5.
- [ ] Открыть wizard без черновика. Выбрать рецепт — формы заполняются из рецепта.

---

### Задача 3 — Убрать modal-in-modal: вынести автоматику в отдельный шаг wizard'а

#### Текущая ситуация

Шаг 3 "Логика" содержит карточку-сводку + кнопку "Настроить", открывающую
`ZoneAutomationEditWizard` как **вложенный модал** поверх `GrowthCycleWizard`.

Проблемы:
- На мобильных два вложенных модала перекрываются
- Backdrop и z-index конфликтуют
- Пользователь теряет контекст

#### Цель

Разделить текущий шаг 3 "Логика" на **два inline-шага**:

| Новый номер | Ключ | Содержимое |
|-------------|------|------------|
| 3 | `logic` | Только дата начала + дата сбора (как сейчас) |
| 4 | `automation` | Контент `ZoneAutomationEditWizard` встроен inline (без модала) |
| 5 | `calibration` | Насосы (было 4) |
| 6 | `confirm` | Запуск (было 5) |

#### Входные данные

- `resources/js/Components/GrowCycle/GrowthCycleWizard.vue` — шаблон
- `resources/js/composables/useGrowthCycleWizard.ts` — массив `steps`, `validateStep`
- `resources/js/Pages/Zones/Tabs/ZoneAutomationEditWizard.vue` — **читать только**, не менять

#### Ожидаемый результат

1. В `useGrowthCycleWizard.ts` добавить шаг в массив `steps`:
   ```ts
   const steps: WizardStep[] = [
     { key: "zone",        label: "Зона" },
     { key: "plant",       label: "Растение" },
     { key: "recipe",      label: "Рецепт" },
     { key: "logic",       label: "Период" },
     { key: "automation",  label: "Автоматика" },
     { key: "calibration", label: "Насосы" },
     { key: "confirm",     label: "Запуск" },
   ];
   ```
2. Тип `WizardStepKey` расширить: добавить `"automation"`.
3. В `validateStep` — case 4 (automation) всегда возвращает `true` (валидация уже встроена в компонент).
4. В шаблоне `GrowthCycleWizard.vue`:
   - Step 3 (`logic`) — только блок с датами.
   - Step 4 (`automation`) — три секции из `ZoneAutomationEditWizard` **скопировать как inline**
     (не вставлять компонент целиком — у него свои footer-кнопки).
     Вместо этого в шаг 4 включить:
     - секцию климата (tab 1 из ZoneAutomationEditWizard)
     - секцию воды (tab 2)
     - секцию освещения (tab 3)
     — переключение через те же tab-кнопки, привязанные к `ref<number> automationTab`.
   - Убрать `ZoneAutomationEditWizard` как вложенный модал.
   - Убрать `automationEditOpen` ref.
5. В `useGrowthCycleWizard.ts` убрать `automationEditOpen`, `onAutomationApply`
   (больше не нужны — формы редактируются напрямую).
6. Confirm screen (step 6) — нумерация не меняется по смыслу, только добавляется строка
   "Автоматика: pH X.X, EC Y.Y, система Z".

#### Ограничения

- **Не менять** `ZoneAutomationEditWizard.vue`.
- Верстку секций (климат, вода, свет) брать из `ZoneAutomationEditWizard.vue` как референс,
  но размещать inline в `GrowthCycleWizard.vue`.
- Привязка к `climateForm` / `waterForm` / `lightingForm` — через `v-model.number` / `v-model`
  напрямую (формы уже реактивные в composable).

#### Критерии приёмки

- [ ] В wizard'е 7 шагов вместо 6.
- [ ] Шаг "Автоматика" не открывает никакого дополнительного модала.
- [ ] На шаге "Автоматика" можно переключать табы Климат / Вода / Свет.
- [ ] Изменение pH на шаге "Автоматика" отражается в confirm screen.
- [ ] `npm run typecheck` без ошибок.
- [ ] `npm run test` для `GrowthCycleWizard` не падает (при наличии тестов).

---

### Задача 4 — Переименовать кнопку "Сохранить" → "Применить" в ZoneAutomationEditWizard при отсутствии немедленного сохранения

> **Примечание:** Эта задача актуальна только если Задача 3 не выполняется —
> т.е. если `ZoneAutomationEditWizard` остаётся как вложенный модал.

#### Текущая ситуация

```vue
<!-- ZoneAutomationEditWizard.vue:404-408 -->
<Button :disabled="isApplying" @click="emitApply">
  {{ isApplying ? 'Отправка...' : 'Сохранить' }}
</Button>
```

При вызове из `GrowthCycleWizard` с `isApplying=false`, кнопка говорит "Сохранить",
но реально сохранения в API не происходит — только локальное применение формы.

#### Цель

Добавить prop `applyLabel?: string` в `ZoneAutomationEditWizard.vue`:

```ts
interface Props {
  // ... существующие ...
  applyLabel?: string   // дефолт: 'Сохранить'
}
```

Использование в `GrowthCycleWizard.vue`:
```vue
<ZoneAutomationEditWizard
  apply-label="Применить"
  ...
/>
```

#### Критерии приёмки

- [ ] В `ZoneAutomationTab` (где есть реальное сохранение) кнопка по-прежнему "Сохранить".
- [ ] В `GrowthCycleWizard` кнопка показывает "Применить".
- [ ] `npm run typecheck` без ошибок.

---

## Порядок выполнения

```
Задача 1 (загрузка профиля)
    ↓
Задача 2 (race condition черновика)
    ↓
Задача 3 (убрать modal-in-modal)  ← если выполнена, Задача 4 не нужна
    ↓ (или вместо Задачи 3)
Задача 4 (переименовать кнопку)
```

Задачи 1 и 2 независимы и могут выполняться параллельно.
Задача 3 зависит от Задачи 1 (нужно убедиться что loadAutomationProfile работает до начала
переделки шагов).

---

## Общие ограничения

- Не менять MQTT протокол, Python сервисы, Laravel API.
- Не трогать `zoneAutomationPayloadBuilders.ts` и `zoneAutomationTypes.ts`.
- Все изменения только в `resources/js/` frontend.
- После каждой задачи: `npm run typecheck` и `npm run lint`.
- Стиль кода: Vue 3 Composition API, TypeScript strict, kebab-case для props в шаблонах.
