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
        <TextField
          v-bind="numAttrs"
          :model-value="lightingForm.luxDay"
          :disabled="!lightingForm.enabled"
          @input="upd('luxDay', toNum($event))"
        />
      </Field>
      <Field label="luxNight">
        <TextField
          v-bind="numAttrs"
          :model-value="lightingForm.luxNight"
          :disabled="!lightingForm.enabled"
          @input="upd('luxNight', toNum($event))"
        />
      </Field>
      <Field label="hoursOn">
        <TextField
          v-bind="numAttrs"
          :model-value="lightingForm.hoursOn"
          :disabled="!lightingForm.enabled"
          @input="upd('hoursOn', toNum($event))"
        />
      </Field>
      <Field label="intervalMinutes">
        <TextField
          v-bind="numAttrs"
          :model-value="lightingForm.intervalMinutes"
          :disabled="!lightingForm.enabled"
          @input="upd('intervalMinutes', toInt($event))"
        />
      </Field>
      <Field label="scheduleStart">
        <TextField
          v-bind="textAttrs"
          :model-value="lightingForm.scheduleStart"
          :disabled="!lightingForm.enabled"
          placeholder="06:00"
          @input="upd('scheduleStart', toStr($event))"
        />
      </Field>
      <Field label="scheduleEnd">
        <TextField
          v-bind="textAttrs"
          :model-value="lightingForm.scheduleEnd"
          :disabled="!lightingForm.enabled"
          placeholder="22:00"
          @input="upd('scheduleEnd', toStr($event))"
        />
      </Field>
      <Field label="manualIntensity">
        <TextField
          v-bind="numAttrs"
          :model-value="lightingForm.manualIntensity"
          :disabled="!lightingForm.enabled"
          @input="upd('manualIntensity', toNum($event))"
        />
      </Field>
      <Field label="manualDurationHours">
        <TextField
          v-bind="numAttrs"
          :model-value="lightingForm.manualDurationHours"
          :disabled="!lightingForm.enabled"
          @input="upd('manualDurationHours', toNum($event))"
        />
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
import TextField from '@/Components/TextField.vue'

import DayNightStrip from '../DayNightStrip.vue'
import { Field, Hint, ToggleField } from '@/Components/Shared/Primitives'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type { LightingFormState } from '@/composables/zoneAutomationTypes'
import { toInt, toNum, toStr } from './sharedFormUtils'

const props = defineProps<{ lightingForm: LightingFormState }>()
const emit = defineEmits<{
  (e: 'update:lightingForm', next: LightingFormState): void
}>()

const { showHints } = useLaunchPreferences()

const numAttrs = { type: 'number' }
const textAttrs = { type: 'text' }

function upd<K extends keyof LightingFormState>(
  key: K,
  value: LightingFormState[K],
): void {
  emit('update:lightingForm', { ...props.lightingForm, [key]: value })
}
</script>
