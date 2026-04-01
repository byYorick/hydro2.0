<template>
  <div class="surface-card surface-card--elevated rounded-2xl border border-[color:var(--border-muted)] p-4">
    <ZoneTargets
      v-if="hasTargets"
      :telemetry="telemetry"
      :targets="targets"
    />
    <div
      v-else
      class="rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-5"
    >
      <p class="text-sm font-semibold text-[color:var(--text-primary)]">Целевые значения не настроены</p>
      <p class="mt-1 text-xs text-[color:var(--text-muted)]">
        Настройте целевые значения для отслеживания параметров зоны
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ZoneTargets from '@/Components/ZoneTargets.vue'
import type { ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'

const props = defineProps<{
  targets: ZoneTargetsType
  telemetry: ZoneTelemetry
}>()

const hasTargets = computed(() => {
  if (!props.targets) return false
  const t = props.targets as Record<string, unknown>
  return Boolean(t.ph !== undefined || t.ec !== undefined || t.climate_request !== undefined)
})
</script>
