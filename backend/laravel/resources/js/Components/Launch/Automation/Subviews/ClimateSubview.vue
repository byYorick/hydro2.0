<template>
  <div class="flex flex-col gap-3.5">
    <div class="flex items-center justify-between gap-3 pb-1 border-b border-dashed border-[var(--border-muted)]">
      <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)]">
        Климат зоны
      </div>
      <ToggleField
        :model-value="zoneClimateForm.enabled"
        label="enabled"
        inline
        @update:model-value="(v) => upd('enabled', v)"
      />
    </div>

    <div
      :class="[
        'grid grid-cols-1 md:grid-cols-2 gap-2.5',
        zoneClimateForm.enabled ? '' : 'opacity-55',
      ]"
    >
      <ShellCard title="CO₂">
        <KV
          :rows="[
            ['co2_sensor', assignments?.co2_sensor ? `Node ${assignments.co2_sensor}` : 'не задано'],
            ['co2_actuator', assignments?.co2_actuator ? `Node ${assignments.co2_actuator}` : 'не задано'],
            ['target ppm', '900'],
            ['hysteresis', '±50'],
          ]"
        />
      </ShellCard>
      <ShellCard title="Корневая вентиляция">
        <KV
          :rows="[
            ['root_vent_actuator', assignments?.root_vent_actuator ? `Node ${assignments.root_vent_actuator}` : 'не задано'],
            ['включение', '> 26°C subroot'],
            ['длительность', '5 мин'],
            ['cooldown', '15 мин'],
          ]"
        />
      </ShellCard>
    </div>

    <Hint :show="showHints">
      Климатический контур опционален. Привязки задаются в
      <b>«Привязки узлов»</b>; целевые ppm и пороги — в
      <span class="font-mono">automation_configs/zone.climate</span>.
    </Hint>
  </div>
</template>

<script setup lang="ts">
import ShellCard from '@/Components/Launch/Shell/ShellCard.vue'
import { KV, Hint, ToggleField } from '@/Components/Shared/Primitives'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type {
  ZoneClimateFormState,
  ZoneAutomationSectionAssignments,
} from '@/composables/zoneAutomationTypes'

const props = defineProps<{
  zoneClimateForm: ZoneClimateFormState
  assignments?: ZoneAutomationSectionAssignments
}>()
const emit = defineEmits<{
  (e: 'update:zoneClimateForm', next: ZoneClimateFormState): void
}>()

const { showHints } = useLaunchPreferences()

function upd<K extends keyof ZoneClimateFormState>(
  key: K,
  value: ZoneClimateFormState[K],
): void {
  emit('update:zoneClimateForm', { ...props.zoneClimateForm, [key]: value })
}
</script>
