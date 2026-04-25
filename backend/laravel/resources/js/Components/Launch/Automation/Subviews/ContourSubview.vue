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
    <div class="grid grid-cols-2 md:grid-cols-4 gap-2.5">
      <Field
        label="systemType"
        required
        hint="из рецепта"
      >
        <div
          class="flex items-center h-8 px-3 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] text-sm font-mono text-[var(--text-primary)] gap-1.5"
        >
          <Ic
            name="lock"
            class="text-[var(--text-dim)]"
            size="sm"
          />
          {{ waterForm.systemType }}
        </div>
      </Field>
      <Field label="tanksCount" hint="2…3">
        <input
          v-bind="numAttrs"
          :value="waterForm.tanksCount"
          @input="upd('tanksCount', toInt($event))"
        >
      </Field>
      <Field label="workingTankL">
        <input
          v-bind="numAttrs"
          :value="waterForm.workingTankL"
          @input="upd('workingTankL', toNum($event))"
        >
      </Field>
      <Field label="cleanTankFillL">
        <input
          v-bind="numAttrs"
          :value="waterForm.cleanTankFillL"
          @input="upd('cleanTankFillL', toNum($event))"
        >
      </Field>
      <Field label="nutrientTankTargetL">
        <input
          v-bind="numAttrs"
          :value="waterForm.nutrientTankTargetL"
          @input="upd('nutrientTankTargetL', toNum($event))"
        >
      </Field>
      <Field label="irrigationBatchL">
        <input
          v-bind="numAttrs"
          :value="waterForm.irrigationBatchL"
          @input="upd('irrigationBatchL', toNum($event))"
        >
      </Field>
      <Field label="mainPumpFlowLpm">
        <input
          v-bind="numAttrs"
          :value="waterForm.mainPumpFlowLpm"
          @input="upd('mainPumpFlowLpm', toNum($event))"
        >
      </Field>
      <Field label="cleanWaterFlowLpm">
        <input
          v-bind="numAttrs"
          :value="waterForm.cleanWaterFlowLpm"
          @input="upd('cleanWaterFlowLpm', toNum($event))"
        >
      </Field>
    </div>

    <SectionLabel>Окно наполнения и температура</SectionLabel>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-2.5">
      <Field label="fillWindowStart">
        <input
          v-bind="textAttrs"
          :value="waterForm.fillWindowStart"
          @input="upd('fillWindowStart', toStr($event))"
        >
      </Field>
      <Field label="fillWindowEnd">
        <input
          v-bind="textAttrs"
          :value="waterForm.fillWindowEnd"
          @input="upd('fillWindowEnd', toStr($event))"
        >
      </Field>
      <Field label="fillTemperatureC">
        <input
          v-bind="numAttrs"
          :value="waterForm.fillTemperatureC"
          @input="upd('fillTemperatureC', toNum($event))"
        >
      </Field>
      <Field label="cleanTankFullThreshold">
        <input
          v-bind="numAttrs"
          :value="waterForm.cleanTankFullThreshold"
          @input="upd('cleanTankFullThreshold', toNum($event))"
        >
      </Field>
      <Field label="refillDurationSeconds">
        <input
          v-bind="numAttrs"
          :value="waterForm.refillDurationSeconds"
          @input="upd('refillDurationSeconds', toInt($event))"
        >
      </Field>
      <Field label="refillTimeoutSeconds">
        <input
          v-bind="numAttrs"
          :value="waterForm.refillTimeoutSeconds"
          @input="upd('refillTimeoutSeconds', toInt($event))"
        >
      </Field>
      <Field label="refillRequiredNodeTypes">
        <input
          v-bind="textAttrs"
          :value="waterForm.refillRequiredNodeTypes"
          placeholder="pump,valve"
          @input="upd('refillRequiredNodeTypes', toStr($event))"
        >
      </Field>
      <Field label="refillPreferredChannel">
        <input
          v-bind="textAttrs"
          :value="waterForm.refillPreferredChannel"
          @input="upd('refillPreferredChannel', toStr($event))"
        >
      </Field>
    </div>

    <SectionLabel>Диагностика и стартовые таймауты</SectionLabel>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-2.5 items-center">
      <ToggleField
        :model-value="!!waterForm.diagnosticsEnabled"
        label="diagnosticsEnabled"
        @update:model-value="(v) => upd('diagnosticsEnabled', v)"
      />
      <Field label="diagnosticsIntervalMinutes">
        <input
          v-bind="numAttrs"
          :value="waterForm.diagnosticsIntervalMinutes"
          @input="upd('diagnosticsIntervalMinutes', toInt($event))"
        >
      </Field>
      <Field label="diagnosticsWorkflow">
        <Select
          :model-value="waterForm.diagnosticsWorkflow ?? 'cycle_start'"
          :options="['startup', 'cycle_start', 'diagnostics']"
          mono
          size="sm"
          @update:model-value="(v: string) => upd('diagnosticsWorkflow', v as 'startup' | 'cycle_start' | 'diagnostics')"
        />
      </Field>
      <Field label="estopDebounceMs">
        <input
          v-bind="numAttrs"
          :value="waterForm.estopDebounceMs ?? 0"
          @input="upd('estopDebounceMs', toInt($event))"
        >
      </Field>
      <Field label="startupCleanFillTimeoutSeconds">
        <input
          v-bind="numAttrs"
          :value="waterForm.startupCleanFillTimeoutSeconds ?? 0"
          @input="upd('startupCleanFillTimeoutSeconds', toInt($event))"
        >
      </Field>
      <Field label="startupSolutionFillTimeoutSeconds">
        <input
          v-bind="numAttrs"
          :value="waterForm.startupSolutionFillTimeoutSeconds ?? 0"
          @input="upd('startupSolutionFillTimeoutSeconds', toInt($event))"
        >
      </Field>
      <Field label="startupPrepareRecirculationTimeoutSeconds">
        <input
          v-bind="numAttrs"
          :value="waterForm.startupPrepareRecirculationTimeoutSeconds ?? 0"
          @input="upd('startupPrepareRecirculationTimeoutSeconds', toInt($event))"
        >
      </Field>
      <Field label="startupCleanFillRetryCycles">
        <input
          v-bind="numAttrs"
          :value="waterForm.startupCleanFillRetryCycles ?? 0"
          @input="upd('startupCleanFillRetryCycles', toInt($event))"
        >
      </Field>
      <Field label="cleanFillMinCheckDelayMs">
        <input
          v-bind="numAttrs"
          :value="waterForm.cleanFillMinCheckDelayMs ?? 0"
          @input="upd('cleanFillMinCheckDelayMs', toInt($event))"
        >
      </Field>
      <Field label="solutionFillCleanMinCheckDelayMs">
        <input
          v-bind="numAttrs"
          :value="waterForm.solutionFillCleanMinCheckDelayMs ?? 0"
          @input="upd('solutionFillCleanMinCheckDelayMs', toInt($event))"
        >
      </Field>
      <Field label="solutionFillSolutionMinCheckDelayMs">
        <input
          v-bind="numAttrs"
          :value="waterForm.solutionFillSolutionMinCheckDelayMs ?? 0"
          @input="upd('solutionFillSolutionMinCheckDelayMs', toInt($event))"
        >
      </Field>
      <ToggleField
        :model-value="!!waterForm.recirculationStopOnSolutionMin"
        label="recirculationStopOnSolutionMin"
        @update:model-value="(v) => upd('recirculationStopOnSolutionMin', v)"
      />
      <ToggleField
        :model-value="!!waterForm.stopOnSolutionMin"
        label="stopOnSolutionMin"
        @update:model-value="(v) => upd('stopOnSolutionMin', v)"
      />
      <ToggleField
        :model-value="!!waterForm.enableDrainControl"
        label="enableDrainControl"
        @update:model-value="(v) => upd('enableDrainControl', v)"
      />
      <Field label="drainTargetPercent">
        <input
          v-bind="numAttrs"
          :value="waterForm.drainTargetPercent"
          @input="upd('drainTargetPercent', toNum($event))"
        >
      </Field>
      <ToggleField
        :model-value="!!waterForm.valveSwitching"
        label="valveSwitching"
        @update:model-value="(v) => upd('valveSwitching', v)"
      />
    </div>

    <SectionLabel>Смена раствора</SectionLabel>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-2.5 items-center">
      <ToggleField
        :model-value="!!waterForm.solutionChangeEnabled"
        label="solutionChangeEnabled"
        @update:model-value="(v) => upd('solutionChangeEnabled', v)"
      />
      <Field label="solutionChangeIntervalMinutes">
        <input
          v-bind="numAttrs"
          :value="waterForm.solutionChangeIntervalMinutes"
          @input="upd('solutionChangeIntervalMinutes', toInt($event))"
        >
      </Field>
      <Field label="solutionChangeDurationSeconds">
        <input
          v-bind="numAttrs"
          :value="waterForm.solutionChangeDurationSeconds"
          @input="upd('solutionChangeDurationSeconds', toInt($event))"
        >
      </Field>
      <Field
        label="manualIrrigationSeconds"
        hint="ручной запуск"
      >
        <input
          v-bind="numAttrs"
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
  'block w-full h-8 rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] px-2.5 text-sm font-mono outline-none focus-visible:ring-2 focus-visible:ring-brand'

const numAttrs = { class: inputCls, type: 'number' }
const textAttrs = { class: inputCls, type: 'text' }

function upd<K extends keyof WaterFormState>(key: K, value: WaterFormState[K]): void {
  emit('update:waterForm', { ...props.waterForm, [key]: value })
}

function onPresetUpdate(next: WaterFormState): void {
  emit('update:waterForm', next)
}

function toNum(e: Event): number {
  const v = (e.target as HTMLInputElement).value
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}
function toInt(e: Event): number {
  return Math.trunc(toNum(e))
}
function toStr(e: Event): string {
  return (e.target as HTMLInputElement).value
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
