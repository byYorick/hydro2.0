<template>
  <div class="flex flex-col gap-3.5">
    <div class="flex items-center justify-between gap-3 pb-1 border-b border-dashed border-[var(--border-muted)]">
      <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)]">
        Стратегия и расписание
      </div>
      <div class="flex gap-1.5">
        <Button
          size="sm"
          :variant="!smart ? 'primary' : 'secondary'"
          @click="upd('irrigationDecisionStrategy', 'task')"
        >
          По времени
        </Button>
        <Button
          size="sm"
          :variant="smart ? 'primary' : 'secondary'"
          @click="upd('irrigationDecisionStrategy', 'smart_soil_v1')"
        >
          SMART soil v1
        </Button>
      </div>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-4 gap-2.5 items-center">
      <Field label="intervalMinutes" required>
        <input
          v-bind="numAttrs"
          :value="waterForm.intervalMinutes"
          @input="upd('intervalMinutes', toInt($event))"
        >
      </Field>
      <Field label="durationSeconds" required>
        <input
          v-bind="numAttrs"
          :value="waterForm.durationSeconds"
          @input="upd('durationSeconds', toInt($event))"
        >
      </Field>
      <ToggleField
        :model-value="waterForm.correctionDuringIrrigation"
        label="correctionDuringIrrigation"
        @update:model-value="(v) => upd('correctionDuringIrrigation', v)"
      />
      <ToggleField
        :model-value="!!waterForm.irrigationAutoReplayAfterSetup"
        label="irrigationAutoReplayAfterSetup"
        @update:model-value="(v) => upd('irrigationAutoReplayAfterSetup', v)"
      />
    </div>

    <template v-if="smart">
      <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] pb-1 border-b border-dashed border-[var(--border-muted)]">
        SMART soil v1 — параметры решения
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-2.5">
        <Field label="irrigationDecisionLookbackSeconds">
          <input
            v-bind="numAttrs"
            :value="waterForm.irrigationDecisionLookbackSeconds ?? 0"
            @input="upd('irrigationDecisionLookbackSeconds', toInt($event))"
          >
        </Field>
        <Field label="irrigationDecisionMinSamples">
          <input
            v-bind="numAttrs"
            :value="waterForm.irrigationDecisionMinSamples ?? 0"
            @input="upd('irrigationDecisionMinSamples', toInt($event))"
          >
        </Field>
        <Field label="irrigationDecisionStaleAfterSeconds">
          <input
            v-bind="numAttrs"
            :value="waterForm.irrigationDecisionStaleAfterSeconds ?? 0"
            @input="upd('irrigationDecisionStaleAfterSeconds', toInt($event))"
          >
        </Field>
        <Field label="irrigationDecisionHysteresisPct">
          <input
            v-bind="numAttrs"
            :value="waterForm.irrigationDecisionHysteresisPct ?? 0"
            @input="upd('irrigationDecisionHysteresisPct', toNum($event))"
          >
        </Field>
        <Field label="irrigationDecisionSpreadAlertThresholdPct">
          <input
            v-bind="numAttrs"
            :value="waterForm.irrigationDecisionSpreadAlertThresholdPct ?? 0"
            @input="upd('irrigationDecisionSpreadAlertThresholdPct', toNum($event))"
          >
        </Field>
      </div>
    </template>

    <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] pb-1 border-b border-dashed border-[var(--border-muted)]">
      Recovery / повторы
    </div>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-2.5">
      <Field label="irrigationRecoveryMaxContinueAttempts">
        <input
          v-bind="numAttrs"
          :value="waterForm.irrigationRecoveryMaxContinueAttempts ?? 0"
          @input="upd('irrigationRecoveryMaxContinueAttempts', toInt($event))"
        >
      </Field>
      <Field label="irrigationRecoveryTimeoutSeconds">
        <input
          v-bind="numAttrs"
          :value="waterForm.irrigationRecoveryTimeoutSeconds ?? 0"
          @input="upd('irrigationRecoveryTimeoutSeconds', toInt($event))"
        >
      </Field>
      <Field label="irrigationMaxSetupReplays">
        <input
          v-bind="numAttrs"
          :value="waterForm.irrigationMaxSetupReplays ?? 0"
          @input="upd('irrigationMaxSetupReplays', toInt($event))"
        >
      </Field>
    </div>

    <Hint :show="showHints">
      SMART soil v1 принимает решение о поливе по выборке датчиков
      влажности. Без сенсора используйте <span class="font-mono">task</span>
      (по времени).
    </Hint>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import { Field, Hint, ToggleField } from '@/Components/Shared/Primitives'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'

const props = defineProps<{ waterForm: WaterFormState }>()
const emit = defineEmits<{ (e: 'update:waterForm', next: WaterFormState): void }>()

const { showHints } = useLaunchPreferences()

const smart = computed(
  () => props.waterForm.irrigationDecisionStrategy === 'smart_soil_v1',
)

const inputCls =
  'block w-full h-8 rounded-lg border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] px-2.5 text-sm font-mono outline-none transition-[border-color,box-shadow,background-color] duration-150 focus:border-brand focus:ring-2 focus:ring-brand-soft focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand-soft'
const numAttrs = { class: inputCls, type: 'number' }

function upd<K extends keyof WaterFormState>(key: K, value: WaterFormState[K]) {
  emit('update:waterForm', { ...props.waterForm, [key]: value })
}
function toNum(e: Event) {
  const n = Number((e.target as HTMLInputElement).value)
  return Number.isFinite(n) ? n : 0
}
function toInt(e: Event) {
  return Math.trunc(toNum(e))
}
</script>
