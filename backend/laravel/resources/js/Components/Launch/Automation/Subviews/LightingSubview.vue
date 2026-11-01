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
          type="number"
          :value="lightingForm.luxDay"
          :disabled="!lightingForm.enabled"
          input-class="font-mono"
          @input="upd('luxDay', toNum($event))"
        />
      </Field>
      <Field label="luxNight">
        <TextField
          type="number"
          :value="lightingForm.luxNight"
          :disabled="!lightingForm.enabled"
          input-class="font-mono"
          @input="upd('luxNight', toNum($event))"
        />
      </Field>
      <Field label="hoursOn">
        <TextField
          type="number"
          :value="lightingForm.hoursOn"
          :disabled="!lightingForm.enabled"
          input-class="font-mono"
          @input="upd('hoursOn', toNum($event))"
        />
      </Field>
      <Field label="intervalMinutes">
        <TextField
          type="number"
          :value="lightingForm.intervalMinutes"
          :disabled="!lightingForm.enabled"
          input-class="font-mono"
          @input="upd('intervalMinutes', toInt($event))"
        />
      </Field>
      <Field label="scheduleStart">
        <TextField
          type="text"
          :value="lightingForm.scheduleStart"
          :disabled="!lightingForm.enabled"
          placeholder="06:00"
          input-class="font-mono"
          @input="upd('scheduleStart', toStr($event))"
        />
      </Field>
      <Field label="scheduleEnd">
        <TextField
          type="text"
          :value="lightingForm.scheduleEnd"
          :disabled="!lightingForm.enabled"
          placeholder="22:00"
          input-class="font-mono"
          @input="upd('scheduleEnd', toStr($event))"
        />
      </Field>
      <Field label="manualIntensity">
        <TextField
          type="number"
          :value="lightingForm.manualIntensity"
          :disabled="!lightingForm.enabled"
          input-class="font-mono"
          @input="upd('manualIntensity', toNum($event))"
        />
      </Field>
      <Field label="manualDurationHours">
        <TextField
          type="number"
          :value="lightingForm.manualDurationHours"
          :disabled="!lightingForm.enabled"
          input-class="font-mono"
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
import DayNightStrip from '../DayNightStrip.vue'
import { Field, Hint, ToggleField } from '@/Components/Shared/Primitives'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type { LightingFormState } from '@/composables/zoneAutomationTypes'
import { toInt, toNum, toStr } from './sharedFormUtils'
import TextField from '@/Components/TextField.vue'

const props = defineProps<{ lightingForm: LightingFormState }>()
const emit = defineEmits<{
  (e: 'update:lightingForm', next: LightingFormState): void
}>()

const { showHints } = useLaunchPreferences()

function upd<K extends keyof LightingFormState>(
  key: K,
  value: LightingFormState[K],
): void {
  emit('update:lightingForm', { ...props.lightingForm, [key]: value })
}
</script>
