<template>
  <div class="flex flex-col gap-3.5">
    <PresetSelector
      :water-form="waterForm"
      :can-configure="true"
      :tanks-count="waterForm.tanksCount"
      @update:water-form="onPresetUpdate"
      @preset-applied="$emit('preset-applied', $event)"
      @preset-cleared="$emit('preset-cleared')"
    />

    <SectionLabel>Топология и баки</SectionLabel>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5">
      <Field
        :label="meta('systemType').label"
        required
        :hint="meta('systemType').hint"
      >
        <div
          class="flex items-center h-8 px-3 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] text-sm font-mono text-[var(--text-primary)] gap-1.5"
          :title="meta('systemType').details"
        >
          <Ic
            name="lock"
            class="text-[var(--text-dim)]"
            size="sm"
          />
          {{ waterForm.systemType }}
        </div>
      </Field>
      <Field :label="meta('tanksCount').label" :hint="meta('tanksCount').hint">
        <input
          v-bind="numAttrs"
          :title="meta('tanksCount').details"
          :value="waterForm.tanksCount"
          @input="upd('tanksCount', toInt($event))"
        >
      </Field>
      <Field :label="meta('workingTankL').label" :hint="meta('workingTankL').hint">
        <input
          v-bind="numAttrs"
          :title="meta('workingTankL').details"
          :value="waterForm.workingTankL"
          @input="upd('workingTankL', toNum($event))"
        >
      </Field>
      <Field :label="meta('cleanTankFillL').label" :hint="meta('cleanTankFillL').hint">
        <input
          v-bind="numAttrs"
          :title="meta('cleanTankFillL').details"
          :value="waterForm.cleanTankFillL"
          @input="upd('cleanTankFillL', toNum($event))"
        >
      </Field>
      <Field :label="meta('nutrientTankTargetL').label" :hint="meta('nutrientTankTargetL').hint">
        <input
          v-bind="numAttrs"
          :title="meta('nutrientTankTargetL').details"
          :value="waterForm.nutrientTankTargetL"
          @input="upd('nutrientTankTargetL', toNum($event))"
        >
      </Field>
      <Field :label="meta('irrigationBatchL').label" :hint="meta('irrigationBatchL').hint">
        <input
          v-bind="numAttrs"
          :title="meta('irrigationBatchL').details"
          :value="waterForm.irrigationBatchL"
          @input="upd('irrigationBatchL', toNum($event))"
        >
      </Field>
      <Field :label="meta('mainPumpFlowLpm').label" :hint="meta('mainPumpFlowLpm').hint">
        <input
          v-bind="numAttrs"
          :title="meta('mainPumpFlowLpm').details"
          :value="waterForm.mainPumpFlowLpm"
          @input="upd('mainPumpFlowLpm', toNum($event))"
        >
      </Field>
      <Field :label="meta('cleanWaterFlowLpm').label" :hint="meta('cleanWaterFlowLpm').hint">
        <input
          v-bind="numAttrs"
          :title="meta('cleanWaterFlowLpm').details"
          :value="waterForm.cleanWaterFlowLpm"
          @input="upd('cleanWaterFlowLpm', toNum($event))"
        >
      </Field>
    </div>

    <SectionLabel>Окно наполнения и температура</SectionLabel>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5">
      <Field :label="meta('fillWindowStart').label" :hint="meta('fillWindowStart').hint">
        <input
          v-bind="textAttrs"
          :title="meta('fillWindowStart').details"
          :value="waterForm.fillWindowStart"
          @input="upd('fillWindowStart', toStr($event))"
        >
      </Field>
      <Field :label="meta('fillWindowEnd').label" :hint="meta('fillWindowEnd').hint">
        <input
          v-bind="textAttrs"
          :title="meta('fillWindowEnd').details"
          :value="waterForm.fillWindowEnd"
          @input="upd('fillWindowEnd', toStr($event))"
        >
      </Field>
      <Field :label="meta('fillTemperatureC').label" :hint="meta('fillTemperatureC').hint">
        <input
          v-bind="numAttrs"
          :title="meta('fillTemperatureC').details"
          :value="waterForm.fillTemperatureC"
          @input="upd('fillTemperatureC', toNum($event))"
        >
      </Field>
      <Field :label="meta('cleanTankFullThreshold').label" :hint="meta('cleanTankFullThreshold').hint">
        <input
          v-bind="numAttrs"
          :title="meta('cleanTankFullThreshold').details"
          :value="waterForm.cleanTankFullThreshold"
          @input="upd('cleanTankFullThreshold', toNum($event))"
        >
      </Field>
      <Field :label="meta('refillDurationSeconds').label" :hint="meta('refillDurationSeconds').hint">
        <input
          v-bind="numAttrs"
          :title="meta('refillDurationSeconds').details"
          :value="waterForm.refillDurationSeconds"
          @input="upd('refillDurationSeconds', toInt($event))"
        >
      </Field>
      <Field :label="meta('refillTimeoutSeconds').label" :hint="meta('refillTimeoutSeconds').hint">
        <input
          v-bind="numAttrs"
          :title="meta('refillTimeoutSeconds').details"
          :value="waterForm.refillTimeoutSeconds"
          @input="upd('refillTimeoutSeconds', toInt($event))"
        >
      </Field>
      <Field :label="meta('refillRequiredNodeTypes').label" :hint="meta('refillRequiredNodeTypes').hint">
        <input
          v-bind="textAttrs"
          :title="meta('refillRequiredNodeTypes').details"
          :value="waterForm.refillRequiredNodeTypes"
          placeholder="pump,valve"
          @input="upd('refillRequiredNodeTypes', toStr($event))"
        >
      </Field>
      <Field :label="meta('refillPreferredChannel').label" :hint="meta('refillPreferredChannel').hint">
        <input
          v-bind="textAttrs"
          :title="meta('refillPreferredChannel').details"
          :value="waterForm.refillPreferredChannel"
          @input="upd('refillPreferredChannel', toStr($event))"
        >
      </Field>
    </div>

    <SectionLabel>Диагностика и стартовые таймауты</SectionLabel>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5 items-center">
      <ToggleField
        :model-value="!!waterForm.diagnosticsEnabled"
        :label="meta('diagnosticsEnabled').label"
        :title="meta('diagnosticsEnabled').details"
        @update:model-value="(v) => upd('diagnosticsEnabled', v)"
      />
      <Field :label="meta('diagnosticsIntervalMinutes').label" :hint="meta('diagnosticsIntervalMinutes').hint">
        <input
          v-bind="numAttrs"
          :title="meta('diagnosticsIntervalMinutes').details"
          :value="waterForm.diagnosticsIntervalMinutes"
          @input="upd('diagnosticsIntervalMinutes', toInt($event))"
        >
      </Field>
      <Field :label="meta('diagnosticsWorkflow').label" :hint="meta('diagnosticsWorkflow').hint">
        <Select
          :title="meta('diagnosticsWorkflow').details"
          :model-value="waterForm.diagnosticsWorkflow ?? 'cycle_start'"
          :options="['startup', 'cycle_start', 'diagnostics']"
          mono
          size="sm"
          @update:model-value="(v: string) => upd('diagnosticsWorkflow', v as 'startup' | 'cycle_start' | 'diagnostics')"
        />
      </Field>
      <Field :label="meta('estopDebounceMs').label" :hint="meta('estopDebounceMs').hint">
        <input
          v-bind="numAttrs"
          :title="meta('estopDebounceMs').details"
          :value="waterForm.estopDebounceMs ?? 0"
          @input="upd('estopDebounceMs', toInt($event))"
        >
      </Field>
      <Field :label="meta('startupCleanFillTimeoutSeconds').label" :hint="meta('startupCleanFillTimeoutSeconds').hint">
        <input
          v-bind="numAttrs"
          :title="meta('startupCleanFillTimeoutSeconds').details"
          :value="waterForm.startupCleanFillTimeoutSeconds ?? 0"
          @input="upd('startupCleanFillTimeoutSeconds', toInt($event))"
        >
      </Field>
      <Field :label="meta('startupSolutionFillTimeoutSeconds').label" :hint="meta('startupSolutionFillTimeoutSeconds').hint">
        <input
          v-bind="numAttrs"
          :title="meta('startupSolutionFillTimeoutSeconds').details"
          :value="waterForm.startupSolutionFillTimeoutSeconds ?? 0"
          @input="upd('startupSolutionFillTimeoutSeconds', toInt($event))"
        >
      </Field>
      <Field :label="meta('startupPrepareRecirculationTimeoutSeconds').label" :hint="meta('startupPrepareRecirculationTimeoutSeconds').hint">
        <input
          v-bind="numAttrs"
          :title="meta('startupPrepareRecirculationTimeoutSeconds').details"
          :value="waterForm.startupPrepareRecirculationTimeoutSeconds ?? 0"
          @input="upd('startupPrepareRecirculationTimeoutSeconds', toInt($event))"
        >
      </Field>
      <Field :label="meta('startupCleanFillRetryCycles').label" :hint="meta('startupCleanFillRetryCycles').hint">
        <input
          v-bind="numAttrs"
          :title="meta('startupCleanFillRetryCycles').details"
          :value="waterForm.startupCleanFillRetryCycles ?? 0"
          @input="upd('startupCleanFillRetryCycles', toInt($event))"
        >
      </Field>
      <Field :label="meta('cleanFillMinCheckDelayMs').label" :hint="meta('cleanFillMinCheckDelayMs').hint">
        <input
          v-bind="numAttrs"
          :title="meta('cleanFillMinCheckDelayMs').details"
          :value="waterForm.cleanFillMinCheckDelayMs ?? 0"
          @input="upd('cleanFillMinCheckDelayMs', toInt($event))"
        >
      </Field>
      <Field :label="meta('solutionFillCleanMinCheckDelayMs').label" :hint="meta('solutionFillCleanMinCheckDelayMs').hint">
        <input
          v-bind="numAttrs"
          :title="meta('solutionFillCleanMinCheckDelayMs').details"
          :value="waterForm.solutionFillCleanMinCheckDelayMs ?? 0"
          @input="upd('solutionFillCleanMinCheckDelayMs', toInt($event))"
        >
      </Field>
      <Field :label="meta('solutionFillSolutionMinCheckDelayMs').label" :hint="meta('solutionFillSolutionMinCheckDelayMs').hint">
        <input
          v-bind="numAttrs"
          :title="meta('solutionFillSolutionMinCheckDelayMs').details"
          :value="waterForm.solutionFillSolutionMinCheckDelayMs ?? 0"
          @input="upd('solutionFillSolutionMinCheckDelayMs', toInt($event))"
        >
      </Field>
      <ToggleField
        :model-value="!!waterForm.recirculationStopOnSolutionMin"
        :label="meta('recirculationStopOnSolutionMin').label"
        :title="meta('recirculationStopOnSolutionMin').details"
        @update:model-value="(v) => upd('recirculationStopOnSolutionMin', v)"
      />
      <ToggleField
        :model-value="!!waterForm.stopOnSolutionMin"
        :label="meta('stopOnSolutionMin').label"
        :title="meta('stopOnSolutionMin').details"
        @update:model-value="(v) => upd('stopOnSolutionMin', v)"
      />
      <ToggleField
        :model-value="!!waterForm.enableDrainControl"
        :label="meta('enableDrainControl').label"
        :title="meta('enableDrainControl').details"
        @update:model-value="(v) => upd('enableDrainControl', v)"
      />
      <Field :label="meta('drainTargetPercent').label" :hint="meta('drainTargetPercent').hint">
        <input
          v-bind="numAttrs"
          :title="meta('drainTargetPercent').details"
          :value="waterForm.drainTargetPercent"
          @input="upd('drainTargetPercent', toNum($event))"
        >
      </Field>
      <ToggleField
        :model-value="!!waterForm.valveSwitching"
        :label="meta('valveSwitching').label"
        :title="meta('valveSwitching').details"
        @update:model-value="(v) => upd('valveSwitching', v)"
      />
    </div>

    <SectionLabel>Смена раствора</SectionLabel>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5 items-center">
      <ToggleField
        :model-value="!!waterForm.solutionChangeEnabled"
        :label="meta('solutionChangeEnabled').label"
        :title="meta('solutionChangeEnabled').details"
        @update:model-value="(v) => upd('solutionChangeEnabled', v)"
      />
      <Field :label="meta('solutionChangeIntervalMinutes').label" :hint="meta('solutionChangeIntervalMinutes').hint">
        <input
          v-bind="numAttrs"
          :title="meta('solutionChangeIntervalMinutes').details"
          :value="waterForm.solutionChangeIntervalMinutes"
          @input="upd('solutionChangeIntervalMinutes', toInt($event))"
        >
      </Field>
      <Field :label="meta('solutionChangeDurationSeconds').label" :hint="meta('solutionChangeDurationSeconds').hint">
        <input
          v-bind="numAttrs"
          :title="meta('solutionChangeDurationSeconds').details"
          :value="waterForm.solutionChangeDurationSeconds"
          @input="upd('solutionChangeDurationSeconds', toInt($event))"
        >
      </Field>
      <Field
        :label="meta('manualIrrigationSeconds').label"
        :hint="meta('manualIrrigationSeconds').hint"
      >
        <input
          v-bind="numAttrs"
          :title="meta('manualIrrigationSeconds').details"
          :value="waterForm.manualIrrigationSeconds"
          @input="upd('manualIrrigationSeconds', toInt($event))"
        >
      </Field>
    </div>

    <Hint :show="showHints">
      Полный набор полей <span class="font-mono">waterFormSchema</span>.
      AE3 валидирует значения через zod и пишет в
      <span class="font-mono">automation_configs/zone/{'{id}'}/zone.water</span>.
    </Hint>
  </div>
