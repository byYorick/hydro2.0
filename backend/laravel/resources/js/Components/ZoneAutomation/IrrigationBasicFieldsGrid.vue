<template>
  <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
    <label
      class="text-xs text-[color:var(--text-muted)]"
      :title="zoneAutomationFieldHelp('water.intervalMinutes')"
    >
      Интервал полива (мин)
      <input
        v-model.number="waterForm.intervalMinutes"
        type="number"
        min="5"
        max="1440"
        class="input-field mt-1 w-full"
        :disabled="!ctx.canConfigure.value || waterForm.irrigationDecisionStrategy === 'task'"
      />
    </label>
    <label
      class="text-xs text-[color:var(--text-muted)]"
      :title="zoneAutomationFieldHelp('water.durationSeconds')"
    >
      Длительность полива (сек)
      <input
        v-model.number="waterForm.durationSeconds"
        type="number"
        min="1"
        max="3600"
        class="input-field mt-1 w-full"
        :disabled="!ctx.canConfigure.value || waterForm.irrigationDecisionStrategy === 'task'"
      />
    </label>
    <label
      class="text-xs text-[color:var(--text-muted)]"
      :title="zoneAutomationFieldHelp('water.irrigationBatchL')"
    >
      Порция полива (л)
      <input
        v-model.number="waterForm.irrigationBatchL"
        type="number"
        min="1"
        max="500"
        class="input-field mt-1 w-full"
        :disabled="!ctx.canConfigure.value"
      />
    </label>
    <label
      class="text-xs text-[color:var(--text-muted)]"
      :title="zoneAutomationFieldHelp('water.fillTemperatureC')"
    >
      Температура набора (°C)
      <input
        v-model.number="waterForm.fillTemperatureC"
        type="number"
        min="5"
        max="35"
        class="input-field mt-1 w-full"
        :disabled="!ctx.canConfigure.value"
      />
    </label>
    <label
      class="text-xs text-[color:var(--text-muted)]"
      :title="zoneAutomationFieldHelp('water.cleanTankFillL')"
    >
      Объём чистого бака (л)
      <input
        v-model.number="waterForm.cleanTankFillL"
        type="number"
        min="10"
        max="5000"
        class="input-field mt-1 w-full"
        :disabled="!ctx.canConfigure.value"
      />
    </label>
    <label
      class="text-xs text-[color:var(--text-muted)]"
      :title="zoneAutomationFieldHelp('water.nutrientTankTargetL')"
    >
      Объём бака раствора (л)
      <input
        v-model.number="waterForm.nutrientTankTargetL"
        type="number"
        min="10"
        max="5000"
        class="input-field mt-1 w-full"
        :disabled="!ctx.canConfigure.value"
      />
    </label>
    <label
      class="text-xs text-[color:var(--text-muted)]"
      :title="zoneAutomationFieldHelp('water.fillWindowStart')"
    >
      Окно набора воды: от
      <input
        v-model="waterForm.fillWindowStart"
        type="time"
        class="input-field mt-1 w-full"
        :disabled="!ctx.canConfigure.value"
      />
    </label>
    <label
      class="text-xs text-[color:var(--text-muted)]"
      :title="zoneAutomationFieldHelp('water.fillWindowEnd')"
    >
      Окно набора воды: до
      <input
        v-model="waterForm.fillWindowEnd"
        type="time"
        class="input-field mt-1 w-full"
        :disabled="!ctx.canConfigure.value"
      />
    </label>
  </div>
</template>

<script setup lang="ts">
import type { WaterFormState } from '@/composables/zoneAutomationTypes'
import { useZoneAutomationSectionContext } from '@/composables/useZoneAutomationSectionContext'
import { zoneAutomationFieldHelp } from '@/constants/zoneAutomationFieldHelp'

const waterForm = defineModel<WaterFormState>('waterForm', { required: true })
const ctx = useZoneAutomationSectionContext()
</script>
