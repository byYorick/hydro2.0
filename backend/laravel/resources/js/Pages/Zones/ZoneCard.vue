<template>
  <div class="rounded-xl border border-neutral-800 bg-neutral-925 p-4 hover:border-neutral-700 transition-all duration-200">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2 flex-1 min-w-0">
        <button
          @click.stop="toggleFavorite"
          class="p-1 rounded hover:bg-neutral-800 transition-colors shrink-0"
          :title="isFavorite ? 'Удалить из избранного' : 'Добавить в избранное'"
        >
          <svg
            class="w-4 h-4 transition-colors"
            :class="isFavorite ? 'text-amber-400 fill-amber-400' : 'text-neutral-500'"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
            />
          </svg>
        </button>
        <div class="text-sm font-semibold truncate">{{ zone.name }}</div>
      </div>
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
import { useFavorites } from '@/composables/useFavorites'
import type { Zone, ZoneTelemetry } from '@/types'

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

interface Props {
  zone: Zone
  telemetry?: ZoneTelemetry | null
}

const props = defineProps<Props>()

const { isZoneFavorite, toggleZoneFavorite } = useFavorites()

const isFavorite = computed(() => isZoneFavorite(props.zone.id))

function toggleFavorite(): void {
  toggleZoneFavorite(props.zone.id)
}

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

