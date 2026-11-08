<template>
  <nav
    class="mb-4 flex flex-wrap gap-2 border-b border-[color:var(--border-muted)] pb-3"
    aria-label="Разделы узла"
  >
    <button
      v-for="tab in tabs"
      :key="tab.id"
      type="button"
      class="btn min-h-11 px-3 text-xs"
      :class="view === tab.id ? 'btn-outline' : 'btn-ghost'"
      :aria-pressed="view === tab.id"
      @click="view = tab.id"
    >
      {{ tab.label }}
    </button>
    <Link
      v-if="zoneId"
      :href="`/zones/${zoneId}?tab=events`"
      class="btn btn-ghost min-h-11 text-xs"
    >
      События зоны →
    </Link>
  </nav>
  <div
    v-if="view === 'state'"
    class="mb-4 grid gap-3 sm:grid-cols-3"
  >
    <div class="surface-card p-4">
      <p class="text-xs text-[color:var(--text-muted)]">
        Связь с узлом
      </p><p class="mt-2 text-lg font-semibold">
        {{ statusLabel }}
      </p><p class="mt-1 text-xs text-[color:var(--text-muted)]">
        Последний пакет: {{ lastPacketLabel }}
      </p>
    </div>
    <div class="surface-card p-4">
      <p class="text-xs text-[color:var(--text-muted)]">
        Свежие измерения каналов
      </p><p class="mt-2 text-lg font-semibold">
        {{ freshSensorCount }} из {{ sensorCount }}
      </p><p class="mt-1 text-xs text-[color:var(--text-muted)]">
        В пределах 5 минут · связь проверяется отдельно
      </p>
    </div>
    <div class="surface-card p-4">
      <p class="text-xs text-[color:var(--text-muted)]">
        Калибровка сенсора
      </p><p class="mt-2 text-lg font-semibold">
        {{ calibrationLabel }}
      </p><button
        type="button"
        class="mt-2 text-xs text-[color:var(--status-info)] hover:underline"
        @click="view = 'calibration'"
      >
        Открыть калибровку →
      </button>
    </div>
  </div>
  <div
    v-if="view === 'calibration' && calibrationInZone"
    class="surface-card mb-4 space-y-3 p-5"
  >
    <h2 class="font-semibold">
      Калибровка в контексте зоны
    </h2><p class="text-sm text-[color:var(--text-muted)]">
      Для насосов и других сенсоров откройте рабочее пространство зоны: там доступны привязки каналов и результаты калибровки.
    </p><Link
      v-if="zoneId"
      :href="`/zones/${zoneId}?tab=devices`"
      class="btn btn-outline min-h-11 text-sm"
    >
      Открыть оборудование зоны →
    </Link><p
      v-else
      class="text-sm"
    >
      Сначала назначьте устройству зону.
    </p>
  </div>
</template>

<script setup lang="ts">
import { Link } from '@inertiajs/vue3'
defineProps<{
  tabs: Array<{ id: string; label: string }>
  zoneId: number | null
  statusLabel: string
  lastPacketLabel: string
  freshSensorCount: number
  sensorCount: number
  calibrationLabel: string
  calibrationInZone: boolean
}>()
const view = defineModel<string>('view', { required: true })
</script>