</template>

<script setup lang="ts">
import { h } from 'vue'
import PresetSelector from '@/Components/AutomationForms/PresetSelector.vue'
import { Field, Select, Hint, ToggleField } from '@/Components/Shared/Primitives'
import Ic from '@/Components/Icons/Ic.vue'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'
import { createMetaResolver, toInt, toNum, toStr, type FieldMeta } from './sharedFormUtils'

const props = defineProps<{
  waterForm: WaterFormState
}>()

const emit = defineEmits<{
  (e: 'update:waterForm', next: WaterFormState): void
  (e: 'preset-applied', preset: unknown): void
  (e: 'preset-cleared'): void
}>()

const { showHints } = useLaunchPreferences()

const inputCls =
  'block w-full h-8 rounded-lg border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] px-2.5 text-sm font-mono outline-none transition-[border-color,box-shadow,background-color] duration-150 focus:border-brand focus:ring-2 focus:ring-brand-soft focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand-soft'

const numAttrs = { class: inputCls, type: 'number' }
const textAttrs = { class: inputCls, type: 'text' }

const WATER_FIELD_META: Partial<Record<keyof WaterFormState, FieldMeta>> = {
  systemType: { label: 'Тип гидросистемы', hint: 'Берётся из активного рецепта', details: 'Определяет сценарий работы водного контура: набор этапов запуска, fill/recirculation и проверки.' },
  tanksCount: { label: 'Число баков', hint: 'Допустимо 2-3', details: 'Определяет топологию контура и набор обязательных шагов при старте.' },
  workingTankL: { label: 'Рабочий объём бака, л', hint: 'База для расчётов доз', details: 'Объём раствора в рабочем баке; влияет на расчёт дозировок и динамику коррекций pH/EC.' },
  cleanTankFillL: { label: 'Наполнение чистого бака, л', hint: 'Стартовый объём чистой воды', details: 'Сколько воды набираем на этапе первичного заполнения перед приготовлением раствора.' },
  nutrientTankTargetL: { label: 'Целевой объём питательного бака, л', hint: 'Цель после приготовления раствора', details: 'Контрольный объём, к которому доводится питательный бак в startup workflow.' },
  irrigationBatchL: { label: 'Объём одного полива, л', hint: 'Разовая порция полива', details: 'Объём раствора на один поливной батч; влияет на частоту циклов и длительность включения помпы.' },
  mainPumpFlowLpm: { label: 'Производительность основной помпы, л/мин', hint: 'Используется в таймингах', details: 'Нужна для расчёта времени операций fill/recirculation/drain и контроля таймаутов.' },
  cleanWaterFlowLpm: { label: 'Поток чистой воды, л/мин', hint: 'Скорость долива', details: 'Определяет длительность шагов набора чистой воды и проверок переполнения.' },
  fillWindowStart: { label: 'Окно наполнения: начало', hint: 'Формат HH:MM', details: 'Время начала, после которого разрешены операции наполнения баков.' },
  fillWindowEnd: { label: 'Окно наполнения: конец', hint: 'Формат HH:MM', details: 'Время окончания разрешённого окна наполнения; вне окна fill блокируется.' },
  fillTemperatureC: { label: 'Температура воды при наполнении, °C', hint: 'Целевая температура', details: 'Референс температуры воды при fill; влияет на стабильность раствора и стартовые условия.' },
  cleanTankFullThreshold: { label: 'Порог «бак полный», %', hint: 'Порог срабатывания уровня', details: 'Значение уровня, при котором система считает бак заполненным и завершает fill этап.' },
  refillDurationSeconds: { label: 'Макс. длительность долива, сек', hint: 'Ограничение одной операции', details: 'Ограничивает время одной попытки долива для защиты от зависших операций.' },
  refillTimeoutSeconds: { label: 'Таймаут долива, сек', hint: 'Hard timeout ожидания', details: 'Предельное время ожидания подтверждения долива, после которого шаг завершается с ошибкой.' },
  refillRequiredNodeTypes: { label: 'Обязательные типы устройств для долива', hint: 'CSV, напр. pump,valve', details: 'Список типов узлов, которые должны быть доступны, чтобы refill был разрешён.' },
  refillPreferredChannel: { label: 'Предпочтительный канал долива', hint: 'Канал актуатора', details: 'Приоритетный канал управления доливом, если доступно несколько каналов.' },
  diagnosticsEnabled: { label: 'Включить диагностику', hint: 'Флаг сценария диагностики', details: 'Разрешает диагностический workflow и проверки состояния контура.' },
  diagnosticsIntervalMinutes: { label: 'Интервал диагностики, мин', hint: 'Период повторных проверок', details: 'Через какой интервал повторять диагностические проверки в runtime.' },
  diagnosticsWorkflow: { label: 'Режим запуска диагностики', hint: 'startup / cycle_start / diagnostics', details: 'Выбирает этап, на котором выполняется диагностика (при старте, перед циклом или отдельным режимом).' },
  estopDebounceMs: { label: 'Подавление дребезга E-STOP, мс', hint: 'Фильтр ложных срабатываний', details: 'Минимальное время подтверждения аварийного сигнала перед остановкой.' },
  startupCleanFillTimeoutSeconds: { label: 'Таймаут этапа «Заполнение чистой водой», сек', hint: 'Startup step timeout', details: 'Максимальное время, отведённое на clean fill в процессе старта.' },
  startupSolutionFillTimeoutSeconds: { label: 'Таймаут этапа «Заполнение раствором», сек', hint: 'Startup step timeout', details: 'Максимальное время для шага solution fill при стартовом запуске.' },
  startupPrepareRecirculationTimeoutSeconds: { label: 'Таймаут этапа «Подготовка рециркуляции», сек', hint: 'Startup step timeout', details: 'Сколько времени даётся на подготовку рециркуляции до перехода в READY.' },
  startupCleanFillRetryCycles: { label: 'Число повторов clean fill', hint: 'Количество попыток', details: 'Сколько раз можно повторить clean fill перед переводом сценария в fail-closed.' },
  cleanFillMinCheckDelayMs: { label: 'Пауза до первой проверки clean fill, мс', hint: 'Минимальная задержка проверки', details: 'Сколько ждать после старта clean fill перед проверкой датчиков/уровня.' },
  solutionFillCleanMinCheckDelayMs: { label: 'Пауза проверки clean-части в solution fill, мс', hint: 'Минимальная задержка проверки', details: 'Минимальная задержка перед проверкой clean-компонента на этапе solution fill.' },
  solutionFillSolutionMinCheckDelayMs: { label: 'Пауза проверки solution-части в solution fill, мс', hint: 'Минимальная задержка проверки', details: 'Минимальная задержка перед проверкой solution-компонента на этапе solution fill.' },
  recirculationStopOnSolutionMin: { label: 'Останавливать рециркуляцию при минимуме раствора', hint: 'Fail-safe рециркуляции', details: 'При достижении минимального уровня раствора рециркуляция останавливается.' },
  stopOnSolutionMin: { label: 'Останавливать контур при минимуме раствора', hint: 'Глобальный fail-safe', details: 'Блокирует операции контура, если уровень раствора опустился ниже минимума.' },
  enableDrainControl: { label: 'Включить управление сливом', hint: 'Контур слива', details: 'Активирует логику управления сливом и связанные проверки безопасности.' },
  drainTargetPercent: { label: 'Целевой уровень слива, %', hint: 'До какого уровня сливать', details: 'Процент уровня, до которого должен выполняться слив при drain операции.' },
  valveSwitching: { label: 'Разрешить переключение клапанов', hint: 'Управление арматурой', details: 'Включает шаги переключения клапанов в водном workflow.' },
  solutionChangeEnabled: { label: 'Включить регулярную смену раствора', hint: 'Фоновый режим', details: 'Разрешает периодическую операцию смены раствора в рабочем режиме.' },
  solutionChangeIntervalMinutes: { label: 'Интервал смены раствора, мин', hint: 'Периодичность операции', details: 'Как часто запускать процедуру смены раствора.' },
  solutionChangeDurationSeconds: { label: 'Длительность процедуры смены, сек', hint: 'Продолжительность операции', details: 'Сколько секунд длится операция смены раствора после старта.' },
  manualIrrigationSeconds: { label: 'Ручной полив, сек', hint: 'Длительность ручного старта', details: 'Сколько секунд работает полив при ручном запуске оператором.' },
}
const meta = createMetaResolver<WaterFormState>(WATER_FIELD_META, {
  label: '',
  hint: 'Параметр водного контура',
  details: 'Параметр влияет на расчёты и переходы workflow водного контура.',
})

function upd<K extends keyof WaterFormState>(key: K, value: WaterFormState[K]): void {
  emit('update:waterForm', { ...props.waterForm, [key]: value })
}

function onPresetUpdate(next: WaterFormState): void {
  emit('update:waterForm', next)
}

// — Inline SectionLabel for visual parity with реф —
const SectionLabel = (_: unknown, ctx: { slots: { default?: () => unknown[] } }) =>
  h(
    'div',
    {
      class:
        'text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] pb-1 border-b border-dashed border-[var(--border-muted)]',
    },
    ctx.slots.default?.() as unknown as string,
  )
</script>
