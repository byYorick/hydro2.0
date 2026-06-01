<template>
  <ZoneAutomationRuntimeSection
    :zone-id="zoneId"
    :fallback-tanks-count="fallbackTanksCount"
    :fallback-system-type="fallbackSystemType"
    @state-change="(state) => emit('state-change', state)"
    @state-snapshot="(snapshot) => emit('state-snapshot', snapshot)"
  />
</template>

<script setup lang="ts">
import ZoneAutomationRuntimeSection from '@/Components/ZoneAutomation/ZoneAutomationRuntimeSection.vue'
import type { AutomationState, AutomationStateType } from '@/types/Automation'
import type { IrrigationSystem } from '@/composables/zoneAutomationTypes'

interface Props {
  zoneId: number | null
  fallbackTanksCount?: number
  fallbackSystemType?: IrrigationSystem
}

withDefaults(defineProps<Props>(), {
  fallbackTanksCount: 2,
  fallbackSystemType: 'drip',
})

const emit = defineEmits<{
  (e: 'state-change', state: AutomationStateType): void
  (e: 'state-snapshot', snapshot: AutomationState): void
}>()
</script>
