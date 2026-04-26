<template>
  <div class="flex flex-col gap-3.5">
    <div class="flex items-center justify-between gap-3 pb-1 border-b border-dashed border-[var(--border-muted)]">
      <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)]">
        Освещение
      </div>
      <ToggleField
        :model-value="lightingForm.enabled"
        label="enabled"
        inline
        @update:model-value="(v) => upd('enabled', v)"
      />
    </div>

    <div
      :class="[
        'grid grid-cols-2 md:grid-cols-4 gap-2.5',
        lightingForm.enabled ? '' : 'opacity-55',
      ]"
    >
      <Field label="luxDay">
        <input
          v-bind="numAttrs"
          :value="lightingForm.luxDay"
          :disabled="!lightingForm.enabled"
          @input="upd('luxDay', toNum($event))"
        >
      </Field>
      <Field label="luxNight">
        <input
          v-bind="numAttrs"
          :value="lightingForm.luxNight"
          :disabled="!lightingForm.enabled"
          @input="upd('luxNight', toNum($event))"
        >
      </Field>
      <Field label="hoursOn">
        <input
          v-bind="numAttrs"
          :value="lightingForm.hoursOn"
          :disabled="!lightingForm.enabled"
          @input="upd('hoursOn', toNum($event))"
        >
      </Field>
      <Field label="intervalMinutes">
        <input
          v-bind="numAttrs"
          :value="lightingForm.intervalMinutes"
          :disabled="!lightingForm.enabled"
          @input="upd('intervalMinutes', toInt($event))"
        >
      </Field>
      <Field label="scheduleStart">
        <input
          v-bind="textAttrs"
          :value="lightingForm.scheduleStart"
          :disabled="!lightingForm.enabled"
          placeholder="06:00"
          @input="upd('scheduleStart', toStr($event))"
        >
      </Field>
      <Field label="scheduleEnd">
        <input
          v-bind="textAttrs"
          :value="lightingForm.scheduleEnd"
          :disabled="!lightingForm.enabled"
          placeholder="22:00"
          @input="upd('scheduleEnd', toStr($event))"
        >
      </Field>
      <Field label="manualIntensity">
        <input
          v-bind="numAttrs"
          :value="lightingForm.manualIntensity"
          :disabled="!lightingForm.enabled"
          @input="upd('manualIntensity', toNum($event))"
        >
      </Field>
      <Field label="manualDurationHours">
        <input
          v-bind="numAttrs"
          :value="lightingForm.manualDurationHours"
          :disabled="!lightingForm.enabled"
          @input="upd('manualDurationHours', toNum($event))"
        >
      </Field>
    </div>

    <DayNightStrip
      :schedule-start="lightingForm.scheduleStart"
      :schedule-end="lightingForm.scheduleEnd"
      :lux-day="lightingForm.luxDay"
      :lux-night="lightingForm.luxNight"
      :enabled="lightingForm.enabled"
    />

    <Hint :show="showHints">
      Если свет выключен на этом этапе — поле <span class="font-mono">light</span>
      в assignments можно оставить пустым; readiness не блокирует запуск.
    </Hint>
  </div>
</template>

<script setup lang="ts">
import DayNightStrip from '../DayNightStrip.vue'
import { Field, Hint, ToggleField } from '@/Components/Shared/Primitives'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type { LightingFormState } from '@/composables/zoneAutomationTypes'

const props = defineProps<{ lightingForm: LightingFormState }>()
const emit = defineEmits<{
  (e: 'update:lightingForm', next: LightingFormState): void
}>()

const { showHints } = useLaunchPreferences()

const inputCls =
  'block w-full h-8 rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] px-2.5 text-sm font-mono outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-55'
const numAttrs = { class: inputCls, type: 'number' }
const textAttrs = { class: inputCls, type: 'text' }

function upd<K extends keyof LightingFormState>(
  key: K,
  value: LightingFormState[K],
): void {
  emit('update:lightingForm', { ...props.lightingForm, [key]: value })
}
function toNum(e: Event) {
  const n = Number((e.target as HTMLInputElement).value)
  return Number.isFinite(n) ? n : 0
}
function toInt(e: Event) {
  return Math.trunc(toNum(e))
}
function toStr(e: Event) {
  return (e.target as HTMLInputElement).value
}
</script>
