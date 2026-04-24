<template>
  <CockpitSchedulerTab
    v-if="cockpitEnabled"
    v-bind="$props"
  />
  <LegacySchedulerTab
    v-else
    v-bind="$props"
  />
</template>

<script setup lang="ts">
import { useFeatureFlag } from '@/composables/useFeatureFlag'
import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'
import CockpitSchedulerTab from '@/Pages/Zones/Tabs/CockpitSchedulerTab.vue'
import LegacySchedulerTab from '@/Pages/Zones/Tabs/LegacySchedulerTab.vue'

defineProps<ZoneAutomationTabProps>()

const cockpitEnabled = useFeatureFlag('scheduler_cockpit_ui')
</script>
