<template>
  <div class="rounded-xl border border-neutral-800 bg-neutral-925 p-4">
    <div class="flex items-center justify-between">
      <div class="text-sm font-semibold">{{ zone.name }}</div>
      <Badge :variant="variant">{{ translateStatus(zone.status) }}</Badge>
    </div>
    <div class="mt-2 text-xs text-neutral-300">
      <div v-if="zone.description">{{ zone.description }}</div>
      <div v-if="zone.greenhouse" class="mt-1">Теплица: {{ zone.greenhouse.name }}</div>
    </div>
    <!-- Метрики (если переданы) -->
    <div v-if="telemetry && hasMetrics" class="mt-3 grid grid-cols-2 gap-2 text-xs">
      <div v-if="telemetry.ph !== null && telemetry.ph !== undefined" class="text-neutral-400">
        pH: <span class="text-neutral-200">{{ formatValue(telemetry.ph, 'ph') }}</span>
      </div>
      <div v-if="telemetry.ec !== null && telemetry.ec !== undefined" class="text-neutral-400">
        EC: <span class="text-neutral-200">{{ formatValue(telemetry.ec, 'ec') }}</span>
      </div>
      <div v-if="telemetry.temperature !== null && telemetry.temperature !== undefined" class="text-neutral-400">
        Темп: <span class="text-neutral-200">{{ formatValue(telemetry.temperature, 'temp') }}°C</span>
      </div>
      <div v-if="telemetry.humidity !== null && telemetry.humidity !== undefined" class="text-neutral-400">
        Влаж: <span class="text-neutral-200">{{ formatValue(telemetry.humidity, 'humidity') }}%</span>
      </div>
    </div>
    <div class="mt-3 flex gap-2">
      <Link :href="`/zones/${zone.id}`" class="inline-block">
        <Button size="sm" variant="secondary">Подробнее</Button>
      </Link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import { translateStatus } from '@/utils/i18n'
import type { Zone, ZoneTelemetry } from '@/types'

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

interface Props {
  zone: Zone
  telemetry?: ZoneTelemetry | null
}

const props = defineProps<Props>()

const variant = computed<BadgeVariant>(() => {
  switch (props.zone.status) {
    case 'RUNNING': return 'success'
    case 'PAUSED': return 'neutral'
    case 'WARNING': return 'warning'
    case 'ALARM': return 'danger'
    default: return 'neutral'
  }
})

const hasMetrics = computed(() => {
  if (!props.telemetry) return false
  const t = props.telemetry
  return (t.ph !== null && t.ph !== undefined) || 
         (t.ec !== null && t.ec !== undefined) ||
         (t.temperature !== null && t.temperature !== undefined) || 
         (t.humidity !== null && t.humidity !== undefined)
})

// Форматирование значений телеметрии
function formatValue(value: number | null | undefined, type: string): string {
  if (value === null || value === undefined) return '-'
  if (typeof value !== 'number') return String(value)
  
  // Для pH показываем 2 знака после точки, для остальных - 1
  const decimals = type === 'ph' ? 2 : 1
  return value.toFixed(decimals)
}
</script>

